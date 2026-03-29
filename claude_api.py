import os
import json
from pathlib import Path
from dotenv import load_dotenv
from anthropic import Anthropic
import database as db

# Load .env file for local development
load_dotenv(Path(__file__).parent / ".env")

# Load config
CONFIG_PATH = Path(__file__).parent / "config.json"

def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)

def get_model(task: str) -> str:
    """Get the model for a specific task."""
    config = load_config()
    return config.get("models", {}).get(task, "claude-sonnet-4-20250514")

def get_max_tokens(task: str) -> int:
    """Get max tokens for a specific task."""
    config = load_config()
    return config.get("defaults", {}).get("max_tokens", {}).get(task, 1024)

def get_default(key: str, fallback=None):
    """Get a default config value."""
    config = load_config()
    return config.get("defaults", {}).get(key, fallback)


def get_language_instruction(lang: str) -> str:
    """Get language instruction for prompts."""
    if lang == "zh":
        return "\n\nIMPORTANT: Generate all content in Chinese (简体中文). Use Chinese for all explanations, questions, and answers."
    return ""  # Default to English, no extra instruction needed

client = None


def get_api_key():
    """Get API key from user session, Streamlit secrets, or environment."""
    # First check if user provided their own key
    try:
        import streamlit as st
        if st.session_state.get("api_key_source") == "own":
            user_key = st.session_state.get("user_api_key")
            if user_key:
                return user_key
    except Exception:
        pass

    # Try Streamlit secrets (for Streamlit Cloud deployment)
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


def reset_client():
    """Reset the client when API key changes."""
    global client
    client = None


def get_client():
    """Get or create the Anthropic client."""
    global client
    if client is None:
        client = Anthropic(api_key=get_api_key())
    return client


def format_reading_history(history: list) -> str:
    """Format reading history into context for the prompt."""
    if not history:
        return ""

    lines = ["The student has previously studied:"]
    for item in history[:10]:  # Limit to last 10 readings
        subtopic = item.get("subtopic", "Unknown")
        topic_name = item.get("topic_name", "")
        date = item.get("completed_at", "")[:10] if item.get("completed_at") else ""
        if topic_name:
            lines.append(f"- {subtopic} ({topic_name}) - {date}")
        else:
            lines.append(f"- {subtopic} - {date}")

    return "\n".join(lines)


def generate_reading(topic: str, subtopic: str, difficulty: int = 1,
                     reading_history: list = None, language: str = "en") -> str:
    """Generate educational reading content on a biology topic."""
    difficulty_desc = {1: "beginner", 2: "intermediate", 3: "advanced"}
    level = difficulty_desc.get(difficulty, "intermediate")

    # Build history context
    history_context = ""
    if reading_history:
        history_context = f"""
{format_reading_history(reading_history)}

Use this context to:
- Avoid repeating concepts they've already learned in detail
- Build on their existing knowledge where relevant
- Reference previous topics when making connections
"""

    lang_instruction = get_language_instruction(language)

    prompt = f"""You are a biology teacher creating educational content.

Generate a clear, engaging explanation about {subtopic} within the broader topic of {topic}.

Target level: {level}
{history_context}
Requirements:
- Start with a brief introduction explaining why this topic matters
- Break down key concepts with clear explanations
- Include 1-2 real-world examples or analogies
- End with 2-3 key takeaways
- Keep it concise but comprehensive (about 400-600 words)
- Use markdown formatting for headers and bullet points
- If the student has prior knowledge, briefly connect new concepts to what they've learned

Do not include any quiz questions - just the educational content.{lang_instruction}"""

    response = get_client().messages.create(
        model=get_model("reading"),
        max_tokens=get_max_tokens("reading"),
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content[0].text


def chat_about_reading(topic: str, subtopic: str, reading_content: str,
                       conversation_history: list = None, difficulty: int = 1,
                       language: str = "en") -> str:
    """Answer a follow-up question while the student is reading."""
    difficulty_desc = {1: "beginner", 2: "intermediate", 3: "advanced"}
    level = difficulty_desc.get(difficulty, "intermediate")
    history = conversation_history or []

    system_prompt = f"""You are a biology tutor helping a student while they read.

Current topic: {topic}
Current subtopic: {subtopic}
Target level: {level}

Use the reading passage below as the primary context. Keep answers accurate, concise, and supportive.
- Prioritize explaining the current reading in simpler terms when helpful
- Answer the student's exact question first
- If the reading does not fully cover the answer, say that clearly and provide a careful biology explanation
- Use markdown when it improves clarity
- Suggest a quick check-for-understanding question only when it is genuinely helpful

Reading passage:
{reading_content}{get_language_instruction(language)}"""

    response = get_client().messages.create(
        model=get_model("chat"),
        max_tokens=get_max_tokens("chat"),
        system=system_prompt,
        messages=history
    )

    return response.content[0].text


def format_test_history(test_history: list, missed_questions: list) -> str:
    """Format test history and missed questions for context."""
    lines = []

    if test_history:
        lines.append("Previous test performance on this topic:")
        for item in test_history[:5]:
            score = item.get("score", "N/A")
            date = item.get("completed_at", "")[:10] if item.get("completed_at") else ""
            lines.append(f"- Score: {score}% on {date}")

    if missed_questions:
        lines.append("\nQuestions the student previously got wrong (for spaced repetition):")
        for q in missed_questions[:5]:
            lines.append(f"- {q}")

    return "\n".join(lines) if lines else ""


def generate_test(topic: str, subtopic: str, num_questions: int = None, difficulty: int = 1,
                  test_history: list = None, missed_questions: list = None, language: str = "en") -> list:
    """Generate multiple choice test questions."""
    if num_questions is None:
        num_questions = get_default("test_questions", 5)

    difficulty_desc = {1: "beginner", 2: "intermediate", 3: "advanced"}
    level = difficulty_desc.get(difficulty, "intermediate")

    # Build history context
    history_context = ""
    if test_history or missed_questions:
        history_text = format_test_history(test_history or [], missed_questions or [])
        if history_text:
            history_context = f"""
{history_text}

Use this context for spaced repetition:
- Include 1-2 questions testing concepts they previously got wrong
- Vary the question format from before to test true understanding
- Adjust difficulty based on their performance history
"""

    prompt = f"""You are a biology teacher creating a quiz.

Generate {num_questions} multiple choice questions about {subtopic} within {topic}.

Target level: {level}
{history_context}
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
Make questions progressively harder. Include a mix of recall and application questions.{get_language_instruction(language)}"""

    response = get_client().messages.create(
        model=get_model("test"),
        max_tokens=get_max_tokens("test"),
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


def format_flashcard_context(missed_questions: list, review_items: list) -> str:
    """Format context for flashcard generation with spaced repetition."""
    lines = []

    if missed_questions:
        lines.append("Concepts the student struggled with (prioritize these):")
        for q in missed_questions[:5]:
            lines.append(f"- {q}")

    if review_items:
        lines.append("\nTopics due for review (spaced repetition):")
        for item in review_items[:3]:
            lines.append(f"- {item.get('subtopic')} (priority: {item.get('priority', 0):.1f})")

    return "\n".join(lines) if lines else ""


def generate_flashcards(topic: str, subtopic: str, num_cards: int = None, difficulty: int = 1,
                        missed_questions: list = None, review_items: list = None, language: str = "en") -> list:
    """Generate flashcard pairs (term/definition)."""
    if num_cards is None:
        num_cards = get_default("flashcard_count", 8)

    difficulty_desc = {1: "beginner", 2: "intermediate", 3: "advanced"}
    level = difficulty_desc.get(difficulty, "intermediate")

    # Build spaced repetition context
    sr_context = ""
    context_text = format_flashcard_context(missed_questions or [], review_items or [])
    if context_text:
        sr_context = f"""
{context_text}

For spaced repetition:
- Create cards that reinforce concepts they got wrong
- Include variations of difficult concepts
- Mix new material with review material
"""

    prompt = f"""You are a biology teacher creating flashcards for studying.

Generate {num_cards} flashcards about {subtopic} within {topic}.

Target level: {level}
{sr_context}
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
- Notable examples{get_language_instruction(language)}"""

    response = get_client().messages.create(
        model=get_model("flashcards"),
        max_tokens=get_max_tokens("flashcards"),
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


def generate_summary(topic: str, subtopics_studied: list, progress_data: list,
                     review_items: list = None, missed_questions: list = None, language: str = "en") -> str:
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

    # Build spaced repetition context
    sr_context = ""
    if review_items or missed_questions:
        sr_lines = []
        if review_items:
            sr_lines.append("Topics due for review:")
            for item in review_items[:3]:
                avg_score = sum(item.get("test_scores", [])) / len(item.get("test_scores", [1])) if item.get("test_scores") else None
                score_str = f" (avg score: {avg_score:.0f}%)" if avg_score else ""
                sr_lines.append(f"- {item.get('subtopic')}{score_str}")

        if missed_questions:
            sr_lines.append("\nConcepts to reinforce:")
            for q in missed_questions[:3]:
                sr_lines.append(f"- {q}")

        sr_context = "\n" + "\n".join(sr_lines)

    prompt = f"""You are a biology tutor providing a personalized study summary.

The student has been studying {topic}, focusing on: {subtopics_str}

Their recent activity:
{activities_str}
{sr_context}

Generate a brief, encouraging summary that:
1. Acknowledges what they've learned
2. Highlights 3-4 key concepts they should remember
3. **Based on spaced repetition data, suggest specific topics to review**
4. Keeps a supportive, motivating tone

Keep it concise (150-250 words). Use markdown formatting.{get_language_instruction(language)}"""

    response = get_client().messages.create(
        model=get_model("summary"),
        max_tokens=get_max_tokens("summary"),
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content[0].text


def get_recommendations(available_minutes: int, progress_summary: list, least_studied: list,
                        review_items: list = None, language: str = "en") -> dict:
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
    topic_catalog = []
    for topic in db.get_all_topics():
        subtopics = ", ".join(topic.get("subtopics", []))
        topic_catalog.append(f'- id: {topic["id"]}, topic: "{topic["name"]}", subtopics: [{subtopics}]')
    topic_catalog_str = "\n".join(topic_catalog)

    # Build spaced repetition context
    sr_context = ""
    if review_items:
        sr_lines = ["Topics due for spaced repetition review (prioritize these):"]
        for item in review_items[:5]:
            priority = item.get("priority", 0)
            missed_count = len(item.get("missed_questions", []))
            sr_lines.append(f"- {item.get('subtopic')} in {item.get('topic_name')} (priority: {priority:.1f}, missed questions: {missed_count})")
        sr_context = "\n" + "\n".join(sr_lines)

    prompt = f"""You are a biology study advisor helping a student plan their study session.

Available time: {available_minutes} minutes

Current progress by topic:
{progress_str}

Topics needing more attention: {', '.join(least_studied_names)}
{sr_context}

Available topics and subtopics to choose from:
{topic_catalog_str}

Based on the available time, recommend a study plan. Return ONLY valid JSON:
{{
  "recommendation": "Brief 1-2 sentence recommendation",
  "suggested_activities": [
    {{
      "activity": "read|test|flashcard|summarize",
      "topic_id": 1,
      "topic": "Topic name exactly as listed above",
      "subtopic": "Specific subtopic exactly as listed above",
      "estimated_minutes": 10,
      "reason": "Why this activity"
    }}
  ]
}}

Guidelines:
- Use only topics and subtopics from the provided catalog
- Keep `topic` and `subtopic` exactly as listed in the catalog so the app can route correctly
- `reason` and `recommendation` should be in the requested language, but identifiers must stay exact
- 5-10 min: Quick flashcards or summary
- 15-30 min: One focused read or test session
- 30-60 min: Combination of read + test or multiple topics
- **Prioritize spaced repetition items that are due for review**
- Include a mix of new material and review
- Keep total time within available minutes{get_language_instruction(language)}"""

    response = get_client().messages.create(
        model=get_model("recommendations"),
        max_tokens=get_max_tokens("recommendations"),
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
