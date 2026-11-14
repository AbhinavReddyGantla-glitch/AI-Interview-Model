import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base_class import Base

class SessionQuestion(Base):
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interview_session.id", ondelete="CASCADE"))
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("question_bank.id", ondelete="CASCADE"))
    order: Mapped[int] = mapped_column(Integer)
    is_answered: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    question = relationship("QuestionBank")

class InterviewSession(Base):
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidate.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(50), default="started")  # started, completed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    candidate = relationship("Candidate", back_populates="sessions")
    session_questions = relationship("SessionQuestion", cascade="all, delete-orphan", order_by="SessionQuestion.order")
    answers = relationship("CandidateAnswer", back_populates="session", cascade="all, delete-orphan")
    scores = relationship("InterviewScore", back_populates="session", cascade="all, delete-orphan")
    reports = relationship("EvaluationReport", back_populates="session", cascade="all, delete-orphan")
