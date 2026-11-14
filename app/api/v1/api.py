from fastapi import APIRouter
from app.api.v1.endpoints import interview, chatbot, evaluation, candidates

api_router = APIRouter()

api_router.include_router(candidates.router, prefix="/candidates", tags=["Resume Ingestion (External Team)"])
api_router.include_router(interview.router, prefix="/interview", tags=["Interview Flow"])
api_router.include_router(chatbot.router, prefix="/chatbot", tags=["Assistant/Chatbot"])
api_router.include_router(evaluation.router, prefix="", tags=["Coaching Team Webhook"])
