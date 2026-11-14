import uuid
from datetime import datetime
from sqlalchemy import String, Text, Integer, JSON, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base_class import Base


class Resume(Base):
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidate.id", ondelete="CASCADE"), nullable=True, index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(500))
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    mime_type: Mapped[str] = mapped_column(String(100), default="application/octet-stream")
    extracted_text: Mapped[str] = mapped_column(Text, nullable=True)
    extracted_chars: Mapped[int] = mapped_column(Integer, default=0)
    parsed_fields: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(50), default="ready", index=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    candidate = relationship("Candidate", back_populates="resumes")

