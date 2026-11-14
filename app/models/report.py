import uuid
from datetime import datetime
from sqlalchemy import Float, Text, ForeignKey, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base_class import Base

class EvaluationReport(Base):
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interview_session.id", ondelete="CASCADE"))
    overall_score: Mapped[float] = mapped_column(Float)
    technical_score: Mapped[float] = mapped_column(Float)
    communication_score: Mapped[float] = mapped_column(Float)
    strengths: Mapped[list[str]] = mapped_column(JSON, default=list)
    weaknesses: Mapped[list[str]] = mapped_column(JSON, default=list)
    learning_plan: Mapped[dict] = mapped_column(JSON, default=dict)
    recommendations: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    session = relationship("InterviewSession", back_populates="reports")
