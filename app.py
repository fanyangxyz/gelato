import streamlit as st
import database as db
import claude_api
from datetime import datetime

# Initialize database
db.init_db()

# Page config
st.set_page_config(
    page_title="Biology Learning App",
    page_icon="🧬",
    layout="wide"
)

# Initialize session state
if "current_user" not in st.session_state:
    st.session_state.current_user = None
if "api_key_source" not in st.session_state:
    st.session_state.api_key_source = None  # "own", "passphrase", or None
if "user_api_key" not in st.session_state:
    st.session_state.user_api_key = None
if "current_page" not in st.session_state:
    st.session_state.current_page = "home"
if "selected_topic" not in st.session_state:
    st.session_state.selected_topic = None
if "selected_subtopic" not in st.session_state:
    st.session_state.selected_subtopic = None
if "available_time" not in st.session_state:
    st.session_state.available_time = 15
if "quiz_questions" not in st.session_state:
    st.session_state.quiz_questions = None
if "quiz_answers" not in st.session_state:
    st.session_state.quiz_answers = {}
if "flashcards" not in st.session_state:
    st.session_state.flashcards = None
if "current_card" not in st.session_state:
    st.session_state.current_card = 0
if "show_back" not in st.session_state:
    st.session_state.show_back = False
if "is_guest" not in st.session_state:
    st.session_state.is_guest = False
if "language" not in st.session_state:
    st.session_state.language = "en"
if "reading_chat_messages" not in st.session_state:
    st.session_state.reading_chat_messages = []
if "reading_chat_context" not in st.session_state:
    st.session_state.reading_chat_context = None


# =============================================================================
# API Key Setup Screen
# =============================================================================

def get_owner_passphrase():
    """Get the owner's passphrase from secrets or environment."""
    try:
        import streamlit as st
        if "ACCESS_PASSPHRASE" in st.secrets:
            return st.secrets["ACCESS_PASSPHRASE"]
    except Exception:
        pass
    import os
    return os.environ.get("ACCESS_PASSPHRASE", "")


def render_api_setup():
    """Render the API key setup screen."""
    st.title("Biology Learning App")
    st.write("To use this app, please provide API access.")

    tab1, tab2 = st.tabs(["Use Your Own API Key", "Enter Access Code"])

    with tab1:
        st.subheader("Your Anthropic API Key")
        user_key = st.text_input(
            "Enter your Anthropic API key",
            type="password",
            placeholder="sk-ant-..."
        )
        st.caption("Your key is not stored permanently. Get one at [console.anthropic.com](https://console.anthropic.com)")

        if st.button("Use My Key", key="use_own_key"):
            if user_key and user_key.startswith("sk-ant-"):
                st.session_state.api_key_source = "own"
                st.session_state.user_api_key = user_key
                st.rerun()
            else:
                st.error("Please enter a valid Anthropic API key (starts with sk-ant-)")

    with tab2:
        st.subheader("Access Code")
        passphrase = st.text_input(
            "Enter access code",
            type="password",
            placeholder="Enter code..."
        )
        st.caption("If you have an access code, enter it here to use the app.")

        if st.button("Submit Code", key="use_passphrase"):
            owner_passphrase = get_owner_passphrase()
            if owner_passphrase and passphrase == owner_passphrase:
                st.session_state.api_key_source = "passphrase"
                st.session_state.user_api_key = None
                st.rerun()
            else:
                st.error("Invalid access code")


# Check if API access is set up
if st.session_state.api_key_source is None:
    render_api_setup()
    st.stop()


# =============================================================================
# Login Screen
# =============================================================================

def render_login():
    """Render the login/user selection screen."""
    st.title("Biology Learning App")
    st.write("Select your profile or create a new one to track your progress.")

    # Guest option
    st.subheader("Quick Start")
    if st.button("Continue as Guest", use_container_width=True):
        st.session_state.current_user = "_guest_"
        st.session_state.is_guest = True
        db.set_current_user("_guest_")
        st.rerun()
    st.caption("Guest progress is not saved between sessions.")

    st.divider()

    existing_users = db.get_users()

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Existing Users")
        if existing_users:
            selected_user = st.selectbox("Select your name", options=existing_users)
            if st.button("Continue", key="login_existing"):
                st.session_state.current_user = selected_user
                st.session_state.is_guest = False
                db.set_current_user(selected_user)
                st.rerun()
        else:
            st.write("No users yet. Create one!")

    with col2:
        st.subheader("New User")
        new_username = st.text_input("Enter your name")
        if st.button("Create & Continue", key="login_new"):
            if new_username.strip():
                username = new_username.strip()
                db.add_user(username)
                st.session_state.current_user = username
                st.session_state.is_guest = False
                db.set_current_user(username)
                st.rerun()
            else:
                st.error("Please enter a name")


# Check if user is logged in
if st.session_state.current_user is None:
    render_login()
    st.stop()

# Set the current user in the database module
db.set_current_user(st.session_state.current_user)


def navigate_to(page: str, topic_id: int = None, subtopic: str = None):
    """Navigate to a different page."""
    st.session_state.current_page = page
    if topic_id:
        st.session_state.selected_topic = topic_id
    if subtopic:
        st.session_state.selected_subtopic = subtopic
    # Reset activity state
    st.session_state.quiz_questions = None
    st.session_state.quiz_answers = {}
    st.session_state.flashcards = None
    st.session_state.current_card = 0
    st.session_state.show_back = False
    st.session_state.reading_content = None
    st.session_state.reading_completed = False
    st.session_state.reading_chat_messages = []
    st.session_state.reading_chat_context = None


def normalize_activity_type(activity_type: str) -> str:
    """Map model-provided activity labels to routed page names."""
    normalized = (activity_type or "read").strip().lower()
    aliases = {
        "read": "read",
        "reading": "read",
        "test": "test",
        "quiz": "test",
        "flashcard": "flashcards",
        "flashcards": "flashcards",
        "cards": "flashcards",
        "summary": "summarize",
        "summarize": "summarize",
        "summarise": "summarize",
    }
    return aliases.get(normalized, "read")


# Sidebar
with st.sidebar:
    st.title("Biology Learning")

    # User info
    if st.session_state.is_guest:
        st.caption("Browsing as: **Guest**")
        st.caption("Progress not saved.")
    else:
        st.caption(f"Logged in as: **{st.session_state.current_user}**")
    if st.button("Switch User", use_container_width=True):
        st.session_state.current_user = None
        st.session_state.is_guest = False
        st.rerun()

    # API key info
    if st.session_state.api_key_source == "own":
        st.caption("Using: Your API key")
    else:
        st.caption("Using: Access code")

    if st.button("Change API Access", use_container_width=True):
        st.session_state.api_key_source = None
        st.session_state.user_api_key = None
        claude_api.reset_client()
        st.rerun()

    st.divider()

    # Language selector
    language_options = {"en": "English", "zh": "中文"}
    selected_lang = st.selectbox(
        "Language / 语言",
        options=list(language_options.keys()),
        format_func=lambda x: language_options[x],
        index=list(language_options.keys()).index(st.session_state.language)
    )
    if selected_lang != st.session_state.language:
        st.session_state.language = selected_lang
        st.rerun()

    st.divider()

    st.subheader("Available Time")
    st.session_state.available_time = st.slider(
        "How many minutes do you have?",
        min_value=5,
        max_value=120,
        value=st.session_state.available_time,
        step=5
    )

    st.divider()

    st.subheader("Navigation")
    if st.button("Home", use_container_width=True):
        navigate_to("home")
    if st.button("Topics", use_container_width=True):
        navigate_to("topics")
    if st.button("Progress", use_container_width=True):
        navigate_to("progress")

    st.divider()

    st.subheader("Quick Activities")
    topics = db.get_all_topics()
    quick_topic = st.selectbox(
        "Select topic",
        options=topics,
        format_func=lambda x: x["name"]
    )

    if quick_topic:
        quick_subtopic = st.selectbox(
            "Select subtopic",
            options=quick_topic["subtopics"]
        )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Read", use_container_width=True):
                st.session_state.selected_topic = quick_topic["id"]
                st.session_state.selected_subtopic = quick_subtopic
                navigate_to("read", quick_topic["id"], quick_subtopic)
        with col2:
            if st.button("Test", use_container_width=True):
                navigate_to("test", quick_topic["id"], quick_subtopic)

        col3, col4 = st.columns(2)
        with col3:
            if st.button("Cards", use_container_width=True):
                navigate_to("flashcards", quick_topic["id"], quick_subtopic)
        with col4:
            if st.button("Summary", use_container_width=True):
                navigate_to("summarize", quick_topic["id"], quick_subtopic)


# Main content
def render_home():
    st.title("Welcome to Biology Learning")
    st.write(f"You have **{st.session_state.available_time} minutes** available.")

    # Get recommendations
    st.subheader("Recommended for You")

    with st.spinner("Getting personalized recommendations..."):
        try:
            progress_summary = db.get_progress_summary()
            least_studied = db.get_least_studied_topics(3)
            review_items = db.get_spaced_repetition_data(limit=5)

            recommendations = claude_api.get_recommendations(
                st.session_state.available_time,
                progress_summary,
                least_studied,
                review_items=review_items,
                language=st.session_state.language
            )

            st.info(recommendations.get("recommendation", "Start exploring biology!"))

            activities = recommendations.get("suggested_activities", [])
            if activities:
                st.write("**Suggested activities:**")
                topics = db.get_all_topics()
                for i, activity in enumerate(activities):
                    with st.container():
                        col1, col2, col3 = st.columns([3, 1, 1])
                        with col1:
                            st.write(f"**{activity.get('topic', 'Topic')}** - {activity.get('subtopic', 'Subtopic')}")
                            st.caption(activity.get("reason", ""))
                        with col2:
                            st.write(f"~{activity.get('estimated_minutes', '?')} min")
                        with col3:
                            act_type = normalize_activity_type(activity.get("activity", "read"))
                            topic_id = activity.get("topic_id")
                            topic_match = next((t for t in topics if t["id"] == topic_id), None)
                            if topic_match is None:
                                topic_match = next((t for t in topics if t["name"] == activity.get("topic")), None)
                            if topic_match and st.button(f"Start", key=f"rec_{i}"):
                                navigate_to(act_type, topic_match["id"], activity.get("subtopic"))
                                st.rerun()
        except Exception as e:
            st.error(f"Could not get recommendations: {e}")
            st.write("Try selecting a topic from the sidebar to get started!")

    # Recent activity
    st.subheader("Recent Activity")
    recent = db.get_recent_activity(5)
    if recent:
        for activity in recent:
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                st.write(f"**{activity['topic_name']}** - {activity.get('subtopic', 'N/A')}")
            with col2:
                st.write(activity["activity_type"].capitalize())
            with col3:
                score = activity.get("score")
                if score:
                    st.write(f"Score: {score}%")
                else:
                    st.write("Completed")
    else:
        st.write("No activity yet. Start learning!")


def render_topics():
    st.title("Biology Topics")

    topics = db.get_all_topics()
    progress = {p["id"]: p for p in db.get_progress_summary()}

    difficulty_labels = {1: "Beginner", 2: "Intermediate", 3: "Advanced"}

    for topic in topics:
        with st.expander(f"**{topic['name']}** ({difficulty_labels[topic['difficulty']]})"):
            st.write(topic["description"])

            # Show progress
            topic_progress = progress.get(topic["id"], {})
            total_activities = topic_progress.get("total_activities") or 0
            st.write(f"Activities completed: {total_activities}")

            st.write("**Subtopics:**")
            for subtopic in topic["subtopics"]:
                col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 1])
                with col1:
                    st.write(subtopic)
                with col2:
                    if st.button("Read", key=f"r_{topic['id']}_{subtopic}"):
                        navigate_to("read", topic["id"], subtopic)
                        st.rerun()
                with col3:
                    if st.button("Test", key=f"t_{topic['id']}_{subtopic}"):
                        navigate_to("test", topic["id"], subtopic)
                        st.rerun()
                with col4:
                    if st.button("Cards", key=f"f_{topic['id']}_{subtopic}"):
                        navigate_to("flashcards", topic["id"], subtopic)
                        st.rerun()
                with col5:
                    if st.button("Summary", key=f"s_{topic['id']}_{subtopic}"):
                        navigate_to("summarize", topic["id"], subtopic)
                        st.rerun()


def render_progress():
    st.title("Your Progress")

    progress_summary = db.get_progress_summary()

    # Overall stats
    total_activities = sum(p.get("total_activities") or 0 for p in progress_summary)
    total_time = sum(p.get("total_time") or 0 for p in progress_summary)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Activities", total_activities)
    with col2:
        st.metric("Total Time", f"{total_time or 0} min")
    with col3:
        topics_started = sum(1 for p in progress_summary if (p.get("total_activities") or 0) > 0)
        st.metric("Topics Started", f"{topics_started}/{len(progress_summary)}")

    st.divider()

    # Progress by topic
    st.subheader("Progress by Topic")

    for p in progress_summary:
        total = p.get("total_activities") or 0

        with st.container():
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"**{p['name']}**")
                # Progress bar (arbitrary scale: 10 activities = 100%)
                progress_pct = min(total / 10, 1.0)
                st.progress(progress_pct)
            with col2:
                st.write(f"{total} activities")

            # Activity breakdown
            reads = p.get("reads") or 0
            tests = p.get("tests") or 0
            flashcards = p.get("flashcards") or 0
            summaries = p.get("summaries") or 0
            avg_score = p.get("avg_test_score")

            details = f"Read: {reads} | Tests: {tests} | Flashcards: {flashcards} | Summaries: {summaries}"
            if avg_score:
                details += f" | Avg Score: {avg_score:.0f}%"
            st.caption(details)

        st.divider()


def render_read():
    topic = db.get_topic_by_id(st.session_state.selected_topic)
    subtopic = st.session_state.selected_subtopic

    if not topic or not subtopic:
        st.error("Please select a topic and subtopic")
        return

    st.title(f"Reading: {subtopic}")
    st.caption(f"Topic: {topic['name']}")

    chat_context = (topic["id"], subtopic, st.session_state.language)
    if st.session_state.reading_chat_context != chat_context:
        st.session_state.reading_chat_messages = [
            {
                "role": "assistant",
                "content": (
                    f"Ask about **{subtopic}** while you read. "
                    "I can explain passages, define terms, or compare concepts."
                )
            }
        ]
        st.session_state.reading_chat_context = chat_context

    # Initialize reading content cache
    if "reading_content" not in st.session_state:
        st.session_state.reading_content = None
    if "reading_completed" not in st.session_state:
        st.session_state.reading_completed = False

    # Generate content if not cached
    if st.session_state.reading_content is None:
        with st.spinner("Generating content..."):
            try:
                # Get reading history for context
                reading_history = db.get_reading_history(limit=10)

                st.session_state.reading_content = claude_api.generate_reading(
                    topic["name"],
                    subtopic,
                    topic["difficulty"],
                    reading_history=reading_history,
                    language=st.session_state.language
                )
                st.session_state.reading_completed = False
            except Exception as e:
                st.error(f"Error generating content: {e}")
                return

    st.markdown(st.session_state.reading_content)

    st.divider()

    if not st.session_state.reading_completed:
        if st.button("Mark as Read", type="primary", use_container_width=True):
            db.record_read(topic["id"], subtopic, time_spent_minutes=10)
            st.session_state.reading_completed = True
            st.rerun()
    else:
        st.success("Reading completed! Progress saved.")
        if st.button("Read Another Topic", use_container_width=True):
            st.session_state.reading_content = None
            st.session_state.reading_completed = False
            navigate_to("topics")
            st.rerun()

    st.divider()

    chat_header_col, chat_action_col = st.columns([3, 1])
    with chat_header_col:
        st.subheader("Reading Chat")
    with chat_action_col:
        if st.button("Reset", key="reset_reading_chat", use_container_width=True):
            st.session_state.reading_chat_messages = [
                {
                    "role": "assistant",
                    "content": (
                        f"Ask about **{subtopic}** while you read. "
                        "I can explain passages, define terms, or compare concepts."
                    )
                }
            ]
            st.rerun()

    chat_messages_container = st.container()
    with chat_messages_container:
        for message in st.session_state.reading_chat_messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    input_col, send_col = st.columns([5, 1])
    with input_col:
        prompt = st.text_input(
            "Ask about this reading",
            key="reading_chat_input_text",
            label_visibility="collapsed",
            placeholder="Ask about this reading"
        )
    with send_col:
        send_clicked = st.button("Send", key="reading_chat_send", use_container_width=True)

    if send_clicked and prompt.strip():
        prompt = prompt.strip()
        st.session_state.reading_chat_messages.append(
            {"role": "user", "content": prompt}
        )

        try:
            reply = claude_api.chat_about_reading(
                topic["name"],
                subtopic,
                st.session_state.reading_content,
                conversation_history=st.session_state.reading_chat_messages,
                difficulty=topic["difficulty"],
                language=st.session_state.language
            )
        except Exception as e:
            reply = f"Sorry, I couldn't answer that right now: {e}"

        st.session_state.reading_chat_messages.append(
            {"role": "assistant", "content": reply}
        )
        st.session_state.reading_chat_input_text = ""
        st.rerun()


def render_test():
    topic = db.get_topic_by_id(st.session_state.selected_topic)
    subtopic = st.session_state.selected_subtopic

    if not topic or not subtopic:
        st.error("Please select a topic and subtopic")
        return

    st.title(f"Test: {subtopic}")
    st.caption(f"Topic: {topic['name']}")

    # Generate questions if not already done
    if st.session_state.quiz_questions is None:
        with st.spinner("Generating quiz questions..."):
            try:
                # Get test history and missed questions for spaced repetition
                test_history = db.get_activity_history(
                    activity_type="test",
                    topic_id=topic["id"],
                    limit=5
                )
                missed_questions = db.get_missed_questions(topic_id=topic["id"], limit=5)
                missed_q_texts = [q.get("question", "") for q in missed_questions]

                st.session_state.quiz_questions = claude_api.generate_test(
                    topic["name"],
                    subtopic,
                    num_questions=5,
                    difficulty=topic["difficulty"],
                    test_history=test_history,
                    missed_questions=missed_q_texts,
                    language=st.session_state.language
                )
            except Exception as e:
                st.error(f"Error generating quiz: {e}")
                return

    questions = st.session_state.quiz_questions

    if not questions:
        st.error("Could not generate questions. Please try again.")
        if st.button("Retry"):
            st.session_state.quiz_questions = None
            st.rerun()
        return

    # Display questions
    with st.form("quiz_form"):
        for i, q in enumerate(questions):
            st.write(f"**Q{i+1}: {q['question']}**")
            st.session_state.quiz_answers[i] = st.radio(
                f"Select answer for Q{i+1}",
                options=range(len(q["options"])),
                format_func=lambda x, opts=q["options"]: opts[x],
                key=f"q_{i}",
                label_visibility="collapsed"
            )

        submitted = st.form_submit_button("Submit Quiz")

        if submitted:
            correct = 0
            st.divider()
            st.subheader("Results")

            for i, q in enumerate(questions):
                user_answer = st.session_state.quiz_answers.get(i, -1)
                is_correct = user_answer == q["correct"]
                if is_correct:
                    correct += 1
                    st.success(f"Q{i+1}: Correct!")
                else:
                    st.error(f"Q{i+1}: Incorrect. The answer was: {q['options'][q['correct']]}")
                st.caption(f"Explanation: {q.get('explanation', 'N/A')}")

            score = int((correct / len(questions)) * 100)
            st.divider()
            st.metric("Your Score", f"{score}%", f"{correct}/{len(questions)} correct")

            # Record progress with detailed question results
            db.record_test(
                topic_id=topic["id"],
                subtopic=subtopic,
                score=score,
                questions=questions,
                user_answers=st.session_state.quiz_answers,
                time_spent_minutes=15
            )

            if st.button("Take Another Quiz"):
                st.session_state.quiz_questions = None
                st.session_state.quiz_answers = {}
                st.rerun()


def render_flashcards():
    topic = db.get_topic_by_id(st.session_state.selected_topic)
    subtopic = st.session_state.selected_subtopic

    if not topic or not subtopic:
        st.error("Please select a topic and subtopic")
        return

    st.title(f"Flashcards: {subtopic}")
    st.caption(f"Topic: {topic['name']}")

    # Generate flashcards if not already done
    if st.session_state.flashcards is None:
        with st.spinner("Generating flashcards..."):
            try:
                # Get missed questions and review items for spaced repetition
                missed_questions = db.get_missed_questions(topic_id=topic["id"], limit=5)
                missed_q_texts = [q.get("question", "") for q in missed_questions]
                review_items = db.get_spaced_repetition_data(limit=3)

                st.session_state.flashcards = claude_api.generate_flashcards(
                    topic["name"],
                    subtopic,
                    num_cards=8,
                    difficulty=topic["difficulty"],
                    missed_questions=missed_q_texts,
                    review_items=review_items,
                    language=st.session_state.language
                )
            except Exception as e:
                st.error(f"Error generating flashcards: {e}")
                return

    cards = st.session_state.flashcards

    if not cards:
        st.error("Could not generate flashcards. Please try again.")
        if st.button("Retry"):
            st.session_state.flashcards = None
            st.rerun()
        return

    # Display current card
    current = st.session_state.current_card
    total = len(cards)

    st.progress((current + 1) / total)
    st.write(f"Card {current + 1} of {total}")

    card = cards[current]

    # Card display
    with st.container():
        st.markdown("---")
        if st.session_state.show_back:
            st.markdown(f"### {card['front']}")
            st.markdown(f"**Answer:** {card['back']}")
        else:
            st.markdown(f"### {card['front']}")
            st.markdown("*Click 'Show Answer' to reveal*")
        st.markdown("---")

    # Controls
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("Previous", disabled=(current == 0)):
            st.session_state.current_card -= 1
            st.session_state.show_back = False
            st.rerun()

    with col2:
        if st.button("Show Answer" if not st.session_state.show_back else "Hide Answer"):
            st.session_state.show_back = not st.session_state.show_back
            st.rerun()

    with col3:
        if current < total - 1:
            if st.button("Next"):
                st.session_state.current_card += 1
                st.session_state.show_back = False
                st.rerun()
        else:
            if st.button("Finish"):
                # Record progress
                db.record_flashcards(
                    topic_id=topic["id"],
                    subtopic=subtopic,
                    card_count=len(cards),
                    time_spent_minutes=10
                )
                st.success("Flashcards completed! Progress saved.")
                st.session_state.flashcards = None
                st.session_state.current_card = 0


def render_summarize():
    topic = db.get_topic_by_id(st.session_state.selected_topic)
    subtopic = st.session_state.selected_subtopic

    if not topic or not subtopic:
        st.error("Please select a topic and subtopic")
        return

    st.title(f"Summary: {subtopic}")
    st.caption(f"Topic: {topic['name']}")

    with st.spinner("Generating personalized summary..."):
        try:
            # Get progress for this topic
            topic_progress = db.get_topic_progress(topic["id"])

            # Get spaced repetition data
            review_items = db.get_spaced_repetition_data(limit=3)
            missed_questions = db.get_missed_questions(topic_id=topic["id"], limit=5)
            missed_q_texts = [q.get("question", "") for q in missed_questions]

            summary = claude_api.generate_summary(
                topic["name"],
                topic["subtopics"],
                topic_progress,
                review_items=review_items,
                missed_questions=missed_q_texts,
                language=st.session_state.language
            )

            st.markdown(summary)

            # Record progress
            db.record_summary(topic["id"], subtopic, time_spent_minutes=5)

            st.success("Summary reviewed! Progress saved.")

        except Exception as e:
            st.error(f"Error generating summary: {e}")


# Route to the correct page
page = st.session_state.current_page

if page == "home":
    render_home()
elif page == "topics":
    render_topics()
elif page == "progress":
    render_progress()
elif page == "read":
    render_read()
elif page == "test":
    render_test()
elif page == "flashcards":
    render_flashcards()
elif page == "summarize":
    render_summarize()
else:
    render_home()
