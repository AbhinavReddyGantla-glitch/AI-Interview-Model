from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import UUID

class InterviewStartRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    email: Optional[str] = Field(default=None)
    candidate_id: Optional[UUID] = Field(default=None, description="Use when resume was pre-ingested by external team")
    resume_summary: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    experience_years: int = Field(default=0, ge=0)
    job_role: Optional[str] = Field(default=None, max_length=255)

class InterviewStartResponse(BaseModel):
    session_id: UUID
    candidate_id: UUID
    status: str
    reused_from_cache: bool
    total_questions: int = Field(default=12)
    min_duration_seconds: int = Field(default=300)
    max_duration_seconds: int = Field(default=600)

class QuestionResponse(BaseModel):
    question_id: UUID
    question_text: str
    difficulty: str
    category: str
    order: int
    total_questions: int = Field(default=12)
    elapsed_seconds: int = Field(default=0)
    min_duration_seconds: int = Field(default=300)
    max_duration_seconds: int = Field(default=600)
    bonus_seconds_added: int = Field(default=0)
    is_extended: bool = Field(default=False)

class AnswerSubmitResponse(BaseModel):
    answer_id: UUID
    session_id: UUID
    question_id: UUID
    transcript: str
    speaking_time_seconds: Optional[float] = None
    keyword_score: float
    completeness_score: float
    similarity_score: float
    overall_score: float
    should_submit: bool = Field(default=False, description="True when interview should finalize")
    elapsed_seconds: int = Field(default=0)
    answered_questions: int = Field(default=0)
    total_questions: int = Field(default=12)
    min_duration_seconds: int = Field(default=300)
    max_duration_seconds: int = Field(default=600)
    bonus_seconds_added: int = Field(default=0)
    is_extended: bool = Field(default=False)
    end_reason: Optional[str] = None
    proctoring_debug_events: Optional[List[dict]] = None
    raw_transcript: Optional[str] = None
    word_confidences: Optional[List[dict]] = None
    transcript_changes: Optional[List[dict]] = None

class SessionStatusResponse(BaseModel):
    session_id: UUID
    candidate_id: UUID
    status: str
    total_questions: int
    answered_questions: int
    is_complete: bool


class CandidateAnswerItem(BaseModel):
    question_id: UUID
    question_text: str
    order: int
    category: str
    difficulty: str
    transcript: Optional[str] = None
    speaking_time_seconds: Optional[float] = None
    overall_score: Optional[float] = None


class SessionStateResponse(BaseModel):
    session_id: UUID
    candidate_id: UUID
    candidate: dict
    status: str
    created_at: str
    total_questions: int
    answered_questions: int
    current_question: Optional[QuestionResponse] = None
    answers: List[CandidateAnswerItem] = Field(default_factory=list)
    elapsed_seconds: int = Field(default=0)
    min_duration_seconds: int = Field(default=300)
    max_duration_seconds: int = Field(default=600)
    bonus_seconds_added: int = Field(default=0)
    is_extended: bool = Field(default=False)
    is_complete: bool = Field(default=False)
    report: Optional[dict] = None

