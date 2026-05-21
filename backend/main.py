import json
from fastapi import FastAPI, UploadFile, File, HTTPException
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

from pdf_processor import process_pdf
from rag import store_chunks, search_chunks, search_chunks_with_score
from memory import load_memory, save_memory, compress_history, update_memory, should_compress, load_quiz_memory, save_quiz_memory

# ---------- Requests --------------
# Preview
class PreviewRequest(BaseModel):
    filename: str

# Quiz
class QuizRequest(BaseModel):
    filename: str
    num_questions: int = 5

class QuizResultRequest(BaseModel):
    filename: str
    score: int
    total: int

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

# ----------  History message --------------
class Message(BaseModel):
    role: str 
    content: str
    sources: Optional[List] = []
    source_type: Optional[str] = "pdf"

class QuestionRequest(BaseModel):
    filename: str
    question: str
    history: Optional[List[Message]] = []

# 创建FastAPI应用,测试接口: http://localhost:8000/docs, uvicorn running on: http://127.0.0.1:8000
app = FastAPI()

load_dotenv() 
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# 允许前端跨域访问（前后端分离时必须配置）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

upload_progress = {}
executor = ThreadPoolExecutor()

# 上传PDF接口：解析PDF → 切块 → 存ChromaDB
@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    
    content = await file.read()  
    filename=file.filename
    upload_progress[filename] = {"status": "processing", "progress": 0}

    asyncio.get_event_loop().run_in_executor(
        executor,
        process_pdf_background,
        content,
        filename
    )

    return {
        "message": "Upload received, processing started.",
        "filename": filename,
        "status": "processing"
    }

def process_pdf_background(content:bytes, filename:str):

    try:
        upload_progress[filename] = {"status": "processing", "progress": 10}
        chunks = process_pdf(content, filename)
        upload_progress[filename] = {"status": "processing", "progress": 50}
        store_chunks(chunks, filename)
        upload_progress[filename] = {"status": "done", "progress": 100, "chunks": len(chunks)}
        print(f"PDF processing complete: {filename}, {len(chunks)} chunks")

    except Exception as e:
        print(f"Error occurred while processing PDF: {e}")
        upload_progress[filename] = {"status": "error", "progress": 0,"message": str(e)}
        print(f"PDF processing error: {e}")

@app.get("/upload/status/{filename}")
async def get_upload_status(filename: str):
    if filename not in upload_progress:
        raise HTTPException(status_code=404, detail="File not found")
    return upload_progress[filename]


@app.post("/ask") 
async def ask_question(request: QuestionRequest):
    memory = load_memory(request.filename)

    # 对话历史
    history_text=""
    if should_compress(request.history, memory):
        print("More than 6 messages, compressing...")
        summary=compress_history(request.history, memory)
        memory["history_summary"]=summary
        history_text=f"History: {summary}\n"
        print(f"History Summary: {summary}")
    else:
        for msg in request.history[-6:]:  # 只保留最近6条
            role_label="Student" if msg.role=="user" else "Assistant"
            history_text += f"{role_label}: {msg.content}\n"   

    # 从ChromaDB检索最相关的5个块
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
            context_parts.append(chunk.page_content) # page_content是LangChain文档对象的属性 
            page_num=chunk.metadata.get("page",0)+1  # 页码从0开始，所以+1 
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
    save_memory(request.filename, memory)
        
    return {
        "question": request.question,
        "answer": answer,
        "source_type": source_type,
        "sources": sources,
        "relevance": best_score<SCORE_THRESHOLD
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
    # 清理可能的 markdown 标记
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
    conv_memory = load_memory(request.filename)
    weak_concepts = conv_memory.get("weak_concepts", [])
    print(f"weak_concepts: {weak_concepts}")

    # get quiz history scores
    quiz_memory = load_quiz_memory(request.filename)
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

    # 清理 markdown 代码块标记
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
