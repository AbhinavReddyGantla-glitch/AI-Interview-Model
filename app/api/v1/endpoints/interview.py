import os
import shutil
import hashlib
import tempfile
import logging
from uuid import UUID
import asyncio
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, WebSocket, WebSocketDisconnect, BackgroundTasks
from sqlalchemy.orm import Session
import websockets

from app.core.config import settings

from app.database.session import get_db
from app.models.candidate import Candidate
from app.models.session import InterviewSession, SessionQuestion
from app.models.question import QuestionBank
from app.models.answer import CandidateAnswer
from app.models.cache import InterviewTemplateCache
from app.models.report import EvaluationReport
from app.models.score import InterviewScore

from app.core.security import verify_api_key
from app.schemas.interview import (
    InterviewStartRequest,
    InterviewStartResponse,
    QuestionResponse,
    AnswerSubmitResponse,
    SessionStatusResponse,
    SessionStateResponse,
    CandidateAnswerItem,
)
from app.schemas.evaluation import EvaluationReportResponse

from app.services.gemini import generate_adaptive_questions, generate_final_report, evaluate_answer_with_gemini
from app.services.speech import transcribe_audio, transcribe_pipeline
from app.services.evaluation import evaluate_answer
from app.services.vision import analyze_video
from app.services.webhook import send_external_evaluation
from app.services.interview_timing import (
    should_end_interview,
    compute_interview_elapsed,
    compute_dynamic_duration,
    MIN_DURATION_SEC,
    MAX_DURATION_SEC,
)

logger = logging.getLogger("app.api.interview")

router = APIRouter()


def compute_fingerprint(job_role: str, experience_years: int, skills: list[str], resume_summary: Optional[str]) -> str:
    """
    Computes a deterministic fingerprint of candidate details to look up in cache.
    """
    norm_role = job_role.lower().strip()
    norm_skills = ",".join(sorted([s.lower().strip() for s in skills]))
    norm_summary = (resume_summary or "").lower().strip()
    content = f"{norm_role}|{experience_years}|{norm_skills}|{norm_summary}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

@router.post("/start", response_model=InterviewStartResponse)
def start_interview(
    request: InterviewStartRequest,
    db: Session = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
):
    """
    Starts a new interview session.
    Accepts either a full candidate profile OR a pre-ingested candidate_id from the resume API.
    Uses fingerprinting to check if questions exist in the InterviewTemplateCache.
    """
    # 0. Resolve candidate from pre-ingested profile or inline registration
    if request.candidate_id:
        candidate = db.query(Candidate).filter(Candidate.id == request.candidate_id).first()
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found. Ingest resume first via /candidates/resume.")
    else:
        if not request.name or not request.email or not request.job_role:
            raise HTTPException(
                status_code=400,
                detail="Provide candidate_id OR name, email, and job_role to start an interview.",
            )
        candidate = db.query(Candidate).filter(Candidate.email == request.email).first()
        if candidate:
            logger.info(f"Existing candidate found for email {request.email}. Updating details.")
            candidate.name = request.name
            candidate.resume_summary = request.resume_summary
            candidate.skills = request.skills
            candidate.experience_years = request.experience_years
            candidate.job_role = request.job_role
        else:
            logger.info(f"Creating new candidate for email {request.email}.")
            candidate = Candidate(
                name=request.name,
                email=request.email,
                resume_summary=request.resume_summary,
                skills=request.skills,
                experience_years=request.experience_years,
                job_role=request.job_role,
            )
            db.add(candidate)
        db.commit()
        db.refresh(candidate)
    # Generate fresh randomized questions using Gemini or extensive randomized fallback
    logger.info(f"Generating fresh randomized questions for candidate {candidate.name} ({candidate.job_role}).")
    questions_list = generate_adaptive_questions(
        candidate.job_role,
        candidate.experience_years,
        candidate.skills,
        resume_summary=candidate.resume_summary,
        num_questions=10,
    )

    # 3. Create interview session
    session = InterviewSession(
        candidate_id=candidate.id,
        status="started"
    )
    db.add(session)
    db.commit()
    db.refresh(session)


    # 4. Link questions to this session via SessionQuestion
    order = 1
    for q_data in questions_list:
        # Check if question text already exists in question bank to avoid duplicates
        q_bank_entry = db.query(QuestionBank).filter(
            QuestionBank.question_text == q_data["question_text"]
        ).first()
        
        if not q_bank_entry:
            q_bank_entry = QuestionBank(
                question_text=q_data["question_text"],
                difficulty=q_data.get("difficulty", "medium"),
                expected_keywords=q_data.get("expected_keywords", []),
                category=q_data.get("category", "technical"),
                role=candidate.job_role
            )
            db.add(q_bank_entry)
            db.commit()
            db.refresh(q_bank_entry)

        sq = SessionQuestion(
            session_id=session.id,
            question_id=q_bank_entry.id,
            order=order,
            is_answered=False
        )
        db.add(sq)
        order += 1
        
    db.commit()

    total_q = db.query(SessionQuestion).filter(SessionQuestion.session_id == session.id).count()

    return InterviewStartResponse(
        session_id=session.id,
        candidate_id=candidate.id,
        status=session.status,
        reused_from_cache=False,
        total_questions=total_q,
        min_duration_seconds=MIN_DURATION_SEC,
        max_duration_seconds=MAX_DURATION_SEC,
    )


@router.get("/{session_id}/next-question", response_model=QuestionResponse)
def get_next_question(session_id: UUID, db: Session = Depends(get_db)):
    """
    Retrieves the next unanswered question for the interview session.
    """
    session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found")
        
    unanswered_sq = db.query(SessionQuestion).filter(
        SessionQuestion.session_id == session_id,
        SessionQuestion.is_answered == False
    ).order_by(SessionQuestion.order).first()
    
    if not unanswered_sq:
        raise HTTPException(status_code=400, detail="All questions have been answered. Please submit the interview.")

    total_q = db.query(SessionQuestion).filter(SessionQuestion.session_id == session_id).count()
    answers = db.query(CandidateAnswer).filter(CandidateAnswer.session_id == session_id).all()
    elapsed = compute_interview_elapsed(session.created_at, answers)
    min_dur, max_dur, bonus_sec, is_ext = compute_dynamic_duration(answers)

    question = unanswered_sq.question
    return QuestionResponse(
        question_id=question.id,
        question_text=question.question_text,
        difficulty=question.difficulty,
        category=question.category,
        order=unanswered_sq.order,
        total_questions=total_q,
        elapsed_seconds=round(elapsed),
        min_duration_seconds=min_dur,
        max_duration_seconds=max_dur,
        bonus_seconds_added=bonus_sec,
        is_extended=is_ext,
    )

@router.post("/{session_id}/answer", response_model=AnswerSubmitResponse)
def submit_answer(
    session_id: UUID,
    question_id: UUID = Form(...),
    answer_text: Optional[str] = Form(None),
    speech_language: Optional[str] = Form(None),
    audio_file: Optional[UploadFile] = File(None),
    video_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    """
    Submits the answer for a specific question in a session.
    Handles optional Speech-to-Text transcription (Phase 6),
    Rule-Based Evaluation (Phase 7), and Video Metric Processing (Phase 8).
    """
    # 1. Verify session and active question
    session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found")

    sq = db.query(SessionQuestion).filter(
        SessionQuestion.session_id == session_id,
        SessionQuestion.question_id == question_id
    ).first()
    if not sq:
        raise HTTPException(status_code=400, detail="Question is not part of this session")
    if sq.is_answered:
        # Idempotent: return the existing answer instead of erroring on retry/double-click
        existing = db.query(CandidateAnswer).filter(
            CandidateAnswer.session_id == session_id,
            CandidateAnswer.question_id == question_id,
        ).first()
        if existing:
            all_answers = db.query(CandidateAnswer).filter(CandidateAnswer.session_id == session_id).all()
            total_q = db.query(SessionQuestion).filter(SessionQuestion.session_id == session_id).count()
            end_now, timing_meta = should_end_interview(session.created_at, all_answers, total_q)
            logger.info("Idempotent answer submission for session=%s question=%s — returning existing.", session_id, question_id)
            return AnswerSubmitResponse(
                answer_id=existing.id,
                session_id=session_id,
                question_id=question_id,
                transcript=existing.transcript,
                speaking_time_seconds=existing.speaking_time_seconds,
                keyword_score=existing.keyword_score,
                completeness_score=existing.completeness_score,
                similarity_score=existing.similarity_score,
                overall_score=existing.overall_score,
                should_submit=end_now,
                elapsed_seconds=timing_meta["elapsed_seconds"],
                answered_questions=timing_meta["answered_questions"],
                total_questions=total_q,
                min_duration_seconds=timing_meta["min_duration_seconds"],
                max_duration_seconds=timing_meta["max_duration_seconds"],
                bonus_seconds_added=timing_meta.get("bonus_seconds_added", 0),
                is_extended=timing_meta.get("is_extended", False),
                end_reason=timing_meta.get("end_reason"),
                proctoring_debug_events=[],
                raw_transcript=existing.transcript,
                word_confidences=[],
                transcript_changes=[],
            )
        raise HTTPException(status_code=400, detail="Question has already been answered")

    question = sq.question
    transcript = ""
    speaking_time = 30.0  # default simulated speaking time in seconds

    # 2. Audio Processing (Speech-to-Text via pipeline)
    audio_url = None
    raw_transcript = ""
    word_confidences = []
    transcript_changes = []

    if audio_file:
        logger.info(f"Processing audio file: {audio_file.filename}")
        try:
            audio_bytes = audio_file.file.read()
            audio_url = f"/uploads/audio/{session_id}_{question_id}_{audio_file.filename}"
            speaking_time = round(max(5.0, len(audio_bytes) / 32000.0), 2)
            
            candidate_obj = session.candidate
            candidate_name_hint = candidate_obj.name if candidate_obj else None
            university_hint = None
            if candidate_obj and hasattr(candidate_obj, "resumes") and candidate_obj.resumes:
                latest_resume = candidate_obj.resumes[-1]
                if latest_resume and latest_resume.parsed_fields:
                    edu = latest_resume.parsed_fields.get("education", [])
                    if edu and isinstance(edu, list):
                        university_hint = edu[0]

            pipeline_res = transcribe_pipeline(
                audio_bytes,
                content_type=audio_file.content_type or "audio/webm",
                language=speech_language or "en-IN",
                candidate_name=candidate_name_hint,
                university=university_hint or getattr(candidate_obj, "education", None),
                job_role=getattr(candidate_obj, "job_role", None) if candidate_obj else None,
                skills=getattr(candidate_obj, "skills", None) if candidate_obj else None,
                question_text=question.question_text,
            )
            transcript = pipeline_res.get("transcript", "")
            raw_transcript = pipeline_res.get("raw_transcript", "")
            word_confidences = pipeline_res.get("words", [])
            transcript_changes = pipeline_res.get("changes", [])
        except Exception:
            logger.exception("Audio transcription failed in transcribe_pipeline; checking for fallback answer_text")

        if not transcript and answer_text and answer_text.strip():
            logger.info("Using client browser speech transcript fallback: %r", answer_text.strip())
            transcript = answer_text.strip()
            raw_transcript = transcript
            word_count = len(transcript.split())
            speaking_time = round(max(5.0, word_count * 0.45), 2)
        elif not transcript:
            raise HTTPException(
                status_code=422,
                detail="No speech detected in your recording. Please speak clearly into your microphone or type your answer before submitting.",
            )
    elif answer_text and answer_text.strip():
        transcript = answer_text.strip()
        raw_transcript = transcript
        word_confidences = []
        transcript_changes = []
        word_count = len(transcript.split())
        speaking_time = round(max(5.0, word_count * 0.45), 2)
    elif answer_text is not None and not answer_text.strip():
        raise HTTPException(
            status_code=422,
            detail="Answer cannot be empty. Please speak your answer or type it in before submitting.",
        )
    else:
        raise HTTPException(status_code=400, detail="Must provide either answer_text or audio_file")

    # 3. Rule-Based & Gemini Semantic Evaluation
    try:
        eval_metrics = evaluate_answer(transcript, question.expected_keywords, speaking_time)
    except Exception:
        logger.exception("Rule-based evaluate_answer failed; using safe defaults")
        eval_metrics = {
            "overall_score": 60.0,
            "completeness_score": 60.0,
            "keyword_score": 60.0,
            "similarity_score": 60.0,
        }
    
    # Try semantic AI evaluation with Gemini
    try:
        gemini_eval = evaluate_answer_with_gemini(
            question.question_text,
            transcript,
            question.expected_keywords,
            speaking_time
        )
        if gemini_eval:
            # Derive the semantic score from its rubric dimensions
            ai_score = (
                gemini_eval["accuracy_score"] * 0.55
                + gemini_eval["completeness_score"] * 0.25
                + gemini_eval["communication_score"] * 0.20
            )
            ai_completeness = gemini_eval["completeness_score"]
            # Blend semantic judgement with deterministic rubric evidence
            eval_metrics["overall_score"] = round((eval_metrics["overall_score"] * 0.4) + (ai_score * 0.6), 2)
            eval_metrics["completeness_score"] = round((eval_metrics["completeness_score"] * 0.4) + (ai_completeness * 0.6), 2)
    except Exception:
        logger.exception("Gemini semantic evaluation failed; continuing with rule-based metrics")

    # 4. Video Metric Processing
    video_metrics = {
        "eye_contact_score": 50.0,   # Neutral default — no real video analysed
        "attention_score": 50.0,
        "face_visibility_score": 50.0,
        "proctoring_debug_events": [],
    }
    if video_file:
        logger.info(f"Processing video file: {video_file.filename}")
        temp_dir = tempfile.gettempdir()
        file_extension = os.path.splitext(video_file.filename or "")[1].lower()
        if file_extension not in {".mp4", ".webm", ".mov", ".avi"}:
            file_extension = ".mp4"
        temp_path = os.path.join(temp_dir, f"{session_id}_{question_id}_temp_video{file_extension}")
        try:
            with open(temp_path, "wb") as buffer:
                shutil.copyfileobj(video_file.file, buffer)
            video_metrics = analyze_video(temp_path)
        except Exception:
            logger.exception("Video analysis failed in analyze_video; continuing with neutral video metrics")
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    # 5. Save Answer and metrics to database
    candidate_answer = CandidateAnswer(
        session_id=session_id,
        question_id=question_id,
        audio_url=audio_url,
        transcript=transcript,
        speaking_time_seconds=speaking_time,
        eye_contact_score=video_metrics["eye_contact_score"],
        attention_score=video_metrics["attention_score"],
        completeness_score=eval_metrics["completeness_score"],
        similarity_score=eval_metrics["similarity_score"],
        keyword_score=eval_metrics["keyword_score"],
        overall_score=eval_metrics["overall_score"]
    )
    db.add(candidate_answer)
    
    # Mark question as answered
    sq.is_answered = True
    db.commit()
    db.refresh(candidate_answer)

    all_answers = db.query(CandidateAnswer).filter(CandidateAnswer.session_id == session_id).all()
    total_q = db.query(SessionQuestion).filter(SessionQuestion.session_id == session_id).count()
    end_now, timing_meta = should_end_interview(session.created_at, all_answers, total_q)

    # Check if extra questions are needed for extended dynamic time
    if timing_meta.get("needs_extra_questions"):
        candidate = session.candidate
        extra_order = total_q + 1
        new_q_bank = QuestionBank(
            question_text=f"Follow-up: Based on your strong performance, can you explain how you would optimize a core Data Structure or SQL query for better efficiency in your {candidate.job_role} projects?",
            difficulty="medium",
            expected_keywords=["optimization", "time complexity", "indexing", "space complexity", "efficiency"],
            category="btech_deep_dive",
            role=candidate.job_role
        )
        db.add(new_q_bank)
        db.commit()
        db.refresh(new_q_bank)
        extra_sq = SessionQuestion(
            session_id=session_id,
            question_id=new_q_bank.id,
            order=extra_order,
            is_answered=False
        )
        db.add(extra_sq)
        db.commit()
        total_q += 1

    return AnswerSubmitResponse(
        answer_id=candidate_answer.id,
        session_id=session_id,
        question_id=question_id,
        transcript=transcript,
        speaking_time_seconds=speaking_time,
        keyword_score=eval_metrics["keyword_score"],
        completeness_score=eval_metrics["completeness_score"],
        similarity_score=eval_metrics["similarity_score"],
        overall_score=eval_metrics["overall_score"],
        should_submit=end_now,
        elapsed_seconds=timing_meta["elapsed_seconds"],
        answered_questions=timing_meta["answered_questions"],
        total_questions=total_q,
        min_duration_seconds=timing_meta["min_duration_seconds"],
        max_duration_seconds=timing_meta["max_duration_seconds"],
        bonus_seconds_added=timing_meta.get("bonus_seconds_added", 0),
        is_extended=timing_meta.get("is_extended", False),
        end_reason=timing_meta.get("end_reason"),
        proctoring_debug_events=video_metrics.get("proctoring_debug_events", []),
        raw_transcript=raw_transcript,
        word_confidences=word_confidences,
        transcript_changes=transcript_changes,
    )

@router.post("/{session_id}/submit", response_model=EvaluationReportResponse)
def submit_interview(
    session_id: UUID,
    background_tasks: BackgroundTasks,
    tab_switches: int = 0,
    integrity_score: Optional[float] = None,
    proctoring_data: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Submits the final interview session, generates reports using Gemini,
    saves the final EvaluationReport, and triggers external webhook payloads in background.
    """
    session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found")
        
    if session.status == "completed":
        # Report already generated, return existing report
        report = db.query(EvaluationReport).filter(EvaluationReport.session_id == session_id).first()
        if report:
            return report

    # 1. Gather all candidate answers and details
    answers = db.query(CandidateAnswer).filter(CandidateAnswer.session_id == session_id).all()
    if not answers:
        raise HTTPException(status_code=400, detail="Cannot submit interview without any answers")

    candidate = session.candidate
    candidate_info = {
        "name": candidate.name,
        "email": candidate.email,
        "job_role": candidate.job_role,
        "experience_years": candidate.experience_years,
        "skills": candidate.skills,
        "resume_summary": candidate.resume_summary
    }

    answers_payload = []
    total_keyword = 0.0
    total_completeness = 0.0
    total_similarity = 0.0
    total_eye_contact = 0.0
    total_attention = 0.0
    
    for a in answers:
        total_keyword += a.keyword_score
        total_completeness += a.completeness_score
        total_similarity += a.similarity_score
        total_eye_contact += (a.eye_contact_score or 85.0)
        total_attention += (a.attention_score or 90.0)

        answers_payload.append({
            "question_text": a.question.question_text,
            "category": a.question.category,
            "expected_keywords": a.question.expected_keywords,
            "transcript": a.transcript,
            "scores": {
                "keyword_score": a.keyword_score,
                "completeness_score": a.completeness_score,
                "similarity_score": a.similarity_score,
                "overall_score": a.overall_score
            }
        })

    num_answers = len(answers)
    global_metrics = {
        "average_keyword_score": total_keyword / num_answers,
        "average_completeness_score": total_completeness / num_answers,
        "average_similarity_score": total_similarity / num_answers,
        "eye_contact_score": total_eye_contact / num_answers,
        "attention_score": total_attention / num_answers
    }

    parsed_events = []
    if proctoring_data:
        try:
            parsed_events = json.loads(proctoring_data)
        except Exception:
            pass

    # Use duration-aware integrity score from client if provided, else fallback
    if integrity_score is not None:
        calc_integrity = round(max(0.0, min(100.0, float(integrity_score))), 1)
    else:
        calc_integrity = max(50.0, 100.0 - (tab_switches * 10.0))

    proctoring_metrics = {
        "tab_switches": tab_switches,
        "integrity_score": calc_integrity,
        "events": parsed_events
    }

    # 2. Run Gemini Final Evaluation (Phase 12) with resilient fallback
    try:
        report_data = generate_final_report(candidate_info, answers_payload, global_metrics, proctoring_metrics)
    except Exception:
        logger.exception("Final report generation via Gemini failed; using fallback offline generator")
        from app.services.gemini import generate_mock_final_report
        report_data = generate_mock_final_report(candidate_info, answers_payload, global_metrics, proctoring_metrics)

    # 3. Save EvaluationReport to DB
    report = EvaluationReport(
        session_id=session_id,
        overall_score=report_data["overall_score"],
        technical_score=report_data["technical_score"],
        communication_score=report_data["communication_score"],
        strengths=report_data.get("strengths", []),
        weaknesses=report_data.get("weaknesses", []),
        learning_plan=report_data.get("learning_plan", {}),
        recommendations=report_data.get("recommendations", "")
    )
    db.add(report)
    
    # Save category breakdown scores as InterviewScore models
    categories = {}
    for a in answers:
        cat = a.question.category
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(a.overall_score)
        
    for cat, scores in categories.items():
        avg_score = sum(scores) / len(scores)
        db.add(InterviewScore(
            session_id=session_id,
            category=cat,
            score=round(avg_score, 2),
            feedback=f"Candidate scored an average of {avg_score:.2f}% on {cat} questions."
        ))

    # Mark session as completed
    session.status = "completed"
    db.commit()
    db.refresh(report)

    # 4. Trigger Webhook to coaching/improvement team asynchronously via BackgroundTasks
    question_breakdown = []
    for a in answers:
        question_breakdown.append({
            "question_text": a.question.question_text,
            "category": a.question.category,
            "difficulty": a.question.difficulty,
            "transcript": a.transcript,
            "expected_keywords": a.question.expected_keywords,
            "scores": {
                "keyword_score": a.keyword_score,
                "completeness_score": a.completeness_score,
                "similarity_score": a.similarity_score,
                "overall_score": a.overall_score,
                "eye_contact_score": a.eye_contact_score,
                "attention_score": a.attention_score,
            },
        })

    webhook_payload = {
        "event": "interview.completed",
        "session_id": str(session_id),
        "candidate": {
            "id": str(candidate.id),
            "name": candidate.name,
            "email": candidate.email,
            "job_role": candidate.job_role,
            "skills": candidate.skills,
            "experience_years": candidate.experience_years,
            "resume_summary": candidate.resume_summary,
        },
        "scores": {
            "overall_score": report.overall_score,
            "technical_score": report.technical_score,
            "communication_score": report.communication_score,
        },
        "recommendation": report.recommendations,
        "roadmap": report.learning_plan,
        "strengths": report.strengths,
        "weaknesses": report.weaknesses,
        "question_breakdown": question_breakdown,
    }
    try:
        background_tasks.add_task(send_external_evaluation, webhook_payload)
    except Exception:
        logger.exception("Failed to schedule background task for external evaluation webhook")

    return report


@router.get("/{session_id}/state", response_model=SessionStateResponse)
def get_interview_state(session_id: UUID, db: Session = Depends(get_db)):
    """
    Restores complete interview session state for the client after a page refresh.
    Returns candidate info, answers progress, current question, timers, and report if complete.
    """
    session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found")

    candidate = session.candidate
    candidate_data = {
        "candidate_id": str(candidate.id) if candidate else "",
        "name": candidate.name if candidate else "Candidate",
        "email": candidate.email if candidate else "",
        "job_role": candidate.job_role if candidate else "Software Engineer",
        "experience_years": candidate.experience_years if candidate else 0,
        "skills": candidate.skills if candidate else [],
        "resume_summary": candidate.resume_summary if candidate else "",
    }

    session_questions = db.query(SessionQuestion).filter(
        SessionQuestion.session_id == session_id
    ).order_by(SessionQuestion.order).all()

    total_q = len(session_questions)
    answers = db.query(CandidateAnswer).filter(CandidateAnswer.session_id == session_id).all()
    answered_count = len(answers)

    elapsed = compute_interview_elapsed(session.created_at, answers)
    min_dur, max_dur, bonus_sec, is_ext = compute_dynamic_duration(answers)

    # Build answers summary list
    sq_map = {sq.question_id: sq.order for sq in session_questions}
    answers_summary = []
    for a in answers:
        q = a.question
        answers_summary.append(CandidateAnswerItem(
            question_id=a.question_id,
            question_text=q.question_text if q else "",
            order=sq_map.get(a.question_id, 0),
            category=q.category if q else "technical",
            difficulty=q.difficulty if q else "medium",
            transcript=a.transcript,
            speaking_time_seconds=a.speaking_time_seconds,
            overall_score=a.overall_score,
        ))

    # Determine current active question
    current_q = None
    unanswered_sq = db.query(SessionQuestion).filter(
        SessionQuestion.session_id == session_id,
        SessionQuestion.is_answered == False
    ).order_by(SessionQuestion.order).first()

    if unanswered_sq:
        q = unanswered_sq.question
        current_q = QuestionResponse(
            question_id=q.id,
            question_text=q.question_text,
            difficulty=q.difficulty,
            category=q.category,
            order=unanswered_sq.order,
            total_questions=total_q,
            elapsed_seconds=round(elapsed),
            min_duration_seconds=min_dur,
            max_duration_seconds=max_dur,
            bonus_seconds_added=bonus_sec,
            is_extended=is_ext,
        )

    # Report if completed
    report_dict = None
    if session.status == "completed":
        report = db.query(EvaluationReport).filter(EvaluationReport.session_id == session_id).first()
        if report:
            report_dict = {
                "id": str(report.id),
                "session_id": str(report.session_id),
                "overall_score": report.overall_score,
                "technical_score": report.technical_score,
                "communication_score": report.communication_score,
                "strengths": report.strengths or [],
                "weaknesses": report.weaknesses or [],
                "learning_plan": report.learning_plan or {},
                "recommendations": report.recommendations or "",
            }

    return SessionStateResponse(
        session_id=session.id,
        candidate_id=session.candidate_id,
        candidate=candidate_data,
        status=session.status,
        created_at=session.created_at.isoformat() if session.created_at else "",
        total_questions=total_q,
        answered_questions=answered_count,
        current_question=current_q,
        answers=answers_summary,
        elapsed_seconds=round(elapsed),
        min_duration_seconds=min_dur,
        max_duration_seconds=max_dur,
        bonus_seconds_added=bonus_sec,
        is_extended=is_ext,
        is_complete=session.status == "completed",
        report=report_dict,
    )


@router.get("/{session_id}/status", response_model=SessionStatusResponse)
def get_session_status(
    session_id: UUID,
    db: Session = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
):
    """Returns interview session progress for external dashboards."""
    session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found")

    total = db.query(SessionQuestion).filter(SessionQuestion.session_id == session_id).count()
    answered = db.query(SessionQuestion).filter(
        SessionQuestion.session_id == session_id,
        SessionQuestion.is_answered == True,
    ).count()

    return SessionStatusResponse(
        session_id=session.id,
        candidate_id=session.candidate_id,
        status=session.status,
        total_questions=total,
        answered_questions=answered,
        is_complete=session.status == "completed",
    )


@router.get("/{session_id}/report", response_model=EvaluationReportResponse)
def get_session_report(
    session_id: UUID,
    db: Session = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
):
    """Retrieve the evaluation report for a completed interview session."""
    session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found")

    report = db.query(EvaluationReport).filter(EvaluationReport.session_id == session_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found. Interview may not be completed yet.")
    return report


@router.websocket("/ws/transcribe")
async def websocket_transcribe(websocket: WebSocket):
    """Real-time audio streaming bridge from browser MediaRecorder to Deepgram STT."""
    await websocket.accept()
    api_key = settings.DEEPGRAM_API_KEY
    if not api_key:
        logger.warning("WebSocket transcription requested, but DEEPGRAM_API_KEY is not configured.")
        await websocket.send_json({
            "type": "warning",
            "message": "DEEPGRAM_API_KEY not configured on server.",
        })
        try:
            while True:
                msg = await websocket.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
        except (WebSocketDisconnect, RuntimeError):
            pass
        return

    model = getattr(settings, "DEEPGRAM_MODEL", "nova-2") or "nova-2"
    lang = getattr(settings, "DEEPGRAM_LANGUAGE", "en") or "en"
    deepgram_url = (
        f"wss://api.deepgram.com/v1/listen?"
        f"model={model}&language={lang}&smart_format=true&punctuate=true&interim_results=true"
    )

    try:
        async with websockets.connect(
            deepgram_url,
            additional_headers={"Authorization": f"Token {api_key}"},
            ping_interval=20,
            ping_timeout=20,
        ) as dg_ws:

            async def client_to_deepgram():
                try:
                    while True:
                        msg = await websocket.receive()
                        if msg.get("type") == "websocket.disconnect":
                            break
                        if "bytes" in msg and msg["bytes"]:
                            await dg_ws.send(msg["bytes"])
                        elif "text" in msg and msg["text"]:
                            if msg["text"] == "CLOSE":
                                await dg_ws.send(json.dumps({"type": "CloseStream"}))
                                break
                except (WebSocketDisconnect, RuntimeError, asyncio.CancelledError):
                    pass
                except Exception as exc:
                    logger.debug("Client to Deepgram forwarder stopped: %s", exc)

            async def deepgram_to_client():
                try:
                    async for raw_msg in dg_ws:
                        try:
                            data = json.loads(raw_msg)
                            channel = data.get("channel", {})
                            alts = channel.get("alternatives", [])
                            if alts:
                                text = alts[0].get("transcript", "")
                                is_final = data.get("is_final", False)
                                speech_final = data.get("speech_final", False)
                                if text:
                                    await websocket.send_json({
                                        "type": "transcript",
                                        "transcript": text,
                                        "is_final": is_final or speech_final,
                                    })
                        except Exception as exc:
                            logger.debug("Error parsing Deepgram message: %s", exc)
                except (WebSocketDisconnect, asyncio.CancelledError):
                    pass
                except Exception as exc:
                    logger.debug("Deepgram to client forwarder stopped: %s", exc)

            await asyncio.gather(client_to_deepgram(), deepgram_to_client(), return_exceptions=True)

    except WebSocketDisconnect:
        logger.debug("Client disconnected from /ws/transcribe")
    except Exception as exc:
        logger.warning("Deepgram live WebSocket connection error: %s", exc)
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
