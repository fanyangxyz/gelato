import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "biology_learning.db"
TOPICS_PATH = Path(__file__).parent / "data" / "topics.json"


def get_connection():
    """Get a database connection."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the database with tables and seed data."""
    conn = get_connection()
    cursor = conn.cursor()

    # Create topics table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS topics (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            subtopics TEXT NOT NULL,
            description TEXT,
            difficulty INTEGER DEFAULT 1
        )
    """)

    # Create progress table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id INTEGER NOT NULL,
            subtopic TEXT,
            activity_type TEXT NOT NULL,
            completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            score INTEGER,
            time_spent_minutes INTEGER,
            FOREIGN KEY (topic_id) REFERENCES topics (id)
        )
    """)

    # Create sessions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ended_at TIMESTAMP,
            total_minutes INTEGER
        )
    """)

    # Seed topics if empty
    cursor.execute("SELECT COUNT(*) FROM topics")
    if cursor.fetchone()[0] == 0:
        with open(TOPICS_PATH) as f:
            data = json.load(f)
        for topic in data["topics"]:
            cursor.execute(
                "INSERT INTO topics (id, name, subtopics, description, difficulty) VALUES (?, ?, ?, ?, ?)",
                (topic["id"], topic["name"], json.dumps(topic["subtopics"]),
                 topic["description"], topic["difficulty"])
            )

    conn.commit()
    conn.close()


def get_all_topics():
    """Get all topics with their subtopics."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM topics ORDER BY difficulty, name")
    rows = cursor.fetchall()
    conn.close()

    topics = []
    for row in rows:
        topics.append({
            "id": row["id"],
            "name": row["name"],
            "subtopics": json.loads(row["subtopics"]),
            "description": row["description"],
            "difficulty": row["difficulty"]
        })
    return topics


def get_topic_by_id(topic_id: int):
    """Get a single topic by ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM topics WHERE id = ?", (topic_id,))
    row = cursor.fetchone()
    conn.close()

    if row:
        return {
            "id": row["id"],
            "name": row["name"],
            "subtopics": json.loads(row["subtopics"]),
            "description": row["description"],
            "difficulty": row["difficulty"]
        }
    return None


def record_progress(topic_id: int, subtopic: str, activity_type: str,
                    score: int = None, time_spent_minutes: int = None):
    """Record a completed activity."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO progress (topic_id, subtopic, activity_type, score, time_spent_minutes)
           VALUES (?, ?, ?, ?, ?)""",
        (topic_id, subtopic, activity_type, score, time_spent_minutes)
    )
    conn.commit()
    conn.close()


def get_progress_summary():
    """Get a summary of progress by topic."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            t.id,
            t.name,
            COUNT(p.id) as total_activities,
            SUM(CASE WHEN p.activity_type = 'read' THEN 1 ELSE 0 END) as reads,
            SUM(CASE WHEN p.activity_type = 'test' THEN 1 ELSE 0 END) as tests,
            SUM(CASE WHEN p.activity_type = 'flashcard' THEN 1 ELSE 0 END) as flashcards,
            SUM(CASE WHEN p.activity_type = 'summarize' THEN 1 ELSE 0 END) as summaries,
            AVG(CASE WHEN p.activity_type = 'test' THEN p.score ELSE NULL END) as avg_test_score,
            SUM(p.time_spent_minutes) as total_time
        FROM topics t
        LEFT JOIN progress p ON t.id = p.topic_id
        GROUP BY t.id, t.name
        ORDER BY t.difficulty, t.name
    """)

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_topic_progress(topic_id: int):
    """Get detailed progress for a specific topic."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM progress
        WHERE topic_id = ?
        ORDER BY completed_at DESC
        LIMIT 20
    """, (topic_id,))

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_least_studied_topics(limit: int = 3):
    """Get topics with the least progress for recommendations."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            t.id,
            t.name,
            t.difficulty,
            COUNT(p.id) as activity_count
        FROM topics t
        LEFT JOIN progress p ON t.id = p.topic_id
        GROUP BY t.id, t.name, t.difficulty
        ORDER BY activity_count ASC, t.difficulty ASC
        LIMIT ?
    """, (limit,))

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_recent_activity(limit: int = 5):
    """Get recent learning activity."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            p.*,
            t.name as topic_name
        FROM progress p
        JOIN topics t ON p.topic_id = t.id
        ORDER BY p.completed_at DESC
        LIMIT ?
    """, (limit,))

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]
