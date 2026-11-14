import uuid
from datetime import datetime
# pyrefly: ignore [missing-import]
from sqlalchemy import String, Text, JSON, DateTime
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base_class import Base

class QuestionBank(Base):
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    question_text: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[str] = mapped_column(String(50))  # easy, medium, hard
    expected_keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    category: Mapped[str] = mapped_column(String(100))   # python, java, dbms, dsa, os, hr
    role: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
