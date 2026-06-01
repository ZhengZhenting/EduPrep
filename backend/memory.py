import json
import os
from datetime import datetime
import anthropic
from datetime import datetime, timezone
from dotenv import load_dotenv

from database import SessionLocal
from models import Memory, QuizProgress, PdfFile

load_dotenv() 
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ----------- Helper Functions -----------
# get pdf id
def _get_pdf_file_id(filename: str, course_id: int=1) -> int:
    db = SessionLocal()
    try:
        pdf_file = db.query(PdfFile).filter(
            PdfFile.filename == filename,
            PdfFile.course_id == course_id
        ).first()
        if not pdf_file:
            raise ValueError(f"PDF file not found in database: {filename}")
        return pdf_file.id
    finally:
        db.close()

# ----------- Learning Memory -----------
# Data Structure
def _default_memory() -> dict:
    """return default structure"""
    return {
        "weak_concepts": [],       
        "learning_style": "",      
        "history_summary": "",
        "last_compressed_at": 0
    }

# load / save memory
def load_memory(filename: str, course_id: int=1) -> dict:
    """read user memeory from a pdf, if empty return default structure"""
    db = SessionLocal()
    try:
        pdf_file_id = _get_pdf_file_id(filename, course_id)
        memory = db.query(Memory).filter(Memory.pdf_file_id == pdf_file_id).first()
        if not memory: 
            return _default_memory()
        return{
            "weak_concepts": memory.weak_concepts or [],
            "learning_style": memory.learning_style or "",
            "history_summary": memory.history_summary or "",
            "last_compressed_at": memory.last_compressed_at or 0
        }
    finally:
        db.close()

def save_memory(filename: str, memory_data: dict, course_id: int=1):
    """save memeory to JSON"""
    db = SessionLocal()
    try:
        pdf_file_id = _get_pdf_file_id(filename, course_id)
        memory_record = db.query(Memory).filter(Memory.pdf_file_id == pdf_file_id).first()

        if not memory_record:
            memory_record = Memory(
                pdf_file_id=pdf_file_id,
                weak_concepts=memory_data.get("weak_concepts", []),
                learning_style=memory_data.get("learning_style", ""),
                history_summary=memory_data.get("history_summary", ""),
                last_compressed_at=memory_data.get("last_compressed_at", 0)
            )
            db.add(memory_record)
        else:
            memory_record.weak_concepts = memory_data.get("weak_concepts", memory_record.weak_concepts)
            memory_record.learning_style = memory_data.get("learning_style", memory_record.learning_style)
            memory_record.history_summary = memory_data.get("history_summary", memory_record.history_summary)
            memory_record.last_compressed_at = memory_data.get("last_compressed_at", memory_record.last_compressed_at)
        db.commit()
    finally:
        db.close()


# Compress History
def should_compress(history: list, memory: dict) -> bool:
    """compress memory every 6 diaglogues"""
    count = len(history)
    if count == 0 or count % 6 != 0:
        return False
    
    last_compressed_at = memory.get("last_compressed_at", 0)
    return count > last_compressed_at

def compress_history(history: list, memory: dict) -> str:
    """compress hisotry"""
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
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}]
    )
    memory["last_compressed_at"] = len(history)
    return message.content[0].text.strip()

# Update Memory
def update_memory(filename: str, question: str, answer: str, memory: dict) -> dict:
    """after every dialogue update Claude with new learning information"""
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
            max_tokens=100,
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

# ----------- Quiz Memory -----------
def load_quiz_memory(filename: str, course_id: int=1) -> dict:
    db = SessionLocal()
    try:
        pdf_file_id = _get_pdf_file_id(filename, course_id)
        records = db.query(QuizProgress).filter(
            QuizProgress.pdf_file_id == pdf_file_id
        ).order_by(QuizProgress.created_at.desc()).limit(5).all()
        
        if not records:
            return {
                "quiz_history": [],
                "average_score": 0.0
            }
        
        quiz_history = [
            {
                "score": r.score,
                "total": r.total,  
                "percentage": r.percentage,
                "date": r.created_at.isoformat()
            }
            for r in records
        ]

        average_score = round(sum(r.percentage for r in records) / len(records), 2)
        return {
            "quiz_history": quiz_history,
            "average_score": average_score
        }
    finally:        
        db.close()


def save_quiz_memory(filename: str, score: int, total: int, wrong_questions: list = None, course_id: int=1):
    """save score after every Quiz"""
    db = SessionLocal()
    try:
        pdf_file_id = _get_pdf_file_id(filename, course_id)
        percentage = round(score / total, 2)
        record = QuizProgress(
            pdf_file_id=pdf_file_id,
            score=score,
            total=total,
            percentage=percentage,
            wrong_questions=wrong_questions or []
        )
        db.add(record)
        db.commit()
    finally:
        db.close()