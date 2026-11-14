"""Vocabulary, Phonetic, and Name Correction Service (Layer 4).

Combines:
1. Double Metaphone & Soundex phonetic encoding.
2. Levenshtein & Jaro-Winkler string similarity (via RapidFuzz).
3. Context-aware phrase replacements (e.g. "screen university" -> "Sreenidhi University").
4. Domain vocabulary glossary from app/data/vocab.json.
"""

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Optional
from rapidfuzz.distance import JaroWinkler, Levenshtein

logger = logging.getLogger("app.services.speech_vocab")

COMMON_ENGLISH_WORDS = {
    "the", "be", "to", "of", "and", "a", "in", "that", "have", "i", "it", "for",
    "not", "on", "with", "he", "as", "you", "do", "at", "this", "but", "his",
    "by", "from", "they", "we", "say", "her", "she", "or", "an", "will", "my",
    "one", "all", "would", "there", "their", "what", "so", "up", "out", "if",
    "about", "who", "get", "which", "go", "me", "when", "make", "can", "like",
    "time", "no", "just", "him", "know", "take", "people", "into", "year", "your",
    "good", "some", "could", "them", "see", "other", "than", "then", "now", "look",
    "only", "come", "its", "over", "think", "also", "back", "after", "use", "used",
    "using", "uses", "two", "how", "our", "work", "working", "worked", "first",
    "well", "way", "even", "new", "want", "because", "any", "these", "give", "day",
    "most", "us", "is", "am", "are", "was", "were", "been", "being", "had", "has",
    "did", "doing", "does", "made", "making", "makes", "went", "gone", "going",
    "said", "saying", "says", "saw", "seen", "seeing", "designed", "design", "designing",
    "built", "build", "building", "created", "create", "creating", "implemented",
    "implement", "implementing", "optimized", "optimize", "optimizing", "handled",
    "handle", "handling", "wrote", "write", "writing", "tested", "test", "testing",
    "run", "running", "ran", "called", "call", "calling", "scalable", "scale",
    "system", "systems", "service", "services", "server", "servers", "database",
    "databases", "table", "tables", "data", "query", "queries", "api", "apis",
}


def soundex(word: str) -> str:
    """Compute American Soundex code for a word."""
    cleaned = re.sub(r"[^A-Za-z]", "", word).upper()
    if not cleaned:
        return ""
    first = cleaned[0]
    mapping = {
        "B": "1", "F": "1", "P": "1", "V": "1",
        "C": "2", "G": "2", "J": "2", "K": "2", "Q": "2", "S": "2", "X": "2", "Z": "2",
        "D": "3", "T": "3",
        "L": "4",
        "M": "5", "N": "5",
        "R": "6",
    }
    encoded = [first]
    prev = mapping.get(first, "")
    for char in cleaned[1:]:
        code = mapping.get(char, "")
        if code != "" and code != prev:
            encoded.append(code)
            prev = code
        elif code == "":
            prev = ""
        if len(encoded) == 4:
            break
    while len(encoded) < 4:
        encoded.append("0")
    return "".join(encoded)


def double_metaphone(word: str) -> tuple[str, str]:
    """Simplified Python implementation of Double Metaphone phonetic hashing.

    Returns primary and alternate phonetic representations.
    """
    w = re.sub(r"[^A-Za-z]", "", word).upper()
    if not w:
        return ("", "")

    # Basic phonetic transformations for Indian/English names
    primary = w
    alt = w

    # Initial transforms
    if primary.startswith(("KN", "GN", "PN", "WR", "PS")):
        primary = primary[1:]
        alt = alt[1:]
    if primary.startswith("X"):
        primary = "S" + primary[1:]
        alt = "S" + alt[1:]

    # Vowel reduction
    vowels = {"A", "E", "I", "O", "U", "Y"}

    # Replace common digraphs
    digraphs = [
        ("PH", "F", "F"),
        ("TH", "T", "0"),
        ("SH", "X", "X"),
        ("CH", "X", "K"),
        ("CK", "K", "K"),
        ("DG", "J", "J"),
        ("GH", "K", "F"),
        ("EE", "I", "I"),
        ("OO", "U", "U"),
        ("DH", "D", "D"),
        ("BH", "B", "B"),
        ("KH", "K", "K"),
    ]
    for d, p, a in digraphs:
        primary = primary.replace(d, p)
        alt = alt.replace(d, a)

    # Clean duplicates
    p_chars = [primary[0]] if primary else []
    for c in primary[1:]:
        if c != p_chars[-1]:
            p_chars.append(c)

    a_chars = [alt[0]] if alt else []
    for c in alt[1:]:
        if c != a_chars[-1]:
            a_chars.append(c)

    # Keep first vowel only
    p_res = [p_chars[0]]
    for c in p_chars[1:]:
        if c not in vowels:
            p_res.append(c)

    a_res = [a_chars[0]]
    for c in a_chars[1:]:
        if c not in vowels:
            a_res.append(c)

    return ("".join(p_res)[:6], "".join(a_res)[:6])


@dataclass
class VocabConfig:
    institutions: list[str]
    degrees_and_education: list[str]
    technical_glossary: list[str]
    phrase_replacements: list[dict[str, Any]]
    phonetic_name_hints: dict[str, str]


_cached_vocab: Optional[VocabConfig] = None


def load_vocab_glossary(vocab_path: Optional[str] = None) -> VocabConfig:
    """Load or return cached vocabulary glossary from JSON."""
    global _cached_vocab
    if _cached_vocab and not vocab_path:
        return _cached_vocab

    path = vocab_path or os.environ.get("STT_VOCAB_PATH")
    if not path or not os.path.exists(path):
        default_path = os.path.join(os.path.dirname(__file__), "..", "data", "vocab.json")
        if os.path.exists(default_path):
            path = default_path

    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            _cached_vocab = VocabConfig(
                institutions=data.get("institutions", []),
                degrees_and_education=data.get("degrees_and_education", []),
                technical_glossary=data.get("technical_glossary", []),
                phrase_replacements=data.get("phrase_replacements", []),
                phonetic_name_hints=data.get("phonetic_name_hints", {}),
            )
            return _cached_vocab
        except Exception as exc:
            logger.warning("Could not parse vocab file %s: %s", path, exc)

    # Default fallback
    _cached_vocab = VocabConfig(
        institutions=["Sreenidhi University", "Sreenidhi Institute of Science and Technology"],
        degrees_and_education=["pursuing", "pursuing my degree", "PhD", "B.Tech"],
        technical_glossary=["FastAPI", "Python", "Docker", "PostgreSQL"],
        phrase_replacements=[],
        phonetic_name_hints={"avino": "Abhinav", "abino": "Abhinav"},
    )
    return _cached_vocab


def build_interview_vocabulary(
    candidate_name: Optional[str] = None,
    university: Optional[str] = None,
    job_role: Optional[str] = None,
    skills: Optional[list[str]] = None,
    question_text: Optional[str] = None,
    vocab_path: Optional[str] = None,
) -> tuple[set[str], dict[str, str]]:
    """Build unified vocabulary set and term dictionary for this specific interview.

    Returns:
        tuple[set[str], dict[str, str]]: (vocabulary_set, normalized_name_map)
    """
    vocab = load_vocab_glossary(vocab_path)
    terms: set[str] = set()
    term_map: dict[str, str] = {}

    def _add_term(t: str):
        cleaned = t.strip()
        if len(cleaned) > 1:
            terms.add(cleaned)
            term_map[cleaned.lower()] = cleaned

    for item in vocab.institutions + vocab.degrees_and_education + vocab.technical_glossary:
        _add_term(item)

    if candidate_name:
        for token in candidate_name.split():
            _add_term(token)

    if university:
        _add_term(university)

    if job_role:
        for token in job_role.split():
            if len(token) > 2:
                _add_term(token)

    if skills:
        for s in skills:
            _add_term(s)

    if question_text:
        # Extract technical keywords from question
        for word in re.findall(r"\b[A-Z][a-zA-Z0-9+#]*\b", question_text):
            if len(word) > 2 and word.lower() not in COMMON_ENGLISH_WORDS:
                _add_term(word)

    return terms, term_map


def find_phonetic_or_similarity_match(
    word: str,
    target_terms: set[str],
    similarity_threshold: float = 0.80,
) -> Optional[str]:
    """Check if word phonetically or textually matches a term in target_terms."""
    w_clean = re.sub(r"[^a-zA-Z0-9]", "", word).lower()
    if not w_clean or len(w_clean) < 3:
        return None

    w_soundex = soundex(w_clean)
    w_meta_p, w_meta_a = double_metaphone(w_clean)

    best_match: Optional[str] = None
    best_score: float = 0.0

    for term in target_terms:
        t_clean = re.sub(r"[^a-zA-Z0-9]", "", term).lower()
        if not t_clean:
            continue

        # Exact normalized match
        if w_clean == t_clean:
            return term

        # RapidFuzz similarity metrics
        jw = JaroWinkler.similarity(w_clean, t_clean)
        lev = 1.0 - (Levenshtein.distance(w_clean, t_clean) / max(len(w_clean), len(t_clean)))
        sim_score = max(jw, lev)

        # Phonetic match bonus
        t_soundex = soundex(t_clean)
        t_meta_p, t_meta_a = double_metaphone(t_clean)

        phonetic_match = False
        if w_soundex and w_soundex == t_soundex:
            phonetic_match = True
        elif w_meta_p and (w_meta_p == t_meta_p or w_meta_p == t_meta_a):
            phonetic_match = True

        if phonetic_match:
            sim_score = max(sim_score, 0.85)

        if sim_score >= similarity_threshold and sim_score > best_score:
            best_score = sim_score
            best_match = term

    return best_match


def apply_vocabulary_corrections(
    transcript: str,
    candidate_name: Optional[str] = None,
    vocabulary: Optional[set[str]] = None,
    word_confidences: Optional[list[dict]] = None,
    similarity_threshold: float = 0.80,
    confidence_threshold: float = 0.75,
) -> tuple[str, list[dict]]:
    """Correct misrecognized words using phonetic and similarity matching.

    Replaces a word only if:
    1. Similarity is above similarity_threshold, AND
    2. Word has low confidence (< confidence_threshold) OR is not a common English word.

    Never overwrites high-confidence common English words.
    """
    if not transcript:
        return "", []

    vocab_config = load_vocab_glossary()
    target_terms = set(vocabulary or [])
    if candidate_name:
        for token in candidate_name.split():
            target_terms.add(token)

    # 1. Apply configured phrase replacements first
    text = transcript
    changes: list[dict] = []

    for rule in vocab_config.phrase_replacements:
        pattern = rule.get("pattern", "")
        rep = rule.get("replacement", "")
        if pattern and rep:
            # Convert JS-style $1 to Python \1
            py_rep = re.sub(r"\$(\d+)", r"\\\1", rep)
            new_text = re.sub(pattern, py_rep, text, flags=re.IGNORECASE)
            if new_text != text:
                changes.append({"from": pattern, "to": py_rep, "reason": "context_phrase_rule"})
                text = new_text

    # 2. Check phonetic name hints
    for misheard, correct in vocab_config.phonetic_name_hints.items():
        chosen_correct = candidate_name if candidate_name else correct
        pattern = rf"\b{re.escape(misheard)}\b"
        if re.search(pattern, text, flags=re.IGNORECASE):
            text = re.sub(pattern, chosen_correct, text, flags=re.IGNORECASE)
            changes.append({"from": misheard, "to": chosen_correct, "reason": "phonetic_name_hint"})

    # 3. Word-by-word similarity and phonetic replacement
    words = text.split()
    conf_map = {}
    if word_confidences:
        for item in word_confidences:
            w_raw = re.sub(r"[^a-zA-Z0-9]", "", item.get("word", "")).lower()
            conf_map[w_raw] = item.get("confidence", item.get("probability", 1.0))

    corrected_words = []
    for word in words:
        clean = re.sub(r"[^a-zA-Z0-9]", "", word).lower()
        conf = conf_map.get(clean, 0.70)  # default if unknown

        # Protection rule: Never overwrite common English words
        if clean in COMMON_ENGLISH_WORDS:
            corrected_words.append(word)
            continue

        # Check for candidate name / vocabulary match
        match = find_phonetic_or_similarity_match(clean, target_terms, similarity_threshold)
        if match and match.lower() != clean:
            # Preserve surrounding punctuation
            prefix = re.match(r"^\W*", word).group(0)
            suffix = re.search(r"\W*$", word).group(0)
            new_word = f"{prefix}{match}{suffix}"
            changes.append({"from": word, "to": new_word, "reason": "phonetic_similarity_match"})
            corrected_words.append(new_word)
        else:
            corrected_words.append(word)

    result_text = " ".join(corrected_words)
    return result_text, changes
