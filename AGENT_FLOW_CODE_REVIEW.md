# Codex Output: Agentic Research Flow Review (CODEX)

## Corrected Conclusion

The research pipeline in this workspace **is implemented with LangGraph**.

- `src/orchestrator_graph.py` runs a conversational ReAct agent (`create_react_agent`) that decides when to call `generate_report`.
- `src/research_graph.py` defines the core workflow as a `StateGraph` with parallel fan-out via `Send`.
- Domain nodes are split into:
  - `src/agents/planner_node.py`
  - `src/agents/specialized_node.py`
  - `src/agents/synthesis_node.py`

I previously reported otherwise because I reviewed a different directory version. This file is the corrected analysis for the current project path.

## End-to-End Flow (as coded)

1. **Conversation Orchestration**
   - `OrchestratorSession` manages user conversation state.
   - A LangGraph ReAct agent asks clarifying questions.
   - It invokes `generate_report` tool once enough context exists.

2. **Graph Entry**
   - `run_research(...)` in `src/research_graph.py` builds `ResearchState` and invokes `research_graph`.

3. **Planner Node**
   - `planner_node` selects and orders subject IDs and builds `ResearchPlan`.
   - Uses single structured LLM call, with fallback plan behavior.

4. **Parallel Fan-Out**
   - `_fan_out` creates one `Send("specialized_node", {..., subject_id})` per subject.
   - Specialized research executes concurrently.

5. **Specialized Node(s)**
   - Each invocation runs a ReAct loop with MCP + Nimble tools.
   - Produces per-subject output merged into `research_outputs` via reducer.

6. **Synthesis Node**
   - Merges all collected research into final report text.

7. **Storage Node**
   - Persists report, chunks, and embeddings.
   - Returns `report_id` (best-effort even if storage fails).

8. **UX/Observability**
   - SSE progress messages via `StepEmitter`.
   - LangSmith traces enabled by environment variables.

## Strengths

- **Explicit graph orchestration:** Clear state transitions in `StateGraph`.
- **Parallelism with intent:** `Send` fan-out maps well to per-subject independent work.
- **Separation of concerns:** planner/specialized/synthesis/storage are isolated nodes.
- **Tool abstraction layer:** MCP/Nimble integrated cleanly via LangChain tools.
- **Fallback behavior:** planner and specialized nodes degrade instead of hard-crashing.

## Risk Map

### High

- **No durable checkpointer configured**
  - Graph is compiled/invoked without persistence backend.
  - In-flight recovery/resume across process restarts is limited.

- **Failure signaling can be too soft**
  - Tool errors are often serialized as strings and returned to model.
  - This can produce “successful” downstream synthesis with degraded evidence.

- **Synthesis completeness is not hard-gated**
  - Prompt asks for `END_OF_REPORT`, but node does not validate/enforce marker.
  - Truncated or partial reports may still flow into storage.

### Medium

- **Concurrency and provider pressure**
  - Fan-out size equals number of selected subjects.
  - Combined with tool-heavy ReAct loops, this can spike rate limits/cost.

- **Retry strategy is narrow**
  - Specialized node retries mainly on rate-limit heuristics.
  - Other transient failures (network/provider) may not be retried robustly.

- **Storage fallback semantics**
  - `storage_node` returns a UUID even when DB storage fails.
  - UI may present report as generated, but persistence/retrieval may be inconsistent.

### Low-Medium

- **State typing looseness**
  - `plan: Any` and mixed dict payloads reduce static guarantees.
  - Harder to validate contracts between nodes at scale.

- **Observability asymmetry**
  - Step-level SSE + LangSmith present, but limited explicit quality metrics (coverage, confidence, missing-source rate).

## Improvement Opportunities (Prioritized)

### P0: Reliability and Correctness

- Add synthesis post-check:
  - validate required sections,
  - enforce `END_OF_REPORT`,
  - auto-retry continuation on truncation.
- Introduce hard quality gate before synthesis:
  - minimum successful subject threshold,
  - explicit “insufficient evidence” mode.

### P1: Durable Execution

- Add LangGraph checkpointing/persistence for resumability.
- Store run status and node outputs by workflow ID for restart-safe recovery.

### P2: Error Semantics

- Standardize tool/node output envelopes:
  - `ok`, `error_type`, `retryable`, `source`.
- Distinguish “empty evidence” from “hard failure” from “partial success.”

### P3: Throughput and Cost Controls

- Cap or adapt fan-out based on:
  - subject count,
  - live rate-limit signals,
  - latency/cost budget.
- Add provider-specific backoff + jitter policies.

### P4: Stronger Contracts

- Tighten `ResearchState` typing and node input/output schemas.
- Add validation helpers per node boundary.

### P5: Confidence & QA Instrumentation

- Track/report:
  - subjects attempted vs successful,
  - tool call failures by class,
  - synthesis completeness score,
  - source citation density.

## Suggested Flow Hardening (Minimal Invasive)

1. Keep current graph structure.
2. Add a `quality_gate_node` between specialized fan-in and synthesis.
3. Add a `validate_report_node` after synthesis.
4. Route failed validations to retry/fallback edge before storage.

This preserves current architecture while materially improving robustness.

## Final Assessment

The current implementation is a solid LangGraph-based orchestration with clear modularity and useful parallelism.  
The main gaps are **durability, strict quality gates, and stronger failure semantics** — not the overall graph design itself.
# Agentic Research Flow — Risk Map & Improvement Analysis

> **Generated by Claude** — March 13, 2026

---

## Flow Architecture

The research pipeline is built on **LangGraph** with a `StateGraph` and `Send()` API for parallel fan-out. The conversational orchestrator uses LangGraph's `create_react_agent`. Tracing is handled by **LangSmith** (auto-traces all LangChain/LangGraph calls).

```
User → OrchestratorSession (LangGraph ReAct agent + generate_report tool)
         │
         │  calls run_research()
         ▼
   ┌─────────────────────────────────────────────────────────┐
   │  LangGraph StateGraph (research_graph.py)               │
   │                                                         │
   │  START → planner_node                                   │
   │            │                                            │
   │            ▼ (conditional edge: _fan_out via Send())    │
   │  ┌─── specialized_node (subject A) ───┐                │
   │  ├─── specialized_node (subject B) ───┤  parallel      │
   │  ├─── specialized_node (subject C) ───┤  via Send()    │
   │  └─── specialized_node (subject N) ───┘                │
   │            │  (merged via Annotated[Dict, operator.or_])│
   │            ▼                                            │
   │       synthesis_node                                    │
   │            │                                            │
   │            ▼                                            │
   │       storage_node → END                                │
   └─────────────────────────────────────────────────────────┘
```

### Key Files

| File | Role |
|------|------|
| `src/orchestrator_graph.py` | LangGraph ReAct orchestrator — conversation, clarifying Qs, triggers `run_research` |
| `src/research_graph.py` | `StateGraph` definition: START → planner → fan-out → specialized × N → synthesis → storage → END |
| `src/agents/planner_node.py` | Graph node: selects/prioritizes research subjects via structured JSON LLM call |
| `src/agents/specialized_node.py` | Graph node: ReAct agent per subject with MCP + Nimble tools (parallel via `Send()`) |
| `src/agents/synthesis_node.py` | Graph node: merges all research outputs into final report |
| `src/agents/chat_agent.py` | RAG-style Q&A over stored reports |
| `src/langchain_tools.py` | `StructuredTool` wrappers for MCP (Alpha Vantage) and Nimble |
| `src/langsmith_service.py` | `StepEmitter` for SSE progress; LangSmith handles LLM/tool tracing automatically |
| `src/research_subjects.py` | 12 subject definitions with prompt templates and trade-type eligibility |
| `src/research_plan.py` | `ResearchPlan` dataclass bridging planner → specialized → synthesis |

### State Schema

Defined in `src/research_graph.py`:

```python
class ResearchState(TypedDict):
    ticker: str
    trade_type: str
    conversation_context: str
    plan: Any                                               # ResearchPlan (set by planner_node)
    subject_id: str                                         # set per Send() invocation
    research_outputs: Annotated[Dict[str, Any], operator.or_]  # merged across parallel nodes
    report_text: str                                        # set by synthesis_node
    report_id: str                                          # set by storage_node
    user_id: Optional[int]
    emitter: Optional[StepEmitter]
```

---

## Risk 1: No Graph Checkpointing — Entire Pipeline is Non-Resumable

**Where:** `src/research_graph.py` — the graph is compiled without a checkpointer

```python
research_graph = _builder.compile()    # no checkpointer= argument
```

**Risk:** LangGraph supports built-in checkpointing (e.g., `MemorySaver`, `SqliteSaver`, `PostgresSaver`) that persists state after every node. Without it, if the synthesis or storage node fails after N parallel specialized agents have completed (minutes of LLM calls and token spend), all research work is lost. The graph must be re-run from START.

**Improvement:** Add a checkpointer to `_builder.compile(checkpointer=...)`. This gives free resumability — on failure, `research_graph.invoke()` can resume from the last successful node rather than replaying the entire graph.

---

## Risk 2: Silent Failure Propagation in Parallel Specialized Nodes

**Where:** `src/agents/specialized_node.py` — error return path (lines 189–200)

```python
error_msg = f"Error in research for {subject.name}: {last_exc}"
print(error_msg)
return {"research_outputs": {subject_id: {
    "subject_id": subject_id,
    "subject_name": subject.name,
    "research_output": error_msg,
    "sources": [],
    ...
    "error": str(last_exc),
}}}
```

**Risk:** Failed specialized nodes return an error string as `research_output` and merge it into `research_outputs` via `operator.or_`. The synthesis node receives this alongside valid results with no distinction. It has no instruction to handle error-poisoned inputs — it may hallucinate content for those sections or produce a report that appears complete but is missing critical analysis. There is no failure threshold to prevent a degraded report from being stored and shown to the user.

**Improvement:**
- Add a conditional edge or a **quality gate node** between specialized_node and synthesis_node that inspects `research_outputs`, filters out errored entries, and aborts if more than N% of subjects failed.
- Pass an explicit "missing sections" list to the synthesis prompt so it can note gaps honestly.
- Add a `completeness` flag to the stored report metadata.

---

## Risk 3: Unbounded Token Cost from Parallel Agents

**Where:** `src/agents/specialized_node.py` lines 19–21, `src/research_graph.py` `_fan_out()`

```python
SPECIALIZED_MODEL = os.getenv("SPECIALIZED_AGENT_MODEL", "gemini-2.5-pro")
SPECIALIZED_MAX_TURNS = int(os.getenv("SPECIALIZED_AGENT_MAX_TURNS", "8"))
SPECIALIZED_MAX_OUTPUT_TOKENS = int(os.getenv("SPECIALIZED_AGENT_MAX_OUTPUT_TOKENS", "6000"))
```

**Risk:** The `Send()` fan-out creates one specialized ReAct agent per subject. For an "Investment" trade type, the planner can select up to 8 subjects, each running `gemini-2.5-pro` with up to 8 ReAct turns and 6,000 output tokens. A single report can consume massive token volume. There is no per-request budget cap, no pre-flight cost estimate, and no circuit breaker if cumulative usage exceeds a threshold.

**Improvement:**
- Add a token budget to `ResearchState` and a shared callback that tracks cumulative usage.
- Use LangChain's `get_openai_callback()` equivalent or LangSmith's run metadata to tally tokens.
- Add a conditional edge that checks budget before each `Send()` and limits subject count if estimated cost is too high.

---

## Risk 4: Planner Fallback Silently Runs All Subjects

**Where:** `src/agents/planner_node.py` — `_fallback_plan()` (lines 121–129)

```python
def _fallback_plan(ticker, trade_type, eligible):
    return ResearchPlan(
        ticker=ticker,
        trade_type=trade_type,
        selected_subject_ids=[s.id for s in eligible],   # ALL of them
        subject_focus={s.id: "" for s in eligible},       # no focus hints
        trade_context="",
        planner_reasoning="fallback: LLM call failed or returned invalid JSON",
    )
```

**Risk:** When the planner LLM call fails (rate limit, malformed JSON, etc.), the fallback runs **every eligible subject** with **no focus hints** and **no trade context**. For Investment type, this means up to 8 subjects on `gemini-2.5-pro`. The cheapest possible failure triggers the most expensive possible execution path.

**Improvement:**
- Fallback should select only the top 3–4 subjects by priority rather than all eligible.
- Retry the planner LLM call once before falling back (the current code doesn't retry).
- Propagate fallback status to the emitter so the user knows the plan was auto-generated.

---

## Risk 5: Each Specialized Node Recreates MCP + Nimble Clients

**Where:** `src/agents/specialized_node.py` — `_get_clients()` (lines 24–44) called inside `specialized_node()` (line 129)

```python
def _get_clients():
    """Initialize MCP and Nimble clients (cached per-process via module-level singletons)."""
    mcp_client = None
    nimble_client = None
    try:
        mcp_manager = MCPManager()
        mcp_client = mcp_manager.get_mcp_client()
    ...
```

**Risk:** Despite the docstring claiming "cached per-process via module-level singletons," `_get_clients()` creates a **new** `MCPManager()` and `NimbleClient()` on every call. With 8 parallel `Send()` invocations, that's 8 redundant client instantiations, 8 separate MCP config file reads, and 8 concurrent HTTP client pools hitting Alpha Vantage. This wastes resources and amplifies the risk of rate limiting.

**Improvement:** Cache the clients at module level (actual singletons):

```python
_mcp_client = None
_nimble_client = None

def _get_clients():
    global _mcp_client, _nimble_client
    if _mcp_client is None:
        # initialize once
    ...
```

Or, better, initialize them once and pass through `ResearchState`.

---

## Risk 6: No Validation of Research Output Quality

**Where:** `src/agents/specialized_node.py` — result dict (lines 171–179)

```python
return {"research_outputs": {subject_id: {
    "subject_id": subject_id,
    "subject_name": subject.name,
    "research_output": output_text,
    "sources": [],          # always empty
    ...
}}}
```

**Risk:** The `sources` list is **always empty** — actual citations are buried in the `research_output` text string, never extracted as structured data. Additionally, there's no validation that:
- The output is relevant to the requested subject
- The output contains actual data (not a Gemini refusal or empty response)
- The output meets a minimum quality bar (length, presence of quantitative data)

An empty or low-quality output silently flows into synthesis and degrades the final report.

**Improvement:**
- Add minimum output length validation (e.g., < 200 chars → treat as failure, retry once).
- Parse source URLs from the text via regex and populate the `sources` field.
- Add a lightweight quality gate node in the graph between specialized and synthesis nodes.

---

## Risk 7: Synthesis Truncation Goes Undetected

**Where:** `src/agents/synthesis_node.py` — synthesis LLM call (lines 210–220)

```python
try:
    response = llm.invoke(
        [SystemMessage(content=system_instructions), HumanMessage(content=synthesis_prompt)]
    )
    report_text = response.content or ""
    return {"report_text": report_text}
except Exception as e:
    error_msg = f"Error synthesizing report: {e}"
    return {"report_text": error_msg}
```

**Risk:** The synthesis prompt requires an `END_OF_REPORT` marker at the end, but the node never checks for it. If Gemini hits the 8,000-token output limit and truncates mid-sentence, the incomplete report is silently stored. The `lwt` worktree had `check_end_marker=True` logic in `gemini_runner.py`, but the LangGraph version lost this safeguard during the migration.

**Improvement:**
- After `llm.invoke()`, check for `END_OF_REPORT` in `report_text`. If missing and content length suggests truncation, retry with a continuation prompt or increase `max_output_tokens`.
- At minimum, flag the report as incomplete in storage metadata.

---

## Risk 8: Orchestrator Recreates ReAct Agent on Every Turn

**Where:** `src/orchestrator_graph.py` — `_get_agent_response()` (lines 104–114)

```python
llm = ChatGoogleGenerativeAI(
    model=ORCHESTRATOR_MODEL,
    temperature=0.7,
    max_output_tokens=ORCHESTRATOR_MAX_OUTPUT_TOKENS,
)
agent = create_react_agent(
    llm,
    [generate_report],
    prompt=system_instructions,
)
```

**Risk:** A new LLM instance and a new ReAct agent graph are compiled on every single conversational turn. `create_react_agent` compiles a LangGraph `StateGraph` internally — this is unnecessary overhead repeated for every user message. Additionally, the `generate_report` tool is redefined as a closure on every turn (lines 75–102), capturing a stale reference to `session` via `self`.

**Improvement:** Create the LLM and agent once during `OrchestratorSession.__init__()` and reuse across turns. Pass dynamic context (ticker, trade_type) via the message rather than recompiling the agent.

---

## Risk 9: Race Conditions on OrchestratorSession State

**Where:** `src/orchestrator_graph.py` — mutable session state (lines 32–38)

```python
self.current_ticker: Optional[str] = None
self.current_trade_type: Optional[str] = None
self.current_report_id: Optional[str] = None
self.last_report_text: Optional[str] = None
self.conversation_history: List[Dict[str, str]] = []
```

**Risk:** `OrchestratorSession` is instantiated per Flask session. If report generation (which calls `run_research` synchronously) is running while the user sends another message, the shared mutable state (`current_report_id`, `last_report_text`, `conversation_history`) can be corrupted. The `generate_report` tool closure (line 94) writes to `session.current_report_id` from inside the LangGraph execution thread.

**Improvement:** Make `generate_report` return results through the graph state rather than mutating the session object. Or add a lock/flag that prevents concurrent mutation during report generation.

---

## Risk 10: Duplicate Rate Limit Retry Logic

**Where:** `src/agents/specialized_node.py` lines 88–93 and 140–187

**Risk:** `_is_rate_limit_error()` and the retry loop are duplicated across specialized_node.py and would be needed in any new node. This is a maintenance burden and divergence risk.

**Improvement:** Extract into a shared `retry.py` utility or use LangChain's built-in retry support (`llm.with_retry()`):

```python
llm = ChatGoogleGenerativeAI(...).with_retry(
    retry_if_exception_type=(RateLimitError,),
    wait_exponential_jitter=True,
    stop_after_attempt=3,
)
```

---

## Risk 11: MCP Tool Result Truncation Loses Data Silently

**Where:** `src/langchain_tools.py` — MCP handler (lines 33–37)

```python
for key in ("annualReports", "quarterlyReports", "monthlyReports", "reports", "items", "data"):
    if key in result and isinstance(result[key], list) and len(result[key]) > MAX_SERIES_ITEMS:
        result[key] = result[key][:MAX_SERIES_ITEMS]
```

**Risk:** Financial data arrays are silently clipped to 5 items (`MAX_SERIES_ITEMS = 5`). A ReAct agent asked to analyze "last 6–8 quarters" of earnings will only see 5 data points with no indication of truncation. The model may draw incomplete trend conclusions.

**Improvement:** Append a truncation marker when clipping data:

```python
result[key] = result[key][:MAX_SERIES_ITEMS]
result[f"_{key}_note"] = f"Truncated: showing {MAX_SERIES_ITEMS} of {original_len} items"
```

---

## Risk 12: `recursion_limit` Tied to Max Turns via Arbitrary Multiplier

**Where:** `src/agents/specialized_node.py` line 153

```python
result = agent.invoke(
    {"messages": [HumanMessage(content=research_prompt)]},
    config={"recursion_limit": SPECIALIZED_MAX_TURNS * 2},
)
```

**Risk:** The recursion limit is set to `SPECIALIZED_MAX_TURNS * 2` (default: 16). In LangGraph, each ReAct "turn" involves two node transitions (LLM call → tool execution), so this is correct at face value. However, if the agent makes multiple tool calls per turn, or if there are internal retries, the limit may be hit prematurely — causing a `GraphRecursionError` that the retry loop treats as a non-rate-limit error and immediately surfaces as a failed subject.

**Improvement:** Set `recursion_limit` with more headroom (e.g., `max_turns * 3`) or catch `GraphRecursionError` explicitly and handle it as a graceful termination rather than a hard failure.

---

## Risk 13: Full State Sent to Every Parallel Node via Send()

**Where:** `src/research_graph.py` — `_fan_out()` (lines 38–44)

```python
def _fan_out(state: ResearchState) -> List[Send]:
    plan = state["plan"]
    return [
        Send("specialized_node", {**state, "subject_id": sid})
        for sid in plan.selected_subject_ids
    ]
```

**Risk:** `{**state}` copies the entire `ResearchState` (including `conversation_context`, `emitter`, and already-accumulated `research_outputs`) into each `Send()` payload. As subjects complete and `research_outputs` grows, later-starting parallel nodes receive increasingly large state copies. This is wasteful and could cause memory pressure with many subjects.

**Improvement:** Only send the fields each specialized node actually reads:

```python
Send("specialized_node", {
    "ticker": state["ticker"],
    "trade_type": state["trade_type"],
    "plan": state["plan"],
    "subject_id": sid,
    "emitter": state.get("emitter"),
})
```

---

## Summary Priority Matrix

| Priority | Risk | Impact | Likelihood | Fix Effort |
|----------|------|--------|------------|------------|
| **P0** | #1 — No graph checkpointing | High — lost work/cost | Medium | Low (one-line change) |
| **P0** | #2 — Silent failure propagation | High — bad reports | Medium | Low |
| **P0** | #7 — Synthesis truncation undetected | High — incomplete reports | High | Low |
| **P1** | #3 — Unbounded token cost | High — cost overrun | Medium | Medium |
| **P1** | #4 — Planner fallback runs all subjects | High — cost spike | Low | Low |
| **P1** | #6 — No quality validation | Medium — bad synthesis | Medium | Medium |
| **P1** | #8 — Agent recreated every turn | Medium — latency/waste | High | Low |
| **P2** | #5 — Per-node client recreation | Medium — rate limits | High | Low |
| **P2** | #9 — Shared mutable session state | Medium — data corruption | Low | Medium |
| **P2** | #13 — Full state in Send() payloads | Low — memory waste | Medium | Low |
| **P2** | #12 — Fragile recursion_limit | Medium — premature failures | Low | Trivial |
| **P3** | #10 — Duplicate retry logic | Low — maintenance | N/A | Low |
| **P3** | #11 — Silent data truncation | Low — incomplete trends | High | Trivial |

---

## Recommended Quick Wins

1. **Add a checkpointer** (#1) — `_builder.compile(checkpointer=MemorySaver())` is a one-line change that enables free resumability.
2. **Add a quality gate node** (#2, #7) — insert a node between specialized and synthesis that filters errored outputs, checks for minimum output length, and aborts if too many subjects failed.
3. **Check for END_OF_REPORT** (#7) — after synthesis LLM call, verify the marker exists; retry or flag as incomplete if missing.
4. **Cache clients as true singletons** (#5) — use module-level globals with initialization guards.
5. **Use `llm.with_retry()`** (#10) — replace manual retry loops with LangChain's built-in retry support.

## Recommended Structural Improvements

1. **Add a token budget system** (#3) — estimate cost pre-flight, track cumulative usage via LangSmith, and abort on overspend.
2. **Minimize Send() payloads** (#13) — only send fields each node reads.
3. **Create orchestrator agent once** (#8) — compile in `__init__`, reuse across turns.
4. **Add output validation** (#6) — extract sources, check output length, gate quality before synthesis.
5. **Cap planner fallback** (#4) — use top 3–4 priority subjects instead of all eligible.


# Agentic Research Flow — Risk Map & Improvement Analysis (CLAUDE)

> **Generated by Claude** — March 13, 2026

---

## Flow Architecture

The research pipeline is built on **LangGraph** with a `StateGraph` and `Send()` API for parallel fan-out. The conversational orchestrator uses LangGraph's `create_react_agent`. Tracing is handled by **LangSmith** (auto-traces all LangChain/LangGraph calls).

```
User → OrchestratorSession (LangGraph ReAct agent + generate_report tool)
         │
         │  calls run_research()
         ▼
   ┌─────────────────────────────────────────────────────────┐
   │  LangGraph StateGraph (research_graph.py)               │
   │                                                         │
   │  START → planner_node                                   │
   │            │                                            │
   │            ▼ (conditional edge: _fan_out via Send())    │
   │  ┌─── specialized_node (subject A) ───┐                │
   │  ├─── specialized_node (subject B) ───┤  parallel      │
   │  ├─── specialized_node (subject C) ───┤  via Send()    │
   │  └─── specialized_node (subject N) ───┘                │
   │            │  (merged via Annotated[Dict, operator.or_])│
   │            ▼                                            │
   │       synthesis_node                                    │
   │            │                                            │
   │            ▼                                            │
   │       storage_node → END                                │
   └─────────────────────────────────────────────────────────┘
```

### Key Files

| File | Role |
|------|------|
| `src/orchestrator_graph.py` | LangGraph ReAct orchestrator — conversation, clarifying Qs, triggers `run_research` |
| `src/research_graph.py` | `StateGraph` definition: START → planner → fan-out → specialized × N → synthesis → storage → END |
| `src/agents/planner_node.py` | Graph node: selects/prioritizes research subjects via structured JSON LLM call |
| `src/agents/specialized_node.py` | Graph node: ReAct agent per subject with MCP + Nimble tools (parallel via `Send()`) |
| `src/agents/synthesis_node.py` | Graph node: merges all research outputs into final report |
| `src/agents/chat_agent.py` | RAG-style Q&A over stored reports |
| `src/langchain_tools.py` | `StructuredTool` wrappers for MCP (Alpha Vantage) and Nimble |
| `src/langsmith_service.py` | `StepEmitter` for SSE progress; LangSmith handles LLM/tool tracing automatically |
| `src/research_subjects.py` | 12 subject definitions with prompt templates and trade-type eligibility |
| `src/research_plan.py` | `ResearchPlan` dataclass bridging planner → specialized → synthesis |

### State Schema

Defined in `src/research_graph.py`:

```python
class ResearchState(TypedDict):
    ticker: str
    trade_type: str
    conversation_context: str
    plan: Any                                               # ResearchPlan (set by planner_node)
    subject_id: str                                         # set per Send() invocation
    research_outputs: Annotated[Dict[str, Any], operator.or_]  # merged across parallel nodes
    report_text: str                                        # set by synthesis_node
    report_id: str                                          # set by storage_node
    user_id: Optional[int]
    emitter: Optional[StepEmitter]
```

---

## Risk 1: No Graph Checkpointing — Entire Pipeline is Non-Resumable

**Where:** `src/research_graph.py` — the graph is compiled without a checkpointer

```python
research_graph = _builder.compile()    # no checkpointer= argument
```

**Risk:** LangGraph supports built-in checkpointing (e.g., `MemorySaver`, `SqliteSaver`, `PostgresSaver`) that persists state after every node. Without it, if the synthesis or storage node fails after N parallel specialized agents have completed (minutes of LLM calls and token spend), all research work is lost. The graph must be re-run from START.

**Improvement:** Add a checkpointer to `_builder.compile(checkpointer=...)`. This gives free resumability — on failure, `research_graph.invoke()` can resume from the last successful node rather than replaying the entire graph.

---

## Risk 2: Silent Failure Propagation in Parallel Specialized Nodes

**Where:** `src/agents/specialized_node.py` — error return path (lines 189–200)

```python
error_msg = f"Error in research for {subject.name}: {last_exc}"
print(error_msg)
return {"research_outputs": {subject_id: {
    "subject_id": subject_id,
    "subject_name": subject.name,
    "research_output": error_msg,
    "sources": [],
    ...
    "error": str(last_exc),
}}}
```

**Risk:** Failed specialized nodes return an error string as `research_output` and merge it into `research_outputs` via `operator.or_`. The synthesis node receives this alongside valid results with no distinction. It has no instruction to handle error-poisoned inputs — it may hallucinate content for those sections or produce a report that appears complete but is missing critical analysis. There is no failure threshold to prevent a degraded report from being stored and shown to the user.

**Improvement:**
- Add a conditional edge or a **quality gate node** between specialized_node and synthesis_node that inspects `research_outputs`, filters out errored entries, and aborts if more than N% of subjects failed.
- Pass an explicit "missing sections" list to the synthesis prompt so it can note gaps honestly.
- Add a `completeness` flag to the stored report metadata.

---

## Risk 3: Unbounded Token Cost from Parallel Agents

**Where:** `src/agents/specialized_node.py` lines 19–21, `src/research_graph.py` `_fan_out()`

```python
SPECIALIZED_MODEL = os.getenv("SPECIALIZED_AGENT_MODEL", "gemini-2.5-pro")
SPECIALIZED_MAX_TURNS = int(os.getenv("SPECIALIZED_AGENT_MAX_TURNS", "8"))
SPECIALIZED_MAX_OUTPUT_TOKENS = int(os.getenv("SPECIALIZED_AGENT_MAX_OUTPUT_TOKENS", "6000"))
```

**Risk:** The `Send()` fan-out creates one specialized ReAct agent per subject. For an "Investment" trade type, the planner can select up to 8 subjects, each running `gemini-2.5-pro` with up to 8 ReAct turns and 6,000 output tokens. A single report can consume massive token volume. There is no per-request budget cap, no pre-flight cost estimate, and no circuit breaker if cumulative usage exceeds a threshold.

**Improvement:**
- Add a token budget to `ResearchState` and a shared callback that tracks cumulative usage.
- Use LangChain's `get_openai_callback()` equivalent or LangSmith's run metadata to tally tokens.
- Add a conditional edge that checks budget before each `Send()` and limits subject count if estimated cost is too high.

---

## Risk 4: Planner Fallback Silently Runs All Subjects

**Where:** `src/agents/planner_node.py` — `_fallback_plan()` (lines 121–129)

```python
def _fallback_plan(ticker, trade_type, eligible):
    return ResearchPlan(
        ticker=ticker,
        trade_type=trade_type,
        selected_subject_ids=[s.id for s in eligible],   # ALL of them
        subject_focus={s.id: "" for s in eligible},       # no focus hints
        trade_context="",
        planner_reasoning="fallback: LLM call failed or returned invalid JSON",
    )
```

**Risk:** When the planner LLM call fails (rate limit, malformed JSON, etc.), the fallback runs **every eligible subject** with **no focus hints** and **no trade context**. For Investment type, this means up to 8 subjects on `gemini-2.5-pro`. The cheapest possible failure triggers the most expensive possible execution path.

**Improvement:**
- Fallback should select only the top 3–4 subjects by priority rather than all eligible.
- Retry the planner LLM call once before falling back (the current code doesn't retry).
- Propagate fallback status to the emitter so the user knows the plan was auto-generated.

---

## Risk 5: Each Specialized Node Recreates MCP + Nimble Clients

**Where:** `src/agents/specialized_node.py` — `_get_clients()` (lines 24–44) called inside `specialized_node()` (line 129)

```python
def _get_clients():
    """Initialize MCP and Nimble clients (cached per-process via module-level singletons)."""
    mcp_client = None
    nimble_client = None
    try:
        mcp_manager = MCPManager()
        mcp_client = mcp_manager.get_mcp_client()
    ...
```

**Risk:** Despite the docstring claiming "cached per-process via module-level singletons," `_get_clients()` creates a **new** `MCPManager()` and `NimbleClient()` on every call. With 8 parallel `Send()` invocations, that's 8 redundant client instantiations, 8 separate MCP config file reads, and 8 concurrent HTTP client pools hitting Alpha Vantage. This wastes resources and amplifies the risk of rate limiting.

**Improvement:** Cache the clients at module level (actual singletons):

```python
_mcp_client = None
_nimble_client = None

def _get_clients():
    global _mcp_client, _nimble_client
    if _mcp_client is None:
        # initialize once
    ...
```

Or, better, initialize them once and pass through `ResearchState`.

---

## Risk 6: No Validation of Research Output Quality

**Where:** `src/agents/specialized_node.py` — result dict (lines 171–179)

```python
return {"research_outputs": {subject_id: {
    "subject_id": subject_id,
    "subject_name": subject.name,
    "research_output": output_text,
    "sources": [],          # always empty
    ...
}}}
```

**Risk:** The `sources` list is **always empty** — actual citations are buried in the `research_output` text string, never extracted as structured data. Additionally, there's no validation that:
- The output is relevant to the requested subject
- The output contains actual data (not a Gemini refusal or empty response)
- The output meets a minimum quality bar (length, presence of quantitative data)

An empty or low-quality output silently flows into synthesis and degrades the final report.

**Improvement:**
- Add minimum output length validation (e.g., < 200 chars → treat as failure, retry once).
- Parse source URLs from the text via regex and populate the `sources` field.
- Add a lightweight quality gate node in the graph between specialized and synthesis nodes.

---

## Risk 7: Synthesis Truncation Goes Undetected

**Where:** `src/agents/synthesis_node.py` — synthesis LLM call (lines 210–220)

```python
try:
    response = llm.invoke(
        [SystemMessage(content=system_instructions), HumanMessage(content=synthesis_prompt)]
    )
    report_text = response.content or ""
    return {"report_text": report_text}
except Exception as e:
    error_msg = f"Error synthesizing report: {e}"
    return {"report_text": error_msg}
```

**Risk:** The synthesis prompt requires an `END_OF_REPORT` marker at the end, but the node never checks for it. If Gemini hits the 8,000-token output limit and truncates mid-sentence, the incomplete report is silently stored. The `lwt` worktree had `check_end_marker=True` logic in `gemini_runner.py`, but the LangGraph version lost this safeguard during the migration.

**Improvement:**
- After `llm.invoke()`, check for `END_OF_REPORT` in `report_text`. If missing and content length suggests truncation, retry with a continuation prompt or increase `max_output_tokens`.
- At minimum, flag the report as incomplete in storage metadata.

---

## Risk 8: Orchestrator Recreates ReAct Agent on Every Turn

**Where:** `src/orchestrator_graph.py` — `_get_agent_response()` (lines 104–114)

```python
llm = ChatGoogleGenerativeAI(
    model=ORCHESTRATOR_MODEL,
    temperature=0.7,
    max_output_tokens=ORCHESTRATOR_MAX_OUTPUT_TOKENS,
)
agent = create_react_agent(
    llm,
    [generate_report],
    prompt=system_instructions,
)
```

**Risk:** A new LLM instance and a new ReAct agent graph are compiled on every single conversational turn. `create_react_agent` compiles a LangGraph `StateGraph` internally — this is unnecessary overhead repeated for every user message. Additionally, the `generate_report` tool is redefined as a closure on every turn (lines 75–102), capturing a stale reference to `session` via `self`.

**Improvement:** Create the LLM and agent once during `OrchestratorSession.__init__()` and reuse across turns. Pass dynamic context (ticker, trade_type) via the message rather than recompiling the agent.

---

## Risk 9: Race Conditions on OrchestratorSession State

**Where:** `src/orchestrator_graph.py` — mutable session state (lines 32–38)

```python
self.current_ticker: Optional[str] = None
self.current_trade_type: Optional[str] = None
self.current_report_id: Optional[str] = None
self.last_report_text: Optional[str] = None
self.conversation_history: List[Dict[str, str]] = []
```

**Risk:** `OrchestratorSession` is instantiated per Flask session. If report generation (which calls `run_research` synchronously) is running while the user sends another message, the shared mutable state (`current_report_id`, `last_report_text`, `conversation_history`) can be corrupted. The `generate_report` tool closure (line 94) writes to `session.current_report_id` from inside the LangGraph execution thread.

**Improvement:** Make `generate_report` return results through the graph state rather than mutating the session object. Or add a lock/flag that prevents concurrent mutation during report generation.

---

## Risk 10: Duplicate Rate Limit Retry Logic

**Where:** `src/agents/specialized_node.py` lines 88–93 and 140–187

**Risk:** `_is_rate_limit_error()` and the retry loop are duplicated across specialized_node.py and would be needed in any new node. This is a maintenance burden and divergence risk.

**Improvement:** Extract into a shared `retry.py` utility or use LangChain's built-in retry support (`llm.with_retry()`):

```python
llm = ChatGoogleGenerativeAI(...).with_retry(
    retry_if_exception_type=(RateLimitError,),
    wait_exponential_jitter=True,
    stop_after_attempt=3,
)
```

---

## Risk 11: MCP Tool Result Truncation Loses Data Silently

**Where:** `src/langchain_tools.py` — MCP handler (lines 33–37)

```python
for key in ("annualReports", "quarterlyReports", "monthlyReports", "reports", "items", "data"):
    if key in result and isinstance(result[key], list) and len(result[key]) > MAX_SERIES_ITEMS:
        result[key] = result[key][:MAX_SERIES_ITEMS]
```

**Risk:** Financial data arrays are silently clipped to 5 items (`MAX_SERIES_ITEMS = 5`). A ReAct agent asked to analyze "last 6–8 quarters" of earnings will only see 5 data points with no indication of truncation. The model may draw incomplete trend conclusions.

**Improvement:** Append a truncation marker when clipping data:

```python
result[key] = result[key][:MAX_SERIES_ITEMS]
result[f"_{key}_note"] = f"Truncated: showing {MAX_SERIES_ITEMS} of {original_len} items"
```

---

## Risk 12: `recursion_limit` Tied to Max Turns via Arbitrary Multiplier

**Where:** `src/agents/specialized_node.py` line 153

```python
result = agent.invoke(
    {"messages": [HumanMessage(content=research_prompt)]},
    config={"recursion_limit": SPECIALIZED_MAX_TURNS * 2},
)
```

**Risk:** The recursion limit is set to `SPECIALIZED_MAX_TURNS * 2` (default: 16). In LangGraph, each ReAct "turn" involves two node transitions (LLM call → tool execution), so this is correct at face value. However, if the agent makes multiple tool calls per turn, or if there are internal retries, the limit may be hit prematurely — causing a `GraphRecursionError` that the retry loop treats as a non-rate-limit error and immediately surfaces as a failed subject.

**Improvement:** Set `recursion_limit` with more headroom (e.g., `max_turns * 3`) or catch `GraphRecursionError` explicitly and handle it as a graceful termination rather than a hard failure.

---

## Risk 13: Full State Sent to Every Parallel Node via Send()

**Where:** `src/research_graph.py` — `_fan_out()` (lines 38–44)

```python
def _fan_out(state: ResearchState) -> List[Send]:
    plan = state["plan"]
    return [
        Send("specialized_node", {**state, "subject_id": sid})
        for sid in plan.selected_subject_ids
    ]
```

**Risk:** `{**state}` copies the entire `ResearchState` (including `conversation_context`, `emitter`, and already-accumulated `research_outputs`) into each `Send()` payload. As subjects complete and `research_outputs` grows, later-starting parallel nodes receive increasingly large state copies. This is wasteful and could cause memory pressure with many subjects.

**Improvement:** Only send the fields each specialized node actually reads:

```python
Send("specialized_node", {
    "ticker": state["ticker"],
    "trade_type": state["trade_type"],
    "plan": state["plan"],
    "subject_id": sid,
    "emitter": state.get("emitter"),
})
```

---

## Summary Priority Matrix

| Priority | Risk | Impact | Likelihood | Fix Effort |
|----------|------|--------|------------|------------|
| **P0** | #1 — No graph checkpointing | High — lost work/cost | Medium | Low (one-line change) |
| **P0** | #2 — Silent failure propagation | High — bad reports | Medium | Low |
| **P0** | #7 — Synthesis truncation undetected | High — incomplete reports | High | Low |
| **P1** | #3 — Unbounded token cost | High — cost overrun | Medium | Medium |
| **P1** | #4 — Planner fallback runs all subjects | High — cost spike | Low | Low |
| **P1** | #6 — No quality validation | Medium — bad synthesis | Medium | Medium |
| **P1** | #8 — Agent recreated every turn | Medium — latency/waste | High | Low |
| **P2** | #5 — Per-node client recreation | Medium — rate limits | High | Low |
| **P2** | #9 — Shared mutable session state | Medium — data corruption | Low | Medium |
| **P2** | #13 — Full state in Send() payloads | Low — memory waste | Medium | Low |
| **P2** | #12 — Fragile recursion_limit | Medium — premature failures | Low | Trivial |
| **P3** | #10 — Duplicate retry logic | Low — maintenance | N/A | Low |
| **P3** | #11 — Silent data truncation | Low — incomplete trends | High | Trivial |

---

## Recommended Quick Wins

1. **Add a checkpointer** (#1) — `_builder.compile(checkpointer=MemorySaver())` is a one-line change that enables free resumability.
2. **Add a quality gate node** (#2, #7) — insert a node between specialized and synthesis that filters errored outputs, checks for minimum output length, and aborts if too many subjects failed.
3. **Check for END_OF_REPORT** (#7) — after synthesis LLM call, verify the marker exists; retry or flag as incomplete if missing.
4. **Cache clients as true singletons** (#5) — use module-level globals with initialization guards.
5. **Use `llm.with_retry()`** (#10) — replace manual retry loops with LangChain's built-in retry support.

## Recommended Structural Improvements

1. **Add a token budget system** (#3) — estimate cost pre-flight, track cumulative usage via LangSmith, and abort on overspend.
2. **Minimize Send() payloads** (#13) — only send fields each node reads.
3. **Create orchestrator agent once** (#8) — compile in `__init__`, reuse across turns.
4. **Add output validation** (#6) — extract sources, check output length, gate quality before synthesis.
5. **Cap planner fallback** (#4) — use top 3–4 priority subjects instead of all eligible.

