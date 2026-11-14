import io
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def _start_session():
    start_payload = {
        "name": "Abhinav Candidate",
        "email": f"flow_test_{uuid.uuid4().hex[:8]}@example.com",
        "job_role": "Backend Engineer",
        "experience_years": 3,
        "skills": ["Python", "FastAPI", "PostgreSQL"],
    }
    r = client.post("/api/v1/interview/start", json=start_payload)
    assert r.status_code == 200, f"Interview start failed: {r.text}"
    session_id = r.json()["session_id"]

    state_res = client.get(f"/api/v1/interview/{session_id}/state")
    assert state_res.status_code == 200
    state = state_res.json()
    q1_id = state["current_question"]["question_id"]
    return session_id, q1_id


def test_transcript_to_answer_endpoint_flow():
    """
    Test Problem B path: transcript captured from candidate -> bound to answer payload -> /answer request -> saved.
    Ensures that spoken answer sent as answer_text reaches the /answer endpoint,
    is saved without duplication, and behaves idempotently on resubmission.
    """
    session_id, question_id = _start_session()

    spoken_answer = "My name is Abhinav and I have extensive experience building scalable APIs with FastAPI and PostgreSQL."
    payload = {
        "question_id": question_id,
        "answer_text": spoken_answer,
        "speech_language": "en-IN",
    }
    answer_res = client.post(f"/api/v1/interview/{session_id}/answer", data=payload)
    assert answer_res.status_code == 200
    ans_data = answer_res.json()

    assert ans_data["session_id"] == session_id
    assert ans_data["question_id"] == question_id
    assert ans_data["transcript"] == spoken_answer
    assert ans_data["overall_score"] is not None
    assert "X-Request-ID" in answer_res.headers

    # Idempotent resubmission check
    resubmit_res = client.post(f"/api/v1/interview/{session_id}/answer", data=payload)
    assert resubmit_res.status_code == 200
    assert resubmit_res.json()["answer_id"] == ans_data["answer_id"]


def test_empty_string_answer_returns_422_json():
    """
    Submitting an empty or blank answer must return 422 with structured JSON.
    """
    session_id, question_id = _start_session()

    res = client.post(
        f"/api/v1/interview/{session_id}/answer",
        data={"question_id": question_id, "answer_text": "    ", "speech_language": "en-IN"},
    )
    assert res.status_code == 422
    data = res.json()
    assert "detail" in data
    assert data["code"] == "HTTP_422"
    assert "empty" in data["detail"].lower()


def test_missing_answer_fields_returns_400_json():
    """
    Submitting with neither answer_text nor audio_file returns 400 with structured JSON.
    """
    session_id, question_id = _start_session()

    bad_res = client.post(f"/api/v1/interview/{session_id}/answer", data={"question_id": question_id})
    assert bad_res.status_code == 400
    data = bad_res.json()
    assert "detail" in data
    assert data["code"] == "HTTP_400"


def test_audio_and_video_upload_with_fallback():
    """
    Submitting multipart audio and video files does not crash with 500 NameError or plain text.
    Fails over safely to answer_text when audio file has corrupt/untranscribable bytes.
    """
    session_id, question_id = _start_session()

    dummy_audio = b"\x1a\x45\xdf\xa3" + b"\x00" * 300
    dummy_video = b"\x1a\x45\xdf\xa3" + b"\x00" * 300

    payload = {
        "question_id": question_id,
        "answer_text": "I used Python and FastAPI to build async services with PostgreSQL.",
        "speech_language": "en-IN",
    }
    files = {
        "audio_file": ("answer.webm", io.BytesIO(dummy_audio), "audio/webm"),
        "video_file": ("answer.webm", io.BytesIO(dummy_video), "video/webm"),
    }
    res = client.post(f"/api/v1/interview/{session_id}/answer", data=payload, files=files)
    assert res.status_code == 200
    data = res.json()
    assert data["transcript"] == "I used Python and FastAPI to build async services with PostgreSQL."
    assert "answer_id" in data


def test_global_exception_handler_returns_json_never_plain_text():
    """
    Verify that 404, 422, and other errors return JSON with detail and code, never plain text.
    """
    # 404 on nonexistent route
    res = client.get("/api/v1/nonexistent-endpoint-xyz")
    assert res.status_code == 404
    assert res.headers["content-type"].startswith("application/json")
    data = res.json()
    assert "detail" in data
    assert data["code"] == "HTTP_404"


def test_submit_interview_with_background_webhook():
    """
    Verify that submit endpoint generates evaluation report and schedules webhook in BackgroundTasks.
    """
    session_id, question_id = _start_session()
    # First submit an answer
    ans_res = client.post(
        f"/api/v1/interview/{session_id}/answer",
        data={
            "question_id": question_id,
            "answer_text": "FastAPI is a modern, fast web framework for building APIs with Python.",
            "speech_language": "en-IN",
        },
    )
    assert ans_res.status_code == 200

    # Submit interview
    submit_res = client.post(f"/api/v1/interview/{session_id}/submit?tab_switches=0&integrity_score=100")
    assert submit_res.status_code == 200
    report = submit_res.json()
    assert "overall_score" in report
    assert "technical_score" in report
    assert "learning_plan" in report
