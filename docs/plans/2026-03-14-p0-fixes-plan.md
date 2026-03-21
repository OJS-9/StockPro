# P0 Fixes Implementation Plan — Research Graph Reliability

> **For Claude:** REQUIRED: Follow this plan task-by-task. Each task is a focused, testable change.
> **Review file:** `AGENT_FLOW_CODE_REVIEW.md` — P0 risks #1, #2, #7

**Goal:** Fix three silent reliability failures in the LangGraph research pipeline: non-resumable graph execution (P0 #1), error-poisoned synthesis from failed nodes (P0 #2), and truncated reports stored without detection (P0 #7).

**Architecture:** All three fixes are additive — no existing node is deleted. P0 #1 is one line. P0 #2 inserts a new `quality_gate_node` between fan-in and synthesis. P0 #7 adds post-invoke validation inside `synthesis_node`.

**Tech Stack:** LangGraph (`langgraph>=0.2`), `langgraph.checkpoint.memory.MemorySaver`, Python 3.10+

**Prerequisites:**
- `langgraph` installed (already in requirements: `langgraph>=0.2`)
- Project runs from project root; all imports use `from src.X import Y` (or bare `from X` when run as module inside `src/`)
- Existing tests: `python -m pytest test_cost_basis.py test_csv_importer.py` → 96 pass

---

## Context References

### Files to Modify
- `src/research_graph.py` (lines 87–99) — graph compilation + edge wiring
- `src/agents/synthesis_node.py` (lines 210–220) — post-invoke validation

### Files to Read Before Starting
- `src/research_graph.py` — full file (99 lines, already read)
- `src/agents/synthesis_node.py` — full file (220 lines, already read)
- `src/agents/specialized_node.py` — error return shape at lines 189–200 (already read)

### State Schema (research_graph.py:25–36)
```python
class ResearchState(TypedDict):
    ticker: str
    trade_type: str
    conversation_context: str
    plan: Any
    subject_id: str
    research_outputs: Annotated[Dict[str, Any], operator.or_]
    report_text: str
    report_id: str
    user_id: Optional[int]
    emitter: Optional[StepEmitter]
```

### Error Output Shape (specialized_node.py:189–200)
A failed specialized node sets `"error": str(last_exc)` in its result dict. Successful nodes do NOT set the `"error"` key. This is the reliable flag.

---

## Phase 1: P0 #1 — Add MemorySaver Checkpointer

> **Exit Criteria:** `research_graph` is compiled with `checkpointer=MemorySaver()`. Invocations pass `thread_id` in config. Existing tests still pass.

### Task 1: Import MemorySaver and compile graph with checkpointer

**Files:**
- Modify: `src/research_graph.py` (lines 17 and 99)

**Step 1:** Open `src/research_graph.py`. Add the MemorySaver import after line 17 (the existing langgraph imports):

```python
from langgraph.checkpoint.memory import MemorySaver
```

**Step 2:** Change line 99 from:
```python
research_graph = _builder.compile()
```
to:
```python
_checkpointer = MemorySaver()
research_graph = _builder.compile(checkpointer=_checkpointer)
```

### Task 2: Pass thread_id in run_research()

`MemorySaver` requires a `thread_id` in the invocation config to scope checkpoints per run. Without it, LangGraph raises a `ValueError`.

**Files:**
- Modify: `src/research_graph.py` — `run_research()` function (lines 102–130)

**Step 1:** In `run_research()`, generate a `thread_id` from the existing `report_id` field (or generate a fresh UUID). Add after the `initial_state` dict:

```python
import uuid as _uuid

thread_id = str(_uuid.uuid4())
result = research_graph.invoke(
    initial_state,
    config={"configurable": {"thread_id": thread_id}},
)
```

The full updated `run_research()` bottom section becomes:
```python
    result = research_graph.invoke(
        initial_state,
        config={"configurable": {"thread_id": str(_uuid.uuid4())}},
    )
    return result
```

Note: `uuid` is already imported at the top of the file as `import uuid`. Use `str(uuid.uuid4())` to avoid re-importing.

**Step 2:** Run tests to confirm nothing broke:
```
python -m pytest test_cost_basis.py test_csv_importer.py -q
```
Expected: all pass (these tests don't invoke research_graph, but they confirm the module loads without error).

**Step 3:** Verify import works:
```
cd /Users/orsalinas/projects/Stock\ Protfolio\ Agent && python -c "from src.research_graph import research_graph; print('OK')"
```
Expected: `OK` (no import errors).

**Step 4:** Commit:
```bash
git add src/research_graph.py
git commit -m "fix: add MemorySaver checkpointer to research_graph (P0 #1)"
```

---

## Phase 2: P0 #2 — Quality Gate Node (Silent Failure Filter)

> **Exit Criteria:** A `quality_gate_node` sits between fan-in and synthesis. It filters errored subjects from `research_outputs`, injects a `failed_subjects` list into synthesis prompt, and aborts with a partial-report error text if more than 50% of subjects failed. Existing graph edges updated.

### Task 3: Add quality_gate_node to research_graph.py

**Files:**
- Modify: `src/research_graph.py` (insert new node + rewire edges)

The quality gate inspects `research_outputs`, separates failed entries (those with `"error"` key set), decides whether to abort, and writes two new state fields: `failed_subjects` (list of subject names that errored) and `research_outputs` (cleaned — only successful entries).

**Step 1:** Add two new fields to `ResearchState` TypedDict (after `report_id: str`):

```python
failed_subjects: List[str]     # subject_ids that errored in specialized_node
is_partial_report: bool        # True if some subjects failed but synthesis proceeds
```

The updated TypedDict block:
```python
class ResearchState(TypedDict):
    ticker: str
    trade_type: str
    conversation_context: str
    plan: Any
    subject_id: str
    research_outputs: Annotated[Dict[str, Any], operator.or_]
    failed_subjects: List[str]
    is_partial_report: bool
    report_text: str
    report_id: str
    user_id: Optional[int]
    emitter: Optional[StepEmitter]
```

Also update `run_research()` initial_state to include the new fields:
```python
"failed_subjects": [],
"is_partial_report": False,
```

**Step 2:** Add the `quality_gate_node` function. Insert it in `research_graph.py` before the `# Build the graph` comment:

```python
def quality_gate_node(state: ResearchState) -> dict:
    """
    Filter errored specialized_node outputs before synthesis.

    - Separates failed subjects (those with 'error' key in their output dict).
    - Aborts with error report_text if >50% of subjects failed.
    - Passes failed_subjects list so synthesis can note gaps honestly.
    """
    research_outputs = state["research_outputs"]
    emitter = state.get("emitter")
    ticker = state["ticker"]

    failed = []
    clean_outputs = {}
    for sid, result in research_outputs.items():
        if result.get("error"):
            failed.append(sid)
        else:
            clean_outputs[sid] = result

    total = len(research_outputs)
    failed_count = len(failed)

    if emitter and failed_count:
        emitter.emit(f"Warning: {failed_count}/{total} research subjects failed")

    # Abort threshold: more than half failed → surface error, skip synthesis
    if total > 0 and failed_count / total > 0.5:
        error_text = (
            f"Research generation failed for {ticker}: "
            f"{failed_count} of {total} subjects returned errors. "
            f"Failed subjects: {', '.join(failed)}. "
            "Please try again."
        )
        print(f"[QualityGate] Aborting synthesis — too many failures: {failed}")
        return {
            "research_outputs": clean_outputs,
            "failed_subjects": failed,
            "is_partial_report": True,
            "report_text": error_text,
        }

    if failed_count:
        print(f"[QualityGate] Proceeding with partial results. Failed: {failed}")

    return {
        "research_outputs": clean_outputs,
        "failed_subjects": failed,
        "is_partial_report": failed_count > 0,
    }
```

**Step 3:** Wire the new node into the graph. Replace the existing edge section:

Old edges (lines 93–97):
```python
_builder.add_edge(START, "planner_node")
_builder.add_conditional_edges("planner_node", _fan_out, ["specialized_node"])
_builder.add_edge("specialized_node", "synthesis_node")
_builder.add_edge("synthesis_node", "storage_node")
_builder.add_edge("storage_node", END)
```

New edges:
```python
_builder.add_node("quality_gate_node", quality_gate_node)

_builder.add_edge(START, "planner_node")
_builder.add_conditional_edges("planner_node", _fan_out, ["specialized_node"])
_builder.add_edge("specialized_node", "quality_gate_node")
_builder.add_conditional_edges("quality_gate_node", _quality_gate_route, ["synthesis_node", "storage_node"])
_builder.add_edge("synthesis_node", "storage_node")
_builder.add_edge("storage_node", END)
```

**Step 4:** Add the routing function `_quality_gate_route` (insert before the graph build block):

```python
def _quality_gate_route(state: ResearchState) -> str:
    """Route to synthesis_node normally, or skip to storage_node on abort."""
    if state.get("report_text") and state.get("is_partial_report") and not state["research_outputs"]:
        # All subjects failed — gate already wrote error report_text, skip synthesis
        return "storage_node"
    return "synthesis_node"
```

### Task 4: Thread failed_subjects into synthesis prompt

**Files:**
- Modify: `src/agents/synthesis_node.py` — `_build_synthesis_prompt()` function (lines 98–180)

When `failed_subjects` are present in state, inject a note into the synthesis prompt so the LLM knows which sections are missing.

**Step 1:** In `synthesis_node()` (line 183), extract `failed_subjects` from state:

```python
failed_subjects = state.get("failed_subjects", [])
```

**Step 2:** Pass `failed_subjects` to `_build_synthesis_prompt()`:

Update the call at line 201:
```python
synthesis_prompt = _build_synthesis_prompt(ticker, trade_type, research_outputs, plan, failed_subjects)
```

**Step 3:** Update the `_build_synthesis_prompt` function signature and inject the missing-sections note:

```python
def _build_synthesis_prompt(
    ticker: str,
    trade_type: str,
    research_outputs: Dict[str, Dict[str, Any]],
    plan: ResearchPlan,
    failed_subjects: List[str] = None,
) -> str:
```

In the `prompt_parts` list, after the research instructions block and before "Research Findings", add:

```python
    if failed_subjects:
        from research_subjects import get_research_subject_by_id
        failed_names = []
        for sid in failed_subjects:
            try:
                failed_names.append(get_research_subject_by_id(sid).name)
            except ValueError:
                failed_names.append(sid)
        prompt_parts += [
            "**NOTE — Missing Research Sections:**",
            f"The following research subjects failed to complete and have NO data available:",
            ", ".join(failed_names),
            "For these sections: explicitly state 'Research unavailable for this section' rather than fabricating or inferring data.",
            "",
        ]
```

**Step 5:** Verify import, run tests:
```
python -c "from src.research_graph import research_graph; print('graph OK')"
python -m pytest test_cost_basis.py test_csv_importer.py -q
```

**Step 6:** Commit:
```bash
git add src/research_graph.py src/agents/synthesis_node.py
git commit -m "fix: add quality_gate_node for silent failure detection (P0 #2)"
```

---

## Phase 3: P0 #7 — Synthesis Truncation Detection

> **Exit Criteria:** `synthesis_node` checks for `END_OF_REPORT` marker after LLM invocation. If missing and output length suggests truncation, retries once with a continuation prompt. If retry also lacks the marker, sets `is_partial_report=True` in state and stores report with `"[INCOMPLETE]"` prefix. Storage node persists a `completeness` flag in report metadata.

### Task 5: Add END_OF_REPORT validation and retry in synthesis_node

**Files:**
- Modify: `src/agents/synthesis_node.py` — `synthesis_node()` function (lines 183–220)

**Step 1:** Add a helper to check marker presence and estimate truncation:

Insert before `synthesis_node()`:

```python
_END_MARKER = "END_OF_REPORT"
_TRUNCATION_THRESHOLD = 0.9  # if output >= 90% of max tokens, likely truncated


def _is_truncated(report_text: str, max_tokens: int) -> bool:
    """Heuristic: report is likely truncated if END_OF_REPORT is missing AND output is long."""
    if _END_MARKER in report_text:
        return False
    # Rough chars-per-token estimate for Gemini: ~4 chars/token
    estimated_tokens = len(report_text) / 4
    return estimated_tokens >= max_tokens * _TRUNCATION_THRESHOLD
```

**Step 2:** Update `synthesis_node()` to check for the marker and retry once:

Replace the `try` block (lines 210–220):

```python
    try:
        response = llm.invoke(
            [SystemMessage(content=system_instructions), HumanMessage(content=synthesis_prompt)]
        )
        report_text = response.content or ""
        print(f"[SynthesisNode] Report: {len(report_text)} chars")

        # Check for truncation
        if _END_MARKER not in report_text:
            if _is_truncated(report_text, SYNTHESIS_MAX_OUTPUT_TOKENS):
                print(f"[SynthesisNode] Truncation detected — retrying with continuation prompt")
                continuation = (
                    "The previous response was cut off. Continue the report from where it stopped. "
                    "Complete all remaining sections and end with: END_OF_REPORT"
                )
                retry_response = llm.invoke([
                    SystemMessage(content=system_instructions),
                    HumanMessage(content=synthesis_prompt),
                    response,  # include original response as context
                    HumanMessage(content=continuation),
                ])
                combined = report_text + "\n" + (retry_response.content or "")
                if _END_MARKER in combined:
                    report_text = combined
                    print(f"[SynthesisNode] Continuation successful: {len(report_text)} chars")
                else:
                    # Mark as incomplete but still store what we have
                    report_text = "[INCOMPLETE REPORT — synthesis was truncated]\n\n" + report_text
                    print(f"[SynthesisNode] Continuation did not complete report — flagging as incomplete")
                    return {"report_text": report_text, "is_partial_report": True}
            else:
                # Short report without marker — likely a genuine LLM choice or refusal
                print(f"[SynthesisNode] END_OF_REPORT marker absent but output is short ({len(report_text)} chars) — proceeding")

        return {"report_text": report_text}

    except Exception as e:
        error_msg = f"Error synthesizing report: {e}"
        print(error_msg)
        return {"report_text": error_msg, "is_partial_report": True}
```

### Task 6: Persist completeness flag in storage_node

**Files:**
- Modify: `src/research_graph.py` — `storage_node()` function (lines 47–83)

**Step 1:** In `storage_node()`, read `is_partial_report` from state:

```python
is_partial_report = state.get("is_partial_report", False)
```

**Step 2:** Add it to the metadata dict:

```python
metadata = {
    "trade_type": trade_type,
    "research_subjects": plan.selected_subject_ids,
    "trade_context": plan.trade_context,
    "planner_reasoning": plan.planner_reasoning,
    "completeness": "partial" if is_partial_report else "complete",
    "failed_subjects": state.get("failed_subjects", []),
}
```

**Step 3:** Run tests and verify imports:
```
python -c "from src.research_graph import research_graph; from src.agents.synthesis_node import synthesis_node; print('OK')"
python -m pytest test_cost_basis.py test_csv_importer.py -q
```

**Step 4:** Commit:
```bash
git add src/agents/synthesis_node.py src/research_graph.py
git commit -m "fix: detect synthesis truncation, retry once, flag incomplete reports (P0 #7)"
```

---

## Risks

| Risk | P | I | Score | Mitigation |
|------|---|---|-------|------------|
| MemorySaver has in-process memory only — does not survive Flask restart | 3 | 2 | 6 | Acceptable for now; upgrade to SqliteSaver in a future P1 task |
| `_quality_gate_route` edge wiring — storage_node skip path requires report_text already set | 4 | 4 | 16 | Condition checked explicitly: `report_text AND is_partial_report AND no clean_outputs` |
| Continuation retry doubles LLM cost on truncated reports | 2 | 2 | 4 | Only fires when output is ≥90% of token limit — rare case |
| `response` object passed as message in continuation — LangChain accepts AIMessage in message list | 2 | 3 | 6 | Wrap in explicit `AIMessage(content=response.content)` if type errors appear |
| `failed_subjects` field added to ResearchState — existing callers of run_research() don't set it | 3 | 2 | 6 | `initial_state` in run_research() sets defaults; TypedDict allows missing optional keys in practice |

---

## Success Criteria

- [ ] `from src.research_graph import research_graph` imports without error
- [ ] `research_graph` has `checkpointer` attribute (MemorySaver instance)
- [ ] `quality_gate_node` exists in graph nodes: `research_graph.nodes`
- [ ] `synthesis_node` checks for `END_OF_REPORT` marker after invocation
- [ ] `storage_node` writes `completeness` key to metadata
- [ ] `python -m pytest test_cost_basis.py test_csv_importer.py -q` all pass
- [ ] `python -c "from src.research_graph import research_graph; print(research_graph.nodes)"` shows all 5 nodes

---

## Implementation Notes

### P0 #1 — MemorySaver import path
The correct import for LangGraph >=0.2 is:
```python
from langgraph.checkpoint.memory import MemorySaver
```
If this import fails, try `from langgraph.checkpoint import MemorySaver` (older API).

### P0 #2 — quality_gate_route edge
`add_conditional_edges("quality_gate_node", _quality_gate_route, ["synthesis_node", "storage_node"])` — the third argument is the list of valid destination node names. Both must be registered nodes at compile time.

### P0 #7 — continuation message format
When passing the original AI response as context for continuation, use:
```python
from langchain_core.messages import AIMessage
AIMessage(content=report_text)
```
rather than the raw `response` object, to avoid type issues across LangChain versions.

### Do NOT do
- Do not add SqliteSaver or PostgresSaver in this PR — MemorySaver is sufficient for P0
- Do not add token counting or budget tracking — that is P1 #3
- Do not change the synthesis LLM model or token limit — only add post-invoke validation
- Do not add source extraction from research_output text — that is P1 #6
