from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from database import Base


class User(Base):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(200), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # user - course relationship
    courses = relationship("Course", back_populates="user", cascade="all, delete-orphan")


class Course(Base):
    __tablename__ = "course"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="courses")
    pdf_files = relationship("PdfFile", back_populates="course", cascade="all, delete-orphan")


class PdfFile(Base):
    __tablename__ = "pdf_file"

    id = Column(Integer, primary_key=True, autoincrement=True)
    course_id = Column(Integer, ForeignKey("course.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(255), nullable=False)
    chunk_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    course = relationship("Course", back_populates="pdf_files")
    messages = relationship("Message", back_populates="pdf_file", cascade="all, delete-orphan")
    notes = relationship("Note", back_populates="pdf_file", cascade="all, delete-orphan")
    memory = relationship("Memory", back_populates="pdf_file", uselist=False, cascade="all, delete-orphan")
    quiz_progress = relationship("QuizProgress", back_populates="pdf_file", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "message"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pdf_file_id = Column(Integer, ForeignKey("pdf_file.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False)         # user / assistant
    content = Column(Text, nullable=False)
    source_type = Column(String(20))                  # pdf / web
    sources = Column(JSONB)                            # 页码列表或URL列表
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    pdf_file = relationship("PdfFile", back_populates="messages")


class Note(Base):
    __tablename__ = "note"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pdf_file_id = Column(Integer, ForeignKey("pdf_file.id", ondelete="CASCADE"), nullable=False)
    type = Column(String(30), nullable=False)         # summary / answer / quiz_explanation
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    pdf_file = relationship("PdfFile", back_populates="notes")


class Memory(Base):
    __tablename__ = "memory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pdf_file_id = Column(Integer, ForeignKey("pdf_file.id", ondelete="CASCADE"), nullable=False, unique=True)
    weak_concepts = Column(JSONB, default=list)
    learning_style = Column(String(50), default="")
    history_summary = Column(Text, default="")
    last_compressed_at = Column(Integer, default=0)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    pdf_file = relationship("PdfFile", back_populates="memory")


class QuizProgress(Base):
    __tablename__ = "quiz_progress"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pdf_file_id = Column(Integer, ForeignKey("pdf_file.id", ondelete="CASCADE"), nullable=False)
    score = Column(Integer, nullable=False)
    total = Column(Integer, nullable=False)
    percentage = Column(Float, nullable=False)
    wrong_questions = Column(JSONB, default=list)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    pdf_file = relationship("PdfFile", back_populates="quiz_progress")