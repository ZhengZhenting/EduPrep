import json
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Form
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from dotenv import load_dotenv
import anthropic
import os
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from typing import List
import asyncio
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy.orm import Session
from wasabi import msg


from pdf_processor import process_pdf
from rag import store_chunks, search_chunks, search_chunks_with_score
from memory import load_memory, save_memory, compress_history, update_memory, should_compress, load_quiz_memory, save_quiz_memory
from database import get_db, SessionLocal
from models import User, Course, PdfFile, Message, Note, Memory, QuizProgress

# ---------- Requests --------------
# Preview
class PreviewRequest(BaseModel):
    filename: str
    course_id: int = Form(1)

# Quiz
class QuizRequest(BaseModel):
    filename: str
    course_id: int = Form(1)
    num_questions: int = 5

class QuizResultRequest(BaseModel):
    filename: str
    course_id: int = Form(1)
    score: int
    total: int

# Ask
class ChatMessage(BaseModel):
    role: str 
    content: str
    sources: Optional[List] = []
    source_type: Optional[str] = "pdf"

class QuestionRequest(BaseModel):
    filename: str
    course_id: int = Form(1)
    question: str
    history: Optional[List[ChatMessage]] = []

# Notes
class NoteCreateRequest(BaseModel):
    filename: str
    course_id: int = Form(1)
    type: str # answer / summary / quiz_explanation
    content: str

# Course
class CourseCreateRequest(BaseModel):
    title: str

class CourseUpdateRequest(BaseModel):
    title: str

# ---------- Structured Output Models --------------
# Preview
class VocabItem(BaseModel):
    term: str = Field(description="German technical term")
    translation: str = Field(description="Chinese translation")

class PreviewResponse(BaseModel):
    summary_de: str = Field(description="5-sentence summary in German")
    summary_zh: str = Field(description="5-sentence summary in Chinese")
    vocabulary: List[VocabItem] = Field(description="10 key technical terms with translations")

# Quiz
class QuizOption(BaseModel):
    A: str = Field(description="First option")
    B: str = Field(description="Second option")
    C: str = Field(description="Third option")
    D: str = Field(description="Fourth option")

class QuizQuestion(BaseModel):
    question: str = Field(description="Question text in German")
    options: QuizOption = Field(description="Four answer options")
    answer: str = Field(description="Correct answer: A, B, C, or D")
    explanation: str = Field(description="Explanation in Chinese")

class QuizResponse(BaseModel):
    questions: List[QuizQuestion] = Field(description="List of quiz questions")

class QuizResultRequest(BaseModel):
    filename: str
    course_id: int = Form(1)
    score: int
    total: int

# create FastAPI application, test: http://localhost:8000/docs, uvicorn running on: http://127.0.0.1:8000
app = FastAPI()

load_dotenv() 
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# allow CORS for testing, in production specify allowed origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

upload_progress = {}
executor = ThreadPoolExecutor()

@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...), course_id: int = Form(1), db: Session = Depends(get_db)):
    
    content = await file.read()  
    filename=file.filename

    course = db.query(Course).filter(Course.id==course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found in database.")
    
    existing = db.query(PdfFile).filter(
        PdfFile.filename==filename,
        PdfFile.course_id==course_id
    ).first() # limit 1

    if existing:
        pdf_file = existing
        print(f"PdfFile already exists in database: {filename}")
    else:
        pdf_file = PdfFile(
            course_id=course_id,
            filename=filename, 
            chunk_count=0
        )
        db.add(pdf_file)
        db.commit()
        db.refresh(pdf_file)
        print(f"New PdfFile record created in database: {filename}, id: {pdf_file.id}")

    upload_progress[filename] = {"status": "processing", "progress": 0}
    asyncio.get_event_loop().run_in_executor(
        executor,
        process_pdf_background,
        content,
        filename,
        pdf_file.id
    )

    return {
        "message": "Upload received, processing started.",
        "filename": filename,
        "pdf_file_id": pdf_file.id,
        "status": "processing"
    }


def process_pdf_background(content:bytes, filename:str, pdf_file_id: int):
    db = SessionLocal()
    try:
        upload_progress[filename] = {"status": "processing", "progress": 10}
        chunks = process_pdf(content, filename)
        upload_progress[filename] = {"status": "processing", "progress": 50}
        store_chunks(chunks, filename)

        pdf_file = db.query(PdfFile).filter(PdfFile.id==pdf_file_id).first()
        if pdf_file:
            pdf_file.chunk_count = len(chunks)
            db.commit()

        upload_progress[filename] = {
            "status": "done", 
            "progress": 100, 
            "chunks": len(chunks),
            "pdf_file_id": pdf_file_id
            }
        print(f"PDF processing complete: {filename}, {len(chunks)} chunks")

    except Exception as e:
        print(f"Error occurred while processing PDF: {e}")
        upload_progress[filename] = {"status": "error", "progress": 0,"message": str(e)}
        print(f"PDF processing error: {e}")

    finally:
        db.close()


@app.get("/upload/status/{filename}")
async def get_upload_status(filename: str):
    if filename not in upload_progress:
        raise HTTPException(status_code=404, detail="File not found")
    return upload_progress[filename]


@app.post("/ask") 
async def ask_question(request: QuestionRequest, db: Session = Depends(get_db)):
    pdf_file = db.query(PdfFile).filter(
        PdfFile.filename==request.filename,
        PdfFile.course_id==request.course_id
    ).first() 

    if not pdf_file:
        raise HTTPException(status_code=404, detail="PDF file not found in database.")
    
    memory = load_memory(request.filename, request.course_id)

    # 对话历史
    history_text=""
    if should_compress(request.history, memory):
        print("More than 6 messages, compressing...")
        summary=compress_history(request.history, memory)
        memory["history_summary"]=summary
        history_text=f"History: {summary}\n"
        print(f"History Summary: {summary}")
    else:
        for msg in request.history[-6:]:  # save only 6 recent messages
            role_label="Student" if msg.role=="user" else "Assistant"
            history_text += f"{role_label}: {msg.content}\n"   

    # search for 5 relevant chunks and calculate relevance score
    results_with_score = search_chunks_with_score(request.question, request.filename, k=5)
    if not results_with_score:
        raise HTTPException(status_code=404, detail=
                            "Relevant chunks not found. Please upload the PDF first.")
    
    best_score=min(score for _, score in results_with_score)
    print(f"RAG Relevance Score: {best_score}")
    SCORE_THRESHOLD = 0.9  # 分数阈值：低于0.9说明PDF里有相关内容

    weak_concepts_text = ""
    if memory.get("weak_concepts"):
        weak_concepts_text = f"\nStudent's weak concepts: {', '.join(memory['weak_concepts'])}. Please elaborate more on these when relevant."

    learning_style_text = ""
    if memory.get("learning_style") and memory["learning_style"] != "未知":
        learning_style_text = f"\nStudent's learning style: {memory['learning_style']}. Please adjust your answer accordingly."


    if best_score < SCORE_THRESHOLD: 
        print(f"RAG Relevance Score {best_score} below threshold, using PDF content to answer") 

        context_parts=[]  
        pages_used=set()  
    
        for chunk,score in results_with_score: 
            context_parts.append(chunk.page_content) # page_content comes from LangChain
            page_num=chunk.metadata.get("page",0)+1  # page starts from 0，so here +1 
            pages_used.add(page_num) 

        context = "\n\n---\n\n".join(context_parts) 
        context = context[:2000]
        source_type="pdf" 
        sources = sorted(list(pages_used)) 

        system_prompt = f"""You are a learning assistant helping international students understand German lecture materials.
            {weak_concepts_text}{learning_style_text}
            Your task is to answer the student's question based strictly on the provided lecture content.

            Rules:
            - Answer ONLY based on the provided lecture content, do not add information not present in the original text
            - Always answer in Chinese
            - Be concise and direct, only address what the question asks
            - Do not proactively add diagrams, formulas, or code blocks
            - Keep the answer under 150 characters"""

        user_prompt = f"""Lecture content: {context}
            {('Conversation history:\n' + history_text) if history_text else ''}
            Student question: {request.question}"""
        
        answer = claude.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=400,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )
        answer = answer.content[0].text.strip()

    else:
        print(f"RAG Relevance Score {best_score} above threshold, using web search to answer")

        from tools import CLAUDE_TOOLS, search_web, generate_mermaid_chart

        first_prompt = f"""
                You are a learning assistant helping international students understand lecture materials.
                {weak_concepts_text}{learning_style_text}

                Rules:
                - Always answer in Chinese
                - Be concise and direct, keep answer under 250 characters
                - Only call search_web if you need current information to answer the question
                - Only call generate_mermaid_chart if the question explicitly asks for a diagram
                - If you can answer directly, do so without calling any tool"""
        
        first_response = claude.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=500,
            system=first_prompt,
            tools=CLAUDE_TOOLS,
            messages=[{"role": "user", "content": f"Student question: {request.question}"}],
        )

        tool_results = []
        source_type = "web"
        sources = []

        if first_response.stop_reason == "tool_use":
            for block in first_response.content:
                if block.type == "tool_use":
                    tool_name=block.name
                    tool_input=block.input
                    print(f"Claude Tool Use: {tool_name}, Parameter: {tool_input}")

                    if tool_name == "search_web":
                        tool_output = search_web.invoke(tool_input["query"])
                        sources = []
                        for line in tool_output.split("\n"):
                            if line.startswith("from:"):
                                sources.append(line.replace("from:", "").strip())
                    elif tool_name == "generate_mermaid_chart":
                        tool_output = await generate_mermaid_chart.ainvoke(tool_input["description"])
                        sources = []
                    else:
                        tool_output = "Tool not found."

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": tool_output
                    })
            
            second_prompt = f"""
                        You are a learning assistant helping international students understand lecture materials.
                        {weak_concepts_text}{learning_style_text}

                        Rules:
                        - Always answer in Chinese
                        - Be concise and direct, keep answer under 250 characters
                        - Only output diagrams or formulas if explicitly needed"""
            second_response = claude.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=500, 
                system=second_prompt,
                messages=[
                    {"role": "user", "content": request.question},
                    {"role": "assistant", "content": first_response.content},
                    {"role": "user", "content": tool_results}
                ]
            )
            answer = second_response.content[0].text

        else:
            print("Claude answered directly without tool use")
            answer = first_response.content[0].text
            source_type = "web"
            sources = []

    memory = update_memory(request.filename, request.question, answer, memory)
    save_memory(request.filename, memory, request.course_id)
    
    user_message = Message(
        pdf_file_id=pdf_file.id,
        role="user",
        content=request.question,
        source_type=None,
        sources=None
    )

    assistant_message = Message(
        pdf_file_id=pdf_file.id,
        role="assistant",
        content=answer,
        source_type=source_type,
        sources=sources
    )

    db.add(user_message)
    db.add(assistant_message)
    db.commit()

    return {
        "question": request.question,
        "answer": answer,
        "source_type": source_type,
        "sources": sources,
        "relevance": best_score<SCORE_THRESHOLD
    }


@app.get("/message/{filename}")
async def get_messages(filename: str, course_id: int = Form(1), db: Session = Depends(get_db)):
    pdf_file = db.query(PdfFile).filter(
        PdfFile.filename==filename,
        PdfFile.course_id==course_id
    ).first()

    if not pdf_file:
        raise HTTPException(status_code=404, detail="PDF file not found in database.")
    
    messages = db.query(Message).filter(
        Message.pdf_file_id==pdf_file.id
        ).order_by(Message.created_at.asc()).all()
    
    return {
        "filename": filename,
        "messages": [
            {
                "role": msg.role,
                "content": msg.content,
                "source_type": msg.source_type,
                "sources": msg.sources or []
            } for msg in messages
        ]
    }


@app.post("/preview")
async def generate_preview(request: PreviewRequest):
    queries = [
        "What is the main topic of this lecture?",
        "What are the key technical terms and their definitions?"
    ]

    all_chunks=[]
    seen_contents=set() 

    for query in queries:
        chunks = search_chunks(query, request.filename, k=3)
        for chunk in chunks:
            if chunk.page_content not in seen_contents:
                all_chunks.append(chunk)
                seen_contents.add(chunk.page_content)

    if not all_chunks:
        raise HTTPException(status_code=404, detail="Relevant chunks not found. Please upload the PDF first.")
    
    context = "\n\n---\n\n".join([c.page_content for c in all_chunks])
    context = context[:2000]

    parser = JsonOutputParser(pydantic_object=PreviewResponse)

    system_prompt = f"""
                You are an academic assistant helping international students understand lecture materials.
                Output ONLY a valid JSON object. Do not wrap in markdown code blocks. No explanation."""

    user_prompt = f"""
                Lecture content:
                {context}
                {parser.get_format_instructions()}
                
                Rules:
                - summary_de: 5 sentences in German
                - summary_zh: 5 sentences in Chinese
                - vocabulary: exactly 10 most important technical terms, each with German term and Chinese translation
                - Output ONLY the JSON, no markdown, no explanation"""
    
    message = claude.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1200,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}]
    )

    raw_text = message.content[0].text.strip()

    # clear markdown
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[-1]
    if raw_text.endswith("```"):
        raw_text = raw_text.rsplit("```", 1)[0].strip()

    try:
        preview_data =  json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse preview response: {e}")
    
    vocab_list = []
    for item in preview_data.get("vocabulary", []):
        if isinstance(item, dict):
            vocab_list.append(f"{item.get('term', '')} ({item.get('translation', '')})")
        else:
            vocab_list.append(str(item))

    # Mindmap
    system_prompt_mindmap = f"""
                    You are a Mermaid diagram expert. 
                    Output ONLY valid Mermaid mindmap syntax. 
                    No markdown fences, no explanation, no text before or after."""
    mindmap_prompt = f"""
                    Generate a Mermaid mindmap showing the structure of this lecture.
                    Lecture content:{context}

                    Rules:
                    - Use mindmap type
                    - Maximum 3 levels deep
                    - Maximum 15 nodes total
                    - All labels in German as they appear in the lecture
                    - Keep node labels short, max 4 words
                    - Output ONLY the Mermaid syntax, no markdown fences, no explanation"""
    mindmap_message = claude.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1000,
        system=system_prompt_mindmap,
        messages=[{"role": "user", "content": mindmap_prompt}]
    )
    mindmap_raw = mindmap_message.content[0].text.strip()
    # clear possible markdown marks
    if mindmap_raw.startswith("```"):
        mindmap_raw = mindmap_raw.split("\n", 1)[-1]
    if mindmap_raw.endswith("```"):
        mindmap_raw = mindmap_raw.rsplit("```", 1)[0].strip()

    mindmap = f"```mermaid\n{mindmap_raw}\n```"

    return {
        "filename": request.filename,
        "summary_de": preview_data.get("summary_de", ""),
        "summary_zh": preview_data.get("summary_zh", ""),
        "vocabulary": vocab_list,
        "mindmap": mindmap
    }


@app.post("/quiz")
async def generate_quiz(request: QuizRequest):
    # get weak concepts
    conv_memory = load_memory(request.filename, request.course_id)
    weak_concepts = conv_memory.get("weak_concepts", [])
    print(f"weak_concepts: {weak_concepts}")

    # get quiz history scores
    quiz_memory = load_quiz_memory(request.filename, request.course_id)
    average_score = quiz_memory.get("average_score", 0.0)
    print(f"average_score: {average_score}")

    # difficulty estimation
    if average_score == 0.0:
        difficulty_hint = "Generate a mix of basic and intermediate questions."
    elif average_score < 0.6:
        difficulty_hint = "Focus on basic conceptual questions to strengthen fundamentals."
    elif average_score >= 0.8:
        difficulty_hint = "Focus on advanced application and analysis questions."
    else:
        difficulty_hint = "Generate a mix of basic and intermediate questions."

    # weak concepts prompt
    weak_concepts_text = ""
    if weak_concepts:
        weak_concepts_text = f"Prioritize questions about these concepts the student is weak on: {', '.join(weak_concepts)}"

    # search for relevant chunks
    queries=[
             "What are the main concepts and definitions?",
             "What are the key technical terms and their applications?",
             "What are the important rules, principles or methods?"
    ]

    all_chunks=[]
    seen_contents=set()

    for query in queries:
            chunks = search_chunks(query, request.filename, k=3)
            for chunk in chunks:
                if chunk.page_content not in seen_contents:
                    all_chunks.append(chunk)
                    seen_contents.add(chunk.page_content)

    if not all_chunks:
            raise HTTPException(status_code=404, detail="Relevant chunks not found. Please upload the PDF first.")
        
    context = "\n\n---\n\n".join([c.page_content for c in all_chunks])
    context = context[:2500]  

    parser = JsonOutputParser(pydantic_object=QuizResponse)

    system_prompt = f""""
            You are a learning assistant creating multiple choice questions for students.
            Output ONLY a valid JSON object. Do not wrap in markdown code blocks. No explanation."""
    
    user_prompt=f"""
            Lecture content: {context}

            {difficulty_hint} 
            {weak_concepts_text}

            {parser.get_format_instructions()}

            Rules:
            - Generate exactly {request.num_questions} questions
            - Each question must be based strictly on the lecture content
            - Questions must be in German
            - Only one option is correct
            - answer field must be exactly one of: A, B, C, D
            - explanation must be in Chinese, 1-2 sentences
            - Options must cover plausible wrong answers"""
        
    message = claude.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=2000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}]
    )

    raw_text = message.content[0].text.strip()

    # clear possible markdown marks
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[-1]
    if raw_text.endswith("```"):
        raw_text = raw_text.rsplit("```", 1)[0].strip()

    try:
        quiz_data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse quiz response: {e}")

    questions=quiz_data.get("questions", [])
    if not questions:
            raise HTTPException(status_code=500, detail="No questions generated.")
    
    return {
            "filename": request.filename,
            "questions": questions
    }


@app.post("/quiz/result")
async def save_quiz_result(request: QuizResultRequest):
    save_quiz_memory(request.filename, request.score, request.total, request.course_id)
    return {"message": "Quiz result saved successfully"}


@app.post("/notes")
async def create_note(request: NoteCreateRequest, db: Session = Depends(get_db)):
    pdf_file = db.query(PdfFile).filter(
        PdfFile.filename==request.filename,
        PdfFile.course_id==request.course_id
    ).first()

    if not pdf_file:
        raise HTTPException(status_code=404, detail="PDF file not found in database.")
    
    note = Note(
        pdf_file_id=pdf_file.id,
        type=request.type,
        content=request.content
    )

    db.add(note)
    db.commit()
    db.refresh(note)

    return {
        "id": note.id,
        "type": note.type,
        "content": note.content,
        "created_at": note.created_at.isoformat()
    }


@app.get("/notes/{filename}")
async def get_notes(filename: str, course_id: int = Form(1), db: Session = Depends(get_db)):
    pdf_file = db.query(PdfFile).filter(
        PdfFile.filename==filename,
        PdfFile.course_id==course_id
    ).first()

    if not pdf_file:
        raise HTTPException(status_code=404, detail="PDF file not found in database.")
    
    notes = db.query(Note).filter(
        Note.pdf_file_id==pdf_file.id
        ).order_by(Note.created_at.asc()).all()
    
    return {
        "filename": filename,
        "notes": [
            {
                "id": note.id,
                "type": note.type,
                "content": note.content,
                "created_at": note.created_at.isoformat()
            } for note in notes
        ]
    }


@app.delete("/notes/{note_id}")
async def delete_note(note_id: int, db: Session = Depends(get_db)):
    note = db.query(Note).filter(Note.id==note_id).first()

    if not note:
        raise HTTPException(status_code=404, detail="Note not found.")
    
    db.delete(note)
    db.commit()

    return {"message": "Note deleted successfully"}


@app.post("/courses")
async def create_course(request: CourseCreateRequest, db: Session = Depends(get_db)):
    course = Course(
        user_id=1, 
        title=request.title
    )

    db.add(course)
    db.commit()
    db.refresh(course)

    return {
        "id": course.id,
        "title": course.title,
        "created_at": course.created_at.isoformat(),
        "pdf_count":0
    }


@app.get("/courses")
async def get_courses(db: Session = Depends(get_db)):
    courses = db.query(Course).filter(Course.user_id == 1).order_by(Course.created_at).all()

    result=[]
    for c in courses:
        pdf_count = db.query(PdfFile).filter(PdfFile.course_id == c.id).count()
        result.append({
            "id": c.id,
            "title": c.title,
            "created_at": c.created_at.isoformat(),
            "pdf_count": pdf_count
        })
    return {
        "courses":result 
    }


@app.get("/courses/{course_id}")
async def get_course(course_id: int, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id==course_id).first()

    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")
    
    pdf_files = db.query(PdfFile).filter(PdfFile.course_id==course.id).order_by(PdfFile.created_at.desc()).all()
    pdf_list = []
    for pdf in pdf_files:
        pdf_list.append({
            "id": pdf.id,
            "filename": pdf.filename,
            "chunk_count": pdf.chunk_count,
            "created_at": pdf.created_at.isoformat()
        })

    return {
        "id": course.id,
        "title": course.title,
        "created_at": course.created_at.isoformat(),
        "pdf_files": pdf_list
    }


@app.patch("/courses/{course_id}")
async def update_course(course_id: int, request: CourseUpdateRequest, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id==course_id).first()

    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")
    
    course.title = request.title
    db.commit()
    db.refresh(course)

    return {
        "id": course.id,
        "title": course.title,
        "created_at": course.created_at.isoformat()
    }


@app.delete("/courses/{course_id}")
async def delete_course(course_id: int, db: Session = Depends(get_db)):
    if course_id == 1:
        raise HTTPException(status_code=400, detail="Default course cannot be deleted")

    course = db.query(Course).filter(Course.id==course_id).first()

    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")
    
    db.delete(course)
    db.commit()

    return {"message": "Course deleted successfully"}