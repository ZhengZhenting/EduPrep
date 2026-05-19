from email.mime import message
import json

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from dotenv import load_dotenv
import anthropic
import os

from pdf_processor import process_pdf
from rag import store_chunks, search_chunks, search_chunks_with_score
from memory import load_memory, save_memory, compress_history, update_memory, should_compress


# 创建FastAPI应用,测试接口: http://localhost:8000/docs, uvicorn running on: http://127.0.0.1:8000
app = FastAPI()

load_dotenv()  # 加载环境变量
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

# 上传PDF接口：解析PDF → 切块 → 存ChromaDB
@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    
    content = await file.read() 
    chunks=process_pdf(content, file.filename)  
    store_chunks(chunks, file.filename) 


    return {
        "message": "PDF uploaded and text extracted successfully!",
        "filename": file.filename, 
        "chunks": len(chunks)
    }


# 对话历史的单条格式
class Message(BaseModel):
    role: str 
    content: str
    sources: Optional[List] = []
    source_type: Optional[str] = "pdf"


class QuestionRequest(BaseModel):
    filename: str
    question: str
    history: Optional[List[Message]] = []  


@app.post("/ask") 
async def ask_question(request: QuestionRequest):
    # 加载用户记忆
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
    SCORE_THRESHOLD = 1.15  # 分数阈值：低于1.15说明PDF里有相关内容

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
        
        message = claude.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=400,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )

    else:
        print(f"RAG Relevance Score {best_score} above threshold, using web search to answer")
        
        try:
            from tavily import TavilyClient
            tavily_client = TavilyClient(api_key=TAVILY_API_KEY)
            search_result = tavily_client.search(
                request.question,
                max_results=3,
                search_depth="basic"
            )
            web_contents = []
            web_sources = []
            for r in search_result["results"]:
                web_contents.append(r["content"])
                web_sources.append(r["url"])
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"网络搜索失败：{e}")
        
        context = "\n\n---\n\n".join(web_contents) # 将多个搜索结果用分隔符连接起来，形成一个整体的上下文
        context = context[:2000]
        source_type="web" 
        sources = web_sources

        system_prompt = f"""You are a learning assistant helping international students understand German lecture materials.
            {weak_concepts_text}{learning_style_text}

            Rules:
            - Always answer in Chinese
            - Organize a clear answer based on the search results
            - Be concise and direct, only address what the question asks, do not list irrelevant supplementary information
            - Keep the answer under 250 characters
            - Only output diagrams, formulas, or code blocks if the question explicitly asks for them"""

        user_prompt = f"""Search results: {context}

            {('Conversation history:\n' + history_text) if history_text else ''}
            Student question: {request.question}"""
        
        message = claude.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=600,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )
        
    answer = message.content[0].text

    memory = update_memory(request.filename, request.question, answer, memory)
    save_memory(request.filename, memory)
        
    return {
        "question": request.question,
        "answer": answer,
        "source_type": source_type,
        "sources": sources,
        "relevance": best_score<SCORE_THRESHOLD
    }

class PreviewRequest(BaseModel):
    filename: str

@app.post("/preview")
async def generate_preview(request: PreviewRequest):
    queries = [
        "What is the main topic of this lecture?",
        "What are the key technical terms and their definitions?"
    ]

    all_chunks=[]
    seen_contents=set() # 用于去重，避免同一块被多次添加

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

    prompt = f"""/no_think
                You are an academic assistant helping international students understand lecture materials.
                Based on the following lecture content, generate a structured preview.
                Lecture content:
                {context}
                Return ONLY a valid JSON object with exactly this structure, no other text before or after:
                {{
                    "summary_de": "5 sentences summary in German",
                    "summary_zh": "5 sentences summary in Chinese",
                    "vocabulary": [
                    "Begriff1 (中文)",
                    "Begriff2 (中文)",
                    "Begriff3 (中文)",
                    "Begriff4 (中文)",
                    "Begriff5 (中文)",
                    "Begriff6 (中文)",
                    "Begriff7 (中文)",
                    "Begriff8 (中文)"
                    ]
                }}

                Rules:
                - Extract exactly 8 most important technical terms for vocabulary in both German and Chinese, and format them as "Term (Chinese translation)".
                - Return ONLY the JSON, no markdown, no explanation, no code blocks, no thinking""" 
    
    message = claude.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )

    raw_text = message.content[0].text.strip()
    # 清理可能的 markdown 代码块标记
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[-1]
    if raw_text.endswith("```"):
        raw_text = raw_text.rsplit("```", 1)[0]

    try:
        preview_data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse AI response as JSON: {e}\nRaw: {raw_text}")

    return {
        "filename": request.filename,
        "summary_de": preview_data.get("summary_de", ""),
        "summary_zh": preview_data.get("summary_zh", ""),
        "vocabulary": preview_data.get("vocabulary", [])
    }


class QuizRequest(BaseModel):
    filename: str
    num_questions: int = 5

@app.post("/quiz")
async def generate_quiz(request: QuizRequest):
    queries=[
             "What are the main concepts and definitions?",
             "What are the key technical terms and their applications?",
             "What are the important rules, principles or methods?"
    ]

    all_chunks=[]
    seen_contents=set() # 用于去重，避免同一块被多次添加

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

    prompt=f""" You are an learning assistant creating multiple choice questions for students.
                    Based on the following lecture content, generate exactly {request.num_questions} multiple choice questions in German.
                    Lecture content:{context}
                    Return ONLY a valid JSON object with exactly this structure:
                    {{
                        "questions": [
                         {{
                             "question": "Clear question based on the lecture content",
                                "options": {{
                                  "A": "first option",
                                  "B": "second option",
                                  "C": "third option",
                                  "D": "fourth option"
                               }},
                                "answer": "A",
                                "explanation": "Explanation in Chinese why this answer is correct"
                            }}
                        ]
                    }}
                    Rules:
                    - Generate exactly {request.num_questions} questions
                    - Each question must be based strictly on the lecture content
                    - Only one option is correct
                    - answer field must be exactly one of: A, B, C, D
                    - explanation must be in Chinese, 1-2 sentences
                    - options must cover plausible wrong answers, not obviously wrong
                    - Return ONLY the JSON, no markdown, no explanation, no code blocks, no thinking"""
        
    message = claude.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    raw_text = message.content[0].text.strip()

    # 清理可能的 markdown 代码块标记
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[-1]
    if raw_text.endswith("```"):
        raw_text = raw_text.rsplit("```", 1)[0]

    try:
        quiz_data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse AI response as JSON: {e}\nRaw: {raw_text}")
   
    questions=quiz_data.get("questions", [])
    if not questions:
            raise HTTPException(status_code=500, detail=f"No questions generated. Raw response: {raw_text}")
    return {
            "filename": request.filename,
            "questions": questions
    }
