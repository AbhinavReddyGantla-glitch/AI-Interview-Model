import uuid
from datetime import datetime
from sqlalchemy import Text, Float, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base_class import Base

class CandidateAnswer(Base):
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interview_session.id", ondelete="CASCADE"))
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("question_bank.id", ondelete="CASCADE"))
    audio_url: Mapped[str] = mapped_column(String(1024), nullable=True)
    transcript: Mapped[str] = mapped_column(Text, nullable=True)
    
    # Evaluation Metrics (used starting Phase 7/8)
    speaking_time_seconds: Mapped[float] = mapped_column(Float, nullable=True)
    eye_contact_score: Mapped[float] = mapped_column(Float, nullable=True)
    attention_score: Mapped[float] = mapped_column(Float, nullable=True)
    completeness_score: Mapped[float] = mapped_column(Float, nullable=True)
    similarity_score: Mapped[float] = mapped_column(Float, nullable=True)
    keyword_score: Mapped[float] = mapped_column(Float, nullable=True)
    overall_score: Mapped[float] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    session = relationship("InterviewSession", back_populates="answers")
    question = relationship("QuestionBank")
