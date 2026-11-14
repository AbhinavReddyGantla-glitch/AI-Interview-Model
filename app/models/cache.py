import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base_class import Base

class InterviewTemplateCache(Base):
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    fingerprint: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    job_role: Mapped[str] = mapped_column(String(255))
    experience_level: Mapped[str] = mapped_column(String(100))
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    questions: Mapped[list[dict]] = mapped_column(JSON, default=list)  # stores structured generated questions
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
