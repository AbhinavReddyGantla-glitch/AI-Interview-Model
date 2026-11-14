import io
import re
import os
import uuid
import hashlib
import logging
from typing import Optional, List, Dict, Any, Tuple
from fastapi import HTTPException

logger = logging.getLogger("app.services.resume")

# Common Technical & Engineering Skill Keywords
SKILL_KEYWORDS = {
    "python", "java", "javascript", "typescript", "c++", "c#", "go", "rust", "kotlin", "swift",
    "react", "angular", "vue", "next.js", "node", "express", "fastapi", "django", "flask", "spring", "spring boot",
    "sql", "nosql", "postgresql", "mysql", "mongodb", "redis", "cassandra", "sqlite",
    "docker", "kubernetes", "aws", "azure", "gcp", "git", "github", "gitlab", "ci/cd", "linux", "bash",
    "rest", "api", "graphql", "grpc", "microservices", "kafka", "rabbitmq",
    "html", "css", "tailwind", "bootstrap",
    "machine learning", "deep learning", "tensorflow", "pytorch", "scikit-learn", "data science", "nlp", "computer vision",
    "data structures", "algorithms", "oop", "system design", "agile", "scrum", "unit testing", "pytest"
}

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".rtf", ".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "text/plain",
    "application/rtf",
    "text/rtf",
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "application/octet-stream",
}


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal and shell injection."""
    clean = os.path.basename(filename.strip().replace("\\", "/"))
    clean = re.sub(r"[^a-zA-Z0-9._-]", "_", clean)
    clean = re.sub(r"_{2,}", "_", clean)
    if not clean or clean.startswith("."):
        clean = f"resume_{uuid.uuid4().hex[:6]}" + (os.path.splitext(filename)[1] or ".pdf")
    return clean


def validate_resume_file(
    file_bytes: bytes,
    filename: str,
    content_type: str,
    max_size_mb: int = 5,
) -> None:
    """
    Validate uploaded file by size, extension, MIME type, and magic bytes / signatures.
    Raises HTTPException with clear structured JSON error on failure.
    """
    if not file_bytes or len(file_bytes) == 0:
        raise HTTPException(
            status_code=400,
            detail="Uploaded resume file is empty.",
            headers={"X-Error-Code": "EMPTY_FILE"},
        )

    # 1. Size Check
    max_bytes = max_size_mb * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File size exceeds the {max_size_mb} MB limit. Please upload a smaller resume.",
            headers={"X-Error-Code": "FILE_TOO_LARGE"},
        )

    # 2. Extension Check (with magic bytes auto-detection if extension is hidden/missing)
    lower_name = (filename or "").lower()
    ext = os.path.splitext(lower_name)[1]
    if ext not in ALLOWED_EXTENSIONS:
        header = file_bytes[:16]
        if header.startswith(b"%PDF") or b"%PDF" in file_bytes[:1024]:
            ext = ".pdf"
        elif header.startswith(b"PK\x03\x04"):
            ext = ".docx"
        elif header.startswith(b"\xff\xd8\xff"):
            ext = ".jpg"
        elif header.startswith(b"\x89PNG\r\n\x1a\n"):
            ext = ".png"
        elif b"\x00\x00\x00\x00" not in file_bytes[:128]:
            try:
                file_bytes.decode("utf-8")
                ext = ".txt"
            except Exception:
                pass

        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type '{ext}'. Please upload a PDF, DOCX, or TXT resume.",
                headers={"X-Error-Code": "UNSUPPORTED_FILE_TYPE"},
            )

    # 3. Magic Bytes / Signature Check
    header = file_bytes[:16]

    if ext == ".pdf":
        if not header.startswith(b"%PDF"):
            # Check within first 1024 bytes (some PDFs have prepended BOM or whitespace)
            if b"%PDF" not in file_bytes[:1024]:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid PDF file format. Missing PDF header.",
                    headers={"X-Error-Code": "INVALID_FILE_SIGNATURE"},
                )

    elif ext == ".docx":
        # DOCX is a zip archive starting with PK\x03\x04
        if not header.startswith(b"PK\x03\x04"):
            raise HTTPException(
                status_code=400,
                detail="Invalid DOCX file format. File is corrupted or not a valid Word document.",
                headers={"X-Error-Code": "INVALID_FILE_SIGNATURE"},
            )

    elif ext in {".jpg", ".jpeg"}:
        if not header.startswith(b"\xff\xd8\xff"):
            raise HTTPException(
                status_code=400,
                detail="Invalid JPEG image format.",
                headers={"X-Error-Code": "INVALID_FILE_SIGNATURE"},
            )

    elif ext == ".png":
        if not header.startswith(b"\x89PNG\r\n\x1a\n"):
            raise HTTPException(
                status_code=400,
                detail="Invalid PNG image format.",
                headers={"X-Error-Code": "INVALID_FILE_SIGNATURE"},
            )

    elif ext in {".txt", ".rtf"}:
        # Plain text should not have extensive null bytes
        if b"\x00\x00\x00\x00" in file_bytes[:128]:
            raise HTTPException(
                status_code=400,
                detail="Invalid text file format. Binary data detected.",
                headers={"X-Error-Code": "INVALID_FILE_SIGNATURE"},
            )


def save_resume_file(
    file_bytes: bytes,
    filename: str,
    upload_dir: str = "uploads/resumes",
) -> Tuple[str, str, int, str]:
    """
    Save resume file to mounted directory under a unique, sanitized name.
    Returns (file_path, safe_filename, file_size, file_hash).
    """
    os.makedirs(upload_dir, exist_ok=True)
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    safe_name = sanitize_filename(filename)
    unique_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"
    file_path = os.path.join(upload_dir, unique_name)

    with open(file_path, "wb") as f:
        f.write(file_bytes)

    logger.info(f"Resume saved successfully to {file_path} (size: {len(file_bytes)} bytes, hash: {file_hash[:10]})")
    return file_path, safe_name, len(file_bytes), file_hash


def extract_text_from_pdf(pdf_bytes: bytes) -> Tuple[str, bool]:
    """
    Cascading PDF text extraction:
    1. PyMuPDF (fitz) - high-speed, handles complex layouts and non-standard fonts
    2. pdfplumber - high precision table and text extraction
    3. pypdf - standard stream extraction
    4. PyMuPDF Page-Render to Image OCR fallback (Gemini Vision / pytesseract)
    Returns (extracted_text, is_scanned_flag).
    """
    text = ""
    is_scanned = False

    # 1. Try PyMuPDF (fitz)
    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages = [page.get_text() or "" for page in doc]
        text = "\n".join(pages).strip()
    except Exception as e:
        logger.debug(f"fitz extraction returned: {e}")

    # 2. Try pdfplumber
    if not text:
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                pages = [page.extract_text() or "" for page in pdf.pages]
                text = "\n".join(pages).strip()
        except Exception as e:
            logger.debug(f"pdfplumber extraction returned: {e}")

    # 3. Try pypdf
    if not text:
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(pdf_bytes))
            pages = [page.extract_text() or "" for page in reader.pages]
            text = "\n".join(pages).strip()
        except Exception as e:
            logger.debug(f"pypdf extraction returned: {e}")

    # 4. If still empty, render PDF pages as images and run OCR
    if not text:
        is_scanned = True
        logger.info("PDF has no extractable text stream. Rendering pages to images for OCR.")
        try:
            import fitz
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            for page in doc[:3]:  # First 3 pages
                pix = page.get_pixmap(dpi=150)
                img_bytes = pix.tobytes("png")
                page_text = extract_text_from_image(img_bytes, "image/png")
                if page_text.strip():
                    text += "\n" + page_text
        except Exception as ocr_err:
            logger.warning(f"PyMuPDF page render OCR failed: {ocr_err}")

    # 5. Raw string salvage fallback
    if not text and len(pdf_bytes) > 20:
        # Search for raw text streams
        raw_matches = re.findall(rb"\(([^\)\\]{3,100})\)\s*Tj", pdf_bytes)
        if raw_matches:
            salvaged = " ".join([m.decode("latin-1", errors="ignore") for m in raw_matches])
            if len(salvaged) > 20:
                text = salvaged
                is_scanned = False

    # 6. Plain text / UTF-8 / ASCII decode fallback (for text-based resumes saved with .pdf extension or corrupt wrappers)
    if not text and len(pdf_bytes) > 10:
        for enc in ("utf-8", "latin-1", "cp1252"):
            try:
                decoded = pdf_bytes.decode(enc, errors="ignore")
                clean_lines = [
                    line.strip() for line in decoded.splitlines()
                    if line.strip() and not line.strip().startswith("%PDF") and any(c.isalnum() for c in line)
                ]
                if clean_lines:
                    candidate_salvage = "\n".join(clean_lines)
                    if len(candidate_salvage) >= 10:
                        logger.info(f"Successfully salvaged {len(candidate_salvage)} chars from PDF byte stream via {enc} decoder.")
                        text = candidate_salvage
                        is_scanned = False
                        break
            except Exception:
                pass

    return text.strip(), is_scanned


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract plain text from DOCX using python-docx with zipfile XML fallback."""
    try:
        import docx
        doc = docx.Document(io.BytesIO(file_bytes))
        paragraphs = [p.text for p in doc.paragraphs if p.text]
        # Also extract table text
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join([cell.text.strip() for cell in row.cells if cell.text.strip()])
                if row_text:
                    paragraphs.append(row_text)
        text = "\n".join(paragraphs).strip()
        if text:
            return text
    except Exception as e:
        logger.warning(f"python-docx failed, falling back to XML extraction: {e}")

    # Fallback to direct zipfile XML parsing
    try:
        import zipfile
        import xml.etree.ElementTree as ET
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
            if "word/document.xml" in z.namelist():
                xml_content = z.read("word/document.xml")
                tree = ET.fromstring(xml_content)
                paragraphs = []
                for p in tree.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
                    texts = [
                        node.text
                        for node in p.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t")
                        if node.text
                    ]
                    if texts:
                        paragraphs.append("".join(texts))
                return "\n".join(paragraphs).strip()
    except Exception as e:
        logger.error(f"DOCX XML extraction failed: {e}")

    return ""


def extract_text_from_txt(file_bytes: bytes) -> str:
    """Extract text from plain text bytes."""
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            return file_bytes.decode(enc).strip()
        except UnicodeDecodeError:
            continue
    return file_bytes.decode("utf-8", errors="replace").strip()


def extract_text_from_rtf(file_bytes: bytes) -> str:
    """Extract text from RTF by stripping control sequences."""
    try:
        text = extract_text_from_txt(file_bytes)
        # Strip RTF formatting control words (\b, \par, etc.)
        pattern = re.compile(r"\\[a-zA-Z0-9]+ ?|[{}]")
        clean = pattern.sub(" ", text)
        return re.sub(r"\s+", " ", clean).strip()
    except Exception as e:
        logger.error(f"RTF extraction failed: {e}")
        return ""


def extract_text_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """Extract text from a resume image via Gemini Vision or pytesseract."""
    from app.core.config import settings

    if settings.GEMINI_API_KEY:
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINI_API_KEY, transport="rest")
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content([
                {"mime_type": mime_type, "data": image_bytes},
                "Extract ALL text from this resume image exactly as written. Return plain text only, no commentary.",
            ])
            text = (response.text or "").strip()
            if text:
                return text
        except Exception as e:
            logger.debug(f"Gemini vision OCR skipped/failed: {e}")

    try:
        import pytesseract
        from PIL import Image
        image = Image.open(io.BytesIO(image_bytes))
        return pytesseract.image_to_string(image).strip()
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"pytesseract extraction returned: {e}")

    return ""


def parse_resume_file(file_bytes: bytes, filename: str, content_type: str) -> Tuple[str, bool]:
    """
    Route file to appropriate text extractor.
    Returns (extracted_text, is_scanned_flag).
    """
    lower_name = (filename or "").lower()
    mime = (content_type or "").lower()

    if lower_name.endswith(".pdf") or mime == "application/pdf" or file_bytes[:16].startswith(b"%PDF") or b"%PDF" in file_bytes[:1024]:
        return extract_text_from_pdf(file_bytes)

    if lower_name.endswith((".docx", ".doc")) or "wordprocessingml" in mime or "msword" in mime or file_bytes[:16].startswith(b"PK\x03\x04"):
        return extract_text_from_docx(file_bytes), False

    if lower_name.endswith(".rtf") or "rtf" in mime:
        return extract_text_from_rtf(file_bytes), False

    if lower_name.endswith(".txt") or mime == "text/plain":
        return extract_text_from_txt(file_bytes), False

    if lower_name.endswith((".jpg", ".jpeg", ".png", ".webp")) or mime.startswith("image/"):
        return extract_text_from_image(file_bytes, mime or "image/jpeg"), False

    # Generic fallback
    try:
        txt = extract_text_from_txt(file_bytes)
        if len(txt) > 20:
            return txt, False
    except Exception:
        pass

    raise HTTPException(
        status_code=400,
        detail="Unsupported file type. Please upload a PDF, DOCX, or TXT resume.",
        headers={"X-Error-Code": "UNSUPPORTED_FILE_TYPE"},
    )


# ══════════════════════════════════════════════════════════════
# Structured Information Extraction (Rule-based & Regex)
# ══════════════════════════════════════════════════════════════

def extract_contact_info(text: str) -> Dict[str, str]:
    """Extract name, email, and phone number from resume text."""
    # Email match
    email_match = re.search(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}", text)
    email = email_match.group(0) if email_match else f"candidate_{uuid.uuid4().hex[:8]}@interview.local"

    # Phone match (supports international and domestic formats)
    phone_pattern = r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}|\b[6-9]\d{9}\b"
    phone_match = re.search(phone_pattern, text)
    phone = phone_match.group(0).strip() if phone_match else ""

    # Name heuristic from top lines
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    name = "Candidate"
    for line in lines[:8]:
        if "@" in line or re.search(r"\d{4,}", line) or len(line) < 3:
            continue
        cleaned = re.sub(r"^(?:candidate\s+name|full\s+name|applicant\s+name|name)\s*[:\-]\s*", "", line, flags=re.IGNORECASE).strip()
        if not cleaned or len(cleaned) < 2:
            continue
        if len(cleaned.split()) <= 6 and not cleaned.lower().startswith(("resume", "curriculum", "cv", "portfolio", "profile", "summary")):
            name = cleaned.title()
            break

    return {"name": name, "email": email, "phone": phone}


def extract_education(text: str) -> List[str]:
    """Extract education history, degrees, and university mentions."""
    degrees = []
    edu_patterns = [
        r"(?:b\.?tech|b\.?e\.?|bachelor(?:'s)?|b\.?s\.?|bca)\s*(?:in\s+[^,\n]+)?",
        r"(?:m\.?tech|m\.?e\.?|master(?:'s)?|m\.?s\.?|mca|mba)\s*(?:in\s+[^,\n]+)?",
        r"(?:ph\.?d|doctorate)\s*(?:in\s+[^,\n]+)?",
        r"(?:university|institute|college|school)\s+of\s+[^,\n]+",
        r"[A-Z][a-zA-Z\s]+(?:University|Institute of Technology|College of Engineering)",
    ]
    for pattern in edu_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for m in matches:
            deg = m.group(0).strip()
            if len(deg) > 4 and deg.title() not in degrees:
                degrees.append(deg.title())

    return degrees[:5]


def extract_skills_from_text(text: str) -> List[str]:
    """Heuristically extract technical skills mentioned in resume text."""
    lower = text.lower()
    found = []
    for skill in SKILL_KEYWORDS:
        # Match as whole word or phrase
        pattern = r"\b" + re.escape(skill) + r"\b"
        if re.search(pattern, lower):
            found.append(skill.title() if skill.isalpha() else skill.upper())
    return sorted(set(found))


def extract_experience_years(text: str) -> int:
    """Estimate years of experience from patterns."""
    patterns = [
        r"(\d+)\+?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience|exp)",
        r"experience\s*[:\-]?\s*(\d+)\+?\s*(?:years?|yrs?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text.lower())
        if match:
            return min(int(match.group(1)), 30)
    return 0


def extract_projects(text: str) -> List[str]:
    """Extract projects from resume text."""
    projects = []
    lines = text.splitlines()
    in_projects = False

    for line in lines:
        stripped = line.strip()
        lower = stripped.lower()
        if any(h in lower for h in ["projects", "academic projects", "key projects", "personal projects"]):
            in_projects = True
            continue
        if in_projects:
            if any(h in lower for h in ["skills", "education", "experience", "certifications", "achievements"]):
                break
            if stripped.startswith(("-", "•", "*")) or (stripped and len(stripped) < 80 and not stripped.endswith(".")):
                clean_line = re.sub(r"^[-•*\s]+", "", stripped)
                if len(clean_line) > 5:
                    projects.append(clean_line)
                    if len(projects) >= 5:
                        break

    return projects


def build_resume_summary(text: str, max_chars: int = 800) -> str:
    """Build a concise summary from the first meaningful paragraphs."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    summary_lines = []
    char_count = 0
    for line in lines[:12]:
        if char_count + len(line) > max_chars:
            break
        summary_lines.append(line)
        char_count += len(line)
    return " ".join(summary_lines) if summary_lines else text[:max_chars]


def parse_resume_with_llm(raw_text: str) -> Optional[Dict[str, Any]]:
    """Optional LLM-based structured parsing via Gemini."""
    from app.core.config import settings

    if not settings.ENABLE_LLM_RESUME_PARSER or not settings.GEMINI_API_KEY:
        return None

    try:
        import json
        import google.generativeai as genai
        genai.configure(api_key=settings.GEMINI_API_KEY, transport="rest")
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = (
            "You are an expert resume parser. Extract structured fields from the following resume text:\n"
            "Return a JSON object with keys: name (str), email (str), phone (str), education (list of str), "
            "skills (list of str), experience_years (int), projects (list of str), job_role (str), resume_summary (str).\n"
            "Return valid JSON only, no markdown formatting.\n\n"
            f"Resume Text:\n{raw_text[:4000]}"
        )
        response = model.generate_content(prompt)
        content = (response.text or "").strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\n|\n```$", "", content)
        data = json.loads(content)
        return data
    except Exception as e:
        logger.warning(f"LLM resume parsing skipped or failed: {e}")
        return None


def parse_resume_text(raw_text: str, filename: str = "", job_role: Optional[str] = None) -> Dict[str, Any]:
    """Parse raw resume text into structured fields using regex/rules, with optional LLM parser."""
    text = (raw_text or "").strip()

    # Try LLM parser if enabled
    llm_parsed = parse_resume_with_llm(text)
    if llm_parsed and isinstance(llm_parsed, dict):
        return {
            "name": llm_parsed.get("name") or "Candidate",
            "email": llm_parsed.get("email") or f"candidate_{uuid.uuid4().hex[:8]}@interview.local",
            "phone": llm_parsed.get("phone") or "",
            "education": llm_parsed.get("education") or [],
            "skills": llm_parsed.get("skills") or [],
            "experience_years": int(llm_parsed.get("experience_years") or 0),
            "projects": llm_parsed.get("projects") or [],
            "job_role": job_role or llm_parsed.get("job_role") or "Software Engineer",
            "resume_summary": llm_parsed.get("resume_summary") or build_resume_summary(text),
            "raw_text": text,
        }

    # Rule-based fallback parser
    contact = extract_contact_info(text) if text else {"name": "Candidate", "email": f"candidate_{uuid.uuid4().hex[:8]}@interview.local", "phone": ""}
    skills = extract_skills_from_text(text) if text else []
    experience = extract_experience_years(text) if text else 0
    education = extract_education(text) if text else []
    projects = extract_projects(text) if text else []
    summary = build_resume_summary(text) if text else ""

    # Infer role if not provided
    inferred_role = job_role
    if not inferred_role and text:
        role_map = {
            "backend": "Backend Engineer",
            "frontend": "Frontend Engineer",
            "fullstack": "Fullstack Engineer",
            "full stack": "Fullstack Engineer",
            "data scientist": "Data Scientist",
            "devops": "DevOps Engineer",
            "software engineer": "Software Engineer",
        }
        lower = text.lower()
        for keyword, role in role_map.items():
            if keyword in lower:
                inferred_role = role
                break
    inferred_role = inferred_role or "Software Engineer"

    # If name is still generic, infer from filename if possible
    name = contact["name"]
    if name == "Candidate" and filename:
        clean_name = re.sub(r"[._-]|resume|cv|\bpdf\b|\bdocx?\b", " ", filename, flags=re.IGNORECASE).strip()
        if len(clean_name) >= 3:
            name = clean_name.title()

    return {
        "name": name,
        "email": contact["email"],
        "phone": contact.get("phone", ""),
        "education": education,
        "skills": skills,
        "experience_years": experience,
        "projects": projects,
        "job_role": inferred_role,
        "resume_summary": summary,
        "raw_text": text,
    }
