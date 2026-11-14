import logging
from sqlalchemy.orm import Session
from app.models.question import QuestionBank

logger = logging.getLogger("app.services.seeder")

# Curated beginner-friendly campus placement questions tailored for 3rd and 4th year Indian B.Tech students
SEED_QUESTIONS = [
    # ═════════════════════════════════════════════════════
    # 1. HR, Self-Intro & Academic Projects (Mandatory Campus Prep)
    # ═════════════════════════════════════════════════════
    {
        "question_text": "Tell me about yourself, your educational background, and your key technical interests.",
        "difficulty": "easy",
        "expected_keywords": ["education", "skills", "projects", "interests", "learning", "branch", "engineering"],
        "category": "hr",
        "role": "Software Engineer"
    },
    {
        "question_text": "Can you walk me through your college mini or final year project, the problem it solves, and the technologies you used?",
        "difficulty": "easy",
        "expected_keywords": ["project", "problem", "solution", "technologies", "frontend", "backend", "database", "implementation"],
        "category": "hr",
        "role": "Software Engineer"
    },
    {
        "question_text": "What was the most challenging bug or obstacle you encountered during your college project, and how did you debug it?",
        "difficulty": "easy",
        "expected_keywords": ["bug", "error", "debugging", "logs", "solution", "stack overflow", "testing"],
        "category": "hr",
        "role": "Software Engineer"
    },
    {
        "question_text": "How do you manage your time when balancing university semester exams, lab assignments, and technical preparation?",
        "difficulty": "easy",
        "expected_keywords": ["prioritization", "schedule", "time management", "deadlines", "consistency", "planning"],
        "category": "hr",
        "role": "Software Engineer"
    },
    {
        "question_text": "Where do you see yourself in your software engineering career over the next 2 to 3 years after graduating?",
        "difficulty": "easy",
        "expected_keywords": ["learning", "growth", "contributing", "skills", "mentorship", "fullstack", "developer"],
        "category": "hr",
        "role": "Software Engineer"
    },

    # ═════════════════════════════════════════════════════
    # 2. Object-Oriented Programming (OOPs) - Core Indian Campus Focus
    # ═════════════════════════════════════════════════════
    {
        "question_text": "Explain the four core principles of Object-Oriented Programming (Encapsulation, Abstraction, Inheritance, Polymorphism) with simple real-world examples.",
        "difficulty": "easy",
        "expected_keywords": ["encapsulation", "abstraction", "inheritance", "polymorphism", "data hiding", "reusability"],
        "category": "oops",
        "role": "Software Engineer"
    },
    {
        "question_text": "What is the difference between Method Overloading (compile-time) and Method Overriding (runtime) in Java or C++?",
        "difficulty": "easy",
        "expected_keywords": ["overloading", "overriding", "compile time", "runtime", "signature", "parameters", "inheritance"],
        "category": "oops",
        "role": "Software Engineer"
    },
    {
        "question_text": "What is the difference between an Abstract Class and an Interface, and when should a developer use each?",
        "difficulty": "easy",
        "expected_keywords": ["abstract class", "interface", "multiple inheritance", "implementation", "methods", "contracts"],
        "category": "oops",
        "role": "Software Engineer"
    },
    {
        "question_text": "What is Encapsulation, and how do access specifiers like private, protected, and public help achieve data hiding?",
        "difficulty": "easy",
        "expected_keywords": ["encapsulation", "data hiding", "private", "protected", "public", "getters", "setters"],
        "category": "oops",
        "role": "Software Engineer"
    },
    {
        "question_text": "What is a Constructor in OOP, and how does a Default Constructor differ from a Parameterized Constructor?",
        "difficulty": "easy",
        "expected_keywords": ["constructor", "initialization", "default", "parameterized", "object creation", "instantiation"],
        "category": "oops",
        "role": "Software Engineer"
    },

    # ═════════════════════════════════════════════════════
    # 3. Data Structures & Basic Algorithms (Beginner-Friendly DSA)
    # ═════════════════════════════════════════════════════
    {
        "question_text": "What is the primary difference between an Array and a Singly Linked List in memory allocation and element access speed?",
        "difficulty": "easy",
        "expected_keywords": ["contiguous", "pointers", "o(1) access", "insertion", "node", "dynamic size", "array", "linked list"],
        "category": "dsa",
        "role": "Software Engineer"
    },
    {
        "question_text": "Explain how a Stack (LIFO) and a Queue (FIFO) work, giving one practical real-world computing example for each.",
        "difficulty": "easy",
        "expected_keywords": ["lifo", "fifo", "push", "pop", "enqueue", "dequeue", "undo redo", "printer queue"],
        "category": "dsa",
        "role": "Software Engineer"
    },
    {
        "question_text": "How does Binary Search work on a sorted array, and why does it have an O(log N) time complexity compared to Linear Search O(N)?",
        "difficulty": "easy",
        "expected_keywords": ["sorted array", "divide and conquer", "o(log n)", "mid point", "binary search", "halving"],
        "category": "dsa",
        "role": "Software Engineer"
    },
    {
        "question_text": "How would you check if a given string or number is a Palindrome using the two-pointer approach?",
        "difficulty": "easy",
        "expected_keywords": ["two pointers", "start", "end", "reverse", "compare", "palindrome", "o(n)"],
        "category": "dsa",
        "role": "Software Engineer"
    },
    {
        "question_text": "What is a Hash Map or Dictionary, and how does it achieve average O(1) time complexity for search and insertion?",
        "difficulty": "easy",
        "expected_keywords": ["hash map", "key value", "hash function", "collision", "o(1)", "bucket"],
        "category": "dsa",
        "role": "Software Engineer"
    },
    {
        "question_text": "What is Recursion in programming, and why is the base case condition critical to avoid stack overflow?",
        "difficulty": "easy",
        "expected_keywords": ["recursion", "base condition", "call stack", "stack overflow", "factorial", "subproblem"],
        "category": "dsa",
        "role": "Software Engineer"
    },
    {
        "question_text": "Briefly compare Bubble Sort and Merge Sort in terms of algorithmic strategy and time complexity.",
        "difficulty": "medium",
        "expected_keywords": ["bubble sort", "merge sort", "o(n^2)", "o(n log n)", "divide and conquer", "comparisons"],
        "category": "dsa",
        "role": "Software Engineer"
    },

    # ═════════════════════════════════════════════════════
    # 4. DBMS & SQL Basics (3rd/4th Year Academic Subject)
    # ═════════════════════════════════════════════════════
    {
        "question_text": "What is the difference between a Primary Key and a Foreign Key in relational database design?",
        "difficulty": "easy",
        "expected_keywords": ["primary key", "foreign key", "unique", "not null", "referential integrity", "relationships"],
        "category": "dbms",
        "role": "Software Engineer"
    },
    {
        "question_text": "Explain the difference between INNER JOIN and LEFT JOIN in SQL with a simple two-table example.",
        "difficulty": "easy",
        "expected_keywords": ["inner join", "left join", "matching rows", "null values", "tables", "records"],
        "category": "dbms",
        "role": "Software Engineer"
    },
    {
        "question_text": "What are the ACID properties in database management? Briefly explain each with a bank transaction example.",
        "difficulty": "medium",
        "expected_keywords": ["acid", "atomicity", "consistency", "isolation", "durability", "transaction", "rollback"],
        "category": "dbms",
        "role": "Software Engineer"
    },
    {
        "question_text": "What is the difference between the WHERE clause and the HAVING clause in an SQL query?",
        "difficulty": "easy",
        "expected_keywords": ["where", "having", "group by", "aggregation", "filter", "rows"],
        "category": "dbms",
        "role": "Software Engineer"
    },
    {
        "question_text": "What is Database Normalization and what is the primary goal of 1NF, 2NF, and 3NF?",
        "difficulty": "easy",
        "expected_keywords": ["normalization", "redundancy", "1nf", "2nf", "3nf", "data integrity", "anomalies"],
        "category": "dbms",
        "role": "Software Engineer"
    },
    {
        "question_text": "What is the difference between DDL (Data Definition Language) and DML (Data Manipulation Language) commands in SQL?",
        "difficulty": "easy",
        "expected_keywords": ["ddl", "dml", "create", "alter", "drop", "insert", "update", "delete", "schema"],
        "category": "dbms",
        "role": "Software Engineer"
    },

    # ═════════════════════════════════════════════════════
    # 5. Operating Systems (Core B.Tech Semester Subject)
    # ═════════════════════════════════════════════════════
    {
        "question_text": "What is the fundamental difference between a Process and a Thread in operating systems?",
        "difficulty": "easy",
        "expected_keywords": ["process", "thread", "memory space", "context switch", "lightweight", "multithreading"],
        "category": "os",
        "role": "Software Engineer"
    },
    {
        "question_text": "What is a Deadlock in operating systems, and what are the four necessary Coffman conditions for a deadlock to occur?",
        "difficulty": "medium",
        "expected_keywords": ["deadlock", "mutual exclusion", "hold and wait", "no preemption", "circular wait"],
        "category": "os",
        "role": "Software Engineer"
    },
    {
        "question_text": "What is Virtual Memory, and how does paging help execute programs larger than physical RAM?",
        "difficulty": "easy",
        "expected_keywords": ["virtual memory", "ram", "paging", "pages", "page fault", "hard drive"],
        "category": "os",
        "role": "Software Engineer"
    },
    {
        "question_text": "What is the difference between Preemptive and Non-Preemptive CPU scheduling?",
        "difficulty": "easy",
        "expected_keywords": ["preemptive", "non preemptive", "cpu scheduling", "round robin", "fcfs", "priority"],
        "category": "os",
        "role": "Software Engineer"
    },

    # ═════════════════════════════════════════════════════
    # 6. Web Basics, Computer Networks & Programming Languages
    # ═════════════════════════════════════════════════════
    {
        "question_text": "What happens step-by-step when you type a website URL into a browser and press Enter?",
        "difficulty": "easy",
        "expected_keywords": ["dns", "ip address", "tcp handshake", "http request", "server response", "rendering"],
        "category": "web_dev",
        "role": "Software Engineer"
    },
    {
        "question_text": "What is the difference between HTTP and HTTPS, and why is SSL/TLS encryption important?",
        "difficulty": "easy",
        "expected_keywords": ["http", "https", "ssl", "tls", "encryption", "port 80", "port 443", "security"],
        "category": "web_dev",
        "role": "Software Engineer"
    },
    {
        "question_text": "What is the difference between HTTP GET and POST request methods?",
        "difficulty": "easy",
        "expected_keywords": ["get", "post", "url parameters", "request body", "security", "idempotent"],
        "category": "web_dev",
        "role": "Software Engineer"
    },
    {
        "question_text": "Explain the difference between a List and a Tuple in Python with respect to mutability and syntax.",
        "difficulty": "easy",
        "expected_keywords": ["mutable", "immutable", "syntax", "performance", "tuple", "list", "brackets"],
        "category": "python",
        "role": "Software Engineer"
    },
    {
        "question_text": "What is the difference between JDK, JRE, and JVM in the Java ecosystem?",
        "difficulty": "easy",
        "expected_keywords": ["jdk", "jre", "jvm", "development", "runtime", "virtual machine", "bytecode"],
        "category": "java",
        "role": "Software Engineer"
    },
    {
        "question_text": "In Java, what is the difference between using the '==' operator and the '.equals()' method when comparing strings?",
        "difficulty": "easy",
        "expected_keywords": ["==", "equals", "reference comparison", "content comparison", "memory address", "string pool"],
        "category": "java",
        "role": "Software Engineer"
    }
]

def seed_questions(db: Session) -> None:
    """
    Seeds the question_bank table with beginner-friendly campus placement questions
    for 3rd and 4th year Indian B.Tech students. Adds any missing questions.
    """
    target_roles = ["Software Engineer", "Backend Engineer", "Frontend Engineer", "Fullstack Engineer"]
    existing = set(
        db.query(QuestionBank.question_text, QuestionBank.role).all()
    )

    added_count = 0
    for q_data in SEED_QUESTIONS:
        for role in target_roles:
            key = (q_data["question_text"], role)
            if key not in existing:
                q = QuestionBank(
                    question_text=q_data["question_text"],
                    difficulty=q_data["difficulty"],
                    expected_keywords=q_data["expected_keywords"],
                    category=q_data["category"],
                    role=role
                )
                db.add(q)
                existing.add(key)
                added_count += 1

    if added_count > 0:
        db.commit()
        logger.info(f"Seeded {added_count} beginner-friendly campus placement questions into database.")
    else:
        logger.info(f"Question bank already up-to-date with {len(existing)} role-question entries.")
