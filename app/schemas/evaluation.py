from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from uuid import UUID

class EvaluationReportResponse(BaseModel):
    id: UUID
    session_id: UUID
    overall_score: float
    technical_score: float
    communication_score: float
    strengths: List[str]
    weaknesses: List[str]
    learning_plan: Dict[str, Any]
    recommendations: Optional[str] = None

    class Config:
        from_attributes = True

class QuestionBreakdown(BaseModel):
    question_text: str
    category: str
    difficulty: str
    transcript: str
    expected_keywords: List[str]
    scores: Dict[str, float]


class EvaluationSendRequest(BaseModel):
    event: str = Field(default="interview.completed")
    candidate: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = None
    scores: Dict[str, float] = Field(..., description="Overall, technical, communication, etc.")
    recommendation: str = Field(..., description="Recommendation summary or decision")
    roadmap: Dict[str, Any] = Field(..., description="Learning roadmap plan (short-term, long-term)")
    strengths: Optional[List[str]] = None
    weaknesses: Optional[List[str]] = None
    question_breakdown: Optional[List[QuestionBreakdown]] = None
