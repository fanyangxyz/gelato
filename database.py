import json
import os
from datetime import datetime
from pathlib import Path

# Check if we're on Streamlit Cloud (has secrets) or local
def is_cloud():
    try:
        import streamlit as st
        return "GITHUB_TOKEN" in st.secrets
    except Exception:
        return False


# =============================================================================
# GitHub-based storage (for Streamlit Cloud)
# =============================================================================

class GitHubStorage:
    def __init__(self):
        import streamlit as st
        from github import Github

        self.token = st.secrets["GITHUB_TOKEN"]
        self.repo_name = st.secrets["GITHUB_REPO"]  # e.g., "username/gelato"
        self.file_path = "data/progress.json"

        self.gh = Github(self.token)
        self.repo = self.gh.get_repo(self.repo_name)
        self._cache = None
        self._sha = None

    def _load(self):
        """Load progress data from GitHub."""
        if self._cache is not None:
            return self._cache

        try:
            contents = self.repo.get_contents(self.file_path)
            self._sha = contents.sha
            self._cache = json.loads(contents.decoded_content.decode())
        except Exception:
            self._cache = {"progress": [], "users": []}
            self._sha = None

        return self._cache

    def _save(self, data):
        """Save progress data to GitHub."""
        content = json.dumps(data, indent=2)
        message = f"Update progress - {datetime.now().isoformat()}"

        try:
            if self._sha:
                self.repo.update_file(self.file_path, message, content, self._sha)
            else:
                self.repo.create_file(self.file_path, message, content)

            # Refresh SHA for next update
            contents = self.repo.get_contents(self.file_path)
            self._sha = contents.sha
            self._cache = data
        except Exception as e:
            print(f"Error saving to GitHub: {e}")
            raise

    def get_progress(self, user_id: str = None):
        progress = self._load().get("progress", [])
        if user_id:
            progress = [p for p in progress if p.get("user_id") == user_id]
        return progress

    def add_progress(self, entry):
        data = self._load()
        entry["id"] = len(data["progress"]) + 1
        entry["completed_at"] = datetime.now().isoformat()
        data["progress"].append(entry)
        self._save(data)

    def get_users(self):
        return self._load().get("users", [])

    def add_user(self, username: str):
        data = self._load()
        if "users" not in data:
            data["users"] = []
        if username not in data["users"]:
            data["users"].append(username)
            self._save(data)

    def clear_cache(self):
        """Force reload from GitHub on next access."""
        self._cache = None
        self._sha = None


# =============================================================================
# Local SQLite storage (for development)
# =============================================================================

class LocalStorage:
    def __init__(self):
        import sqlite3
        self.db_path = Path(__file__).parent / "data" / "biology_learning.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self):
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_conn()
        cursor = conn.cursor()

        # Create users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL
            )
        """)

        # Create progress table with user_id
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                topic_id INTEGER NOT NULL,
                subtopic TEXT,
                activity_type TEXT NOT NULL,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                score INTEGER,
                time_spent_minutes INTEGER
            )
        """)

        conn.commit()
        conn.close()

    def get_progress(self, user_id: str = None):
        conn = self._get_conn()
        cursor = conn.cursor()
        if user_id:
            cursor.execute("SELECT * FROM progress WHERE user_id = ? ORDER BY completed_at DESC", (user_id,))
        else:
            cursor.execute("SELECT * FROM progress ORDER BY completed_at DESC")
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def add_progress(self, entry):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO progress (user_id, topic_id, subtopic, activity_type, score, time_spent_minutes)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (entry.get("user_id"), entry.get("topic_id"), entry.get("subtopic"),
             entry.get("activity_type"), entry.get("score"), entry.get("time_spent_minutes"))
        )
        conn.commit()
        conn.close()

    def get_users(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM users ORDER BY username")
        rows = cursor.fetchall()
        conn.close()
        return [row["username"] for row in rows]

    def add_user(self, username: str):
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO users (username) VALUES (?)", (username,))
            conn.commit()
        except Exception:
            pass  # User already exists
        conn.close()

    def clear_cache(self):
        pass  # No caching for local


# =============================================================================
# Storage interface (auto-selects based on environment)
# =============================================================================

_storage = None

def get_storage():
    global _storage
    if _storage is None:
        if is_cloud():
            _storage = GitHubStorage()
        else:
            _storage = LocalStorage()
    return _storage


# =============================================================================
# Topics (always read from local JSON, never changes)
# =============================================================================

TOPICS_PATH = Path(__file__).parent / "data" / "topics.json"

def get_all_topics():
    """Get all topics with their subtopics."""
    with open(TOPICS_PATH) as f:
        data = json.load(f)
    return data["topics"]


def get_topic_by_id(topic_id: int):
    """Get a single topic by ID."""
    topics = get_all_topics()
    for topic in topics:
        if topic["id"] == topic_id:
            return topic
    return None


# =============================================================================
# User operations
# =============================================================================

def get_users():
    """Get all registered usernames."""
    return get_storage().get_users()


def add_user(username: str):
    """Add a new user."""
    get_storage().add_user(username)


# =============================================================================
# Database operations (compatible interface)
# =============================================================================

# Current user context (set by the app)
_current_user = None

def set_current_user(username: str):
    """Set the current user context."""
    global _current_user
    _current_user = username


def get_current_user():
    """Get the current user context."""
    return _current_user


def init_db():
    """Initialize the database."""
    get_storage()  # Ensures storage is initialized


def record_progress(topic_id: int, subtopic: str, activity_type: str,
                    score: int = None, time_spent_minutes: int = None,
                    details: dict = None):
    """Record a completed activity for the current user."""
    if not _current_user:
        raise ValueError("No user set. Call set_current_user first.")

    # Skip saving for guests
    if _current_user == "_guest_":
        return

    entry = {
        "user_id": _current_user,
        "topic_id": topic_id,
        "subtopic": subtopic,
        "activity_type": activity_type,
        "score": score,
        "time_spent_minutes": time_spent_minutes
    }

    # Add activity-specific details
    if details:
        entry["details"] = details

    get_storage().add_progress(entry)


def record_read(topic_id: int, subtopic: str, time_spent_minutes: int = 10):
    """Record a reading activity."""
    record_progress(
        topic_id=topic_id,
        subtopic=subtopic,
        activity_type="read",
        time_spent_minutes=time_spent_minutes
    )


def record_test(topic_id: int, subtopic: str, score: int, questions: list,
                user_answers: dict, time_spent_minutes: int = 15):
    """Record a test activity with detailed question results."""
    # Build detailed results for each question
    question_results = []
    for i, q in enumerate(questions):
        user_answer_idx = user_answers.get(i, -1)
        correct_idx = q.get("correct", 0)
        is_correct = user_answer_idx == correct_idx

        question_results.append({
            "question": q.get("question", ""),
            "user_answer": q["options"][user_answer_idx] if 0 <= user_answer_idx < len(q["options"]) else None,
            "correct_answer": q["options"][correct_idx] if 0 <= correct_idx < len(q["options"]) else None,
            "is_correct": is_correct
        })

    record_progress(
        topic_id=topic_id,
        subtopic=subtopic,
        activity_type="test",
        score=score,
        time_spent_minutes=time_spent_minutes,
        details={
            "question_count": len(questions),
            "correct_count": sum(1 for r in question_results if r["is_correct"]),
            "questions": question_results
        }
    )


def record_flashcards(topic_id: int, subtopic: str, card_count: int,
                      time_spent_minutes: int = 10):
    """Record a flashcard activity."""
    record_progress(
        topic_id=topic_id,
        subtopic=subtopic,
        activity_type="flashcard",
        time_spent_minutes=time_spent_minutes,
        details={
            "card_count": card_count
        }
    )


def record_summary(topic_id: int, subtopic: str, time_spent_minutes: int = 5):
    """Record a summary activity."""
    record_progress(
        topic_id=topic_id,
        subtopic=subtopic,
        activity_type="summarize",
        time_spent_minutes=time_spent_minutes
    )


def get_reading_history(topic_id: int = None, limit: int = 10):
    """Get the user's reading history."""
    progress = get_storage().get_progress(_current_user)
    topics = {t["id"]: t["name"] for t in get_all_topics()}

    readings = []
    for p in progress:
        if p.get("activity_type") != "read":
            continue
        if topic_id and p.get("topic_id") != topic_id:
            continue

        p["topic_name"] = topics.get(p.get("topic_id"), "Unknown")
        readings.append(p)

    return readings[:limit]


def get_missed_questions(topic_id: int = None, limit: int = 10):
    """Get questions the user got wrong for review."""
    progress = get_storage().get_progress(_current_user)

    missed = []
    for p in progress:
        if p.get("activity_type") != "test":
            continue
        if topic_id and p.get("topic_id") != topic_id:
            continue

        details = p.get("details", {})
        for q in details.get("questions", []):
            if not q.get("is_correct"):
                missed.append({
                    "topic_id": p.get("topic_id"),
                    "subtopic": p.get("subtopic"),
                    "question": q.get("question"),
                    "correct_answer": q.get("correct_answer"),
                    "user_answer": q.get("user_answer"),
                    "date": p.get("completed_at")
                })

    return missed[:limit]


def get_progress_summary():
    """Get a summary of progress by topic for the current user."""
    topics = get_all_topics()
    progress = get_storage().get_progress(_current_user)

    summary = []
    for topic in topics:
        topic_progress = [p for p in progress if p.get("topic_id") == topic["id"]]

        reads = sum(1 for p in topic_progress if p.get("activity_type") == "read")
        tests = sum(1 for p in topic_progress if p.get("activity_type") == "test")
        flashcards = sum(1 for p in topic_progress if p.get("activity_type") == "flashcard")
        summaries = sum(1 for p in topic_progress if p.get("activity_type") == "summarize")

        test_scores = [p.get("score") for p in topic_progress
                       if p.get("activity_type") == "test" and p.get("score") is not None]
        avg_score = sum(test_scores) / len(test_scores) if test_scores else None

        total_time = sum(p.get("time_spent_minutes") or 0 for p in topic_progress)

        summary.append({
            "id": topic["id"],
            "name": topic["name"],
            "total_activities": len(topic_progress),
            "reads": reads,
            "tests": tests,
            "flashcards": flashcards,
            "summaries": summaries,
            "avg_test_score": avg_score,
            "total_time": total_time
        })

    return summary


def get_topic_progress(topic_id: int):
    """Get detailed progress for a specific topic for the current user."""
    progress = get_storage().get_progress(_current_user)
    return [p for p in progress if p.get("topic_id") == topic_id][:20]


def get_least_studied_topics(limit: int = 3):
    """Get topics with the least progress for recommendations."""
    summary = get_progress_summary()
    sorted_topics = sorted(summary, key=lambda x: (x["total_activities"], x["id"]))
    return sorted_topics[:limit]


def get_recent_activity(limit: int = 5):
    """Get recent learning activity for the current user."""
    progress = get_storage().get_progress(_current_user)
    topics = {t["id"]: t["name"] for t in get_all_topics()}

    recent = []
    for p in progress[:limit]:
        p["topic_name"] = topics.get(p.get("topic_id"), "Unknown")
        recent.append(p)

    return recent
