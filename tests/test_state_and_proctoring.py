import unittest
import uuid
from fastapi.testclient import TestClient
from app.main import app
from app.services.vision import analyze_video, _compute_ear
from app.services.gemini import generate_mock_final_report

client = TestClient(app)

class StateAndProctoringTests(unittest.TestCase):
    def test_state_invalid_session_returns_404(self):
        random_uuid = str(uuid.uuid4())
        response = client.get(f"/api/v1/interview/{random_uuid}/state")
        self.assertEqual(response.status_code, 404)

    def test_interview_state_restoration_flow(self):
        # 1. Start an interview
        start_payload = {
            "name": "State Candidate",
            "email": f"state_{uuid.uuid4().hex[:8]}@example.com",
            "job_role": "Backend Engineer",
            "experience_years": 1,
            "skills": ["Python", "FastAPI", "SQL"]
        }
        start_resp = client.post("/api/v1/interview/start", json=start_payload)
        self.assertEqual(start_resp.status_code, 200)
        session_id = start_resp.json()["session_id"]

        # 2. Query state - should be in 'started' status with Question 1 active
        state_resp = client.get(f"/api/v1/interview/{session_id}/state")
        self.assertEqual(state_resp.status_code, 200)
        state_data = state_resp.json()
        self.assertEqual(state_data["session_id"], session_id)
        self.assertEqual(state_data["status"], "started")
        self.assertEqual(state_data["candidate"]["name"], "State Candidate")
        self.assertEqual(state_data["answered_questions"], 0)
        self.assertIsNotNone(state_data["current_question"])
        self.assertEqual(state_data["current_question"]["order"], 1)

        q1_id = state_data["current_question"]["question_id"]

        # 3. Submit an answer for Question 1
        answer_resp = client.post(
            f"/api/v1/interview/{session_id}/answer",
            data={
                "question_id": q1_id,
                "answer_text": "I would use Python and optimize database indexes to ensure O(1) or O(log N) lookup time complexity.",
                "speech_language": "en-IN"
            }
        )
        self.assertEqual(answer_resp.status_code, 200)

        # 4. Query state again - should show 1 answered question and advance to Question 2
        state_resp2 = client.get(f"/api/v1/interview/{session_id}/state")
        self.assertEqual(state_resp2.status_code, 200)
        state_data2 = state_resp2.json()
        self.assertEqual(state_data2["answered_questions"], 1)
        self.assertEqual(len(state_data2["answers"]), 1)
        self.assertEqual(state_data2["answers"][0]["question_id"], q1_id)
        self.assertIsNotNone(state_data2["current_question"])
        self.assertEqual(state_data2["current_question"]["order"], 2)

        # 5. Submit interview with proctoring data
        submit_resp = client.post(
            f"/api/v1/interview/{session_id}/submit?tab_switches=1&integrity_score=98.0"
        )
        self.assertEqual(submit_resp.status_code, 200)

        # 6. Query state after completion - should be 'completed' with full report
        state_resp3 = client.get(f"/api/v1/interview/{session_id}/state")
        self.assertEqual(state_resp3.status_code, 200)
        state_data3 = state_resp3.json()
        self.assertEqual(state_data3["status"], "completed")
        self.assertTrue(state_data3["is_complete"])
        self.assertIsNotNone(state_data3["report"])
        self.assertIn("overall_score", state_data3["report"])

    def test_vision_proctoring_debug_events_and_tolerance(self):
        result = analyze_video("non_existent_file.webm")
        self.assertIn("eye_contact_score", result)
        self.assertIn("attention_score", result)
        self.assertIn("face_visibility_score", result)
        self.assertIn("proctoring_debug_events", result)
        self.assertGreaterEqual(result["eye_contact_score"], 85.0)

        # Verify debug event schema
        events = result["proctoring_debug_events"]
        self.assertTrue(len(events) > 0)
        ev = events[0]
        self.assertIn("event", ev)
        self.assertIn("confidence", ev)
        self.assertIn("duration_sec", ev)
        self.assertIn("severity", ev)
        self.assertIn("penalty", ev)
        self.assertIn("reason", ev)

    def test_report_integrity_score_tolerance(self):
        candidate_info = {"name": "Test", "job_role": "Developer"}
        answers = [{"overall_score": 85.0}]
        global_metrics = {"eye_contact_score": 95.0, "attention_score": 95.0}

        # Candidate with minor tab switch (score 98%)
        report = generate_mock_final_report(
            candidate_info,
            answers,
            global_metrics,
            proctoring_metrics={"tab_switches": 1, "integrity_score": 98.0}
        )
        self.assertGreaterEqual(report["overall_score"], 80.0)
        self.assertIn("High exam integrity", report["integrity_verdict"])


if __name__ == "__main__":
    unittest.main()
