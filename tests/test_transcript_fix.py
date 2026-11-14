"""
Unit tests for fix_transcript() de-duplication logic and frontend JS-equivalent behavior.
Also tests that 'my name is Sam' said once yields 'My name is Sam.' submitted exactly once.
"""
import unittest
import uuid
from fastapi.testclient import TestClient

from app.services.speech import fix_transcript
from app.main import app

client = TestClient(app)


class TestFixTranscript(unittest.TestCase):
    """Tests for the fix_transcript() backend helper."""

    def test_trim_whitespace(self):
        self.assertEqual(fix_transcript("  hello world  "), "Hello world")

    def test_capitalize_first_letter(self):
        self.assertEqual(fix_transcript("my name is Sam"), "My name is Sam")

    def test_collapse_duplicate_words(self):
        result = fix_transcript("my name is Sam my name is Sam")
        self.assertEqual(result, "My name is Sam")

    def test_collapse_partial_repeat(self):
        # "my name is Sam my name is" → should remove trailing partial repeat
        result = fix_transcript("my name is Sam my name is")
        # The repeated prefix "my name is" at the end should be collapsed
        self.assertNotIn("my name is Sam my name is", result)

    def test_name_correction_applied(self):
        result = fix_transcript("my name is dinesh", candidate_name="Dinesh Kumar")
        self.assertIn("Dinesh", result)

    def test_name_correction_multiple_tokens(self):
        result = fix_transcript("saicharan keerthireddi is my name", candidate_name="Saicharan Keerthireddi")
        self.assertIn("Saicharan", result)
        self.assertIn("Keerthireddi", result)

    def test_empty_transcript_returns_empty(self):
        self.assertEqual(fix_transcript(""), "")
        self.assertEqual(fix_transcript(None), "")

    def test_no_duplication_single_phrase(self):
        result = fix_transcript("My name is Sam.")
        self.assertEqual(result, "My name is Sam.")

    def test_extra_terms_correction(self):
        result = fix_transcript("aditya sharma is here", extra_terms=["Aditya", "Sharma"])
        self.assertIn("Aditya", result)

    def test_long_text_no_mutation(self):
        text = "I would use a hash table for O(1) lookups and handle collision with chaining."
        result = fix_transcript(text)
        self.assertEqual(result[0], result[0].upper())
        # No words should be dropped from a non-duplicated sentence
        self.assertIn("hash table", result)

    def test_observed_bad_output_test_case(self):
        """
        OBSERVED BAD OUTPUT TEST CASE:
        'My name is Avino. I'm University. I'm currently pursuing my PhD. My name is Abino I am from screen University I'm currently posting with degrees'
        Candidate name: Abhinav
        Must produce:
        - Only one occurrence of 'My name is' (collapses duplicate sentence)
        - Correct candidate name 'Abhinav'
        - Correct university 'Sreenidhi' (fixes 'screen')
        - Correct 'pursuing' (fixes 'posting')
        """
        bad_input = (
            "My name is Avino. I'm University. I'm currently pursuing my PhD. "
            "My name is Abino I am from screen University I'm currently posting with degrees"
        )
        cleaned = fix_transcript(bad_input, candidate_name="Abhinav")
        self.assertEqual(cleaned.lower().count("my name is"), 1)
        self.assertIn("Abhinav", cleaned)
        self.assertIn("Sreenidhi", cleaned)
        self.assertIn("pursuing", cleaned.lower())
        self.assertNotIn("screen", cleaned.lower())
        self.assertNotIn("posting", cleaned.lower())
        self.assertEqual(
            cleaned,
            "My name is Abhinav I am from Sreenidhi University I'm currently pursuing my degree",
        )


class TestAnswerIdempotency(unittest.TestCase):
    """Tests that /answer is idempotent — submitting same question twice is safe."""

    def _start_session_and_get_q1(self):
        start_payload = {
            "name": "Sam Idem",
            "email": f"sam_idem_{uuid.uuid4().hex[:8]}@example.com",
            "job_role": "Software Engineer",
            "experience_years": 1,
            "skills": ["Python", "SQL"],
        }
        r = client.post("/api/v1/interview/start", json=start_payload)
        self.assertEqual(r.status_code, 200)
        session_id = r.json()["session_id"]

        state = client.get(f"/api/v1/interview/{session_id}/state").json()
        q1_id = state["current_question"]["question_id"]
        return session_id, q1_id

    def test_double_submit_same_answer_returns_200_both_times(self):
        session_id, q1_id = self._start_session_and_get_q1()
        payload = {
            "question_id": q1_id,
            "answer_text": "My name is Sam. I would use Python and optimize database indexes.",
            "speech_language": "en-IN",
        }
        r1 = client.post(f"/api/v1/interview/{session_id}/answer", data=payload)
        self.assertEqual(r1.status_code, 200, f"First submit failed: {r1.text}")

        # Second submit of same question should not 400 — idempotent
        r2 = client.post(f"/api/v1/interview/{session_id}/answer", data=payload)
        self.assertEqual(r2.status_code, 200, f"Second submit (idempotent) should return 200 but got: {r2.text}")
        # Both should return the same answer_id
        self.assertEqual(r1.json()["answer_id"], r2.json()["answer_id"])

    def test_my_name_is_sam_submitted_once(self):
        """Prove that text 'My name is Sam' submitted once is stored exactly once."""
        session_id, q1_id = self._start_session_and_get_q1()
        payload = {
            "question_id": q1_id,
            "answer_text": "My name is Sam.",
            "speech_language": "en-IN",
        }
        r = client.post(f"/api/v1/interview/{session_id}/answer", data=payload)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        # Transcript must not be double-duplicated by the backend
        self.assertEqual(data["transcript"].count("My name is Sam"), 1)

    def test_missing_answer_raises_400(self):
        session_id, q1_id = self._start_session_and_get_q1()
        # No answer_text, no audio_file → 400
        r = client.post(f"/api/v1/interview/{session_id}/answer", data={"question_id": q1_id})
        self.assertEqual(r.status_code, 400)


class TestDeDuplicationLogicPython(unittest.TestCase):
    """Python-side equivalents of the JS collapseRepeatedPhrases tests."""

    def test_no_duplication_passthrough(self):
        self.assertEqual(fix_transcript("My name is Sam."), "My name is Sam.")

    def test_exact_duplicate_phrase_collapsed(self):
        r = fix_transcript("hash table hash table")
        self.assertEqual(r.lower(), "hash table")

    def test_triplicate_collapsed_to_single(self):
        r = fix_transcript("hello world hello world hello world")
        self.assertEqual(r.lower(), "hello world")

    def test_non_repeated_preserved(self):
        r = fix_transcript("binary search is O log n in a sorted array")
        self.assertIn("binary search", r.lower())
        self.assertIn("sorted array", r.lower())

    def test_repeated_sentence_with_punctuation_collapsed(self):
        r = fix_transcript("My name is Sam. My name is Sam.")
        self.assertEqual(r.lower().rstrip("."), "my name is sam")

    def test_repeated_sentence_one_with_period_one_without(self):
        r = fix_transcript("My name is Sam My name is Sam.")
        self.assertEqual(r.lower().rstrip("."), "my name is sam")


if __name__ == "__main__":
    unittest.main()
