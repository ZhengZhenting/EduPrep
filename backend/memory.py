import json
import os
from datetime import datetime
import anthropic
from dotenv import load_dotenv


MEMORY_DIR = "./memory_store"
os.makedirs(MEMORY_DIR, exist_ok=True)  # 启动时自动创建目录

load_dotenv() 
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ─────────────────────────────────────────────
# Learning Memory
# ─────────────────────────────────────────────
# Data Structure
def _default_memory() -> dict:
    """返回空记忆的默认结构"""
    return {
        "weak_concepts": [],       
        "learning_style": "",      
        "history_summary": "",
        "last_compressed_at": 0,
        "last_updated": ""
    }

# load / save
def load_memory(filename: str) -> dict:
    """读取某个PDF对应的用户记忆，文件不存在则返回默认结构"""
    path = _memory_path(filename)
    if not os.path.exists(path):
        return _default_memory()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return _default_memory()

def save_memory(filename: str, memory: dict):
    """保存记忆到 JSON 文件"""
    memory["last_updated"] = datetime.now().isoformat()
    path = _memory_path(filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)

def _memory_path(filename: str) -> str:
    """把文件名转成合法的存储路径"""
    safe_name = filename.replace(".", "_").replace(" ", "_")
    return os.path.join(MEMORY_DIR, f"{safe_name}_memory.json")

# Compress History
def should_compress(history: list, memory: dict) -> bool:
    """
    只在以下两个条件同时满足时才压缩：
    1. 对话历史达到6的倍数
    2. 当前这批历史还没有被压缩过
    """
    count = len(history)
    if count == 0 or count % 6 != 0:
        return False
    
    last_compressed_at = memory.get("last_compressed_at", 0)
    return count > last_compressed_at

def compress_history(history: list, memory: dict) -> str:
    """把对话历史压缩成一段摘要，返回摘要字符串"""
    history_text = ""
    for msg in history:
        role_label = "Student" if msg.role == "user" else "Assistant"
        history_text += f"{role_label}: {msg.content}\n"
    prompt = f"""Compress the folowing conversation history into a concise summary in Chinese (200 characters or less).
            Only keep key information: what topics were discussed, what concepts the student was confused about, what
            History：{history_text}
            Output format: Directly output the summary text, without any title or prefix."""   
    message = claude.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=250,
        messages=[{"role": "user", "content": prompt}]
    )
    memory["last_compressed_at"] = len(history)
    return message.content[0].text.strip()

# Update Memory
def update_memory(filename: str, question: str, answer: str, memory: dict) -> dict:
    """每次对话结束后，让 Claude 提取新的学习信息更新记忆"""
    prompt = f"""Retrieve information from the following student question and assistant answer.

        Student Question: {question}
        Assistant Answer: {answer}

        Current Known Information:
        - weak_concepts: {memory.get('weak_concepts', [])}
        - learning_style: {memory.get('learning_style', 'unknown')}

        Output JSON, structure as follows:
        {{
        "weak_concepts": ["Concept1", "Concept2"],
        "learning_style": examples, principles, or unknown
        }}
        Rules:
        - weak_concepts: if the student's question indicates confusion about a particular concept, add it to the list; keep at most 5 concepts, remove duplicates
        - learning_style: according to the student's question, determine if they prefer examples, principles, or unknown
-       only output JSON, no explanations, no markdown, no extra text."""
    
    try:
        message = claude.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=250,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = message.content[0].text.strip()

        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]

        new_info = json.loads(raw)
        memory["weak_concepts"] = new_info.get("weak_concepts", memory["weak_concepts"])
        memory["learning_style"] = new_info.get("learning_style", memory["learning_style"])

    except Exception as e:
        print(f"Update memory failed: {e}")

    return memory

# ─────────────────────────────────────────────
# Quiz Memory
# ─────────────────────────────────────────────
def _quiz_memory_path(filename: str) -> str:
    safe_name = filename.replace(".", "_").replace(" ", "_")
    return os.path.join(MEMORY_DIR, f"{safe_name}_quiz_memory.json")


def load_quiz_memory(filename: str) -> dict:
    path = _quiz_memory_path(filename)
    if not os.path.exists(path):
        return {"quiz_history": [], "average_score": 0.0}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"quiz_history": [], "average_score": 0.0}


def save_quiz_memory(filename: str, score: int, total: int):
    """每次 Quiz 完成后调用，保存得分"""
    memory = load_quiz_memory(filename)

    memory["quiz_history"].append({
        "score": score,
        "total": total,
        "percentage": round(score / total, 2),
        "date": datetime.now().isoformat()
    })

    # save recent 5 records
    memory["quiz_history"] = memory["quiz_history"][-5:]

    # update average score
    if memory["quiz_history"]:
        memory["average_score"] = round(
            sum(r["percentage"] for r in memory["quiz_history"]) / len(memory["quiz_history"]), 2
        )

    path = _quiz_memory_path(filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)