"""Deterministic, explainable per-answer scoring."""
import re
from typing import Dict, List, Set


def _tokens(text: str) -> List[str]:
    """Normalize punctuation and hyphens consistently for phrases and tokens."""
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _concept_coverage(answer_tokens: Set[str], keyword: str) -> float:
    """Return 0, .5, or 1 for a concept without substring false positives."""
    concept_tokens = set(_tokens(keyword))
    if not concept_tokens:
        return 0.0
    overlap = len(concept_tokens & answer_tokens) / len(concept_tokens)
    if overlap == 1:
        return 1.0
    return 0.5 if len(concept_tokens) > 1 and overlap >= 0.5 else 0.0


def _length_score(word_count: int) -> float:
    """Reward a substantive response, without treating verbosity as quality."""
    if word_count < 8:
        return word_count / 8 * 35
    if word_count < 25:
        return 35 + (word_count - 8) / 17 * 55
    if word_count <= 140:
        return 90.0
    return max(55.0, 90.0 - (word_count - 140) * 0.25)


def _coherence_score(tokens: List[str]) -> float:
    """Detect obvious keyword stuffing/repetition using lexical diversity."""
    if len(tokens) < 8:
        return 25.0
    diversity = len(set(tokens)) / len(tokens)
    return max(0.0, min(100.0, (diversity - 0.25) / 0.45 * 100.0))


def _speaking_time_score(seconds: float) -> float:
    if seconds < 5:
        return 0.0
    if seconds < 20:
        return 45.0 + ((seconds - 5.0) / 15.0 * 45.0)
    if seconds <= 120:
        return 90.0
    return max(45.0, 90.0 - (seconds - 120.0) * 0.3)

def evaluate_answer(
    transcript: str, 
    expected_keywords: List[str], 
    speaking_time_seconds: float = 30.0
) -> Dict[str, float]:
    """
    Score an answer using auditable concept coverage and response quality.

    ``keyword_score`` is strict full-concept coverage. ``similarity_score`` also
    gives limited credit for multi-word concepts that were partially addressed;
    it is retained for API compatibility but is no longer a duplicate token-set
    calculation.
    """
    words = _tokens(transcript)
    if not words:
        return {
            "keyword_score": 0.0,
            "completeness_score": 0.0,
            "similarity_score": 0.0,
            "overall_score": 0.0
        }
    
    concepts = list(dict.fromkeys(k.strip() for k in (expected_keywords or []) if _tokens(k)))
    answer_tokens = set(words)
    coverages = [_concept_coverage(answer_tokens, concept) for concept in concepts]
    full_matches = sum(coverage == 1.0 for coverage in coverages)
    keyword_score = 100.0 * full_matches / len(concepts) if concepts else 0.0
    similarity_score = 100.0 * sum(coverages) / len(concepts) if concepts else 0.0

    length_score = _length_score(len(words))
    coherence_score = _coherence_score(words)
    completeness_score = length_score * 0.45 + similarity_score * 0.4 + coherence_score * 0.15
    speaking_time_score = _speaking_time_score(max(0.0, speaking_time_seconds or 0.0))

    if concepts:
        overall_score = (keyword_score * 0.45 + similarity_score * 0.20 +
                         completeness_score * 0.25 + speaking_time_score * 0.10)
    else:
        # Questions without an authored rubric receive a provisional quality score.
        overall_score = completeness_score * 0.8 + speaking_time_score * 0.2
    
    return {
        "keyword_score": round(keyword_score, 2),
        "completeness_score": round(min(100.0, completeness_score), 2),
        "similarity_score": round(similarity_score, 2),
        "overall_score": round(min(100.0, overall_score), 2)
    }
