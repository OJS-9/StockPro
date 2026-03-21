# ask_user_questions Orchestrator Tool Implementation Plan

> **For Claude:** REQUIRED: Follow this plan task-by-task. No TDD needed for this refactor — it is low-risk, single-flow, and has no existing unit tests for popup_start. Manual smoke test is sufficient.

**Goal:** Replace the standalone `_fetch_clarifying_questions()` Gemini call in `app.py` with an `ask_user_questions` tool on the `OrchestratorSession` LangGraph ReAct agent, so the orchestrator itself decides when and what to ask.

**Architecture:** The orchestrator's system prompt is updated to describe the `ask_user_questions(questions)` tool. When the agent calls it, the tool stores structured questions on `session.pending_questions` and returns a confirmation string. `popup_start()` in `app.py` calls `agent.start_research()`, then reads `agent.pending_questions`. The frontend response shape is unchanged.

**Tech Stack:** Flask, LangGraph `create_react_agent`, `langchain_core.tools.tool`, Google Gemini (gemini-2.5-flash via LangChain)

**Prerequisites:** No schema or dependency changes needed. Existing `OrchestratorSession`, `_get_agent_response`, and `get_orchestration_instructions` are the only touch points.

---

## Relevant Codebase Files

### Files to Modify
- `src/orchestrator_graph.py` — add `pending_questions` state field, add `ask_user_questions` tool inside `_get_agent_response`, update `start_research` return type note
- `src/research_prompt.py` — update `get_orchestration_instructions()` to describe the tool
- `src/app.py` — update `popup_start()` to call `agent.start_research()` and read `agent.pending_questions`; remove `_fetch_clarifying_questions()`

### Patterns to Follow
- `src/orchestrator_graph.py` lines 75–102 — `generate_report` tool defined inline with `@tool` decorator inside `_get_agent_response`; `ask_user_questions` follows the exact same pattern
- `src/orchestrator_graph.py` lines 32–40 — session state fields on `__init__`; add `pending_questions` the same way
- `src/app.py` lines 621–654 — `popup_start()` current shape; replace `_fetch_clarifying_questions()` call with `agent.start_research()` + read `pending_questions`

---

## Phase 1: Add `pending_questions` State to OrchestratorSession

> **Exit Criteria:** `OrchestratorSession` has a `pending_questions` field (list) initialized to `[]` in `__init__` and cleared in `reset_conversation()`.

### Task 1: Add state field

**Files:**
- Modify: `src/orchestrator_graph.py` lines 32–40 (`__init__`) and lines 184–191 (`reset_conversation`)

**Step 1:** In `__init__`, after `self.last_report_text: Optional[str] = None`, add:
```python
self.pending_questions: List[Dict[str, Any]] = []
```

**Step 2:** In `reset_conversation()`, after `self.current_report_id = None`, add:
```python
self.pending_questions = []
```

Also remove the stale `self.current_plan = None` line (it references an attribute that doesn't exist in `__init__` — it will cause an AttributeError if anything reads it before reset is called). Replace it with nothing or leave the surrounding lines intact.

**Step 3:** No test — verify manually at the end of Phase 3.

**Step 4:** Commit
```bash
git add src/orchestrator_graph.py
git commit -m "feat: add pending_questions state field to OrchestratorSession"
```

---

## Phase 2: Add `ask_user_questions` Tool

> **Exit Criteria:** The `ask_user_questions` tool exists inside `_get_agent_response`, is passed to `create_react_agent`, stores structured questions on `session.pending_questions`, and returns a confirmation string.

### Task 2: Define the tool inline

**Files:**
- Modify: `src/orchestrator_graph.py` lines 75–114 (`_get_agent_response`)

**Step 1:** Inside `_get_agent_response`, directly above the `generate_report` tool (line 75), add:

```python
@tool
def ask_user_questions(questions: List[Dict[str, Any]]) -> str:
    """
    Ask the user clarifying questions before generating the report.
    Call this ONCE at the start of a new research session with 1–3 multiple-choice questions.
    Each question must have a 'question' key (string) and an 'options' key (list of 3–4 strings).
    Example: [{"question": "What is your time horizon?", "options": ["1 day", "1 week", "1 month", "3+ months"]}]
    Do NOT call this tool more than once per session.
    """
    session.pending_questions = questions
    return "Questions captured. Waiting for user answers before generating the report."
```

**Step 2:** Pass the tool to `create_react_agent`. Change the tools list from `[generate_report]` to:
```python
[ask_user_questions, generate_report]
```

**Step 3:** Commit
```bash
git add src/orchestrator_graph.py
git commit -m "feat: add ask_user_questions tool to orchestrator ReAct agent"
```

---

## Phase 3: Update System Prompt

> **Exit Criteria:** `get_orchestration_instructions()` clearly describes the `ask_user_questions` tool, when to call it, the expected JSON structure, and its relationship to `generate_report`.

### Task 3: Update orchestration instructions

**Files:**
- Modify: `src/research_prompt.py` — `get_orchestration_instructions()` (lines 142–191)

**Step 1:** Replace the `**Guidelines:**` and `**When to Trigger**` sections with:

```
**Available Tools:**
1. `ask_user_questions(questions)` — Call this ONCE at the start of the session to gather user context.
   - Pass 1–3 multiple-choice questions as a JSON array.
   - Each item: {{"question": "...", "options": ["A", "B", "C"]}}
   - Call this BEFORE `generate_report`. Do not skip it.
   - After calling it, stop and wait — do not call `generate_report` in the same turn.

2. `generate_report()` — Call this after the user has answered your questions.
   - Only call once you have the user's answers in the conversation.
   - After calling, tell the user that research has started.

**Guidelines:**
- Always start a new research session by calling `ask_user_questions` with 1–3 focused questions.
- Tailor your questions to {trade_type}: Day Trade → immediate catalysts/risk; Swing Trade → event horizon/sector momentum; Investment → time horizon/thesis focus/risk tolerance.
- Do NOT generate the report on the first turn. Ask questions first.
- After the user answers, call `generate_report` without waiting for more input.
```

**Step 2:** Commit
```bash
git add src/research_prompt.py
git commit -m "feat: update orchestration system prompt to describe ask_user_questions tool"
```

---

## Phase 4: Update `popup_start()` and Remove Standalone Gemini Call

> **Exit Criteria:** `popup_start()` calls `agent.start_research()`, reads `agent.pending_questions`, and returns the same JSON shape as before. `_fetch_clarifying_questions()` is deleted from `app.py`.

### Task 4: Refactor popup_start

**Files:**
- Modify: `src/app.py` lines 147–176 (`_fetch_clarifying_questions`) and lines 621–654 (`popup_start`)

**Step 1:** Delete `_fetch_clarifying_questions()` entirely (lines 147–176).

**Step 2:** Replace the body of `popup_start()` after the session/agent init block. Current code:
```python
agent.current_ticker = ticker
agent.current_trade_type = trade_type
session['current_ticker'] = ticker
session['current_trade_type'] = trade_type

from research_subjects import get_research_subjects_for_trade_type
questions = _fetch_clarifying_questions(ticker, trade_type)
subjects = [...]
return jsonify({'questions': questions, 'session_id': session_id, 'subjects': subjects})
```

New code:
```python
session['current_ticker'] = ticker
session['current_trade_type'] = trade_type

# Let the orchestrator agent run one turn; it will call ask_user_questions tool
agent.start_research(ticker, trade_type)
questions = agent.pending_questions

# Fallback if agent did not call the tool (defensive — should not happen)
if not questions:
    questions = [{"question": f"What is your primary goal for researching {ticker}?",
                  "options": ["Long-term investment", "Swing trade", "Day trade", "General analysis"]}]

from research_subjects import get_research_subjects_for_trade_type
subjects = [
    {
        "id": s.id,
        "name": s.name,
        "description": s.description,
        "priority": s.priority.get(trade_type, 99),
    }
    for s in get_research_subjects_for_trade_type(trade_type)
]
return jsonify({'questions': questions, 'session_id': session_id, 'subjects': subjects})
```

Note: `agent.start_research()` already sets `current_ticker` and `current_trade_type` internally — the redundant explicit assignments can be removed.

**Step 3:** Commit
```bash
git add src/app.py
git commit -m "refactor: replace _fetch_clarifying_questions with orchestrator ask_user_questions tool"
```

---

## Phase 5: Manual Smoke Test

> **Exit Criteria:** Full popup flow works end-to-end in browser. Questions come from orchestrator. Frontend popup renders correctly. Report generates after answering questions.

### Task 5: Smoke test

**Step 1:** Start the Flask app:
```bash
cd "/Users/orsalinas/projects/Stock Protfolio Agent"
python src/app.py
```

**Step 2:** Open `http://localhost:5000`, log in, submit a ticker (e.g., NVDA) with trade type "Investment".

**Step 3:** Verify the popup modal renders with 1–3 questions from the orchestrator.

**Step 4:** Answer the questions and click Submit. Verify:
- The "Generating report..." toast appears.
- `/api/report_status/<session_id>` eventually returns `{"status": "ready", "report_id": "..."}`.
- Clicking the toast navigates to the report page.

**Step 5:** If the agent does NOT call `ask_user_questions` on the first turn (it calls `generate_report` instead or returns a text response), the fallback question will be used. If this happens consistently, tighten the system prompt: add "You MUST call `ask_user_questions` as your first action on any new research session" at the top of the instructions.

---

## Risks

| Risk | P | I | Score | Mitigation |
|------|---|---|-------|------------|
| Agent ignores `ask_user_questions` and calls `generate_report` directly | 3 | 3 | 9 | Fallback in `popup_start()` provides default question; tighten prompt if needed |
| Agent returns text instead of calling any tool | 2 | 3 | 6 | Fallback covers this; `pending_questions` stays `[]` → fallback triggers |
| `start_research()` adds to `conversation_history` before questions are captured | 1 | 2 | 2 | Tool stores directly on `session.pending_questions` before any history change |
| `popup_start()` latency increase (now involves a full LLM call) | 3 | 2 | 6 | gemini-2.5-flash is fast (~1–2s); acceptable trade-off |
| Agent calls `ask_user_questions` with malformed JSON | 2 | 2 | 4 | `pending_questions` will contain whatever the agent passes; frontend already handles missing/empty gracefully via fallback |

---

## Success Criteria

- [ ] `popup_start` returns `{questions, session_id, subjects}` — same shape as before
- [ ] Questions are generated by the orchestrator agent, not a standalone Gemini call
- [ ] `_fetch_clarifying_questions()` is deleted from `app.py`
- [ ] Fallback question exists if agent fails to call the tool
- [ ] Report generation still works after answering questions
- [ ] No regressions in existing test suite: `python -m pytest test_cost_basis.py test_csv_importer.py`
