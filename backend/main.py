from fastapi import FastAPI, UploadFile, File,  HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import httpx
import json

from pdf_processor import process_pdf
from rag import store_chunks, search_chunks


# 创建FastAPI应用,测试接口: http://localhost:8000/docs, uvicorn running on: http://127.0.0.1:8000
app = FastAPI()

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
    sources: Optional[List[int]] = []


# 问答接口：RAG检索 → 组装Prompt → LLM回答
class QuestionRequest(BaseModel):
    filename: str
    question: str
    history: Optional[List[Message]] = []  


@app.post("/ask")
async def ask_question(request: QuestionRequest):
    # 从ChromaDB检索最相关的5个块
    relevant_chunks = search_chunks(request.question, request.filename, k=5)
    if not relevant_chunks:
        raise HTTPException(status_code=404, detail="Relevant chunks not found. Please upload the PDF first.")
    

    # 把检索到的块组装成上下文,同时收集页码信息
    context_parts=[]
    pages_used=set()  
    
    for chunk in relevant_chunks:
        context_parts.append(chunk.page_content) # page_content是LangChain文档对象的属性
        page_num=chunk.metadata.get("page",0)+1  # 页码从0开始，所以+1
        pages_used.add(page_num)

    context = "\n\n---\n\n".join(context_parts)
    sources = sorted(list(pages_used))

    history_text=""
    for msg in request.history[-6:]:  # 只保留最近6条对话历史
        role_label="Student" if msg.role=="user" else "Assistant"
        if msg.role == "assistant" and msg.sources:
            sources_label = f"(Source from Pages： {', '.join(str(p) for p in msg.sources)} )"
            history_text += f"{role_label}{sources_label}: {msg.content}\n"
        else:
            history_text += f"{role_label}: {msg.content}\n"

    prompt = f"""You are an learning assistant that helps answer questions based on the content of a PDF document. 
            Here are the relevant chunks:{context} 
            {'Here are the recent conversation history:'+history_text if history_text else ''}
            please answer the following question in Chinese based on the above content: {request.question}
            if it's not in the content, say "Sorry, I don't know the answer to that question based on the provided PDF."""
    
    sources_line = json.dumps({"sources": sources})  + "\n"  # 将页码列表转换为JSON字符串

    async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "qwen2.5:3b",
                "prompt": prompt,
                "stream": False,
                "think": False 
            }
        )
    result = response.json()
        
    return {
        "question": request.question,
        "answer": result["response"],
        "sources": sources
    }


class PreviewRequest(BaseModel):
    filename: str

@app.post("/preview")
async def generate_preview(request: PreviewRequest):
    queries = [
        "What is the main topic of this lecture?",
        "What are the key technical terms and their definitions?",
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
    context = context[:3000]  # 限制上下文长度，避免超过模型输入限制

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
                    "Begriff8 (中文)",
                    "Begriff9 (中文)",
                    "Begriff10 (中文)"
                    ]
                }}

                Rules:
                - Extract exactly 10 most important technical terms for vocabulary in both German and Chinese, and format them as "Term (Chinese translation)".
                - Return ONLY the JSON, no markdown, no explanation, no code blocks, no thinking""" 
    
    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(
        "http://localhost:11434/api/generate",
        json={
            "model": "qwen2.5:3b",
            "prompt": prompt,
            "stream": False,
            "think": False,
            "options": {
                "num_ctx": 4096,
                "temperature": 0.3
            }
        }
        )

    result = response.json()

    try:
        preview_data = json.loads(result)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse AI response as JSON: {e}\nRaw response: {result}")

    return {
        "filename": request.filename,
        "summary_de": preview_data.get("summary_de", ""),
        "summary_zh": preview_data.get("summary_zh", ""),
        "vocabulary": preview_data.get("vocabulary", [])
    }