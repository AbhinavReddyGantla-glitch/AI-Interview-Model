"""Interview duration logic — dynamic time extensions based on candidate performance depth."""
from datetime import datetime
from typing import Any, Tuple

BASE_MIN_DURATION_SEC = 300   # 5 minutes base min
BASE_MAX_DURATION_SEC = 600   # 10 minutes base max
MAX_ALLOWED_DURATION_SEC = 900 # 15 minutes absolute max cap
MIN_QUESTIONS = 4
TARGET_QUESTION_COUNT = 12

# Maintain compatibility exports
MIN_DURATION_SEC = BASE_MIN_DURATION_SEC
MAX_DURATION_SEC = BASE_MAX_DURATION_SEC


def compute_interview_elapsed(session_created_at: datetime, answers: list) -> float:
    """Wall-clock elapsed time since the session started."""
    wall = (datetime.utcnow() - session_created_at).total_seconds()
    speaking = sum(getattr(a, "speaking_time_seconds", 0) or 0 for a in answers)
    return max(wall, speaking)


def compute_dynamic_duration(answers: list) -> Tuple[int, int, int, bool]:
    """
    Computes dynamic min_duration_seconds and max_duration_seconds.
    If candidate answers well (overall_score >= 60%), bonus time is added:
    - Excellent answer (overall_score >= 80% or high depth): +120 seconds bonus
    - Good answer (overall_score >= 60%): +60 seconds bonus
    
    Returns: (min_duration_sec, max_duration_sec, bonus_seconds, is_extended)
    """
    if not answers:
        return BASE_MIN_DURATION_SEC, BASE_MAX_DURATION_SEC, 0, False

    bonus_seconds = 0
    for a in answers:
        score = getattr(a, "overall_score", 0.0) or 0.0
        words = len((getattr(a, "transcript", None) or "").split())
        speaking = getattr(a, "speaking_time_seconds", 0.0) or 0.0

        if score >= 80.0 or (score >= 70.0 and (words >= 40 or speaking >= 30)):
            bonus_seconds += 120  # +2 minutes for excellent answer
        elif score >= 60.0 or words >= 25 or speaking >= 20:
            bonus_seconds += 60   # +1 minute for good answer

    dynamic_max = min(MAX_ALLOWED_DURATION_SEC, BASE_MAX_DURATION_SEC + bonus_seconds)
    dynamic_min = min(dynamic_max - 60, BASE_MIN_DURATION_SEC + (bonus_seconds // 2))
    is_extended = bonus_seconds > 0

    return dynamic_min, dynamic_max, bonus_seconds, is_extended


def should_end_interview(session_created_at: datetime, answers: list, total_questions: int) -> Tuple[bool, dict[str, Any]]:
    """
    Decide whether the interview should wrap up after the latest answer.
    - If the candidate answers well, duration dynamically increases (up to 20 minutes max).
    - Interview continues as long as candidate is performing well and time/questions remain.
    - Ends when dynamic max duration is reached or all questions are exhausted.
    """
    elapsed = compute_interview_elapsed(session_created_at, answers)
    answered = len(answers)
    unanswered = max(0, total_questions - answered)

    min_dur, max_dur, bonus_sec, is_extended = compute_dynamic_duration(answers)

    meta: dict[str, Any] = {
        "elapsed_seconds": round(elapsed),
        "min_duration_seconds": min_dur,
        "max_duration_seconds": max_dur,
        "bonus_seconds_added": bonus_sec,
        "is_extended": is_extended,
        "answered_questions": answered,
        "total_questions": total_questions,
        "remaining_questions": unanswered,
    }

    if elapsed >= max_dur:
        meta["end_reason"] = "max_duration_reached"
        return True, meta

    if unanswered == 0:
        if elapsed < max_dur * 0.75 and is_extended:
            meta["end_reason"] = "questions_exhausted_time_remains"
            meta["needs_extra_questions"] = True
            return False, meta
        meta["end_reason"] = "all_questions_answered"
        return True, meta

    if elapsed < min_dur:
        meta["end_reason"] = "minimum_duration_not_met"
        return False, meta

    if answered < MIN_QUESTIONS:
        meta["end_reason"] = "minimum_questions_not_met"
        return False, meta

    avg_words = sum(len((getattr(a, "transcript", None) or "").split()) for a in answers) / answered if answered > 0 else 0
    avg_speaking = sum(getattr(a, "speaking_time_seconds", 0) or 0 for a in answers) / answered if answered > 0 else 0

    meta["avg_answer_words"] = round(avg_words, 1)
    meta["avg_speaking_seconds"] = round(avg_speaking, 1)

    meta["end_reason"] = "continuing_dynamic_interview"
    return False, meta

