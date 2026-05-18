from fastapi import FastAPI, UploadFile, File,  HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from tavily import TavilyClient
from dotenv import load_dotenv #读取环境变量
from langchain_ollama import ChatOllama
from langchain_classic.agents import create_react_agent, AgentExecutor  #创建ReAct格式的Agent,运行Agent
from langchain_core.prompts import PromptTemplate
import os
import httpx
import json

from pdf_processor import process_pdf
from rag import store_chunks, search_chunks, search_chunks_with_score
from tools import ALL_TOOLS


# 创建FastAPI应用,测试接口: http://localhost:8000/docs, uvicorn running on: http://127.0.0.1:8000
app = FastAPI()

load_dotenv()  # 加载环境变量
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
OLLAMA_URL = os.getenv("OLLAMA_URL")

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
    # 从ChromaDB检索最相关的5个块
    results_with_score = search_chunks_with_score(request.question, request.filename, k=5)
    if not results_with_score:
        raise HTTPException(status_code=404, detail=
                            "Relevant chunks not found. Please upload the PDF first.")
    
    best_score=min(score for _, score in results_with_score)
    print(f"RAG最佳相关性分数: {best_score}")
    SCORE_THRESHOLD = 1.15  # 分数阈值：低于1.15说明PDF里有相关内容

    # 对话历史
    history_text=""
    for msg in request.history[-6:]:  # 只保留最近6条
        role_label="Student" if msg.role=="user" else "Assistant"
        if msg.role == "assistant" and msg.sources:
            history_text += f"{role_label}(from{msg.source_type}): {msg.content}\n"
        else:
            history_text += f"{role_label}: {msg.content}\n"   


    if best_score < SCORE_THRESHOLD: #pdf相关内容足够好，使用PDF内容回答
        print(f"RAG分数{best_score}没有超过阈值，使用PDF内容回答") 

        context_parts=[]  
        pages_used=set()  
    
        for chunk,score in results_with_score: 
            context_parts.append(chunk.page_content) # page_content是LangChain文档对象的属性 
            page_num=chunk.metadata.get("page",0)+1  # 页码从0开始，所以+1 
            pages_used.add(page_num) 

        context = "\n\n---\n\n".join(context_parts) 
        source_type="pdf" 
        sources = sorted(list(pages_used)) 

        prompt = f"""You are an learning assistant that helps answer questions based on the content of a PDF document. 
            {source_type}{context}
            {'Here are the recent conversation history:'+history_text if history_text else ''}
            please answer the following question in Chinese based on the above content: {request.question}"""
    

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
            OLLAMA_URL,
            json={
                "model": "qwen2.5:3b",
                "prompt": prompt,
                "stream": False,
                "think": False 
            }
            )
        answer = response.json()["response"]

    else: #pdf相关内容不够好，使用网络搜索回答
        print(f"RAG分数{best_score}超过阈值，使用网络搜索回答")
        try: 
            tavily_client=TavilyClient(api_key=TAVILY_API_KEY) 
            search_result=tavily_client.search( 
                request.question, 
                max_results=3, 
                search_depth="basic"  
            )
            web_contents=[] 
            web_sources=[] 
            for r in search_result["results"]: 
                web_contents.append(r["content"]) 
                web_sources.append(r["url"])  

        except Exception as e: 
            raise HTTPException(status_code=500, detail=f"网络搜索失败：{e}") 
        
        context = "\n\n---\n\n".join(web_contents) 
        source_type="web" 
        sources = web_sources

        react_prompt=PromptTemplate.from_template(
             """Answer the following questions as best you can. You have access to the following tools: {tools}
                Use the following format strictly:
                Question: the input question you must answer
                Thought: you should always think about what to do
                Action: the action to take, should be one of [{tool_names}]
                Action Input: the input to the action
                Observation: the result of the action
                ... (Thought/Action/Action Input/Observation can repeat at most 2 more times)
                Thought: I now know the final answer
                Final Answer: the final answer to the original input question

                Begin!
                Question: {input}
                Thought: {agent_scratchpad}""")
        
        llm = ChatOllama(model="qwen2.5:7b", temperature=0.1)
        agent = create_react_agent(llm, ALL_TOOLS, react_prompt)
        agent_executor = AgentExecutor(
            agent=agent, 
            tools=ALL_TOOLS, 
            max_iterations=3,
            handle_parsing_errors=True,
            verbose=True)
        
        agent_input=f"""You are an educational assistant helping international students understand lecture materials.

            The following content is retrieved from web search (PDF did not contain relevant information):{context}

            {'Conversation history:\n' + history_text if history_text else ''}

            Student question: {request.question}

            Instructions:
            - Answer in Chinese
            - Organize the web content into a clear, fluent response
            - Use generate_mermaid_chart ONLY if the question explicitly involves a process flow or system architecture
            - Use render_math_formula ONLY if the question involves mathematical equations
            - Use highlight_code ONLY if the question involves programming code
            - Use AT MOST 1 tool, and ONLY when it genuinely improves understanding
            - Most questions do NOT need tools — default to a well-written Chinese text answer"""
             
        result = await agent_executor.ainvoke({"input": agent_input})
        answer=result.get("output","")

    
        
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
        OLLAMA_URL,
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

    result = response.json() # 返回的是Ollama整个API响应的Python字典
    raw_text = result["response"].strip() # 取出AI生成的JSON格式文本并去除首尾空白

    try:
        preview_data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse AI response as JSON: {e}\nRaw response: {raw_text}")

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
    context = context[:4000]  

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
        
    async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                OLLAMA_URL,
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
    raw_text = result["response"].strip()

    try:
            quiz_data = json.loads(raw_text)
    except json.JSONDecodeError as e:
            raise HTTPException(status_code=500, detail=f"Failed to parse AI response as JSON: {e}\nRaw response: {raw_text}")
        
    questions=quiz_data.get("questions", [])
    if not questions:
            raise HTTPException(status_code=500, detail=f"No questions generated. Raw response: {raw_text}")
    return {
            "filename": request.filename,
            "questions": questions
    }
