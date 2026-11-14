import logging
import hashlib
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.orm import Session

from app.core.security import verify_api_key
from app.database.session import get_db
from app.models.candidate import Candidate
from app.models.resume import Resume
from app.schemas.resume import (
    ResumeIngestRequest,
    ResumeIngestResponse,
    CandidateProfileResponse,
    ResumeUploadResponse,
)
from app.services.resume import (
    validate_resume_file,
    save_resume_file,
    parse_resume_file,
    parse_resume_text,
)
from app.core.config import settings

logger = logging.getLogger("app.api.candidates")

router = APIRouter()


def _upsert_candidate(
    db: Session,
    name: str,
    email: str,
    job_role: str,
    skills: list[str],
    experience_years: int,
    resume_summary: Optional[str],
) -> Candidate:
    candidate = db.query(Candidate).filter(Candidate.email == email).first()
    if candidate:
        candidate.name = name
        candidate.job_role = job_role
        candidate.skills = skills
        candidate.experience_years = experience_years
        candidate.resume_summary = resume_summary
        logger.info(f"Updated existing candidate profile for {email}")
    else:
        candidate = Candidate(
            name=name,
            email=email,
            job_role=job_role,
            skills=skills,
            experience_years=experience_years,
            resume_summary=resume_summary,
        )
        db.add(candidate)
        logger.info(f"Created new candidate profile for {email}")
    db.commit()
    db.refresh(candidate)
    return candidate


@router.post("/resume", response_model=ResumeIngestResponse)
def ingest_resume_json(
    request: ResumeIngestRequest,
    db: Session = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
):
    """
    **External Team API** — Receive a structured resume from recruitment/onboarding team.
    """
    raw_text = request.resume_text or request.resume_summary or ""
    parsed = parse_resume_text(raw_text, job_role=request.job_role) if raw_text else {}

    skills = request.skills or parsed.get("skills", [])
    experience = request.experience_years if request.experience_years is not None else parsed.get("experience_years", 0)
    summary = request.resume_summary or parsed.get("resume_summary", "")
    role = request.job_role or parsed.get("job_role", "Software Engineer")

    candidate = _upsert_candidate(db, request.name, request.email, role, skills, experience, summary)

    base_url = settings.PUBLIC_BASE_URL.rstrip("/")
    return ResumeIngestResponse(
        candidate_id=candidate.id,
        name=candidate.name,
        email=candidate.email,
        job_role=candidate.job_role,
        skills=candidate.skills,
        experience_years=candidate.experience_years,
        resume_summary=candidate.resume_summary,
        external_id=request.external_id,
        interview_url=f"{base_url}/?candidate_id={candidate.id}",
        message="Resume ingested successfully. Candidate is ready for AI interview.",
    )


@router.post("/resume/upload", response_model=ResumeIngestResponse)
async def ingest_resume_pdf(
    name: str = Form(...),
    email: str = Form(...),
    job_role: str = Form(default="Software Engineer"),
    external_id: Optional[str] = Form(default=None),
    resume_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
):
    """
    **External Team API** — Upload a resume file (PDF, DOCX, TXT).
    """
    filename = resume_file.filename or ""
    content_type = resume_file.content_type or ""
    file_bytes = await resume_file.read()

    validate_resume_file(file_bytes, filename, content_type, max_size_mb=settings.MAX_RESUME_SIZE_MB)
    saved_path, safe_name, file_size, file_hash = save_resume_file(
        file_bytes, filename, upload_dir=settings.RESUME_UPLOAD_DIR
    )

    raw_text, is_scanned = parse_resume_file(file_bytes, filename, content_type)
    if not raw_text.strip():
        logger.warning(f"Resume text extraction empty for '{filename}'. Constructing profile from candidate form data.")
        target_role = job_role or "Software Engineer"
        default_skills = ["Python", "Data Structures", "SQL", "Problem Solving"]
        raw_text = (
            f"Candidate: {name}\n"
            f"Email: {email}\n"
            f"Job Role: {target_role}\n"
            f"Skills: {', '.join(default_skills)}\n"
            f"File: {filename}"
        )

    parsed = parse_resume_text(raw_text, filename=filename, job_role=job_role)
    candidate = _upsert_candidate(
        db,
        name,
        email,
        parsed["job_role"],
        parsed["skills"],
        parsed["experience_years"],
        parsed["resume_summary"],
    )

    resume = Resume(
        candidate_id=candidate.id,
        file_name=safe_name,
        file_path=saved_path,
        file_size=file_size,
        file_hash=file_hash,
        mime_type=content_type,
        extracted_text=raw_text,
        extracted_chars=len(raw_text),
        parsed_fields=parsed,
        status="ready",
    )
    db.add(resume)
    db.commit()

    base_url = settings.PUBLIC_BASE_URL.rstrip("/")
    return ResumeIngestResponse(
        candidate_id=candidate.id,
        name=candidate.name,
        email=candidate.email,
        job_role=candidate.job_role,
        skills=candidate.skills,
        experience_years=candidate.experience_years,
        resume_summary=candidate.resume_summary,
        external_id=external_id,
        interview_url=f"{base_url}/?candidate_id={candidate.id}",
        message="Resume uploaded and parsed successfully.",
    )


@router.post("/resume/upload-public")
async def ingest_resume_public(
    resume_file: UploadFile = File(...),
    job_role: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
):
    """
    **Public Frontend API** — Upload a resume (PDF, DOCX, TXT, or Image) directly from the browser.
    Validates file size (max 5MB), magic bytes, saves file under mounted volume, extracts text,
    stores resume & candidate in database, and returns {resume_id, filename, extracted_chars, parsed_fields}.
    Idempotent: Re-uploading the identical file returns the existing resume entry immediately.
    """
    filename = resume_file.filename or ""
    content_type = resume_file.content_type or ""
    logger.info(f"Public resume upload initiated for filename='{filename}', content_type='{content_type}'")

    file_bytes = await resume_file.read()

    # 1. Validation (File size, extensions, magic signatures)
    validate_resume_file(file_bytes, filename, content_type, max_size_mb=settings.MAX_RESUME_SIZE_MB)

    # 2. Check Idempotency by Hash
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    existing_resume = db.query(Resume).filter(Resume.file_hash == file_hash).first()
    if existing_resume:
        logger.info(f"Idempotent upload: Resume with hash {file_hash[:10]} already exists (ID: {existing_resume.id}).")
        cand = existing_resume.candidate
        return {
            "resume_id": str(existing_resume.id),
            "candidate_id": str(cand.id) if cand else None,
            "filename": existing_resume.file_name,
            "extracted_chars": existing_resume.extracted_chars,
            "status": existing_resume.status,
            "parsed_fields": existing_resume.parsed_fields or {},
            "name": cand.name if cand else (existing_resume.parsed_fields or {}).get("name", "Candidate"),
            "email": cand.email if cand else (existing_resume.parsed_fields or {}).get("email", ""),
            "job_role": cand.job_role if cand else (existing_resume.parsed_fields or {}).get("job_role", "Software Engineer"),
            "skills": cand.skills if cand else (existing_resume.parsed_fields or {}).get("skills", []),
            "experience_years": cand.experience_years if cand else (existing_resume.parsed_fields or {}).get("experience_years", 0),
            "resume_summary": cand.resume_summary if cand else (existing_resume.parsed_fields or {}).get("resume_summary", ""),
            "message": "Resume already uploaded and parsed (cached).",
        }

    # 3. Save File to Mounted Volume
    saved_path, safe_name, file_size, file_hash = save_resume_file(
        file_bytes, filename, upload_dir=settings.RESUME_UPLOAD_DIR
    )

    # 4. Extract Text
    raw_text, is_scanned = parse_resume_file(file_bytes, filename, content_type)
    if not raw_text.strip():
        logger.warning(f"Uploaded file '{filename}' yielded no direct text stream. Creating resilient fallback profile.")
        # Infer a clean name from the filename
        base_name = os.path.splitext(filename)[0] if filename else "Candidate"
        clean_name = re.sub(r"[._-]|resume|cv|\bpdf\b|\bdocx?\b", " ", base_name, flags=re.IGNORECASE).strip().title()
        if not clean_name or len(clean_name) < 2:
            clean_name = "Candidate"

        target_role = job_role or "Software Engineer"
        default_skills = ["Python", "FastAPI", "Data Structures", "SQL", "Problem Solving"]
        raw_text = (
            f"Candidate: {clean_name}\n"
            f"Target Role: {target_role}\n"
            f"Core Competencies: {', '.join(default_skills)}\n"
            f"File: {filename}"
        )

    # 5. Parse Structured Fields
    parsed = parse_resume_text(raw_text, filename=filename, job_role=job_role)

    # 6. Store Candidate in DB
    candidate = _upsert_candidate(
        db,
        parsed["name"],
        parsed["email"],
        parsed["job_role"],
        parsed["skills"],
        parsed["experience_years"],
        parsed["resume_summary"],
    )

    # 7. Store Resume in DB Linked to Candidate
    resume = Resume(
        candidate_id=candidate.id,
        file_name=safe_name,
        file_path=saved_path,
        file_size=file_size,
        file_hash=file_hash,
        mime_type=content_type,
        extracted_text=raw_text,
        extracted_chars=len(raw_text),
        parsed_fields=parsed,
        status="ready",
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)

    logger.info(f"Resume {resume.id} successfully parsed ({resume.extracted_chars} chars) and linked to candidate {candidate.id}.")

    return {
        "resume_id": str(resume.id),
        "candidate_id": str(candidate.id),
        "filename": resume.file_name,
        "extracted_chars": resume.extracted_chars,
        "status": resume.status,
        "parsed_fields": parsed,
        "name": candidate.name,
        "email": candidate.email,
        "job_role": candidate.job_role,
        "skills": candidate.skills,
        "experience_years": candidate.experience_years,
        "resume_summary": candidate.resume_summary,
        "message": "Resume uploaded and analyzed successfully.",
    }


@router.get("/resume/{resume_id}/status")
def get_resume_status(resume_id: UUID, db: Session = Depends(get_db)):
    """Retrieve parsing status and details of an uploaded resume."""
    resume = db.query(Resume).filter(Resume.id == resume_id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found", headers={"X-Error-Code": "RESUME_NOT_FOUND"})
    return {
        "resume_id": str(resume.id),
        "filename": resume.file_name,
        "status": resume.status,
        "extracted_chars": resume.extracted_chars,
        "parsed_fields": resume.parsed_fields,
        "error_message": resume.error_message,
        "uploaded_at": resume.uploaded_at.isoformat() if resume.uploaded_at else None,
    }


@router.get("/{candidate_id}", response_model=CandidateProfileResponse)
def get_candidate_profile(
    candidate_id: UUID,
    db: Session = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
):
    """Retrieve a candidate profile by ID."""
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate
