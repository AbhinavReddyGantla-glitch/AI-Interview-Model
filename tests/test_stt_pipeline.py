"""Unit tests for the Layered STT pipeline (Layers 1-7)."""

import unittest
from app.services.speech_audio import compute_audio_hash, preprocess_audio
from app.services.speech_engine import STTResult, WordConfidence, get_stt_engine
from app.services.speech_vocab import (
    apply_vocabulary_corrections,
    build_interview_vocabulary,
    double_metaphone,
    soundex,
)
from app.services.speech import fix_transcript


class STTPipelineTests(unittest.TestCase):
    def test_audio_hash_deterministic(self):
        h1 = compute_audio_hash(b"hello world 123")
        h2 = compute_audio_hash(b"hello world 123")
        h3 = compute_audio_hash(b"different audio")
        self.assertEqual(h1, h2)
        self.assertNotEqual(h1, h3)

    def test_soundex_encoding(self):
        # Soundex for Indian and English names
        self.assertEqual(soundex("Robert"), soundex("Rupert"))
        self.assertTrue(len(soundex("Abhinav")) == 4)
        self.assertTrue(soundex("Abhinav").startswith("A"))

    def test_double_metaphone_encoding(self):
        p, a = double_metaphone("Smith")
        self.assertTrue(len(p) > 0)
        p2, a2 = double_metaphone("Smyth")
        self.assertEqual(p, p2)

    def test_vocabulary_builder(self):
        terms, term_map = build_interview_vocabulary(
            candidate_name="Abhinav Sharma",
            university="Sreenidhi Institute",
            job_role="Backend Developer",
            skills=["Python", "FastAPI"],
            question_text="How do you handle database transactions in PostgreSQL?",
        )
        self.assertIn("Abhinav", terms)
        self.assertIn("Sharma", terms)
        self.assertIn("Python", terms)
        self.assertIn("FastAPI", terms)
        self.assertIn("PostgreSQL", terms)

    def test_observed_bad_sample_regression(self):
        """Regression test for the observed bad transcript:

        Input: 'My name is Avino. I'm University. I'm currently pursuing my PhD. My name is Abino I am from screen University I'm currently posting with degrees'
        Expected: exactly one clean sentence with candidate name Abhinav and Sreenidhi University.
        """
        raw = (
            "My name is Avino. I'm University. I'm currently pursuing my PhD. "
            "My name is Abino I am from screen University I'm currently posting with degrees"
        )
        fixed, _ = apply_vocabulary_corrections(raw, candidate_name="Abhinav")
        final = fix_transcript(fixed, candidate_name="Abhinav")

        self.assertEqual(
            final,
            "My name is Abhinav I am from Sreenidhi University I'm currently pursuing my degree",
        )
        self.assertEqual(final.lower().count("my name is"), 1)
        self.assertNotIn("avino", final.lower())
        self.assertNotIn("abino", final.lower())
        self.assertNotIn("screen", final.lower())
        self.assertNotIn("posting", final.lower())

    def test_high_confidence_common_words_preserved(self):
        raw = "I designed scalable microservices using PostgreSQL and Python."
        fixed, changes = apply_vocabulary_corrections(
            raw,
            candidate_name="Abhinav",
            vocabulary={"pursuing", "degree"},
            word_confidences=[
                {"word": "using", "confidence": 0.95},
                {"word": "microservices", "confidence": 0.90},
            ],
        )
        self.assertIn("using", fixed)
        self.assertIn("scalable microservices", fixed)

    def test_engine_factory(self):
        whisper_engine = get_stt_engine("whisper")
        self.assertIsNotNone(whisper_engine)
        deepgram_engine = get_stt_engine("deepgram")
        self.assertIsNotNone(deepgram_engine)
        azure_engine = get_stt_engine("azure")
        self.assertIsNotNone(azure_engine)


if __name__ == "__main__":
    unittest.main()

