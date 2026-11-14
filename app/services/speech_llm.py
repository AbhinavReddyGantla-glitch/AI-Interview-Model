"""LLM Context Correction Service (Layer 5).

Optional post-processing pass using Gemini / LLM to fix speech recognition
errors while preserving speaker wording, tone, and sentence structure.
Toggled via ENABLE_LLM_TRANSCRIPT_CORRECTION.
"""

import json
import logging
import os
import re
from typing import Any, Optional

from app.core.config import settings
from app.services.speech_engine import WordConfidence

logger = logging.getLogger("app.services.speech_llm")


def is_llm_correction_enabled() -> bool:
    """Check if LLM context correction is enabled via settings or env."""
    val = getattr(settings, "ENABLE_LLM_TRANSCRIPT_CORRECTION", None)
    if val is not None:
        if isinstance(val, bool):
            return val
        return str(val).strip().lower() in ("true", "1", "yes")
    return os.environ.get("ENABLE_LLM_TRANSCRIPT_CORRECTION", "false").lower() in ("true", "1", "yes")


def llm_context_correction(
    raw_transcript: str,
    words: Optional[list[WordConfidence]] = None,
    question_text: Optional[str] = None,
    vocabulary: Optional[list[str]] = None,
    candidate_name: Optional[str] = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Execute LLM context correction on transcript if enabled.

    Returns:
        tuple[str, list[dict]]: (corrected_transcript, list_of_changes)
    """
    if not raw_transcript or not raw_transcript.strip():
        return raw_transcript, []

    if not is_llm_correction_enabled():
        return raw_transcript, []

    api_key = getattr(settings, "GEMINI_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        logger.debug("LLM transcript correction enabled but GEMINI_API_KEY not configured.")
        return raw_transcript, []

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")

        # Format low-confidence words hint
        low_conf_words = []
        if words:
            for w in words:
                if w.low_confidence or w.probability < 0.70:
                    low_conf_words.append(f"{w.word} ({w.probability:.2f})")

        vocab_str = ", ".join(vocabulary[:40]) if vocabulary else "None provided"
        low_conf_str = ", ".join(low_conf_words[:20]) if low_conf_words else "None"

        system_prompt = (
            "You are a precision speech-to-text correction engine for a technical interview assessment platform.\n"
            "Your ONLY goal is to fix phonetic recognition errors (especially Indian-accented English, names, institutions, and CS technical terms).\n\n"
            "CRITICAL RULES:\n"
            "1. KEEP THE SPEAKER'S EXACT WORDING, GRAMMAR, AND SENTENCE STRUCTURE. Do NOT rephrase or make it sound more professional.\n"
            "2. DO NOT add words that were not spoken, and DO NOT remove content.\n"
            "3. If candidate name is misheard (e.g. 'Avino'/'Abino' when candidate is 'Abhinav'), fix it.\n"
            "4. If university is misheard (e.g. 'screen university' -> 'Sreenidhi University'), fix it.\n"
            "5. If a phrase is an obvious duplicate loop (e.g. repeated sentence fragments), remove the duplicate.\n"
            "6. Output STRICTLY valid JSON with no markdown and no backticks in this schema:\n"
            '{"corrected_text": "<full corrected string>", "changes": [{"from": "<misheard>", "to": "<corrected>", "reason": "<brief rationale>"}]}\n'
        )

        user_content = (
            f"Candidate Name: {candidate_name or 'Unknown'}\n"
            f"Interview Question: {question_text or 'Technical assessment'}\n"
            f"Target Terms/Vocabulary: {vocab_str}\n"
            f"Low Confidence Words: {low_conf_str}\n"
            f"Raw Transcript: \"{raw_transcript}\"\n"
        )

        response = model.generate_content([system_prompt, user_content])
        if not response or not response.text:
            return raw_transcript, []

        cleaned_text = response.text.strip()
        # Strip potential markdown fences
        if cleaned_text.startswith("```"):
            cleaned_text = re.sub(r"^```(?:json)?\s*", "", cleaned_text)
            cleaned_text = re.sub(r"\s*```$", "", cleaned_text)

        data = json.loads(cleaned_text)
        corrected = data.get("corrected_text", "").strip()
        changes = data.get("changes", [])

        if corrected:
            logger.info("LLM transcript correction succeeded. %d changes applied.", len(changes))
            return corrected, changes

    except Exception as exc:
        logger.warning("LLM transcript correction error: %s. Falling back to uncorrected text.", exc)

    return raw_transcript, []

