import os
import json
from pathlib import Path
from dotenv import load_dotenv
from anthropic import Anthropic

# Load .env file for local development
load_dotenv(Path(__file__).parent / ".env")

client = None


def get_api_key():
    """Get API key from Streamlit secrets (cloud) or environment (local)."""
    # Try Streamlit secrets first (for Streamlit Cloud deployment)
    try:
        import streamlit as st
        if "ANTHROPIC_API_KEY" in st.secrets:
            return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        pass

    # Fall back to environment variable (local development)
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY not found. "
            "Set it in .env (local) or Streamlit secrets (cloud)."
        )
    return api_key


def get_client():
    """Get or create the Anthropic client."""
    global client
    if client is None:
        client = Anthropic(api_key=get_api_key())
    return client


def generate_reading(topic: str, subtopic: str, difficulty: int = 1) -> str:
    """Generate educational reading content on a biology topic."""
    difficulty_desc = {1: "beginner", 2: "intermediate", 3: "advanced"}
    level = difficulty_desc.get(difficulty, "intermediate")

    prompt = f"""You are a biology teacher creating educational content.

Generate a clear, engaging explanation about {subtopic} within the broader topic of {topic}.

Target level: {level}

Requirements:
- Start with a brief introduction explaining why this topic matters
- Break down key concepts with clear explanations
- Include 1-2 real-world examples or analogies
- End with 2-3 key takeaways
- Keep it concise but comprehensive (about 400-600 words)
- Use markdown formatting for headers and bullet points

Do not include any quiz questions - just the educational content."""

    response = get_client().messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content[0].text


def generate_test(topic: str, subtopic: str, num_questions: int = 5, difficulty: int = 1) -> list:
    """Generate multiple choice test questions."""
    difficulty_desc = {1: "beginner", 2: "intermediate", 3: "advanced"}
    level = difficulty_desc.get(difficulty, "intermediate")

    prompt = f"""You are a biology teacher creating a quiz.

Generate {num_questions} multiple choice questions about {subtopic} within {topic}.

Target level: {level}

Return ONLY valid JSON in this exact format:
{{
  "questions": [
    {{
      "question": "What is the question?",
      "options": ["A) First option", "B) Second option", "C) Third option", "D) Fourth option"],
      "correct": 0,
      "explanation": "Brief explanation of why this is correct"
    }}
  ]
}}

The "correct" field should be the index (0-3) of the correct option.
Make questions progressively harder. Include a mix of recall and application questions."""

    response = get_client().messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}]
    )

    # Parse the JSON response
    text = response.content[0].text
    # Try to extract JSON from the response
    try:
        # Handle case where response might have markdown code blocks
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        data = json.loads(text.strip())
        return data.get("questions", [])
    except json.JSONDecodeError:
        return []


def generate_flashcards(topic: str, subtopic: str, num_cards: int = 8, difficulty: int = 1) -> list:
    """Generate flashcard pairs (term/definition)."""
    difficulty_desc = {1: "beginner", 2: "intermediate", 3: "advanced"}
    level = difficulty_desc.get(difficulty, "intermediate")

    prompt = f"""You are a biology teacher creating flashcards for studying.

Generate {num_cards} flashcards about {subtopic} within {topic}.

Target level: {level}

Return ONLY valid JSON in this exact format:
{{
  "flashcards": [
    {{
      "front": "Term or question",
      "back": "Definition or answer (keep concise, 1-2 sentences)"
    }}
  ]
}}

Include a mix of:
- Key vocabulary terms
- Important concepts
- Processes or mechanisms
- Notable examples"""

    response = get_client().messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )

    text = response.content[0].text
    try:
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        data = json.loads(text.strip())
        return data.get("flashcards", [])
    except json.JSONDecodeError:
        return []


def generate_summary(topic: str, subtopics_studied: list, progress_data: list) -> str:
    """Generate a personalized summary based on what the user has studied."""

    activities_desc = []
    for p in progress_data[:10]:  # Last 10 activities
        activity = p.get("activity_type", "activity")
        subtopic = p.get("subtopic", "topic")
        score = p.get("score")
        if score:
            activities_desc.append(f"- {activity} on {subtopic} (score: {score}%)")
        else:
            activities_desc.append(f"- {activity} on {subtopic}")

    activities_str = "\n".join(activities_desc) if activities_desc else "No prior activities recorded"
    subtopics_str = ", ".join(subtopics_studied) if subtopics_studied else "various subtopics"

    prompt = f"""You are a biology tutor providing a personalized study summary.

The student has been studying {topic}, focusing on: {subtopics_str}

Their recent activity:
{activities_str}

Generate a brief, encouraging summary that:
1. Acknowledges what they've learned
2. Highlights 3-4 key concepts they should remember
3. Suggests what to focus on next
4. Keeps a supportive, motivating tone

Keep it concise (150-250 words). Use markdown formatting."""

    response = get_client().messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content[0].text


def get_recommendations(available_minutes: int, progress_summary: list, least_studied: list) -> dict:
    """Get AI-powered recommendations based on time and progress."""

    # Format progress for the prompt
    progress_desc = []
    for p in progress_summary:
        total = p.get("total_activities") or 0
        avg_score = p.get("avg_test_score")
        score_str = f", avg test score: {avg_score:.0f}%" if avg_score else ""
        progress_desc.append(f"- {p['name']}: {total} activities{score_str}")

    progress_str = "\n".join(progress_desc) if progress_desc else "No progress yet"

    least_studied_names = [t["name"] for t in least_studied]

    prompt = f"""You are a biology study advisor helping a student plan their study session.

Available time: {available_minutes} minutes

Current progress by topic:
{progress_str}

Topics needing more attention: {', '.join(least_studied_names)}

Based on the available time, recommend a study plan. Return ONLY valid JSON:
{{
  "recommendation": "Brief 1-2 sentence recommendation",
  "suggested_activities": [
    {{
      "activity": "read|test|flashcard|summarize",
      "topic": "Topic name",
      "subtopic": "Specific subtopic to focus on",
      "estimated_minutes": 10,
      "reason": "Why this activity"
    }}
  ]
}}

Guidelines:
- 5-10 min: Quick flashcards or summary
- 15-30 min: One focused read or test session
- 30-60 min: Combination of read + test or multiple topics
- Prioritize less-studied topics
- Keep total time within available minutes"""

    response = get_client().messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}]
    )

    text = response.content[0].text
    try:
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        return json.loads(text.strip())
    except json.JSONDecodeError:
        return {
            "recommendation": "Start with the basics and build from there!",
            "suggested_activities": []
        }
