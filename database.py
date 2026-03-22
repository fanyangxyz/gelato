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
            self._cache = {"progress": [], "sessions": []}
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

    def get_progress(self):
        return self._load().get("progress", [])

    def add_progress(self, entry):
        data = self._load()
        entry["id"] = len(data["progress"]) + 1
        entry["completed_at"] = datetime.now().isoformat()
        data["progress"].append(entry)
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

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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

    def get_progress(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM progress ORDER BY completed_at DESC")
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def add_progress(self, entry):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO progress (topic_id, subtopic, activity_type, score, time_spent_minutes)
               VALUES (?, ?, ?, ?, ?)""",
            (entry.get("topic_id"), entry.get("subtopic"), entry.get("activity_type"),
             entry.get("score"), entry.get("time_spent_minutes"))
        )
        conn.commit()
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
# Database operations (compatible interface)
# =============================================================================

def init_db():
    """Initialize the database."""
    get_storage()  # Ensures storage is initialized


def record_progress(topic_id: int, subtopic: str, activity_type: str,
                    score: int = None, time_spent_minutes: int = None):
    """Record a completed activity."""
    get_storage().add_progress({
        "topic_id": topic_id,
        "subtopic": subtopic,
        "activity_type": activity_type,
        "score": score,
        "time_spent_minutes": time_spent_minutes
    })


def get_progress_summary():
    """Get a summary of progress by topic."""
    topics = get_all_topics()
    progress = get_storage().get_progress()

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
    """Get detailed progress for a specific topic."""
    progress = get_storage().get_progress()
    return [p for p in progress if p.get("topic_id") == topic_id][:20]


def get_least_studied_topics(limit: int = 3):
    """Get topics with the least progress for recommendations."""
    summary = get_progress_summary()
    sorted_topics = sorted(summary, key=lambda x: (x["total_activities"], x["id"]))
    return sorted_topics[:limit]


def get_recent_activity(limit: int = 5):
    """Get recent learning activity."""
    progress = get_storage().get_progress()
    topics = {t["id"]: t["name"] for t in get_all_topics()}

    recent = []
    for p in progress[:limit]:
        p["topic_name"] = topics.get(p.get("topic_id"), "Unknown")
        recent.append(p)

    return recent
