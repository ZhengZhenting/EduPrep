from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import PyPDF2
import io
import httpx


# 创建FastAPI应用,测试接口: http://localhost:8000/docs, uvicorn running on: http://127.0.0.1:8000
app = FastAPI()

# 允许前端跨域访问（前后端分离时必须配置）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 临时用内存存储PDF文字的空字典（dict {"a": 1}）（后续接入vector db）
pdf_text_store = {} 

@app.get("/")
def root():
    return {"message": "EduPrep backend is running!"}


# 接口：上传PDF并提取文字 
@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    # 1. 读取上传的文件内容（二进制）,使用PyPDF2提取PDF文本，逐页提取文字
    content = await file.read()
    pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))

    full_text = ""
    for page_num, page in enumerate(pdf_reader.pages):
        text = page.extract_text()
        if text:
            full_text += f"--- Page {page_num + 1} ---\n" 
            full_text += text


    # 3. 存储提取的文本（这里用内存字典，后续接入vector db）
    pdf_text_store[file.filename] = full_text

    # 4. 返回提取的文本
    return {
        "message": "PDF uploaded and text extracted successfully!",
        "filename": file.filename, 
        "pages": len(pdf_reader.pages),
        "preview": full_text[:500]  # 返回前500字符作为预览
    }


# 查看已上传的PDF列表
@app.get("/pdfs")
def list_pdfs():
    return {
        "pdf files": list(pdf_text_store.keys())
    }



class QueryRequest(BaseModel):
    filename: str
    question: str


@app.post("/ask")
async def ask_question(request: QueryRequest):
    # 1. 从内存字典获取PDF文本
    pdf_text = pdf_text_store.get(request.filename)
    if not pdf_text:
        return {"error": f"PDF file '{request.filename}' not found. Please upload it first."}
    
    # 2. 构造发给AI的Prompt
    prompt = f"""You are an assistant that helps answer questions based on the content of a PDF document. 
            The content of the PDF is as follows:{pdf_text[:4000]} 
            please answer the following question based on the above content: {request.question}
            if it's not in the content, say "Sorry, I don't know the answer to that question based on the provided PDF."""
    
    # 3. 调用AI接口
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "qwen2.5:3b",
                "prompt": prompt,
                "stream": False
            }
        )

    # 4. 解析并返回回答
        result = response.json()
        return{
            "question": request.question,
            "answer": result["response"]
        }
