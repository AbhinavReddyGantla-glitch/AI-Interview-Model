import uuid
from datetime import datetime
from sqlalchemy import String, Text, Integer, JSON, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base_class import Base

class Candidate(Base):
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    resume_summary: Mapped[str] = mapped_column(Text, nullable=True)
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    experience_years: Mapped[int] = mapped_column(Integer, default=0)
    job_role: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    sessions = relationship("InterviewSession", back_populates="candidate", cascade="all, delete-orphan")
    resumes = relationship("Resume", back_populates="candidate", cascade="all, delete-orphan")
