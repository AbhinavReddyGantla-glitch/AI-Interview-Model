from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
from uuid import UUID
from datetime import datetime


class ResumeIngestRequest(BaseModel):
    """Structured resume payload from the external recruitment team."""
    name: str = Field(..., max_length=255)
    email: EmailStr
    job_role: str = Field(default="Software Engineer", max_length=255)
    experience_years: Optional[int] = Field(default=None, ge=0)
    skills: Optional[List[str]] = Field(default=None)
    resume_summary: Optional[str] = Field(default=None, description="Plain-text resume or bio")
    resume_text: Optional[str] = Field(default=None, description="Full resume text for auto-parsing")
    external_id: Optional[str] = Field(default=None, description="ID from the upstream system")


class ResumeIngestResponse(BaseModel):
    candidate_id: UUID
    name: str
    email: str
    job_role: str
    skills: List[str]
    experience_years: int
    resume_summary: Optional[str]
    external_id: Optional[str]
    interview_url: str
    message: str


class CandidateProfileResponse(BaseModel):
    id: UUID
    name: str
    email: str
    job_role: str
    skills: List[str]
    experience_years: int
    resume_summary: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class ResumeUploadResponse(BaseModel):
    resume_id: UUID
    filename: str
    extracted_chars: int
    status: str
    parsed_fields: dict
    candidate_id: Optional[UUID] = None
    message: Optional[str] = None
