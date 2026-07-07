"""
app.py
------
Streamlit front end for NeuroSort AI. This file is deliberately thin — all
agent logic lives in agent.py, storage logic in storage.py, and input
safety in guardrails.py — so the UI layer stays easy to read and test.
"""

import os

import streamlit as st

import storage
from agent import run_triage
from guardrails import InputTooLongError, flag_injection_attempt, sanitize_input

st.set_page_config(page_title="NeuroSort AI", page_icon="🧠", layout="wide")
storage.init_db()

st.title("🧠 NeuroSort AI")
st.caption(
    "Dump every task, worry, and idea in your head. NeuroSort triages it into "
    "what to do now, what to schedule, what to delegate, and what to let go of "
    "— and actually creates the calendar event / draft email for you."
)

with st.sidebar:
    st.subheader("Setup")
    api_key = st.text_input(
        "Gemini API key",
        type="password",
        value=os.environ.get("GEMINI_API_KEY", ""),
        help="Get a free key at aistudio.google.com. Never shared or logged.",
    )
    st.divider()
    st.subheader("Your history")
    stats = storage.get_stats()
    st.metric("Tasks triaged (all time)", stats["total_tasks"])
    if stats["avg_cognitive_load"] is not None:
        st.metric("Avg. cognitive load score", stats["avg_cognitive_load"])
    for cat, count in stats["by_category"].items():
        st.write(f"- **{cat}**: {count}")

brain_dump = st.text_area(
    "What's on your mind?",
    height=200,
    placeholder=(
        "e.g. Need to reply to Sarah about the invoice today, dentist appointment "
        "next Tuesday, ask Raj to review the PR, keep thinking about whether to "
        "repaint the kitchen..."
    ),
)

col1, col2 = st.columns([1, 5])
with col1:
    submit = st.button("Triage it", type="primary", use_container_width=True)

if submit:
    if not api_key:
        st.error("Add your Gemini API key in the sidebar first.")
    elif not brain_dump.strip():
        st.warning("Type something to triage.")
    else:
        try:
            cleaned = sanitize_input(brain_dump)
        except InputTooLongError as e:
            st.error(str(e))
            st.stop()

        if flag_injection_attempt(cleaned):
            st.session_state["injection_warning"] = True
        else:
            st.session_state["injection_warning"] = False

        with st.spinner("Triaging..."):
            try:
                run = run_triage(api_key=api_key, brain_dump_text=cleaned)
            except Exception as e:
                st.error(f"Something went wrong calling Gemini: {e}")
                st.stop()

        # Store the result in session state (not just a local variable) so
        # it survives the rerun below and the sidebar's task count reflects
        # this run immediately instead of staying one run behind.
        st.session_state["last_run"] = run
        st.rerun()

if st.session_state.get("injection_warning"):
    st.warning(
        "Heads up: your last input matched a pattern commonly used in prompt "
        "injection attempts. NeuroSort still treats it strictly as data to "
        "triage, not as instructions — flagging this for transparency."
    )

run = st.session_state.get("last_run")
if run is not None:
    if run.cognitive_load_score is not None:
        st.subheader(f"Cognitive Load: {run.cognitive_load_score}/100")
        st.caption(run.cognitive_load_rationale)

    buckets = {"do_now_task": [], "schedule_task": [], "delegate_task": [], "archive_task": []}
    for call in run.calls:
        buckets.setdefault(call.tool_name, []).append(call)

    col_now, col_sched, col_deleg, col_arch = st.columns(4)

    with col_now:
        st.markdown("### ⚡ Do now")
        for c in buckets["do_now_task"]:
            st.success(c.result["task"])

    with col_sched:
        st.markdown("### 📅 Scheduled")
        for c in buckets["schedule_task"]:
            st.info(f"{c.result['task']} — *{c.result['when_requested']}*")
            with open(c.result["ics_path"], "rb") as f:
                st.download_button(
                    "Download .ics",
                    f.read(),
                    file_name=os.path.basename(c.result["ics_path"]),
                    mime="text/calendar",
                    key=f"ics_{c.result['task_id']}",
                )

    with col_deleg:
        st.markdown("### 📤 Delegated")
        for c in buckets["delegate_task"]:
            st.info(f"{c.result['task']} → **{c.result['recipient_hint']}**")
            with open(c.result["eml_path"], "rb") as f:
                st.download_button(
                    "Download draft email",
                    f.read(),
                    file_name=os.path.basename(c.result["eml_path"]),
                    mime="message/rfc822",
                    key=f"eml_{c.result['task_id']}",
                )

    with col_arch:
        st.markdown("### 🗄️ Archived")
        for c in buckets["archive_task"]:
            st.write(c.result["task"])

    if not run.calls:
        st.warning(
            "The model didn't triage anything. Try describing at least one "
            "concrete task or idea."
        )

st.divider()
with st.expander("📜 Full history (persisted across sessions)"):
    history = storage.get_history(limit=50)
    if not history:
        st.write("No history yet.")
    for row in history:
        st.write(f"`{row['created_at'][:19]}` **[{row['category']}]** {row['content']}")
