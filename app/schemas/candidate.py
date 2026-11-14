from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from uuid import UUID

class CandidateBase(BaseModel):
    name: str = Field(..., max_length=255)
    email: str = Field(..., description="Email address of the candidate")
    resume_summary: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    experience_years: int = Field(default=0, ge=0)
    job_role: str = Field(..., max_length=255)

class CandidateCreate(CandidateBase):
    pass

class CandidateResponse(CandidateBase):
    id: UUID
    created_at: datetime

    class Config:
        from_attributes = True
