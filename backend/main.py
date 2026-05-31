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
from observability import langfuse, logger, generate_request_id


from pdf_processor import process_pdf
from rag import store_chunks, search_chunks, search_chunks_with_score
from memory import load_memory, save_memory, compress_history, update_memory, should_compress, load_quiz_memory, save_quiz_memory
from database import get_db, SessionLocal
from models import User, Course, PdfFile, Message, Note, Memory, QuizProgress
from tools import search_web, generate_mermaid_chart
from auth import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    decode_token, get_current_user
)

# ---------- Requests --------------
# Auth Request Models
class RegisterRequest(BaseModel):
    email: str
    name: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class RefreshRequest(BaseModel):
    refresh_token: str

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

@app.post("/auth/register")
async def register(request: RegisterRequest, db: Session = Depends(get_db)): 
    existing = db.query(User).filter(User.email == request.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user = User(
        email=request.email,
        name=request.name,
        password_hash=hash_password(request.password)
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    default_course=Course(user_id=user.id,title="Default Course")
    db.add(default_course)
    db.commit()

    return{
        "id":user.id,
        "email":user.email,
        "name":user.name
    }


@app.post("/auth/login")
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email==request.email).first()

    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return {
        "access_token": create_access_token(user.id),
        "refresh_token": create_refresh_token(user.id),
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name
        }
    }


@app.post("/auth/refresh")
async def refresh_token(request: RefreshRequest, db: Session = Depends(get_db)):
    payload=decode_token(request.refresh_token)

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Not a refresh token")
    
    user_id = int(payload.get("sub"))
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return {
        "access_token": create_access_token(user.id),
        "token_type": "bearer"
    }


@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...), 
                     course_id: int = Form(1), 
                     db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user) #auth
):
    
    content = await file.read()  
    filename=file.filename

    course = db.query(Course).filter(Course.id==course_id, Course.user_id==current_user.id).first()
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
async def get_upload_status(filename: str,current_user: User = Depends(get_current_user)):
    if filename not in upload_progress:
        raise HTTPException(status_code=404, detail="File not found")
    return upload_progress[filename]


@app.post("/ask")
async def ask_question(request: QuestionRequest, 
                       db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    request_id = generate_request_id()
    logger.info(f"[{request_id}] /ask started | filename={request.filename} | question={request.question[:50]}")

    with langfuse.start_as_current_observation(
        as_type="span",
        name="ask",
        input={
            "question": request.question,
            "filename": request.filename,
            "course_id": request.course_id
        }
    ) as root_span:
        
        course =db.query(Course).filter(
        Course.id==request.course_id,
        Course.user_id == current_user.id).first()

        if not course:
            raise HTTPException(status_code=403, detail="Not authorized.")

        pdf_file = db.query(PdfFile).filter(
            PdfFile.filename == request.filename,
            PdfFile.course_id == request.course_id
        ).first()

        if not pdf_file:
            raise HTTPException(status_code=404, detail="PDF file not found in database.")

        memory = load_memory(request.filename, request.course_id)

        history_text = ""
        if should_compress(request.history, memory):
            print("More than 6 messages, compressing...")
            summary = compress_history(request.history, memory)
            memory["history_summary"] = summary
            history_text = f"History: {summary}\n"
            print(f"History Summary: {summary}")
        else:
            for msg in request.history[-6:]:
                role_label = "Student" if msg.role == "user" else "Assistant"
                history_text += f"{role_label}: {msg.content}\n"

        SCORE_THRESHOLD = 0.9

        with langfuse.start_as_current_observation(
            as_type="span",
            name="rag-retrieval",
            input={"query": request.question}
        ) as rag_span:
            results_with_score, best_score = search_chunks_with_score(
                request.question, request.filename, k=5
            )
            if not results_with_score:
                raise HTTPException(
                    status_code=404,
                    detail="Relevant chunks not found. Please upload the PDF first."
                )

            rag_span.update(
                output={
                    "best_cosine_score": best_score,
                    "chunks_found": len(results_with_score),
                    "branch": "pdf" if best_score < SCORE_THRESHOLD else "pdf+web"
                }
            )

        print(f"RAG Relevance Score: {best_score}")
        logger.info(f"[{request_id}] RAG score={best_score:.4f}")

        weak_concepts_text = ""
        if memory.get("weak_concepts"):
            weak_concepts_text = f"\nStudent's weak concepts: {', '.join(memory['weak_concepts'])}. Please elaborate more on these when relevant."

        learning_style_text = ""
        if memory.get("learning_style") and memory["learning_style"] != "未知":
            learning_style_text = f"\nStudent's learning style: {memory['learning_style']}. Please adjust your answer accordingly."

        context_parts = []
        pages_used = set()
        for chunk, score in results_with_score:
            context_parts.append(chunk.page_content)
            page_num = chunk.metadata.get("page", 0) + 1
            pages_used.add(page_num)

        context = "\n\n---\n\n".join(context_parts)[:2000]

        pdf_system_prompt = f"""You are a learning assistant helping international students understand German lecture materials.
            {weak_concepts_text}{learning_style_text}
            Your task is to answer the student's question based on the provided lecture content.

            Rules:
            - Answer in Chinese
            - Be concise and direct, only address what the question asks
            - Do not proactively add diagrams, formulas, or code blocks
            - If the lecture content is relevant, answer strictly from it
            - If the lecture content is not relevant to the question, say "讲义中未找到直接相关内容。"
            - Keep the answer under 200 characters"""

        pdf_user_prompt = f"""Lecture content:
            {context}

            {('Conversation history:\n' + history_text) if history_text else ''}
            Student question: {request.question}"""

        with langfuse.start_as_current_observation(
            as_type="generation",
            name="pdf-answer",
            model="claude-sonnet-4-5",
            input={"system": pdf_system_prompt[:300], "user": pdf_user_prompt[:300]}
        ) as pdf_gen:
            pdf_response = claude.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=400,
                system=pdf_system_prompt,
                messages=[{"role": "user", "content": pdf_user_prompt}]
            )
            pdf_answer = pdf_response.content[0].text.strip()

            pdf_gen.update(
                output=pdf_answer,
                usage_details={
                    "input": pdf_response.usage.input_tokens,
                    "output": pdf_response.usage.output_tokens
                }
            )

        print(f"PDF answer generated, score={best_score}")
        logger.info(f"[{request_id}] PDF answer | tokens={pdf_response.usage.input_tokens}+{pdf_response.usage.output_tokens}")

        source_type = "pdf"
        web_supplement = ""
        web_sources = []

        if best_score >= SCORE_THRESHOLD:
            print(f"RAG Relevance Score {best_score} above threshold, adding web supplement")

            tool_output = str(search_web.invoke(request.question))
            for line in tool_output.split("\n"):
                if line.startswith("from:"):
                    web_sources.append(line.replace("from:", "").strip())
            print(f"search_web returned, sources: {web_sources}")

            supplement_system = f"""You are a learning assistant helping international students.
                {weak_concepts_text}{learning_style_text}

                Rules:
                - Always answer in Chinese
                - Be concise, keep supplement under 200 characters
                - Only use the web search results to supplement the PDF answer
                - Do not repeat what the PDF answer already said"""

            with langfuse.start_as_current_observation(
                as_type="generation",
                name="web-supplement",
                model="claude-sonnet-4-5",
                input={"question": request.question}
            ) as web_gen:
                supplement_response = claude.messages.create(
                    model="claude-sonnet-4-5",
                    max_tokens=500,
                    system=supplement_system,
                    messages=[{"role": "user", "content": f"""PDF answer: {pdf_answer}
                        Web search results: {tool_output[:1500]}
                        Student question: {request.question}
                        Provide a brief supplement based on the web search results."""}]
                )

                web_supplement = supplement_response.content[0].text.strip()
                source_type = "pdf+web"

                web_gen.update(
                    output=web_supplement,
                    usage_details={
                        "input": supplement_response.usage.input_tokens,
                        "output": supplement_response.usage.output_tokens
                    }
                )

        root_span.update(
            output={"source_type": source_type, "answer_length": len(pdf_answer)}
        )
        logger.info(f"[{request_id}] /ask completed | source_type={source_type}")

        full_answer = f"{pdf_answer}\n{web_supplement}" if web_supplement else pdf_answer
        memory = update_memory(request.filename, request.question, full_answer, memory)
        save_memory(request.filename, memory, request.course_id)

        final_sources = {
            "pages": sorted(list(pages_used)),
            "urls": web_sources if source_type == "pdf+web" else []
        }

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
            content=pdf_answer,
            source_type=source_type,
            sources=final_sources.get("urls", [])
        )
        db.add(user_message)
        db.add(assistant_message)
        db.commit()

    langfuse.flush()

    return {
        "question": request.question,
        "answer": pdf_answer,
        "web_supplement": web_supplement,
        "source_type": source_type,
        "sources": final_sources,
        "relevance": best_score < SCORE_THRESHOLD
    }


@app.get("/message/{filename}")
async def get_messages(filename: str, 
                       course_id: int = 1, 
                       db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    course =db.query(Course).filter(
        Course.id==course_id,
        Course.user_id == current_user.id).first()

    if not course:
        raise HTTPException(status_code=403, detail="Not authorized.")

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
async def generate_preview(request: PreviewRequest,current_user: User = Depends(get_current_user)):
    request_id = generate_request_id()
    logger.info(f"[{request_id}] /preview started | filename={request.filename}")

    with langfuse.start_as_current_observation(
        as_type="span",
        name="preview",
        input={"filename": request.filename}
    ) as root_span:

        queries = [
            "What is the main topic of this lecture?",
            "What are the key technical terms and their definitions?"
        ]

        all_chunks = []
        seen_contents = set()
        for query in queries:
            chunks = search_chunks(query, request.filename, k=3)
            for chunk in chunks:
                if chunk.page_content not in seen_contents:
                    all_chunks.append(chunk)
                    seen_contents.add(chunk.page_content)

        if not all_chunks:
            raise HTTPException(
                status_code=404,
                detail="Relevant chunks not found. Please upload the PDF first."
            )

        context = "\n\n---\n\n".join([c.page_content for c in all_chunks])[:2000]

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

        with langfuse.start_as_current_observation(
            as_type="generation",
            name="preview-summary",
            model="claude-sonnet-4-5",
            input={"system": system_prompt, "user": user_prompt}
        ) as summary_gen:
            message = claude.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=1200,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}]
            )
            raw_text = message.content[0].text.strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[-1]
            if raw_text.endswith("```"):
                raw_text = raw_text.rsplit("```", 1)[0].strip()

            summary_gen.update(
                output=raw_text,
                usage_details={
                    "input": message.usage.input_tokens,
                    "output": message.usage.output_tokens
                }
            )

        try:
            preview_data = json.loads(raw_text)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=500, detail=f"Failed to parse preview response: {e}")

        logger.info(f"[{request_id}] Preview summary generated | input_tokens={message.usage.input_tokens}")

        vocab_list = []
        for item in preview_data.get("vocabulary", []):
            if isinstance(item, dict):
                vocab_list.append(f"{item.get('term', '')} ({item.get('translation', '')})")
            else:
                vocab_list.append(str(item))

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

        with langfuse.start_as_current_observation(
            as_type="generation",
            name="preview-mindmap",
            model="claude-sonnet-4-5",
            input={"system": system_prompt_mindmap, "user": mindmap_prompt}
        ) as mindmap_gen:
            mindmap_message = claude.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=1000,
                system=system_prompt_mindmap,
                messages=[{"role": "user", "content": mindmap_prompt}]
            )
            mindmap_raw = mindmap_message.content[0].text.strip()
            if mindmap_raw.startswith("```"):
                mindmap_raw = mindmap_raw.split("\n", 1)[-1]
            if mindmap_raw.endswith("```"):
                mindmap_raw = mindmap_raw.rsplit("```", 1)[0].strip()

            mindmap_gen.update(
                output=mindmap_raw,
                usage_details={
                    "input": mindmap_message.usage.input_tokens,
                    "output": mindmap_message.usage.output_tokens
                }
            )

        mindmap = f"```mermaid\n{mindmap_raw}\n```"

        logger.info(f"[{request_id}] Preview mindmap generated | input_tokens={mindmap_message.usage.input_tokens}")

        root_span.update(output={"vocab_count": len(vocab_list)})

    langfuse.flush()
    logger.info(f"[{request_id}] /preview completed")

    return {
        "filename": request.filename,
        "summary_de": preview_data.get("summary_de", ""),
        "summary_zh": preview_data.get("summary_zh", ""),
        "vocabulary": vocab_list,
        "mindmap": mindmap
    }


@app.post("/quiz")
async def generate_quiz(request: QuizRequest,current_user: User = Depends(get_current_user)):
    request_id = generate_request_id()
    logger.info(f"[{request_id}] /quiz started | filename={request.filename} | num_questions={request.num_questions}")

    conv_memory = load_memory(request.filename, request.course_id)
    weak_concepts = conv_memory.get("weak_concepts", [])
    print(f"weak_concepts: {weak_concepts}")

    quiz_memory = load_quiz_memory(request.filename, request.course_id)
    average_score = quiz_memory.get("average_score", 0.0)
    print(f"average_score: {average_score}")

    if average_score == 0.0:
        difficulty_hint = "Generate a mix of basic and intermediate questions."
    elif average_score < 0.6:
        difficulty_hint = "Focus on basic conceptual questions to strengthen fundamentals."
    elif average_score >= 0.8:
        difficulty_hint = "Focus on advanced application and analysis questions."
    else:
        difficulty_hint = "Generate a mix of basic and intermediate questions."

    weak_concepts_text = ""
    if weak_concepts:
        weak_concepts_text = f"Prioritize questions about these concepts the student is weak on: {', '.join(weak_concepts)}"

    with langfuse.start_as_current_observation(
        as_type="span",
        name="quiz",
        input={
            "filename": request.filename,
            "num_questions": request.num_questions,
            "difficulty": difficulty_hint,
            "average_score": average_score
        }
    ) as root_span:

        queries = [
            "What are the main concepts and definitions?",
            "What are the key technical terms and their applications?",
            "What are the important rules, principles or methods?"
        ]

        all_chunks = []
        seen_contents = set()
        for query in queries:
            chunks = search_chunks(query, request.filename, k=3)
            for chunk in chunks:
                if chunk.page_content not in seen_contents:
                    all_chunks.append(chunk)
                    seen_contents.add(chunk.page_content)

        if not all_chunks:
            raise HTTPException(
                status_code=404,
                detail="Relevant chunks not found. Please upload the PDF first."
            )

        context = "\n\n---\n\n".join([c.page_content for c in all_chunks])[:2500]

        parser = JsonOutputParser(pydantic_object=QuizResponse)

        system_prompt = f"""
                You are a learning assistant creating multiple choice questions for students.
                Output ONLY a valid JSON object. Do not wrap in markdown code blocks. No explanation."""

        user_prompt = f"""
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

        with langfuse.start_as_current_observation(
            as_type="generation",
            name="quiz-generation",
            model="claude-sonnet-4-5",
            input={"system": system_prompt, "user": user_prompt}
        ) as quiz_gen:
            message = claude.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=2000,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}]
            )
            raw_text = message.content[0].text.strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[-1]
            if raw_text.endswith("```"):
                raw_text = raw_text.rsplit("```", 1)[0].strip()

            quiz_gen.update(
                output=raw_text,
                usage_details={
                    "input": message.usage.input_tokens,
                    "output": message.usage.output_tokens
                }
            )

        try:
            quiz_data = json.loads(raw_text)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=500, detail=f"Failed to parse quiz response: {e}")

        questions = quiz_data.get("questions", [])
        if not questions:
            raise HTTPException(status_code=500, detail="No questions generated.")

        root_span.update(output={"questions_count": len(questions)})

    langfuse.flush()
    logger.info(f"[{request_id}] /quiz completed | questions_generated={len(questions)}")

    return {
        "filename": request.filename,
        "questions": questions
    }


@app.post("/quiz/result")
async def save_quiz_result(request: QuizResultRequest,current_user: User = Depends(get_current_user)):
    save_quiz_memory(request.filename, request.score, request.total, request.course_id)
    return {"message": "Quiz result saved successfully"}


@app.post("/notes")
async def create_note(request: NoteCreateRequest, 
                      db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    course =db.query(Course).filter(
        Course.id==request.course_id,
        Course.user_id == current_user.id).first()

    if not course:
        raise HTTPException(status_code=403, detail="Not authorized.")

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
async def get_notes(filename: str, 
                    course_id: int = 1, 
                    db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    course =db.query(Course).filter(
        Course.id==course_id,
        Course.user_id == current_user.id).first()

    if not course:
        raise HTTPException(status_code=403, detail="Not authorized.")
    
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
async def delete_note(note_id: int, 
                      db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    note = db.query(Note).filter(Note.id==note_id).first()

    if not note:
        raise HTTPException(status_code=404, detail="Note not found.")
    
    pdf_file = db.query(PdfFile).filter(PdfFile.id == note.pdf_file_id).first()
    course = db.query(Course).filter(
        Course.id == pdf_file.course_id,
        Course.user_id == current_user.id
    ).first()

    if not course:
        raise HTTPException(status_code=403, detail="Not authorized.")
    
    db.delete(note)
    db.commit()

    return {"message": "Note deleted successfully"}


@app.post("/courses")
async def create_course(request: CourseCreateRequest, 
                        db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)
):
    course = Course(
        user_id=current_user.id, 
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
async def get_courses(db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    courses = db.query(Course).filter(Course.user_id == current_user.id).order_by(Course.created_at).all()

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
async def get_course(course_id: int, 
                     db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    course = db.query(Course).filter(Course.id==course_id,Course.user_id == current_user.id).first()

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
async def update_course(course_id: int, 
                        request: CourseUpdateRequest, 
                        db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    course = db.query(Course).filter(Course.id==course_id, Course.user_id==current_user.id).first()

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
async def delete_course(course_id: int, 
                        db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)):

    course = db.query(Course).filter(Course.id==course_id, Course.user_id==current_user.id).first()

    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")
    
    db.delete(course)
    db.commit()

    return {"message": "Course deleted successfully"}