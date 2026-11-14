import io
import os
import uuid
import pytest
from fastapi.testclient import TestClient
import docx
from pypdf import PdfWriter

from app.main import app
from app.database.session import SessionLocal
from app.models.resume import Resume
from app.models.candidate import Candidate

client = TestClient(app, raise_server_exceptions=False)


def _make_valid_pdf(text: str = "Candidate Name: Jane Doe\nEmail: jane.doe@example.com\nSkills: Python, FastAPI, Docker, SQL\nExperience: 3 years of experience in backend development.") -> bytes:
    """Create a minimal valid PDF with a selectable text stream."""
    stream_content = f"BT /F1 12 Tf 50 700 Td ({text.replace('\n', ') Tj 0 -15 Td (')}) Tj ET".encode("latin-1")
    pdf_bytes = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj
4 0 obj
<< /Length """ + str(len(stream_content)).encode("ascii") + b""" >>
stream
""" + stream_content + b"""
endstream
endobj
5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000244 00000 n
0000000350 00000 n
trailer
<< /Size 6 /Root 1 0 R >>
startxref
450
%%EOF"""
    return pdf_bytes


def _make_valid_docx(name: str = "John Developer", email: str = "john.dev@example.com", skills: list = None) -> bytes:
    """Create a valid DOCX file using python-docx."""
    if skills is None:
        skills = ["Python", "FastAPI", "PostgreSQL", "Docker", "Git"]
    doc = docx.Document()
    doc.add_heading(name, 0)
    doc.add_paragraph(f"Email: {email} | Phone: +1-555-0199")
    doc.add_heading("Education", level=1)
    doc.add_paragraph("B.Tech in Computer Science - Stanford University")
    doc.add_heading("Technical Skills", level=1)
    doc.add_paragraph(", ".join(skills))
    doc.add_heading("Experience", level=1)
    doc.add_paragraph("2 years of experience building REST APIs and microservices.")
    doc.add_heading("Projects", level=1)
    doc.add_paragraph("AI Mock Interview Platform: Built with FastAPI, PostgreSQL, and WebSockets.")

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _make_scanned_pdf() -> bytes:
    """Create a PDF with no extractable text stream (simulating a pure scanned image PDF)."""
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_upload_valid_pdf():
    """Test uploading a valid PDF resume extracts text and creates DB records."""
    pdf_bytes = _make_valid_pdf()
    files = {"resume_file": ("jane_doe_resume.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    res = client.post("/api/v1/candidates/resume/upload-public", files=files)
    assert res.status_code == 200, f"Upload failed: {res.text}"

    data = res.json()
    assert "resume_id" in data
    assert "candidate_id" in data
    assert data["filename"].endswith(".pdf")
    assert data["extracted_chars"] > 0
    assert data["status"] == "ready"
    assert "parsed_fields" in data
    assert "Python" in data["skills"] or "FastAPI" in data["skills"]


def test_upload_valid_docx():
    """Test uploading a valid DOCX resume extracts text, skills, and education."""
    docx_bytes = _make_valid_docx()
    files = {
        "resume_file": (
            "john_developer.docx",
            io.BytesIO(docx_bytes),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }
    res = client.post("/api/v1/candidates/resume/upload-public", files=files)
    assert res.status_code == 200, f"DOCX upload failed: {res.text}"

    data = res.json()
    assert data["status"] == "ready"
    assert data["extracted_chars"] > 0
    assert "John Developer" in data["name"]
    assert "john.dev@example.com" in data["email"]
    assert any("python" in s.lower() for s in data["skills"])


def test_upload_valid_txt():
    """Test uploading a valid plain text resume."""
    txt_content = (
        "Alice Engineer\n"
        "Email: alice@engineer.org\n"
        "Education: Bachelor of Science in Computer Science\n"
        "Skills: Java, Spring Boot, MySQL, Kubernetes, Docker\n"
        "Experience: 4 years of experience as a Backend Software Engineer."
    ).encode("utf-8")
    files = {"resume_file": ("alice_resume.txt", io.BytesIO(txt_content), "text/plain")}
    res = client.post("/api/v1/candidates/resume/upload-public", files=files)
    assert res.status_code == 200, f"TXT upload failed: {res.text}"

    data = res.json()
    assert data["status"] == "ready"
    assert data["extracted_chars"] > 0
    assert "Alice" in data["name"]
    assert "alice@engineer.org" in data["email"]


def test_upload_empty_file():
    """Test that a 0-byte file returns 400 JSON error."""
    files = {"resume_file": ("empty.pdf", io.BytesIO(b""), "application/pdf")}
    res = client.post("/api/v1/candidates/resume/upload-public", files=files)
    assert res.status_code == 400
    assert res.headers["content-type"].startswith("application/json")
    data = res.json()
    assert "detail" in data
    assert "empty" in data["detail"].lower()


def test_upload_wrong_file_type():
    """Test that an unsupported file extension returns 400 JSON error."""
    files = {"resume_file": ("malicious.exe", io.BytesIO(b"MZ\x90\x00\x03\x00\x00\x00"), "application/x-msdownload")}
    res = client.post("/api/v1/candidates/resume/upload-public", files=files)
    assert res.status_code == 400
    assert res.headers["content-type"].startswith("application/json")
    data = res.json()
    assert "unsupported" in data["detail"].lower()


def test_upload_oversized_file():
    """Test that a file > 5MB returns 413 JSON error."""
    large_bytes = b"%PDF-1.4 " + b"0" * (6 * 1024 * 1024)
    files = {"resume_file": ("huge_resume.pdf", io.BytesIO(large_bytes), "application/pdf")}
    res = client.post("/api/v1/candidates/resume/upload-public", files=files)
    assert res.status_code == 413
    assert res.headers["content-type"].startswith("application/json")
    data = res.json()
    assert "5 mb" in data["detail"].lower() or "too large" in data["detail"].lower()


def test_upload_scanned_pdf_without_text():
    """Test that a blank/scanned PDF without standard extractable text is handled gracefully without 422 crash."""
    blank_pdf = _make_scanned_pdf()
    files = {"resume_file": ("scanned_blank.pdf", io.BytesIO(blank_pdf), "application/pdf")}
    res = client.post("/api/v1/candidates/resume/upload-public", files=files)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/json")
    data = res.json()
    assert data["status"] == "ready"
    assert "candidate_id" in data
    assert data["name"]


def test_upload_user_resume_file():
    """Test uploading the exact user resume that previously triggered stream EOF / 422."""
    resume_path = os.path.join("uploads", "resumes", "c3cc8ffc_G_Abhinav_Reddy_Resume.pdf")
    if os.path.exists(resume_path):
        with open(resume_path, "rb") as f:
            pdf_bytes = f.read()
        files = {"resume_file": ("G_Abhinav_Reddy_Resume.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
        res = client.post("/api/v1/candidates/resume/upload-public", files=files)
        assert res.status_code == 200
        data = res.json()
        assert "Abhinav" in data["name"]
        assert len(data["skills"]) > 0
        assert data["status"] == "ready"


def test_upload_duplicate_idempotent():
    """Test that re-uploading the exact same resume is idempotent and returns the existing record."""
    docx_bytes = _make_valid_docx(name="Idempotent Candidate", email=f"idem_{uuid.uuid4().hex[:6]}@example.com")
    files1 = {
        "resume_file": (
            "idempotent_test.docx",
            io.BytesIO(docx_bytes),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }
    res1 = client.post("/api/v1/candidates/resume/upload-public", files=files1)
    assert res1.status_code == 200
    data1 = res1.json()
    resume_id1 = data1["resume_id"]

    # Re-upload same bytes
    files2 = {
        "resume_file": (
            "idempotent_test.docx",
            io.BytesIO(docx_bytes),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }
    res2 = client.post("/api/v1/candidates/resume/upload-public", files=files2)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["resume_id"] == resume_id1
    assert "already uploaded" in data2.get("message", "").lower() or data2["candidate_id"] == data1["candidate_id"]


def test_end_to_end_resume_to_question_generation():
    """
    End-to-End Test:
    1. Upload resume with specific technical skills & education.
    2. Candidate profile is created/linked.
    3. Start interview with candidate_id.
    4. Verify session questions adaptively incorporate candidate's role and skills.
    5. Fetch next question.
    """
    unique_email = f"e2e_{uuid.uuid4().hex[:8]}@testdomain.com"
    docx_bytes = _make_valid_docx(
        name="E2E Fullstack Engineer",
        email=unique_email,
        skills=["React", "Node", "FastAPI", "PostgreSQL", "Docker", "GraphQL"],
    )
    upload_res = client.post(
        "/api/v1/candidates/resume/upload-public",
        files={"resume_file": ("fullstack_resume.docx", io.BytesIO(docx_bytes), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        data={"job_role": "Fullstack Engineer"},
    )
    assert upload_res.status_code == 200
    upload_data = upload_res.json()
    candidate_id = upload_data["candidate_id"]

    # Start Interview using candidate_id
    start_payload = {
        "candidate_id": candidate_id,
        "name": upload_data["name"],
        "email": upload_data["email"],
        "job_role": upload_data["job_role"],
        "experience_years": upload_data["experience_years"],
        "skills": upload_data["skills"],
        "resume_summary": upload_data.get("resume_summary", ""),
    }
    start_res = client.post("/api/v1/interview/start", json=start_payload)
    assert start_res.status_code == 200, f"Interview start failed: {start_res.text}"
    start_data = start_res.json()
    session_id = start_data["session_id"]
    assert start_data["total_questions"] >= 1

    # Fetch next question
    q_res = client.get(f"/api/v1/interview/{session_id}/next-question")
    assert q_res.status_code == 200
    q_data = q_res.json()
    assert "question_text" in q_data
    assert len(q_data["question_text"]) > 10


def test_resume_status_endpoint():
    """Test retrieving status of an uploaded resume via GET /resume/{resume_id}/status."""
    pdf_bytes = _make_valid_pdf()
    upload_res = client.post(
        "/api/v1/candidates/resume/upload-public",
        files={"resume_file": ("status_test.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert upload_res.status_code == 200
    resume_id = upload_res.json()["resume_id"]

    status_res = client.get(f"/api/v1/candidates/resume/{resume_id}/status")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["resume_id"] == resume_id
    assert status_data["status"] == "ready"
    assert status_data["extracted_chars"] > 0
    assert "parsed_fields" in status_data

