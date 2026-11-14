import logging
from fastapi import APIRouter, Header, HTTPException
from app.schemas.evaluation import EvaluationSendRequest
from app.core.config import settings

logger = logging.getLogger("app.api.evaluation")

router = APIRouter()


@router.post("/evaluation")
def receive_evaluation(
    request: EvaluationSendRequest,
    x_webhook_secret: str | None = Header(default=None),
):
    """
    **Coaching Team Webhook** — Receives evaluation results after an interview completes.
    The improvement team uses this data to guide the candidate on skill development.

    Configure EXTERNAL_EVALUATION_URL to point to this endpoint on the coaching team's server.
    """
    if settings.EXTERNAL_WEBHOOK_SECRET:
        if not x_webhook_secret or x_webhook_secret != settings.EXTERNAL_WEBHOOK_SECRET:
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

    logger.info("Coaching team webhook received evaluation payload")
    logger.info(f"Event: {request.event}")
    if request.candidate:
        logger.info(f"Candidate: {request.candidate.get('name')} ({request.candidate.get('email')})")
    logger.info(f"Scores: {request.scores}")
    logger.info(f"Recommendation: {request.recommendation}")
    logger.info(f"Roadmap: {request.roadmap}")
    if request.strengths:
        logger.info(f"Strengths: {request.strengths}")
    if request.weaknesses:
        logger.info(f"Weaknesses: {request.weaknesses}")
    if request.question_breakdown:
        logger.info(f"Question breakdown: {len(request.question_breakdown)} questions")

    return {
        "status": "success",
        "message": "Evaluation received. Coaching team can now prepare personalized skill improvement guidance.",
        "received": {
            "event": request.event,
            "session_id": request.session_id,
            "candidate_email": request.candidate.get("email") if request.candidate else None,
            "overall_score": request.scores.get("overall_score"),
        },
    }
