from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey, JSON, UniqueConstraint
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
    concepts = relationship("Concept", back_populates="course", cascade="all, delete-orphan")
    concept_edges = relationship("ConceptEdge", back_populates="course", cascade="all, delete-orphan")
    concept_masteries = relationship("ConceptMastery", back_populates="course", cascade="all, delete-orphan")
    learning_paths=relationship("LearningPath", back_populates="course", cascade="all, delete-orphan")


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

class Concept(Base):
    __tablename__ = "concept"

    id = Column(Integer, primary_key=True, autoincrement=True)
    course_id = Column(Integer, ForeignKey("course.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    attributes = Column(JSONB, default=dict)  # Store additional attributes as JSON
    embedding = Column(JSONB)  # Store embedding as JSON array，PostgreSQL 的一种数据类型，JSON 的二进制存储格式
    source_refs= Column(JSONB, default=list)  # Store source references as JSON array
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    #UniqueConstraint 在数据库层强制"某几列的组合不能重复"(复合唯一约束)
    __table_args__ = (UniqueConstraint("course_id", "name", name="uq_concept_course_name"),)

    #back_populates 把一段关系的"两头"绑在一起,让双向导航自动同步
    course = relationship("Course", back_populates="concepts")
    masteries = relationship("ConceptMastery", back_populates="concept", cascade="all, delete-orphan")

class ConceptEdge(Base):
    __tablename__ = "concept_edge"

    id = Column(Integer, primary_key=True, autoincrement=True)
    course_id = Column(Integer, ForeignKey("course.id", ondelete="CASCADE"), nullable=False)
    from_concept_id = Column(Integer, ForeignKey("concept.id", ondelete="CASCADE"), nullable=False)
    to_concept_id = Column(Integer, ForeignKey("concept.id", ondelete="CASCADE"), nullable=False)
    relation_type = Column(String(100), nullable=False)  # e.g., "prerequisite", "related_to"
    weight= Column(Float, default=1.0)  # Optional weight for the relationship
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("from_concept_id", "to_concept_id", "relation_type", name="uq_concept_edge"),
    )

    course = relationship("Course", back_populates="concept_edges")
    from_concept = relationship("Concept", foreign_keys=[from_concept_id])
    to_concept = relationship("Concept", foreign_keys=[to_concept_id])

class ConceptMastery(Base):
    __tablename__ = "concept_mastery"

    id = Column(Integer, primary_key=True, autoincrement=True)
    course_id = Column(Integer, ForeignKey("course.id", ondelete="CASCADE"), nullable=False)
    concept_id = Column(Integer, ForeignKey("concept.id", ondelete="CASCADE"), nullable=False)
    mastery_prob = Column(Float, default=0.0)  # 掌握概率 [0,1]，BKT 更新
    last_review = Column(DateTime)
    next_review = Column(DateTime) 
    fsrs_state= Column(JSONB) 
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint("concept_id", "course_id", name="uq_concept_mastery"),)

    course = relationship("Course", back_populates="concept_masteries")
    concept = relationship("Concept", back_populates="masteries")

class LearningPath(Base):
    __tablename__ = "learning_path"

    id = Column(Integer, primary_key=True, autoincrement=True)
    course_id = Column(Integer, ForeignKey("course.id", ondelete="CASCADE"), nullable=False)
    ordered_concept_ids = Column(JSONB, default=list)  # Store ordered concept IDs as JSON array 拓扑排序后的概念 id 列表
    generated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    course = relationship("Course", back_populates="learning_paths")