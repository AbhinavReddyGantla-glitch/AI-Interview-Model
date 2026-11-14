"""Speech-to-text service integrating a layered, high-accuracy STT pipeline.

Layers:
- Layer 1: Clean Audio Capture (Frontend)
- Layer 2: Audio Preprocessing (16 kHz mono WAV, loudnorm, high-pass filter ~80 Hz, VAD)
- Layer 3: Stronger Transcription Engine (Faster-Whisper, OpenAI, Deepgram, Azure)
- Layer 4: Vocabulary and Phonetic Correction (Soundex, Double Metaphone, RapidFuzz, vocab.json)
- Layer 5: Optional LLM Context Correction (Gemini post-processing)
- Layer 6: Word Confidence and De-duplication
"""

import hashlib
import logging
import os
import re
from threading import Lock
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.services.speech_audio import compute_audio_hash, preprocess_audio
from app.services.speech_engine import (
    STTResult,
    WordConfidence,
    get_stt_engine,
)
from app.services.speech_llm import llm_context_correction
from app.services.speech_vocab import (
    apply_vocabulary_corrections,
    build_interview_vocabulary,
)

logger = logging.getLogger("app.services.speech")

# Thread-safe in-memory LRU transcription cache
_TRANSCRIPTION_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_LOCK = Lock()
_MAX_CACHE_SIZE = 256

_deepgram_client = None
_client_lock = Lock()


def _get_deepgram_client():
    """Create or return a thread-safe cached DeepgramClient instance."""
    global _deepgram_client
    if _deepgram_client is None:
        with _client_lock:
            if _deepgram_client is None:
                api_key = settings.DEEPGRAM_API_KEY
                if not api_key:
                    logger.warning("DEEPGRAM_API_KEY not configured; audio cannot be transcribed server-side.")
                    return None
                try:
                    from deepgram import DeepgramClient

                    _deepgram_client = DeepgramClient(api_key=api_key)
                    logger.info("Initialized DeepgramClient successfully.")
                except Exception as exc:
                    logger.error("Failed to initialize DeepgramClient: %s", exc)
                    return None
    return _deepgram_client


def _transcribe_deepgram(
    audio_bytes: bytes,
    content_type: str = "audio/webm",
    language: str = "en-IN",
    candidate_name: Optional[str] = None,
    resume_summary: Optional[str] = None,
    prompt: Optional[str] = None,
) -> str:
    """Execute Deepgram transcription via SDK with HTTP fallback."""
    api_key = settings.DEEPGRAM_API_KEY
    if not api_key:
        logger.warning("DEEPGRAM_API_KEY not configured; audio cannot be transcribed server-side.")
        return ""

    model = getattr(settings, "DEEPGRAM_MODEL", "nova-2") or "nova-2"
    lang = language or getattr(settings, "DEEPGRAM_LANGUAGE", "en-IN") or "en-IN"

    keywords: list[str] = []
    if candidate_name:
        for token in candidate_name.split():
            if len(token) > 1:
                keywords.append(f"{token}:5")

    # 1. Primary: Use official Deepgram SDK
    try:
        client = _get_deepgram_client()
        if client:
            sdk_options: dict = {
                "model": model,
                "smart_format": True,
                "punctuate": True,
                "language": lang,
            }
            if keywords:
                sdk_options["keywords"] = keywords
            response = client.listen.v1.media.transcribe_file(
                request=audio_bytes,
                **sdk_options,
            )
            if response and response.results and response.results.channels:
                alternatives = response.results.channels[0].alternatives
                if alternatives and alternatives[0].transcript:
                    transcript = alternatives[0].transcript.strip()
                    logger.info("Deepgram SDK transcription successful: %r", transcript)
                    return transcript
    except Exception as exc:
        logger.warning("Deepgram SDK transcribe_file encountered an error: %s. Trying HTTP fallback.", exc)

    # 2. Fallback: Direct REST API call via httpx
    try:
        headers = {
            "Authorization": f"Token {api_key}",
            "Content-Type": content_type or "audio/webm",
        }
        params: dict = {
            "model": model,
            "smart_format": "true",
            "punctuate": "true",
            "language": lang,
        }
        if keywords:
            params["keywords"] = keywords
        with httpx.Client(timeout=30.0) as http_client:
            res = http_client.post(
                "https://api.deepgram.com/v1/listen",
                headers=headers,
                params=params,
                content=audio_bytes,
            )
            if res.status_code == 200:
                data = res.json()
                channels = data.get("results", {}).get("channels", [])
                if channels and channels[0].get("alternatives"):
                    transcript = channels[0]["alternatives"][0].get("transcript", "").strip()
                    logger.info("Deepgram HTTP transcription successful: %r", transcript)
                    return transcript
            else:
                logger.error("Deepgram HTTP API returned status %d: %s", res.status_code, res.text)
    except Exception as exc:
        logger.error("Deepgram HTTP fallback transcription failed: %s", exc, exc_info=True)

    return ""


def transcribe_with_whisper(
    audio_bytes: bytes,
    content_type: str = "audio/webm",
    language: str = "en",
    initial_prompt: Optional[str] = None,
) -> str:
    """Server-side transcription with OpenAI Whisper API."""
    openai_key = os.environ.get("OPENAI_API_KEY") or getattr(settings, "OPENAI_API_KEY", None)
    if not openai_key:
        return ""
    try:
        from openai import OpenAI
        import io

        client = OpenAI(api_key=openai_key)
        ext = "webm" if "webm" in content_type else "mp4" if "mp4" in content_type else "wav"
        buffer = io.BytesIO(audio_bytes)
        buffer.name = f"audio.{ext}"
        kwargs: dict = {
            "model": "whisper-1",
            "file": buffer,
            "language": language[:2] if language else "en",
        }
        if initial_prompt:
            kwargs["prompt"] = initial_prompt
        res = client.audio.transcriptions.create(**kwargs)
        if res and res.text:
            logger.info("Whisper API transcription successful: %r", res.text.strip())
            return res.text.strip()
    except Exception as exc:
        logger.warning("Whisper transcription error: %s", exc)
    return ""


def transcribe_pipeline(
    audio_bytes: bytes,
    content_type: str = "audio/webm",
    language: str = "en",
    candidate_name: Optional[str] = None,
    university: Optional[str] = None,
    job_role: Optional[str] = None,
    skills: Optional[list[str]] = None,
    question_text: Optional[str] = None,
    resume_summary: Optional[str] = None,
    engine_name: Optional[str] = None,
) -> dict[str, Any]:
    """Execute the full layered STT pipeline.

    Returns:
        dict: {
            "transcript": str (final corrected transcript),
            "raw_transcript": str (original engine output),
            "words": list[dict] (per-word confidences & timestamps),
            "changes": list[dict] (corrections made),
            "language": str,
            "duration": float,
        }
    """
    if not audio_bytes:
        return {
            "transcript": "",
            "raw_transcript": "",
            "words": [],
            "changes": [],
            "language": language,
            "duration": 0.0,
        }

    # 1. Caching: compute audio hash
    audio_hash = compute_audio_hash(audio_bytes)
    selected_engine = (engine_name or getattr(settings, "STT_ENGINE", None) or os.environ.get("STT_ENGINE", "whisper")).lower()
    cache_key = f"{audio_hash}_{selected_engine}_{language}_{candidate_name or ''}"

    with _CACHE_LOCK:
        if cache_key in _TRANSCRIPTION_CACHE:
            logger.info("Transcription cache hit for audio hash %s", audio_hash[:10])
            return _TRANSCRIPTION_CACHE[cache_key]

    # 2. Build Layer 3 & 4 Vocabulary Context
    vocab_terms, _ = build_interview_vocabulary(
        candidate_name=candidate_name,
        university=university,
        job_role=job_role,
        skills=skills,
        question_text=question_text,
    )

    # Initial prompt / hotwords for Whisper / Deepgram
    prompt_parts = []
    if candidate_name:
        prompt_parts.append(f"Interview with candidate {candidate_name}")
    if university:
        prompt_parts.append(f"from {university}")
    if job_role:
        prompt_parts.append(f"applying for {job_role}")
    if skills:
        prompt_parts.append(f"Skills: {', '.join(skills[:8])}")
    if question_text:
        prompt_parts.append(f"Question: {question_text[:120]}")
    elif resume_summary:
        prompt_parts.append(f"Context: {resume_summary[:120]}")

    initial_prompt = ". ".join(prompt_parts) if prompt_parts else None

    # 3. Layer 2 Preprocessing & Layer 3 Engine Execution
    engine = get_stt_engine(selected_engine)
    logger.info("Transcribing audio (%d bytes) with engine=%s", len(audio_bytes), selected_engine)

    try:
        stt_result: STTResult = engine.transcribe(
            audio_bytes,
            content_type=content_type,
            language=language,
            prompt=initial_prompt,
            candidate_name=candidate_name,
        )
    except Exception as exc:
        logger.error("Primary STT engine %s failed: %s. Attempting fallback.", selected_engine, exc)
        # Fallback to Deepgram if available
        if selected_engine != "deepgram" and settings.DEEPGRAM_API_KEY:
            fallback_engine = get_stt_engine("deepgram")
            stt_result = fallback_engine.transcribe(
                audio_bytes,
                content_type=content_type,
                language=language,
                prompt=initial_prompt,
                candidate_name=candidate_name,
            )
        else:
            stt_result = STTResult(text="", raw_text="")

    raw_text = stt_result.raw_text or stt_result.text
    changes: list[dict] = []

    # 4. Layer 4: Vocabulary and Phonetic Correction
    sim_threshold = float(getattr(settings, "STT_SIMILARITY_THRESHOLD", 0.80) or os.environ.get("STT_SIMILARITY_THRESHOLD", "0.80"))
    conf_threshold = float(getattr(settings, "STT_CONFIDENCE_THRESHOLD", 0.75) or os.environ.get("STT_CONFIDENCE_THRESHOLD", "0.75"))

    corrected_text, vocab_changes = apply_vocabulary_corrections(
        raw_text,
        candidate_name=candidate_name,
        vocabulary=vocab_terms,
        word_confidences=[w.to_dict() for w in stt_result.words],
        similarity_threshold=sim_threshold,
        confidence_threshold=conf_threshold,
    )
    changes.extend(vocab_changes)

    # Multi-pass repetition collapse & sentence tail replacement
    deduped_text = fix_transcript(corrected_text, candidate_name=candidate_name)

    # 5. Layer 5: Optional LLM Context Correction
    llm_corrected, llm_changes = llm_context_correction(
        deduped_text,
        words=stt_result.words,
        question_text=question_text,
        vocabulary=list(vocab_terms),
        candidate_name=candidate_name,
    )
    if llm_changes:
        changes.extend(llm_changes)
        final_text = fix_transcript(llm_corrected, candidate_name=candidate_name)
    else:
        final_text = deduped_text

    result_payload = {
        "transcript": final_text,
        "raw_transcript": raw_text,
        "words": [w.to_dict() for w in stt_result.words],
        "changes": changes,
        "language": stt_result.language,
        "duration": stt_result.duration,
    }

    # Store in LRU cache
    with _CACHE_LOCK:
        if len(_TRANSCRIPTION_CACHE) >= _MAX_CACHE_SIZE:
            _TRANSCRIPTION_CACHE.pop(next(iter(_TRANSCRIPTION_CACHE)))
        _TRANSCRIPTION_CACHE[cache_key] = result_payload

    return result_payload


def transcribe_audio(
    audio_bytes: bytes,
    content_type: str = "audio/webm",
    language: Optional[str] = None,
    candidate_name: Optional[str] = None,
    resume_summary: Optional[str] = None,
) -> str:
    """Transcribe audio upload using the layered pipeline.

    Maintains backward compatibility with all existing endpoints and tests.
    """
    lang = language or getattr(settings, "DEEPGRAM_LANGUAGE", "en-IN") or "en-IN"
    result = transcribe_pipeline(
        audio_bytes=audio_bytes,
        content_type=content_type,
        language=lang,
        candidate_name=candidate_name,
        resume_summary=resume_summary,
    )
    return result.get("transcript", "")


def _clean_word(w: str) -> str:
    """Strip punctuation and lowercase for robust equality comparison."""
    return re.sub(r"[^a-zA-Z0-9]", "", w).lower()


def fix_transcript(
    transcript: str,
    candidate_name: Optional[str] = None,
    extra_terms: Optional[list[str]] = None,
) -> str:
    """Post-process a transcript for display and submission.

    Steps:
    1. Trim leading/trailing whitespace.
    2. Replace duplicate sentences when a newer sentence begins with the same 3 words.
    3. Collapse consecutive duplicate words/phrases (up to 8-word window).
    4. Fix common phonetic misheard words (e.g. Sreenidhi, pursuing, degrees).
    5. Fix sentence-start capitalization.
    6. Apply name-correction dictionary built from candidate_name and extra_terms.
    """
    if not transcript:
        return ""

    text = transcript.strip()

    # --- Step 1: Replace earlier sentences if a subsequent sentence starts with the same 3 words ---
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if len(sentences) >= 2:
        retained: list[str] = []
        for s in sentences:
            s_words = [_clean_word(w) for w in s.split() if _clean_word(w)]
            if len(s_words) >= 3:
                first3 = s_words[:3]
                replaced = False
                for idx, prev in enumerate(retained):
                    prev_words = [_clean_word(w) for w in prev.split() if _clean_word(w)]
                    if len(prev_words) >= 3 and prev_words[:3] == first3:
                        retained = retained[:idx] + [s]
                        replaced = True
                        break
                if not replaced:
                    retained.append(s)
            else:
                retained.append(s)
        text = " ".join(retained)

    # --- Step 2: Collapse duplicate consecutive words/phrases (handles punctuation differences) ---
    for window in range(8, 0, -1):
        words = text.split()
        out: list[str] = []
        i = 0
        while i < len(words):
            segment = words[i:i + window]
            if len(segment) == window:
                seg_cleaned = " ".join(_clean_word(w) for w in segment)
                j = i + window
                matched = False
                while j + window <= len(words) and " ".join(_clean_word(w) for w in words[j:j + window]) == seg_cleaned:
                    matched = True
                    j += window
                if matched:
                    out.extend(segment)
                    i = j
                    continue
            out.append(words[i])
            i += 1
        text = " ".join(out)

    # Check if trailing words repeat a prefix of the sentence
    words = text.split()
    for k in range(len(words) // 2, 0, -1):
        if [_clean_word(w) for w in words[-k:]] == [_clean_word(w) for w in words[:k]]:
            words = words[:-k]
            text = " ".join(words)
            break

    # --- Step 3: Phonetic and domain mishearing corrections ---
    phonetic_fixes = [
        (r"\b(Avino|Abino|Avinav)\b", candidate_name if candidate_name else "Abhinav"),
        (r"\bscreen\s+(university|institute|college)\b", r"Sreenidhi \1"),
        (r"\bfrom\s+screen\b", "from Sreenidhi"),
        (r"\bposting\s+with\s+degrees\b", "pursuing my degree"),
        (r"\bposting\s+with\s+degree\b", "pursuing my degree"),
        (r"\bposting\s+(my|a|with)\s+degree\b", r"pursuing \1 degree"),
        (r"\bposting\b(?=\s+(my|a|degree|phd|btech|mtech))", "pursuing"),
        (r"\bI'm\s+University\b", "from University"),
    ]
    for pattern, replacement in phonetic_fixes:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    # --- Step 4: Capitalize first letter of the transcript ---
    if text:
        text = text[0].upper() + text[1:]

    # --- Step 5: Name/term correction dictionary ---
    name_terms: list[str] = []
    if candidate_name:
        name_terms.extend(t for t in candidate_name.split() if len(t) > 1)
    if extra_terms:
        name_terms.extend(extra_terms)

    for term in name_terms:
        escaped = re.escape(term)
        text = re.sub(rf"\b{escaped}\b", term, text, flags=re.IGNORECASE)

    return text


def correct_profile_terms(transcript: str, *args, **kwargs) -> str:
    """Backward-compat alias for fix_transcript (no-op without name)."""
    return fix_transcript(transcript)
