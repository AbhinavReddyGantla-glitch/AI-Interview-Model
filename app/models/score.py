import uuid
from datetime import datetime
from sqlalchemy import String, Float, Text, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base_class import Base

class InterviewScore(Base):
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interview_session.id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(String(100))  # e.g. python, dsa, communication
    score: Mapped[float] = mapped_column(Float)
    feedback: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    session = relationship("InterviewSession", back_populates="scores")
