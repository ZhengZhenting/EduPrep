from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import PyPDF2
import io
import httpx

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
    
    content = await file.read() # 读取上传的文件内容  
   
    chunks=process_pdf(content, file.filename)   # 调用pdf_processor.py中的函数，返回切好的文本块列表

    store_chunks(chunks, file.filename)  # 存入ChromaDB

    # 返回提取的文本
    return {
        "message": "PDF uploaded and text extracted successfully!",
        "filename": file.filename, 
        "chunks": len(chunks)
    }



# 问答接口：RAG检索 → 组装Prompt → LLM回答
class QuestionRequest(BaseModel):
    filename: str
    question: str

@app.post("/ask")
async def ask_question(request: QuestionRequest):
    # 1. 从ChromaDB检索最相关的5个块
    relevant_chunks = search_chunks(request.question, request.filename, k=5)
    if not relevant_chunks:
        return {"error": "Relevant chunks not found. Please upload the PDF first."}
    
    # 2. 把检索到的块组装成上下文,同时收集页码信息
    context_parts=[]
    pages_used=set()  # 用set收集页码，避免重复，后续可以把用到的页码也返回给前端，提示用户答案来源于PDF的哪些页
    for chunk in relevant_chunks:
        context_parts.append(chunk.page_content) # page_content是LangChain文档对象的属性
        page_num=chunk.metadata.get("page",0)+1  # 页码从0开始，所以+1
        pages_used.add(page_num)

    context = "\n\n---\n\n".join(context_parts) # 用分隔符连接多个块，保持一定的格式，方便AI理解

    # 3. 构造发给AI的Prompt
    prompt = f"""You are an assistant that helps answer questions based on the content of a PDF document. 
            Here are the relevant chunks:{context} 
            please answer the following question based on the above content: {request.question}
            if it's not in the content, say "Sorry, I don't know the answer to that question based on the provided PDF."""
    
    # 3. 调用AI接口
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "qwen3:4b",
                "prompt": prompt,
                "stream": False
            }
        )

    # 4. 解析并返回回答
        result = response.json()
        return{
            "question": request.question,
            "answer": result["response"],
            "sources": sorted(pages_used)  # 返回用到的页码列表，提示用户答案来源于PDF的哪些页
        }
