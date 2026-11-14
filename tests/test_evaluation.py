import unittest

from app.services.evaluation import evaluate_answer


class EvaluationTests(unittest.TestCase):
    def test_empty_answer_scores_zero(self):
        result = evaluate_answer("", ["binary search"], 30)
        self.assertEqual(result["overall_score"], 0.0)

    def test_phrase_matching_requires_concept_tokens(self):
        result = evaluate_answer(
            "I would use a binary tree and explain the lookup steps clearly.",
            ["binary search", "time complexity"],
            35,
        )
        self.assertEqual(result["keyword_score"], 0.0)
        self.assertEqual(result["similarity_score"], 25.0)

    def test_complete_relevant_answer_outscores_long_irrelevant_answer(self):
        keywords = ["hash table", "collision", "time complexity"]
        relevant = (
            "A hash table stores keys in buckets. A collision occurs when keys map "
            "to the same bucket, so I would use chaining. Average lookup time "
            "complexity is O one, although a poor hash function can degrade it."
        )
        irrelevant = " ".join(["I enjoy teamwork and learning from projects."] * 45)
        self.assertGreater(
            evaluate_answer(relevant, keywords, 45)["overall_score"],
            evaluate_answer(irrelevant, keywords, 45)["overall_score"],
        )

    def test_scores_stay_within_public_range(self):
        result = evaluate_answer("database indexing improves query efficiency", ["database indexing"], 10000)
        self.assertTrue(all(0.0 <= score <= 100.0 for score in result.values()))


if __name__ == "__main__":
    unittest.main()
