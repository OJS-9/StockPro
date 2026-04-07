# StockPro -- Agent Architecture Reference

This document describes the agent patterns used in the StockPro research pipeline.

---

## Framework

All agents use **LangGraph** with **LangChain**. The key primitives:

- `create_react_agent` (LangGraph prebuilt) -- creates a ReAct loop agent
- `ChatGoogleGenerativeAI` (langchain-google-genai) -- Gemini model wrapper
- `StateGraph` + `Send()` (LangGraph) -- orchestrates the research pipeline with parallel fan-out
- `StructuredTool` (LangChain) -- wraps yfinance, MCP, and Nimble functions as agent tools

There is **no OpenAI Agents SDK** usage in this project. Old references to it are stale.

---

## Agent Inventory

| Agent | Model (default) | Env override | File |
|---|---|---|---|
| Orchestrator | gemini-2.5-flash | `ORCHESTRATOR_MODEL` | `src/orchestrator_graph.py` |
| Planner | gemini-2.5-flash | `PLANNER_MODEL` | `src/agents/planner_node.py` |
| Specialized (xN) | gemini-2.5-pro | `SPECIALIZED_AGENT_MODEL` | `src/agents/specialized_node.py` |
| Synthesis | gemini-2.5-pro | `SYNTHESIS_AGENT_MODEL` | `src/agents/synthesis_node.py` |
| Report chat | gemini-2.5-flash | `CHAT_AGENT_MODEL` | `src/agents/chat_agent.py` |

---

## Research Graph

Defined in `src/research_graph.py` as a LangGraph `StateGraph`:

```
START -> planner_node -> _fan_out (Send per subject) -> specialized_node (parallel)
      -> quality_gate_node -> synthesis_node -> storage_node -> END
```

- **planner_node**: single LLM call, outputs `ResearchPlan` (subject IDs + focus hints)
- **specialized_node**: ReAct agent with tools, runs once per subject via `Send()`
- **quality_gate_node**: filters errored outputs, aborts if >50% failed
- **synthesis_node**: merges all research into final report, checks for truncation
- **storage_node**: chunks + embeds + persists to PostgreSQL

State merging for parallel outputs uses `Annotated[Dict, operator.or_]`.

---

## Orchestrator

`OrchestratorSession` in `src/orchestrator_graph.py`:

- Wraps a LangGraph `create_react_agent` with two tools:
  - `ask_user_questions` -- captures clarifying questions for the popup flow
  - `generate_report` -- triggers the full research pipeline
- Manages conversation history, current ticker/trade_type, and pending questions
- Called from Flask routes: `popup_start`, `start_generation`, `continue_conversation`

---

## Tool Registration

Tools are registered in `src/langchain_tools.py` as LangChain `StructuredTool` instances:

1. **yfinance** (primary): `yfinance_fundamentals`, `yfinance_analyst`, `yfinance_ownership`, `yfinance_options`
2. **MCP** (selective): only `NEWS_SENTIMENT` from Alpha Vantage via `ESSENTIAL_MCP_TOOLS`
3. **Nimble** (web): `nimble_web_search`, `nimble_extract`, `perplexity_research`

yfinance is the default for company fundamentals. MCP is only used for news sentiment. Other MCP tools (OVERVIEW, INCOME_STATEMENT, etc.) exist but are not registered in agents -- yfinance covers the same data.

---

## Alpha Vantage MCP

HTTP JSON-RPC client in `src/mcp_client.py`. Config loaded from `mcp.json` by `src/mcp_manager.py`.

Available tools (all accessible via `mcp_tools.py`, but only NEWS_SENTIMENT active in agents):

| Tool | Data |
|---|---|
| OVERVIEW | Company profile, sector, market cap, ratios |
| INCOME_STATEMENT | Revenue, expenses, net income |
| BALANCE_SHEET | Assets, liabilities, equity |
| CASH_FLOW | Operating, investing, financing cash flows |
| EARNINGS | Quarterly EPS actual vs estimate |
| NEWS_SENTIMENT | News articles with sentiment scores |

Tool outputs are truncated (max 5 series items, max 5 news items) before passing to agents.

---

## Spend Budget

`src/spend_budget.py` provides per-run USD cost estimation:

- Estimates token usage based on subject count and agent settings
- Converts budget into `effective_max_turns` and `effective_max_output_tokens`
- Applied in `_fan_out` and enforced in specialized_node
- Budget + effective settings persisted to report metadata

Env vars: `RESEARCH_SPEND_BUDGET_USD_DEFAULT`, `GEMINI_INPUT_USD_PER_1K_TOKENS`, `GEMINI_OUTPUT_USD_PER_1K_TOKENS`

---

## Error Handling

- **Rate limit retry**: exponential backoff via `src/retry_utils.py` (`run_with_exponential_backoff`)
- **Planner fallback**: if LLM call fails, falls back to all eligible subjects
- **Per-agent isolation**: individual specialized agent failures don't crash the pipeline
- **Quality gate**: filters errored outputs, aborts synthesis if majority failed
- **Synthesis truncation**: checks for END_OF_REPORT marker, retries once on truncation
- **Storage fallback**: report renders in UI even if DB storage fails; RAG chat disabled

---

## Observability

- **LangSmith**: auto-traces all LangChain/LangGraph calls when `LANGCHAIN_TRACING_V2=true`
- **StepEmitter** (`src/langsmith_service.py`): SSE progress messages for frontend (planner started, subject N researching, synthesis, etc.)
- **report_quality.py**: post-hoc markdown structure assessment (headings, sections)

---

*Last updated: April 2026*
