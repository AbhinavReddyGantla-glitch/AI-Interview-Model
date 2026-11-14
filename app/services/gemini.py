import json
import re
import random
import logging
from typing import List, Dict, Any, Optional
from app.core.config import settings

logger = logging.getLogger("app.services.gemini")

GEMINI_AVAILABLE = False
try:
    if settings.GEMINI_API_KEY:
        import google.generativeai as genai
        genai.configure(api_key=settings.GEMINI_API_KEY, transport="rest")
        GEMINI_AVAILABLE = True
    else:
        logger.warning("GEMINI_API_KEY is empty. Running Gemini integration in mock/fallback mode.")
except ImportError:
    logger.warning("google-generativeai package not available. Running Gemini integration in mock/fallback mode.")

def clean_json_response(text: str) -> str:
    """Cleans response text from Gemini to extract JSON string, removing markdown code fences if present."""
    cleaned = text.strip()
    match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', cleaned)
    if match:
        return match.group(1).strip()
    return cleaned

def bounded_score(value: Any, fallback: float) -> float:
    """Return a finite 0-100 score; model output must never corrupt scoring."""
    try:
        score = float(value)
        if score != score or score in (float("inf"), float("-inf")):
            raise ValueError("non-finite score")
        return round(min(100.0, max(0.0, score)), 2)
    except (TypeError, ValueError):
        return fallback

def get_generative_model(model_name: str = "gemini-1.5-flash"):
    """Safely retrieves a generative model, with fallback models."""
    import google.generativeai as genai
    for name in [model_name, "gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"]:
        try:
            return genai.GenerativeModel(name)
        except Exception:
            continue
    return genai.GenerativeModel("gemini-1.5-flash")

def generate_adaptive_questions(
    role: str,
    experience_years: int,
    skills: List[str],
    resume_summary: Optional[str] = None,
    num_questions: int = 10,
) -> List[Dict[str, Any]]:
    """
    Generates tailored, randomized interview questions tailored specifically for
    college students, recent graduates, and entry-level freshers (0-1 years exp).
    Questions are compact, crystal clear, foundational, and conversational.
    Falls back to a randomized offline bank if Gemini is unavailable.
    """
    if not GEMINI_AVAILABLE:
        logger.info("Gemini not available. Generating randomized questions from local database pool.")
        return get_mock_adaptive_questions(role, skills, num_questions)

    try:
        model = get_generative_model()
        
        resume_context = f"\n- Candidate Project/Resume Summary: {resume_summary}" if resume_summary else ""
        skills_str = ", ".join(skills) if skills else "Core Java/Python, Data Structures, OOP, SQL, Web Basics"
        
        focus_angles = random.sample([
            "college academic projects and basic debugging",
            "core data structures and fundamental algorithms",
            "object-oriented programming with simple real-world examples",
            "basic SQL queries and database concepts",
            "foundational problem-solving and logic",
            "handling academic team projects and eagerness to learn"
        ], k=3)
        
        prompt = f"""
You are a friendly, encouraging technical interviewer conducting an entry-level campus placement interview specifically tailored for 3rd and 4th year Indian B.Tech engineering college students (candidates for campus recruitment drives like TCS, Infosys, Wipro, Cognizant, Accenture, Capgemini, and product startups).

Candidate Profile:
- Target Role: {role}
- Experience Level: 3rd / 4th Year Indian B.Tech Engineering Student (Campus Placement Fresher, 0-1 years)
- Skills & Background: {skills_str}{resume_context}
- Focus Angles: {', '.join(focus_angles)}

MANDATORY FIRST QUESTION:
- Question 1 (index 0) MUST ALWAYS BE: "Tell me about yourself, your educational background, and your key technical interests."

STRICT RULES FOR 3RD & 4TH YEAR INDIAN B.TECH COLLEGE STUDENTS:
1. BEGINNER-FRIENDLY & COMPACT: Questions must be short, clear, and direct (1-2 sentences maximum, under 30 words). Never use convoluted phrasing or multiple sub-questions.
2. FOUNDATIONAL CAMPUS CURRICULUM LEVEL: Focus purely on standard B.Tech semester curriculum:
   - OOP Principles: 4 pillars with real-world examples, Overloading vs Overriding, Abstract Class vs Interface, Constructors, Encapsulation with getters/setters.
   - Core DSA (Basics): Array vs Linked List (memory & access), Stack (LIFO) vs Queue (FIFO), Binary Search (O(log N) vs O(N)), Palindrome check, Hash Map lookup concept, Recursion base case.
   - DBMS & SQL: Primary Key vs Foreign Key, INNER vs LEFT JOIN, ACID properties (bank example), WHERE vs HAVING, 1NF/2NF/3NF Normalization purpose.
   - Operating Systems: Process vs Thread (memory space), Deadlock conditions (Coffman conditions), Virtual Memory & Paging concept.
   - Web & Networks: URL browser request flow (DNS/HTTP), HTTP vs HTTPS (SSL/TLS), GET vs POST methods.
   - Academic Project: High-level overview of their mini/final year project, tech stack, and how they debugged an issue.
3. ABSOLUTELY FORBIDDEN: Do NOT ask complex distributed systems, microservices, Kubernetes, Redis clusters, or hard competitive LeetCode problems (e.g., dynamic programming, segment trees).
4. BALANCED QUESTION MIX ({num_questions} total):
   - Question 1: Self-introduction / background.
   - 1 Project / Academic problem-solving question.
   - 3 Core Data Structures & Basic Algorithms.
   - 2 OOP Principles & Language Fundamentals (Java/Python/C++).
   - 2 Database & SQL Basics.
   - 1 Core OS / Web Networking Fundamental.
5. Difficulty distribution: ~6 easy, ~3-4 medium.

Return strictly a valid JSON array of {num_questions} objects with NO markdown preamble:
[
  {{
    "question_text": "Short, clear, beginner-friendly question for a 3rd/4th year B.Tech student.",
    "difficulty": "easy" | "medium",
    "expected_keywords": ["keyword1", "keyword2", "keyword3", "keyword4"],
    "category": "hr" | "dsa" | "oops" | "dbms" | "os" | "web_dev" | "project",
    "role": "{role}"
  }}
]
"""
        response = model.generate_content(
            prompt,
            generation_config={"temperature": 0.75, "top_p": 0.9}
        )
        cleaned_text = clean_json_response(response.text)
        questions = json.loads(cleaned_text)
        if isinstance(questions, list) and len(questions) >= 5:
            # Find or ensure the self-intro question is strictly at index 0
            intro_q = None
            remaining_qs = []
            for q in questions:
                q_text = q.get("question_text", "").lower()
                if not intro_q and ("tell me about yourself" in q_text or "introduce yourself" in q_text or "background" in q_text):
                    intro_q = q
                else:
                    remaining_qs.append(q)
            
            if not intro_q:
                intro_q = {
                    "question_text": "Tell me about yourself, your educational background, and your key technical interests.",
                    "difficulty": "easy",
                    "expected_keywords": ["education", "skills", "projects", "interests", "learning"],
                    "category": "hr",
                    "role": role
                }
            
            random.shuffle(remaining_qs)
            final_questions = [intro_q] + remaining_qs
            return final_questions[:num_questions]
        raise ValueError("Invalid format or insufficient questions returned from Gemini")
    except Exception as e:
        logger.error(f"Error generating questions via Gemini: {e}. Falling back to randomized local pool.")
        return get_mock_adaptive_questions(role, skills, num_questions)

def evaluate_answer_with_gemini(
    question_text: str,
    transcript: str,
    expected_keywords: List[str],
    speaking_time_seconds: float = 30.0,
) -> Dict[str, Any]:
    """
    Uses Gemini to perform semantic evaluation of a single candidate answer.
    Combines AI understanding with keyword matching.
    """
    if not GEMINI_AVAILABLE or not transcript or len(transcript.strip().split()) < 4:
        return None

    try:
        model = get_generative_model()
        prompt = f"""
You are evaluating a college student / fresher candidate's answer during a campus technical interview.
Question: "{question_text}"
Expected Key Concepts: {', '.join(expected_keywords)}
Candidate Spoken Transcript: "{transcript}"
Speaking Duration: {speaking_time_seconds:.1f} seconds

Evaluate strictly and honestly for a college student / fresher candidate:
1. Technical Accuracy (0-100) — score 0 if the answer is blank, off-topic, or incorrect
2. Completeness & Depth (0-100) — score 0 if the answer is missing key concepts
3. Clarity of Communication (0-100) — score 0 if the answer is incomprehensible or empty

Return strictly a JSON object with keys:
- "accuracy_score": float 0-100
- "completeness_score": float 0-100
- "communication_score": float 0-100
- "overall_score": float 0-100
- "feedback": short 1-2 sentence constructive observation
"""
        response = model.generate_content(
            prompt,
            generation_config={"temperature": 0.3}
        )
        cleaned_text = clean_json_response(response.text)
        result = json.loads(cleaned_text)
        if not isinstance(result, dict):
            return None
        required_scores = ("accuracy_score", "completeness_score", "communication_score", "overall_score")
        if any(key not in result for key in required_scores):
            logger.warning("Gemini semantic evaluation omitted required score fields.")
            return None
        for key in required_scores:
            result[key] = bounded_score(result[key], -1.0)
        if any(result[key] < 0 for key in required_scores):
            logger.warning("Gemini semantic evaluation returned invalid score values.")
            return None
        result["feedback"] = str(result.get("feedback", "")).strip()[:600]
        return result
    except Exception as e:
        logger.warning(f"Semantic evaluation with Gemini failed ({e}), using rule-based metrics.")
        return None

def generate_final_report(
    candidate_info: Dict[str, Any],
    answers: List[Dict[str, Any]],
    global_metrics: Dict[str, Any],
    proctoring_metrics: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Uses Gemini to perform final evaluation of candidate's interview performance.
    Combines resume summary, answers, rule-based scores, vision metrics, and proctoring stats.
    """
    if not GEMINI_AVAILABLE:
        logger.info("Gemini not available. Running fallback report generator.")
        return generate_mock_final_report(candidate_info, answers, global_metrics, proctoring_metrics)

    try:
        model = get_generative_model()
        
        payload = {
            "candidate": candidate_info,
            "answers": answers,
            "global_metrics": global_metrics,
            "proctoring_metrics": proctoring_metrics or {"tab_switches": 0, "integrity_score": 100}
        }
        
        prompt = f"""
You are an AI hiring evaluator for campus placements and fresher hiring.
Analyze the candidate's interview performance:
{json.dumps(payload, indent=2)}

Generate a strict but fair evaluation report. Be honest — if the candidate gave no answers or blank answers, reflect that clearly with low scores. Return strictly a JSON object with:
- "technical_score": float 0-100
- "communication_score": float 0-100
- "overall_score": float 0-100
- "recommendations": paragraph summarizing fresher hiring recommendation (Strong Hire / Hire / Consider / Needs Work) with actionable guidance.
- "strengths": list of 3-4 specific strengths observed.
- "weaknesses": list of 2-3 specific areas for improvement.
- "learning_plan": object with "short_term" (2-3 foundational items) and "long_term" (2-3 career progression items).
- "integrity_verdict": 1-2 sentences summarizing proctoring compliance and exam focus.
"""
        response = model.generate_content(
            prompt,
            generation_config={"temperature": 0.4}
        )
        cleaned_text = clean_json_response(response.text)
        report = json.loads(cleaned_text)
        required_scores = ("technical_score", "communication_score", "overall_score")
        if not isinstance(report, dict) or any(key not in report for key in required_scores):
            raise ValueError("Gemini report omitted required score fields")
        for key in required_scores:
            report[key] = bounded_score(report[key], -1.0)
        if any(report[key] < 0 for key in required_scores):
            raise ValueError("Gemini report contains invalid score fields")
        return report
    except Exception as e:
        logger.error(f"Error generating final report via Gemini: {e}. Generating mock final report.")
        return generate_mock_final_report(candidate_info, answers, global_metrics, proctoring_metrics)

def call_chatbot_gemini(query: str, session_context: Optional[Dict[str, Any]] = None) -> str:
    """
    Calls Gemini AI for intelligent candidate support chat.
    """
    if not GEMINI_AVAILABLE:
        return get_smart_offline_chatbot_response(query)

    try:
        model = get_generative_model()
        context_str = f"Context: Role '{session_context.get('role', 'Candidate')}', Stage: '{session_context.get('stage', 'Interview')}'." if session_context else ""
        
        prompt = f"""
You are Aria, an empathetic, encouraging, and highly knowledgeable AI Campus Placement Mentor for 3rd and 4th year Indian B.Tech engineering students on the Saarthak AI Interview platform.
You help students prepare for technical interviews (covering OOPs, DSA basics, DBMS/SQL, OS, Web fundamentals, and academic mini/major projects) and campus drives (TCS, Infosys, Wipro, Cognizant, Accenture, Capgemini, and product startups).
{context_str}
Candidate Message: "{query}"

Instructions:
- Provide a clear, supportive, structured, and practical answer in 2-4 sentences.
- If asked about technical concepts, explain them simply with a memorable real-world analogy.
- If asked for interview tips or advice, share actionable B.Tech campus placement strategies (e.g., STAR method for projects, how to structure technical answers, how to answer "Tell me about yourself").
- Maintain a warm, mentor-like, motivational tone!
"""
        response = model.generate_content(
            prompt,
            generation_config={"temperature": 0.7, "max_output_tokens": 250}
        )
        return response.text.strip()
    except Exception as e:
        logger.error(f"Error calling chatbot Gemini: {e}")
        return get_smart_offline_chatbot_response(query)

def get_smart_offline_chatbot_response(query: str) -> str:
    """Provides rich, intelligent answers for 3rd and 4th year B.Tech students when Gemini API is offline."""
    q = query.lower().strip()
    if any(k in q for k in ["hi", "hello", "hey", "good morning", "good evening", "namaste"]):
        return "Hello! I'm Aria, your AI Campus Placement Mentor. Whether you need help explaining your final year project, revising OOPs/DSA concepts, or understanding scoring, I'm here for you!"
    if any(k in q for k in ["tell me about yourself", "introduce", "self intro", "introduction"]):
        return "Structure your 1-minute intro in 3 parts: 1) Your name, college, branch, and GPA; 2) Key technical skills & favorite college project; 3) Your enthusiasm to start your career and contribute as a software engineer!"
    if any(k in q for k in ["project", "final year", "mini project"]):
        return "Use the STAR method: explain the Problem (Situation/Task), your chosen tech stack and your specific contribution (Action), and the final impact or working prototype (Result)!"
    if any(k in q for k in ["oop", "oops", "object oriented", "pillar"]):
        return "The 4 OOP pillars are: 1) Encapsulation (data hiding via private variables and getters/setters), 2) Abstraction (hiding implementation details via interfaces/abstract classes), 3) Inheritance (code reusability), and 4) Polymorphism (many forms via overloading and overriding)."
    if any(k in q for k in ["dsa", "data structure", "algorithm"]):
        return "For campus drives, master the fundamentals: Arrays vs Linked Lists, Stack (LIFO), Queue (FIFO), Binary Search (O(log N)), and Hash Maps (O(1) lookups). Explain your approach and time complexity before writing code!"
    if any(k in q for k in ["dbms", "sql", "acid", "join"]):
        return "Focus on: 1) Primary vs Foreign Keys, 2) INNER vs LEFT JOIN, 3) ACID properties (Atomicity, Consistency, Isolation, Durability with a banking example), and 4) Normalization basics (1NF, 2NF, 3NF)."
    if any(k in q for k in ["os", "operating system", "process", "thread", "deadlock"]):
        return "Key OS concepts asked in campus placements: Process vs Thread (threads share memory, processes don't), Deadlock conditions (Mutual exclusion, Hold & wait, No preemption, Circular wait), and Paging in Virtual Memory."
    if any(k in q for k in ["scoring", "how is score", "evaluate", "marks", "grade", "rubric"]):
        return "Your score evaluates: 1) Core technical accuracy & expected keywords, 2) Conceptual completeness, 3) Communication clarity & pacing, and 4) Proctoring integrity (tab focus and camera presence)."
    if any(k in q for k in ["proctor", "camera", "tab", "warning", "switch"]):
        return "Focus Guard tracks your webcam presence and tab focus. Switching tabs or obscuring your face logs proctoring warnings and reduces your trust score. Keep this tab active!"
    if any(k in q for k in ["campus", "placement", "tcs", "infosys", "wipro", "drive", "fresher"]):
        return "For campus placement drives, recruiters look for strong conceptual clarity in OOPs, basic problem-solving logic, an honest project explanation, and clear communication. Speak confidently and pause to structure your thoughts!"
    if any(k in q for k in ["nervous", "scared", "fear", "anxiety", "don't know", "dont know"]):
        return "It's completely natural to feel nervous! If you don't know an exact answer, stay calm, explain what related concepts you do know, and talk through your thought process. Recruiters appreciate honest problem-solving attitude!"
    if any(k in q for k in ["time", "duration", "how long"]):
        return "The interview is designed for 10 foundational questions and takes around 8 to 10 minutes. If you give detailed answers, Aria dynamically extends the time bonus."
    return "I'm here to help you ace your campus placement interview! Ask me about OOPs, DSA, DBMS, project explanation tips, 'Tell me about yourself', or scoring rules."

# Compact, College Student / Fresher Offline Question Pool
EXTENSIVE_OFFLINE_QUESTION_POOL = [
    # HR & Academic Projects
    {"question_text": "Tell me about yourself, your educational background, and your key technical interests.", "difficulty": "easy", "expected_keywords": ["education", "skills", "projects", "interests", "learning"], "category": "hr"},
    {"question_text": "Can you briefly describe your final year or favorite college project and the technologies you used?", "difficulty": "easy", "expected_keywords": ["project", "technologies", "problem", "solution", "implementation"], "category": "hr"},
    {"question_text": "How do you approach learning a new programming language or framework when starting a project?", "difficulty": "easy", "expected_keywords": ["documentation", "practice", "tutorials", "projects", "debugging"], "category": "hr"},
    {"question_text": "Describe a technical challenge you encountered while building a project and how you solved it.", "difficulty": "medium", "expected_keywords": ["problem", "debugging", "solution", "research", "result"], "category": "hr"},
    {"question_text": "How do you manage deadlines when balancing multiple coursework assignments and coding projects?", "difficulty": "easy", "expected_keywords": ["planning", "prioritization", "time management", "deadlines"], "category": "hr"},
    {"question_text": "Where do you see yourself in your software engineering career over the next 2 to 3 years?", "difficulty": "easy", "expected_keywords": ["career growth", "skills", "learning", "contributing", "goals"], "category": "hr"},
    
    # OOP Fundamentals
    {"question_text": "Explain the four core principles of Object-Oriented Programming (OOP) with simple everyday examples.", "difficulty": "easy", "expected_keywords": ["encapsulation", "abstraction", "inheritance", "polymorphism"], "category": "oops"},
    {"question_text": "What is the difference between method overloading and method overriding?", "difficulty": "easy", "expected_keywords": ["overloading", "overriding", "compile time", "runtime", "parameters"], "category": "oops"},
    {"question_text": "What is the difference between an Abstract Class and an Interface?", "difficulty": "medium", "expected_keywords": ["abstract class", "interface", "multiple inheritance", "implementation", "methods"], "category": "oops"},
    {"question_text": "What is Encapsulation, and how do getters and setters help achieve data hiding?", "difficulty": "easy", "expected_keywords": ["encapsulation", "data hiding", "access modifiers", "private", "getters"], "category": "oops"},
    {"question_text": "Explain the concept of Polymorphism with an example like Animal or Shape.", "difficulty": "easy", "expected_keywords": ["polymorphism", "many forms", "method overriding", "dynamic binding"], "category": "oops"},
    {"question_text": "What is a Constructor in OOP, and what is the difference between default and parameterized constructors?", "difficulty": "easy", "expected_keywords": ["constructor", "initialization", "default", "parameterized", "instantiation"], "category": "oops"},

    # DSA & Problem Solving (Fresher Basics)
    {"question_text": "What is the main difference between an Array and a Linked List in memory and access speed?", "difficulty": "easy", "expected_keywords": ["contiguous", "pointers", "o(1) access", "insertion", "node"], "category": "dsa"},
    {"question_text": "Explain the difference between a Stack (LIFO) and a Queue (FIFO) with real-world examples.", "difficulty": "easy", "expected_keywords": ["lifo", "fifo", "push", "pop", "enqueue", "dequeue"], "category": "dsa"},
    {"question_text": "How does Binary Search work, and what is its time complexity compared to Linear Search?", "difficulty": "easy", "expected_keywords": ["sorted array", "divide and conquer", "o(log n)", "mid point", "binary search"], "category": "dsa"},
    {"question_text": "How does a Hash Map or Dictionary achieve fast lookups, and what happens when two keys collide?", "difficulty": "medium", "expected_keywords": ["hash map", "key value", "hash function", "collision", "o(1)"], "category": "dsa"},
    {"question_text": "How would you check if a given string is a Palindrome?", "difficulty": "easy", "expected_keywords": ["two pointers", "reverse", "compare", "start end", "palindrome"], "category": "dsa"},
    {"question_text": "Explain Bubble Sort and compare it briefly with Merge Sort in terms of time complexity.", "difficulty": "medium", "expected_keywords": ["bubble sort", "merge sort", "o(n^2)", "o(n log n)", "divide and conquer"], "category": "dsa"},
    {"question_text": "What is Recursion? Give a classic example such as finding the factorial of a number.", "difficulty": "easy", "expected_keywords": ["recursion", "base condition", "recursive call", "stack", "factorial"], "category": "dsa"},
    {"question_text": "What is a Binary Tree, and what is the difference between Pre-order, In-order, and Post-order traversals?", "difficulty": "medium", "expected_keywords": ["binary tree", "root", "left right", "inorder", "traversal"], "category": "dsa"},

    # DBMS & SQL Basics
    {"question_text": "What is the difference between a Primary Key and a Foreign Key in a relational database?", "difficulty": "easy", "expected_keywords": ["primary key", "foreign key", "unique", "not null", "referential integrity"], "category": "dbms"},
    {"question_text": "What is the difference between INNER JOIN and LEFT JOIN in SQL?", "difficulty": "easy", "expected_keywords": ["inner join", "left join", "matching rows", "null values", "tables"], "category": "dbms"},
    {"question_text": "Explain the ACID properties in database management in simple terms.", "difficulty": "medium", "expected_keywords": ["atomicity", "consistency", "isolation", "durability", "transaction"], "category": "dbms"},
    {"question_text": "What is the difference between the WHERE clause and the HAVING clause in SQL?", "difficulty": "easy", "expected_keywords": ["where", "having", "group by", "aggregation", "filter"], "category": "dbms"},
    {"question_text": "What is Database Normalization and why do we normalize tables?", "difficulty": "easy", "expected_keywords": ["normalization", "redundancy", "1nf", "2nf", "3nf", "data integrity"], "category": "dbms"},
    {"question_text": "What is the difference between SQL (Relational) and NoSQL (Document/Key-Value) databases?", "difficulty": "easy", "expected_keywords": ["relational", "nosql", "tables", "schema", "scaling"], "category": "dbms"},

    # OS & Core CS Fundamentals
    {"question_text": "What is the difference between a Process and a Thread in operating systems?", "difficulty": "easy", "expected_keywords": ["process", "thread", "memory space", "context switch", "lightweight"], "category": "os"},
    {"question_text": "What is a Deadlock in operating systems, and what is one simple condition that causes it?", "difficulty": "easy", "expected_keywords": ["deadlock", "mutual exclusion", "hold and wait", "resource", "circular wait"], "category": "os"},
    {"question_text": "What is Virtual Memory, and how does it help a computer run large programs?", "difficulty": "medium", "expected_keywords": ["virtual memory", "ram", "paging", "hard disk", "page fault"], "category": "os"},
    {"question_text": "What is the difference between Multiprogramming, Multiprocessing, and Multitasking?", "difficulty": "medium", "expected_keywords": ["cpu", "cores", "processes", "concurrency", "execution"], "category": "os"},

    # Web Development & Networking Basics
    {"question_text": "What happens when you type a website URL into a browser and press Enter?", "difficulty": "easy", "expected_keywords": ["dns", "ip address", "http request", "server response", "rendering"], "category": "web_dev"},
    {"question_text": "What is the difference between HTTP GET and POST request methods?", "difficulty": "easy", "expected_keywords": ["get", "post", "url parameters", "request body", "security", "idempotent"], "category": "web_dev"},
    {"question_text": "What is the difference between HTTP and HTTPS?", "difficulty": "easy", "expected_keywords": ["http", "https", "ssl", "tls", "encryption", "port 443"], "category": "web_dev"},
    {"question_text": "What is a REST API, and what format is commonly used to exchange data?", "difficulty": "easy", "expected_keywords": ["rest", "api", "json", "http methods", "stateless"], "category": "web_dev"},
    {"question_text": "What is the difference between Client-Side scripting (Frontend) and Server-Side programming (Backend)?", "difficulty": "easy", "expected_keywords": ["frontend", "backend", "browser", "server", "database"], "category": "web_dev"},
]

def get_mock_adaptive_questions(role: str, skills: List[str], num_questions: int = 10) -> List[Dict[str, Any]]:
    """Generates a randomized, compact set of questions suitable for a college student/fresher with Question 1 as Self-Intro."""
    # Question 1: Always Tell me about yourself
    intro_question = {
        "question_text": "Tell me about yourself, your educational background, and your key technical interests.",
        "difficulty": "easy",
        "expected_keywords": ["background", "education", "skills", "projects", "interests"],
        "category": "hr",
        "role": role
    }
    
    pool_without_intro = [q for q in EXTENSIVE_OFFLINE_QUESTION_POOL if "tell me about yourself" not in q["question_text"].lower()]
    
    selected = []
    
    # 1 Project / HR
    hr_pool = [q for q in pool_without_intro if q["category"] == "hr"]
    if hr_pool:
        selected.extend(random.sample(hr_pool, min(1, len(hr_pool))))
    
    # 3 DSA
    dsa_pool = [q for q in pool_without_intro if q["category"] == "dsa"]
    if dsa_pool:
        selected.extend(random.sample(dsa_pool, min(3, len(dsa_pool))))
    
    # 2 OOP
    oops_pool = [q for q in pool_without_intro if q["category"] == "oops"]
    if oops_pool:
        selected.extend(random.sample(oops_pool, min(2, len(oops_pool))))
    
    # 2 DBMS
    dbms_pool = [q for q in pool_without_intro if q["category"] == "dbms"]
    if dbms_pool:
        selected.extend(random.sample(dbms_pool, min(2, len(dbms_pool))))
    
    # 1 OS / Web
    other_pool = [q for q in pool_without_intro if q["category"] in ["os", "web_dev"]]
    remaining = max(1, (num_questions - 1) - len(selected))
    if other_pool:
        selected.extend(random.sample(other_pool, min(remaining, len(other_pool))))
    
    formatted_remaining = []
    for item in selected:
        q_copy = dict(item)
        q_copy["role"] = role
        formatted_remaining.append(q_copy)
    
    random.shuffle(formatted_remaining)
    return [intro_question] + formatted_remaining[:num_questions - 1]

def generate_mock_final_report(
    candidate_info: Dict[str, Any],
    answers: List[Dict[str, Any]],
    global_metrics: Dict[str, Any],
    proctoring_metrics: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Generates a comprehensive rule-based evaluation report."""
    valid_scores = [a["overall_score"] for a in answers if a.get("overall_score") is not None]
    avg_answer_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0.0
    
    eye_contact = global_metrics.get("eye_contact_score", 82.0)
    attention = global_metrics.get("attention_score", 88.0)
    
    # Factor proctoring into integrity
    tab_switches = (proctoring_metrics or {}).get("tab_switches", 0)
    integrity_score = (proctoring_metrics or {}).get("integrity_score")
    if integrity_score is None:
        integrity_score = max(50.0, 100.0 - (tab_switches * 10.0))
    integrity_score = round(max(30.0, min(100.0, float(integrity_score))), 1)
    
    technical_score = round(avg_answer_score * 0.95, 1)
    communication_score = round((avg_answer_score * 0.65) + (eye_contact * 0.18) + (attention * 0.17), 1)
    overall_score = round((technical_score * 0.55) + (communication_score * 0.35) + (integrity_score * 0.10), 1)
    
    if overall_score >= 82:
        status = "Strong Hire"
        rec_text = f"Candidate demonstrated strong technical and communication skills suitable for the {candidate_info.get('job_role', 'Engineering')} role."
    elif overall_score >= 70:
        status = "Hire"
        rec_text = f"Candidate shows acceptable fundamentals for the {candidate_info.get('job_role', 'Engineering')} role with some gaps to address."
    elif overall_score >= 50:
        status = "Needs Review"
        rec_text = f"Candidate showed limited knowledge of core concepts required for the {candidate_info.get('job_role', 'Engineering')} role. Significant improvement needed before hire."
    else:
        status = "Reject"
        rec_text = f"Candidate failed to demonstrate basic competency for the {candidate_info.get('job_role', 'Engineering')} role. Answers were mostly absent or incorrect."
    
    if integrity_score >= 95:
        integrity_verdict = f"High exam integrity ({round(integrity_score)}%). Natural eye movements, blinking, and speaking posture maintained with zero false penalties."
    elif integrity_score >= 80:
        integrity_verdict = f"Solid exam integrity ({round(integrity_score)}%). Minor focus adjustments ({tab_switches} alerts) within allowable exam thresholds."
    else:
        integrity_verdict = f"Proctoring caution logged: {tab_switches} focus interruptions with {round(integrity_score)}% integrity trust score."

    return {
        "technical_score": technical_score,
        "communication_score": communication_score,
        "overall_score": overall_score,
        "recommendations": f"{rec_text} Overall recommendation status: {status}.",
        "strengths": [
            "Showed up and attempted the interview session.",
            "Camera remained active throughout the session.",
            "Proctoring compliance was maintained."
        ] if overall_score < 50 else [
            "Clear articulation of fundamental engineering principles.",
            "Methodical approach to problem-solving.",
            "Maintained professional camera engagement throughout the session."
        ],
        "weaknesses": [
            "Did not provide substantive answers to technical questions.",
            "Needs to study core B.Tech subjects: DSA, OOPs, DBMS, OS.",
            "Must practice speaking answers aloud before attempting interviews."
        ] if overall_score < 50 else [
            "Could discuss real-world edge-cases and optimization trade-offs in deeper detail.",
            "Can refine concise pacing during open-ended conceptual explanations."
        ],
        "learning_plan": {
            "short_term": [
                "Practice time and space complexity trade-offs for high-scale queries.",
                "Review concurrent multithreading patterns and distributed caching strategies."
            ],
            "long_term": [
                "Build end-to-end cloud-native microservices with production telemetry.",
                "Strengthen system architecture design and fault-tolerant distributed principles."
            ]
        },
        "integrity_verdict": integrity_verdict
    }
