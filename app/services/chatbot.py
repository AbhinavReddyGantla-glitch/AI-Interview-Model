import re
import logging
from typing import Optional, Dict, Any
from app.services.gemini import call_chatbot_gemini

logger = logging.getLogger("app.services.chatbot")

EXPANDED_FAQ_DATA = [
    # ═════════════════════════════════════════════════
    # 1. Campus Placement & Interview Strategy (3rd/4th Year B.Tech)
    # ═════════════════════════════════════════════════
    {
        "keywords": ["campus", "placement", "placement tips", "drive", "tcs", "infosys", "wipro", "accenture", "cognizant", "capgemini"],
        "answer": "For 3rd & 4th year campus placement drives: 1) Master core OOPs (pillars, interface vs abstract class); 2) Revise fundamental DSA (Arrays, Linked Lists, Stacks, Queues, Binary Search); 3) Know your DBMS basics (Joins, Primary/Foreign keys, ACID); 4) Explain your academic project using the STAR method; and 5) Speak clearly with structured thoughts!"
    },
    {
        "keywords": ["tell me about yourself", "introduce", "introduction", "self intro", "how to introduce"],
        "answer": "Use the 3-step Fresher Pitch: 1) Personal & College: 'I am [Name], currently in my 3rd/4th year of B.Tech in [Branch] at [College]'; 2) Tech Skills & Projects: 'My core strengths are in [Java/Python/Web/DSA], and I recently built [Project Name]'; 3) Career Goal: 'I'm excited to start my career as a software engineer where I can solve real-world problems!'"
    },
    {
        "keywords": ["project", "final year project", "mini project", "explain project", "how to explain project"],
        "answer": "Explain your college project using the STAR framework: 1) Situation: What problem does your project solve? 2) Task: What was your specific responsibility? 3) Action: What technologies (React, Python, Java, SQL, Node) and libraries did you use? 4) Result: What was the outcome or working prototype? Be ready to explain one bug you solved!"
    },
    {
        "keywords": ["nervous", "scared", "fear", "anxiety", "don't know", "dont know", "stuck"],
        "answer": "Don't panic! It's completely normal to feel nervous. If you don't know the exact answer to a question: 1) Take a deep breath; 2) Be honest: 'I am not 100% sure about that specific detail, but based on my understanding of related concepts...'; 3) Explain your reasoning. Recruiters value honesty and logical problem-solving over memorization!"
    },
    {
        "keywords": ["tip", "advice", "how to prepare", "best way to answer", "strategy", "preparation"],
        "answer": "Top 3 Interview Tips: 1) State definition first, then provide a code or real-world example; 2) For DSA questions, always state the Time and Space Complexity (Big-O); 3) Speak steadily and naturally—Aria evaluates clarity and conceptual completeness!"
    },

    # ═════════════════════════════════════════════════
    # 2. Core CS Curriculum Revision (OOP, DSA, DBMS, OS)
    # ═════════════════════════════════════════════════
    {
        "keywords": ["oop", "oops", "object oriented", "four pillars", "pillars of oop"],
        "answer": "The 4 OOP Pillars are: 1) Encapsulation: Bundling data and methods into a single class with private variables; 2) Abstraction: Hiding implementation details and showing only essential features; 3) Inheritance: Deriving child classes from a parent class for reusability; 4) Polymorphism: Performing a single action in different ways (Overloading & Overriding)."
    },
    {
        "keywords": ["overloading", "overriding", "difference between overloading and overriding"],
        "answer": "Method Overloading happens within the SAME class: methods share the same name but have DIFFERENT parameters (Compile-time / Static polymorphism). Method Overriding happens between Parent and Child classes: child class redefines a parent method with the EXACT SAME signature (Runtime / Dynamic polymorphism)."
    },
    {
        "keywords": ["interface", "abstract class", "difference between abstract class and interface"],
        "answer": "An Abstract Class can have both abstract (without body) and concrete methods, instance variables, and constructors. An Interface historically contains only method declarations (contracts) and constants (though Java 8+ allows default/static methods). A class can implement multiple interfaces but extend only one abstract class."
    },
    {
        "keywords": ["primary key", "foreign key", "difference between primary key and foreign key"],
        "answer": "A Primary Key uniquely identifies each record in a table and CANNOT be NULL. A Foreign Key is a field in one table that references the Primary Key of another table, establishing a relationship and enforcing referential integrity (foreign keys can accept NULLs)."
    },
    {
        "keywords": ["acid", "acid properties", "atomicity", "consistency", "isolation", "durability"],
        "answer": "ACID properties ensure reliable database transactions: 1) Atomicity: 'All or nothing' execution; 2) Consistency: Database remains in a valid state before and after transaction; 3) Isolation: Concurrent transactions don't interfere with each other; 4) Durability: Committed data is permanently saved even during power failure."
    },
    {
        "keywords": ["join", "inner join", "left join", "sql join", "joins in sql"],
        "answer": "INNER JOIN returns only rows where there is a match in BOTH tables. LEFT JOIN returns ALL rows from the left table, plus matched rows from the right table (with NULL values for non-matching rows on the right)."
    },
    {
        "keywords": ["array vs linked list", "difference between array and linked list", "linked list"],
        "answer": "Arrays store elements in contiguous memory with instant O(1) random access by index, but have fixed size and costly O(N) insertions. Linked Lists store nodes dynamically via pointers with flexible sizing and O(1) pointer-based insertions, but require sequential O(N) access and extra memory for pointer links."
    },
    {
        "keywords": ["stack", "queue", "difference between stack and queue", "lifo", "fifo"],
        "answer": "A Stack follows LIFO (Last In First Out)—the last added element is removed first (e.g., browser Back button, Ctrl+Z Undo). A Queue follows FIFO (First In First Out)—the first added element is processed first (e.g., printer queue, ticket counter line)."
    },
    {
        "keywords": ["binary search", "how does binary search work"],
        "answer": "Binary Search operates on a SORTED array using divide-and-conquer: it checks the middle element and cuts the search space in half each step. Because it repeatedly halves the array, its time complexity is O(log N), compared to Linear Search O(N)."
    },
    {
        "keywords": ["process vs thread", "difference between process and thread", "process", "thread"],
        "answer": "A Process is an executing program with its own independent memory address space and heavy context-switching overhead. A Thread is a lightweight sub-execution unit within a process that shares the process's code, data, and heap memory."
    },
    {
        "keywords": ["deadlock", "what is deadlock", "conditions for deadlock", "coffman"],
        "answer": "A Deadlock occurs when two or more processes are permanently blocked because each holds a resource that the other process needs. The 4 Coffman conditions required for deadlock are: Mutual Exclusion, Hold and Wait, No Preemption, and Circular Wait."
    },

    # ═════════════════════════════════════════════════
    # 3. Platform Features: End Interview, Proctoring, Scoring
    # ═════════════════════════════════════════════════
    {
        "keywords": ["end interview", "finish interview", "stop interview", "quit interview", "exit interview", "leave interview"],
        "answer": "You can conclude your interview at any time by clicking the red 'End Interview' button located at the top right of your screen. A confirmation dialog will appear, and confirming will safely submit your answers to Gemini AI to generate your final performance scorecard!"
    },
    {
        "keywords": ["how long", "duration", "time limit", "total time", "interview length", "minutes"],
        "answer": "The interview typically takes 8 to 12 minutes across 10 foundational questions. As you explain concepts in detail, Aria dynamically grants time bonuses to ensure you finish comfortably."
    },
    {
        "keywords": ["topics", "syllabus", "what will be asked", "questions about", "question types"],
        "answer": "Questions are beginner-friendly and tailored for 3rd/4th year B.Tech students: Self-Intro, Academic Mini/Major Projects, OOPs Pillars, Basic DSA (Arrays, Linked Lists, Stacks, Binary Search), DBMS/SQL, and Core OS fundamentals."
    },
    {
        "keywords": ["score", "scoring", "evaluate", "marks", "calculated", "criteria", "grading", "report"],
        "answer": "Aria's multi-metric scoring evaluates: 1) Technical accuracy & key concept terms (40%), 2) Answer completeness & depth (30%), 3) Communication fluency & confidence (20%), and 4) Proctoring integrity trust (10%)."
    },
    {
        "keywords": ["proctor", "tab switch", "camera requirement", "warning", "focus", "integrity", "cheating"],
        "answer": "Focus Guard proctoring monitors your webcam feed and tab focus in real-time. Switching tabs or obscuring your camera logs a warning and deducts from your proctoring trust score. Keep your browser tab open and focused!"
    },
    {
        "keywords": ["technical issue", "mic not working", "camera error", "support", "help", "glitch", "bug", "audio"],
        "answer": "If you experience microphone or camera issues: 1) Click the padlock/settings icon in your browser URL bar and allow Camera and Microphone permissions; 2) Ensure you are on Google Chrome or Microsoft Edge; 3) Refresh the page."
    },
    {
        "keywords": ["who are you", "what is aria", "who is aria", "bot", "assistant"],
        "answer": "I'm Aria 😊, your AI Campus Placement Interviewer and real-time mentor! I ask structured technical questions with live voice lip-sync, listen to your answers, and provide detailed feedback to help you get placed!"
    },
    {
        "keywords": ["hello", "hi", "hey", "good morning", "good evening", "greetings", "namaste"],
        "answer": "Hello! I'm Aria 😊. I'm here to support you throughout your campus placement preparation and interview session. Ask me any technical question or interview tip!"
    },
    {
        "keywords": ["thank", "thanks", "helpful", "awesome", "great"],
        "answer": "You're very welcome! Stay calm, speak clearly into your mic, structure your thoughts, and best of luck with your placement interview! 🚀"
    }
]

def handle_chatbot_query(query: str, session_context: Optional[Dict[str, Any]] = None) -> str:
    """
    Intelligent campus-placement chatbot handler:
    1. Pattern & keyword matching against curated B.Tech placement guidance.
    2. Fallback to Gemini AI for deep, customized mentoring.
    3. Safe default fallback to always provide actionable advice.
    """
    if not query or not query.strip():
        return "Feel free to ask me anything about campus placements, OOPs, DSA, DBMS, project tips, or how to end your interview!"

    q_lower = query.lower().strip()

    # Pattern check across FAQs
    for item in EXPANDED_FAQ_DATA:
        for kw in item["keywords"]:
            if kw in q_lower or re.search(r'\b' + re.escape(kw) + r'\b', q_lower):
                logger.info(f"FAQ keyword match found for '{kw}' in query: '{query}'")
                return item["answer"]

    # Delegate to Gemini AI
    logger.info(f"Delegating chatbot query '{query}' to Gemini AI.")
    try:
        response = call_chatbot_gemini(query, session_context)
        if response and len(response.strip()) > 5:
            return response
    except Exception as e:
        logger.error(f"Error getting response from Gemini: {e}")

    return "I'm here to help you crack your campus placement interview! Ask me about OOPs pillars, DSA basics, SQL queries, explaining your final year project, or the 'End Interview' button at the top right."
