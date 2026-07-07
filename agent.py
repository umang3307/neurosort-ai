"""
agent.py
--------
The agent core for NeuroSort AI.

Architecture (Course Day 2: Agent Tools & Interoperability):
  1. The user's brain-dump text is split by the model into discrete tasks.
  2. For each task, the model calls exactly one tool to triage it.
  3. Unlike a pure classifier, each tool here has a REAL side effect:
       - schedule_task   -> generates an actual downloadable .ics calendar file
       - delegate_task   -> generates an actual draft email (.eml + mailto link)
       - do_now_task     -> persists the task to the "focus now" queue (SQLite)
       - archive_task    -> persists the task to the archive (SQLite)
  4. All triage decisions are written to persistent storage (storage.py),
     so the agent has memory across sessions.

We use manual function-calling (rather than the SDK's "automatic function
calling") so the control flow is explicit and auditable — every tool call
the model makes is logged and its real-world side effect is visible in
the code, which matters both for correctness and for the security review
in guardrails.py.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from google import genai
from google.genai import types

import storage
from guardrails import build_isolated_prompt

OUTPUT_DIR = Path(__file__).parent / "data" / "generated"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MODEL_NAME = "gemini-2.5-flash"

SYSTEM_INSTRUCTIONS = """You are NeuroSort, a task-triage agent for people with racing,
cluttered thoughts (e.g. ADHD-style brain dumps). You will receive a block of raw,
unstructured text describing multiple tasks, worries, and ideas.

For EVERY distinct task or item you find in the text, call exactly one tool:
  - do_now_task: for anything urgent or quick (<10 minutes) that should be done immediately
  - schedule_task: for anything that has or needs a specific date/time
  - delegate_task: for anything that should be handed off to another person
  - archive_task: for anything that is just a note, worry, or idea with no required action

IMPORTANT: Issue ALL of these tool calls together in a single response, in parallel —
one function call per task, plus one final call to estimate_cognitive_load for the
whole input — rather than spreading them across multiple turns. Do not summarize
instead of calling tools."""


# ---------------------------------------------------------------------------
# Tool implementations — each one has a REAL side effect, not just text.
# ---------------------------------------------------------------------------

def do_now_task(task: str) -> dict:
    """Add a task to the persisted 'focus now' queue."""
    row_id = storage.add_task(category="do_now", content=task)
    return {"status": "added_to_focus_queue", "task_id": row_id, "task": task}


def schedule_task(task: str, when: str) -> dict:
    """
    Create a real, downloadable .ics calendar file for the task and persist
    the scheduling decision.
    """
    from icalendar import Calendar, Event
    from datetime import datetime, timedelta, timezone

    cal = Calendar()
    cal.add("prodid", "-//NeuroSort AI//neurosort//")
    cal.add("version", "2.0")

    event = Event()
    event.add("summary", task)
    event.add("description", f"Scheduled by NeuroSort AI. Original note: {when}")
    # We can't reliably parse arbitrary natural language dates without a
    # dedicated NLP-date library, so we default to "tomorrow 9am" as a
    # placeholder slot and put the user's original phrasing in the
    # description so they can correct it in their calendar app.
    start = datetime.now(timezone.utc).replace(
        hour=9, minute=0, second=0, microsecond=0
    ) + timedelta(days=1)
    event.add("dtstart", start)
    event.add("dtend", start + timedelta(minutes=30))
    event.add("uid", str(uuid.uuid4()))
    cal.add_component(event)

    filename = f"event_{uuid.uuid4().hex[:8]}.ics"
    filepath = OUTPUT_DIR / filename
    filepath.write_bytes(cal.to_ical())

    row_id = storage.add_task(category="schedule", content=task, detail=when)
    return {
        "status": "ics_file_created",
        "task_id": row_id,
        "task": task,
        "when_requested": when,
        "ics_path": str(filepath),
    }


def delegate_task(task: str, recipient_hint: str) -> dict:
    """
    Draft a real .eml email file the user can review and send, delegating
    the task to the named recipient.
    """
    subject = f"Could you help with: {task}"
    body = (
        f"Hi,\n\nCould you take care of the following?\n\n  {task}\n\n"
        f"(Drafted by NeuroSort AI on behalf of the sender.)\n"
    )
    eml_content = (
        f"To: {recipient_hint}\n"
        f"Subject: {subject}\n"
        f"Content-Type: text/plain; charset=UTF-8\n\n"
        f"{body}"
    )
    filename = f"delegation_{uuid.uuid4().hex[:8]}.eml"
    filepath = OUTPUT_DIR / filename
    filepath.write_text(eml_content, encoding="utf-8")

    row_id = storage.add_task(category="delegate", content=task, detail=recipient_hint)
    return {
        "status": "draft_email_created",
        "task_id": row_id,
        "task": task,
        "recipient_hint": recipient_hint,
        "eml_path": str(filepath),
        "subject": subject,
        "body": body,
    }


def archive_task(task: str) -> dict:
    """Persist a note/idea to the archive with no required action."""
    row_id = storage.add_task(category="archive", content=task)
    return {"status": "archived", "task_id": row_id, "task": task}


def estimate_cognitive_load(score: int, rationale: str) -> dict:
    """Record the model's estimate of how overloaded the input sounded."""
    return {"score": score, "rationale": rationale}


TOOL_FUNCTIONS = {
    "do_now_task": do_now_task,
    "schedule_task": schedule_task,
    "delegate_task": delegate_task,
    "archive_task": archive_task,
    "estimate_cognitive_load": estimate_cognitive_load,
}

TOOL_DECLARATIONS = [
    {
        "name": "do_now_task",
        "description": "Triage a task as urgent/quick — add it to the immediate focus queue.",
        "parameters": {
            "type": "object",
            "properties": {"task": {"type": "string", "description": "The task text."}},
            "required": ["task"],
        },
    },
    {
        "name": "schedule_task",
        "description": "Triage a task that has or needs a specific date/time — creates a calendar event.",
        "parameters": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "The task text."},
                "when": {
                    "type": "string",
                    "description": "The user's original phrasing of the date/time, e.g. 'next Tuesday'.",
                },
            },
            "required": ["task", "when"],
        },
    },
    {
        "name": "delegate_task",
        "description": "Triage a task that should be handed to someone else — drafts an email.",
        "parameters": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "The task text."},
                "recipient_hint": {
                    "type": "string",
                    "description": "Who the task should go to, as mentioned or implied by the user.",
                },
            },
            "required": ["task", "recipient_hint"],
        },
    },
    {
        "name": "archive_task",
        "description": "Triage a note/worry/idea with no required action — files it away.",
        "parameters": {
            "type": "object",
            "properties": {"task": {"type": "string", "description": "The note/idea text."}},
            "required": ["task"],
        },
    },
    {
        "name": "estimate_cognitive_load",
        "description": "Record an estimate (0-100) of how mentally overloaded the input sounds.",
        "parameters": {
            "type": "object",
            "properties": {
                "score": {"type": "integer", "description": "0-100 overload estimate."},
                "rationale": {"type": "string", "description": "One sentence explaining the score."},
            },
            "required": ["score", "rationale"],
        },
    },
]


def _call_with_retry(client, model, contents, config, max_attempts: int = 3):
    """
    Call generate_content with automatic backoff on 429 RESOURCE_EXHAUSTED
    (free-tier rate limits). Google's error payload includes a suggested
    retryDelay in seconds — we honor that instead of guessing.
    """
    last_error = None
    for attempt in range(max_attempts):
        try:
            return client.models.generate_content(
                model=model, contents=contents, config=config
            )
        except Exception as e:  # noqa: BLE001 - SDK raises plain Exceptions for HTTP errors
            last_error = e
            message = str(e)
            if "RESOURCE_EXHAUSTED" not in message and "429" not in message:
                raise
            match = re.search(r"retryDelay['\"]?:\s*['\"]?(\d+)", message)
            wait_seconds = int(match.group(1)) if match else 15
            if attempt < max_attempts - 1:
                time.sleep(wait_seconds + 1)
    raise last_error


@dataclass
class TriageResult:
    tool_name: str
    args: dict
    result: dict


@dataclass
class TriageRun:
    calls: list[TriageResult] = field(default_factory=list)
    cognitive_load_score: int | None = None
    cognitive_load_rationale: str = ""


def run_triage(api_key: str, brain_dump_text: str) -> TriageRun:
    """
    Send the sanitized user text to Gemini, execute every tool call the
    model makes, and return a structured record of what happened.
    """
    client = genai.Client(api_key=api_key)

    prompt = build_isolated_prompt(SYSTEM_INSTRUCTIONS, brain_dump_text)

    tools = types.Tool(function_declarations=TOOL_DECLARATIONS)
    config = types.GenerateContentConfig(
        tools=[tools],
        tool_config=types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(mode="ANY")
        ),
    )

    contents = [types.Content(role="user", parts=[types.Part(text=prompt)])]

    run = TriageRun()
    # We prompt the model to issue all tool calls in one turn (see
    # SYSTEM_INSTRUCTIONS), so this should usually resolve in 1 iteration.
    # We still cap it defensively at 4 in case the model splits work across
    # turns, so a misbehaving model can't spin forever burning API calls
    # and hitting free-tier rate limits.
    for _ in range(4):
        response = _call_with_retry(
            client, MODEL_NAME, contents, config
        )

        candidate = response.candidates[0] if response.candidates else None
        if not candidate or not candidate.content or not candidate.content.parts:
            break

        function_calls = [
            part.function_call for part in candidate.content.parts if part.function_call
        ]
        if not function_calls:
            break

        contents.append(candidate.content)
        function_response_parts = []

        for fc in function_calls:
            fn = TOOL_FUNCTIONS.get(fc.name)
            args = dict(fc.args) if fc.args else {}
            if fn is None:
                result = {"error": f"unknown tool {fc.name}"}
            else:
                result = fn(**args)

            if fc.name == "estimate_cognitive_load":
                run.cognitive_load_score = result.get("score")
                run.cognitive_load_rationale = result.get("rationale", "")
            else:
                run.calls.append(TriageResult(tool_name=fc.name, args=args, result=result))

            function_response_parts.append(
                types.Part(
                    function_response=types.FunctionResponse(
                        name=fc.name, response={"result": json.dumps(result)}
                    )
                )
            )

        contents.append(types.Content(role="tool", parts=function_response_parts))

    if run.cognitive_load_score is not None:
        storage.log_session(brain_dump_text, run.cognitive_load_score)

    return run
