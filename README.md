# 🧠 NeuroSort AI

An agent that takes a messy, unstructured "brain dump" of tasks, worries, and
ideas, and actually triages it — creating a real calendar event, drafting a
real email, and remembering everything across sessions — instead of just
handing back a categorized list.

Built for the **Kaggle "AI Agents: Intensive Vibe Coding" Capstone Project**
(Google × Kaggle).

## The problem

People with racing or cluttered thoughts (ADHD-style brain dumps, high-stress
weeks, context-switching between work/life) often lose tasks because writing
them down doesn't actually route them anywhere. A todo list still requires
you to decide, for every line, whether it's urgent, needs scheduling, needs
delegating, or is just noise — which is exactly the executive-function step
that's hardest when you're already overloaded.

## The solution

NeuroSort takes one block of free-form text and, for every distinct item it
finds, decides and **acts**:

| Category | What NeuroSort does |
|---|---|
| ⚡ Do now | Adds it to a persisted "focus queue" |
| 📅 Schedule | Generates a real, downloadable `.ics` calendar file |
| 📤 Delegate | Drafts a real `.eml` email addressed to the person implied by the text |
| 🗄️ Archive | Files it away as a note with no required action |

It also estimates a **Cognitive Load Score** for the input, and remembers
your full triage history across restarts.

## Why this is an agent, not a classifier

Every tool the model can call has a genuine side effect — a file is written
to disk, a database row is created — not just a label. The agent decides
*which* action to take and then the code actually performs it. This mirrors
real agent deployments (e.g. an agent that doesn't just say "I'd schedule
this" but actually creates the calendar entry).

## Course concepts applied (3+ required)

1. **Agent Tools & Interoperability (Day 2)** — Gemini function calling
   drives four distinct tools, each with a real-world side effect
   (`agent.py`).
2. **Context Engineering: Sessions, Skills & Memory (Day 3)** — all triage
   decisions and cognitive-load estimates persist in a local SQLite
   database (`storage.py`), so the agent has memory across sessions instead
   of forgetting everything after each run.
3. **Agent Quality & Security (Day 4)** — input length limits, control
   character stripping, delimiter-based prompt isolation (user text is
   wrapped in `<user_input>` tags rather than f-string concatenated into the
   instructions), and heuristic prompt-injection flagging (`guardrails.py`).

## Architecture

```
neurosort-ai/
├── app.py            # Streamlit UI — thin, no business logic
├── agent.py          # Gemini function-calling loop + tool implementations
├── storage.py        # SQLite persistence (the agent's memory)
├── guardrails.py      # Input sanitization + prompt-injection defenses
├── tests/
│   ├── test_guardrails.py
│   └── test_storage.py
├── data/              # Created at runtime: SQLite DB + generated .ics/.eml files
└── requirements.txt
```

The function-calling loop in `agent.py` is manual (not the SDK's "automatic
function calling" convenience mode) so every tool call is explicit,
auditable, and logged — important both for correctness and for the security
story above.

## Running it locally

```bash
git clone https://github.com/umang3307/neurosort-ai
cd neurosort-ai
pip install -r requirements.txt
streamlit run app.py
```

You'll need a free Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey).
Paste it into the sidebar — it's only held in the Streamlit session, never
logged or written to disk.

## Running the tests

```bash
pip install pytest
pytest tests/ -v
```

## Deployment

Deployed with Cloud Run: **https://neurosort-ai.streamlit.app/**

## Demo video

**https://youtu.be/kjdoVMu-eWw**

## Limitations & honest tradeoffs

- Date parsing for `schedule_task` currently defaults to a placeholder slot
  (tomorrow 9am) with the user's original phrasing kept in the event
  description, since robust natural-language date parsing is out of scope
  for this capstone — a production version would add a proper date/time
  parser.
- The injection-detection in `guardrails.py` is a heuristic tripwire, not a
  guarantee; it flags likely attempts for transparency but the real defense
  is that user text is never treated as instructions in the first place.
- Delegation currently produces a downloadable draft email rather than
  sending one directly, so a human stays in the loop before anything goes
  out — a deliberate safety choice, not a missing feature.
