# AI Interview Evaluation Platform

SaaS-ready AI interview evaluation system for edutech companies. External teams send resumes, the platform generates personalized questions, evaluates candidates, and pushes results to a coaching team for skill improvement guidance.

## Architecture

```
┌─────────────────────┐     resume API      ┌──────────────────────────┐
│  Recruitment Team   │ ──────────────────► │  AI Interview Platform   │
│  (sends resume)     │                     │  (FastAPI + PostgreSQL)  │
└─────────────────────┘                     └────────────┬─────────────┘
                                                         │
                    candidate takes interview            │ webhook
                    (web UI or API)                      ▼
                                              ┌──────────────────────────┐
                                              │  Coaching / Improvement  │
                                              │  Team (receives scores,  │
                                              │  roadmap, breakdown)     │
                                              └──────────────────────────┘
```

## Quick Start

### 1. Prerequisites

- Python 3.11+
- PostgreSQL 14+ (or use Docker Compose)
- Optional: [Gemini API key](https://aistudio.google.com/) for AI question generation and reports
- A Google Cloud project with the Speech-to-Text API enabled and Application Default Credentials (or a service-account key) for server-side transcription.

### 2. Local Setup

```bash
# Clone and enter project
cd AI-Interview-Model

# Create virtual environment
python -m venv .venv
.\.venv\Scripts\activate        # Windows
# source .venv/bin/activate     # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Configure environment
copy .env.template .env         # Windows
# cp .env.template .env         # macOS/Linux
# Edit .env with your DATABASE_URL and optional API keys

# Run database migrations
alembic upgrade head

# Start server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000** for the interview UI, or **http://localhost:8000/docs** for Swagger API docs.

### 3. Docker Compose

```bash
docker compose up --build
```

## SaaS API Flow

### Step 1 — External team sends resume

**JSON payload:**

```bash
curl -X POST http://localhost:8000/api/v1/candidates/resume \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "name": "Jane Doe",
    "email": "jane@example.com",
    "job_role": "Backend Engineer",
    "resume_text": "5 years Python, FastAPI, PostgreSQL, REST APIs, Docker...",
    "external_id": "HR-12345"
  }'
```

**PDF upload:**

```bash
curl -X POST http://localhost:8000/api/v1/candidates/resume/upload \
  -H "X-API-Key: your-api-key" \
  -F "name=Jane Doe" \
  -F "email=jane@example.com" \
  -F "job_role=Backend Engineer" \
  -F "resume_file=@resume.pdf"
```

Response includes `candidate_id` and `interview_url` to send to the candidate.

### Step 2 — Start interview (API or web UI)

```bash
curl -X POST http://localhost:8000/api/v1/interview/start \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"candidate_id": "<candidate_id_from_step_1>"}'
```

Or open the `interview_url` in a browser — the form auto-fills from the resume.

### Step 3 — Interview loop

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/interview/{session_id}/next-question` | GET | Get next question |
| `/api/v1/interview/{session_id}/answer` | POST | Submit answer (text, audio, video) |
| `/api/v1/interview/{session_id}/status` | GET | Check progress |
| `/api/v1/interview/{session_id}/submit` | POST | Finalize and generate report |
| `/api/v1/interview/{session_id}/report` | GET | Retrieve evaluation report |

### Step 4 — Coaching team receives results

When an interview is submitted, the platform POSTs to `EXTERNAL_EVALUATION_URL`:

```json
{
  "event": "interview.completed",
  "session_id": "...",
  "candidate": {
    "name": "Jane Doe",
    "email": "jane@example.com",
    "job_role": "Backend Engineer",
    "skills": ["Python", "SQL", "REST"],
    "resume_summary": "..."
  },
  "scores": {
    "overall_score": 78.5,
    "technical_score": 82.0,
    "communication_score": 74.0
  },
  "recommendation": "Maybe Hire — solid fundamentals...",
  "roadmap": {
    "short_term": ["Review database indexing", "Practice system design"],
    "long_term": ["Build distributed systems experience"]
  },
  "strengths": ["..."],
  "weaknesses": ["..."],
  "question_breakdown": [
    {
      "question_text": "...",
      "transcript": "...",
      "expected_keywords": ["..."],
      "scores": { "overall_score": 80.0 }
    }
  ]
}
```

Point `EXTERNAL_EVALUATION_URL` to your coaching team's server. Use `EXTERNAL_WEBHOOK_SECRET` for signed webhooks.

## Configuration

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `GEMINI_API_KEY` | Google Gemini for question generation and final reports |
| `GOOGLE_APPLICATION_CREDENTIALS` | Absolute path to the Google Cloud service-account JSON key |
| `GOOGLE_SPEECH_LANGUAGE_CODE` | English recognition locale (defaults to `en-IN`) |
| `GOOGLE_SPEECH_MODEL` | Recognition model (defaults to `latest_long`) |
| `API_KEY` | SaaS API key (leave empty in dev to disable auth) |
| `EXTERNAL_EVALUATION_URL` | Webhook URL for coaching team |
| `EXTERNAL_WEBHOOK_SECRET` | Optional shared secret for webhook verification |
| `PUBLIC_BASE_URL` | Base URL for interview links sent to candidates |

## Features

- **Resume-driven questions** — Questions tailored to role, skills, and resume content
- **Adaptive difficulty** — Easy → Medium → Hard progression (SRS FR-TRK-001)
- **Multi-modal answers** — Text, audio (STT), and video (eye contact / attention)
- **Rule-based + AI evaluation** — Keyword scoring plus Gemini final report
- **SaaS API** — REST endpoints with optional API key auth
- **Webhook integration** — Full payload to coaching/improvement team
- **Question caching** — Fingerprint-based reuse for similar profiles
- **Fallback mode** — Works without Gemini; audio-only answers require Google Cloud credentials

## Project Structure

```
app/
├── api/v1/endpoints/   # REST API routes
├── core/               # Config, security, logging
├── database/           # SQLAlchemy session
├── models/             # Database models
├── schemas/            # Pydantic request/response models
├── services/           # AI, speech, vision, resume, webhook
└── static/             # React-style web UI (HTML/CSS/JS)
alembic/                # Database migrations
```

## License

Proprietary — for edutech company internal use.
