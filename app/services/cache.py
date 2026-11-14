import logging
from typing import Optional
from sqlalchemy.orm import Session
from app.models.cache import InterviewTemplateCache
from app.services.resume import compute_profile_fingerprint, skills_similarity, experience_bucket

logger = logging.getLogger("app.services.cache")

SIMILARITY_THRESHOLD = 0.65


def find_cached_questions(
    db: Session,
    job_role: str,
    experience_years: int,
    skills: list[str],
) -> tuple[Optional[list[dict]], bool, str]:
    """
    Look up cached interview questions for a similar resume profile.
    1. Exact fingerprint match
    2. Fuzzy match: same role + similar skills + same experience bucket
    Returns (questions, cache_hit, match_type).
    """
    fingerprint = compute_profile_fingerprint(job_role, experience_years, skills)

    exact = db.query(InterviewTemplateCache).filter(
        InterviewTemplateCache.fingerprint == fingerprint
    ).first()
    if exact:
        logger.info(f"Exact cache hit for fingerprint {fingerprint[:12]}...")
        return exact.questions, True, "exact"

    bucket = experience_bucket(experience_years)
    candidates = db.query(InterviewTemplateCache).filter(
        InterviewTemplateCache.job_role == job_role
    ).all()

    best_match = None
    best_score = 0.0
    for entry in candidates:
        entry_bucket = experience_bucket(
            int(entry.experience_level.replace(" years", "").replace("+", "") or "0")
        )
        if entry_bucket != bucket:
            continue
        score = skills_similarity(skills, entry.skills or [])
        if score >= SIMILARITY_THRESHOLD and score > best_score:
            best_score = score
            best_match = entry

    if best_match:
        logger.info(f"Similar cache hit ({best_score:.0%} skill overlap) — skipping Gemini.")
        return best_match.questions, True, f"similar ({best_score:.0%})"

    return None, False, "miss"
