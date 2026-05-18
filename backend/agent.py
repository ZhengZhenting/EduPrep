import httpx
import json
import re

# ！！！This file is not used for now ！！！

MODEL="qwen2.5:3b"

async def classify_intent(question:str, rag_chunks:list)->dict:
    """
    让LLM判断RAG检索到的内容能不能回答这个问题
    
    返回：
    {
        "use_pdf": True/False,
        "reason": "判断原因"
    }
    """

    if not rag_chunks:
        return{"use_pdf": False, "reason": "No chunks retrieved"}
    
    context_preview = "\n\n".join([
        f"[Chunk{i+1}]: {chunk.page_content[:500]}"  # 每块只取前500字，节省token
        for i, chunk in enumerate(rag_chunks[:5])
    ])
    for i, chunk in enumerate(rag_chunks[:3]):
        print(f"块{i+1}：{chunk.page_content[:200]}")

    prompt = f"""You are a relevance checker. Your only job is to decide if the provided text chunks can answer the question.
        Question: {question}
        Context Preview:{context_preview}
        Can these chunks answer the question?
        - Answer YES if ANY of these conditions are true：
            1) The chunks directly explain the concept asked about
            2) The chunks contain definitions, examples or descriptions related to the question
            3) The chunks partially answer the question (even if not perfectly)
        - Answer NO only if ALL of these conditions are true:
            1) The chunks are completely unrelated to the question
            2) The question asks about something outside the lecture scope
            3) The question requires real-time or external information (news, prices, current events)

        Reply with ONLY a JSON object:
        {{"decision": "YES", "reason": "brief reason"}}
        or
        {{"decision": "NO", "reason": "brief reason"}}

        No other text."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                 "http://localhost:11434/api/generate",
                 json={
                    "model": MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "think":False,
                    "options": {
                        "temperature": 0.1,  # 极低温度，让判断更稳定
                        "num_ctx": 2048      # 判断任务不需要太长上下文
                    }
                 }
            )

        result = response.json()
        raw_text = result["response"].strip()
        print(f"Agent原始返回：{raw_text}")

        decision_data = json.loads(raw_text)
        decision = decision_data.get("decision", "NO").upper()
        reason = decision_data.get("reason", "")

        print(f"Agent Decision：{decision} | Reason：{reason}")

        return {"use_pdf": decision == "YES", "reason": reason}
    
    except Exception as e:
        print(f"Error, use PDF content as default: {e}")
        return {"use_pdf": True, "reason": "Fallback due to error"}