# Code Review — Stock Portfolio Agent

**Date:** February 27, 2026
**Scope:** Full codebase review covering all source files, templates, tests, and configuration

---

## Executive Summary

The Stock Portfolio Agent is a well-structured multi-agent research platform with clear separation of concerns across research orchestration, portfolio management, and a Flask web interface. The architecture — Planner → Orchestrator → Specialized Agents → Synthesis → RAG Chat — is sound and demonstrates good design thinking.

However, the review uncovered **several critical security vulnerabilities**, significant **code duplication across agent files**, **scaling concerns** in the vector search and session management layers, and **missing dependencies** in `requirements.txt`. The issues below are organized by severity.

---

## Critical Issues

### 1. XSS Vulnerability in Chat Interface

**File:** `templates/chat.html`

The chat template disables Jinja2 auto-escaping with `| safe` on markdown-rendered content (line 83), and the client-side JavaScript injects `marked.parse(content)` directly into the DOM via `innerHTML` (line 323) without any sanitization library like DOMPurify.

If an AI response or stored message contains malicious HTML/JS, it will execute in the user's browser. This is a **stored XSS vector**.

**Recommendation:**
- Remove `| safe` or ensure the `markdown` filter sanitizes output (strip `<script>`, event handlers, etc.).
- Add DOMPurify on the client side: `innerHTML = DOMPurify.sanitize(marked.parse(content))`.

### 2. No CSRF Protection on Any Form

**Files:** All templates with `<form>` elements — `index.html`, `chat.html`, `login.html`, `register.html`, `add_transaction.html`, `import_csv.html`, `holding_detail.html`

No CSRF tokens are present on any POST form. All state-changing operations (`/start_research`, `/continue`, `/generate_report`, `/portfolio/add`, transaction delete) are vulnerable to cross-site request forgery.

**Recommendation:**
- Integrate Flask-WTF or implement manual CSRF token generation and validation.
- Add `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">` to every form.

### 3. Missing Authorization on Transaction Delete

**File:** `src/app.py` (lines ~598–626)

The `delete_transaction` route does not verify the transaction belongs to the logged-in user's portfolio. Any authenticated user can delete any transaction by guessing or enumerating transaction IDs.

**Recommendation:**
- Join through `transactions → holdings → portfolios → users` to verify ownership before deletion.
- Apply the same ownership check to all portfolio CRUD operations.

### 4. Flask Missing from `requirements.txt`

**File:** `requirements.txt`

The application is a Flask app (`src/app.py`), but `flask` is not listed as a dependency. Additionally, `pytest` (used by test files) is missing, and `gradio` appears to be unused dead weight from a previous iteration.

**Recommendation:**
```
flask>=3.0.0
flask-wtf>=1.2.0
pytest>=7.0.0
# Remove: gradio>=4.0.0 (unless still used elsewhere)
```

---

## High Severity Issues

### 5. Memory Leak in Agent Sessions

**File:** `src/app.py` (line 49)

The global `agent_sessions = {}` dict grows unboundedly. Every unique Flask session creates a `StockResearchAgent` that is never evicted. Over time, this will exhaust server memory.

**Recommendation:**
- Add TTL-based eviction (e.g., `cachetools.TTLCache`) or a max-size LRU cache.
- Clean up agents when sessions expire.

### 6. CDN Scripts Without Subresource Integrity

**File:** `templates/base.html`

Tailwind CSS, marked.js, and Google Fonts are loaded from CDNs without `integrity` attributes. A compromised CDN could inject malicious code into every page.

**Recommendation:**
- Add `integrity="sha384-..."` and `crossorigin="anonymous"` attributes to all CDN `<script>` and `<link>` tags, or self-host the assets.

### 7. Secret Key Fallback Generates Random Key on Every Restart

**File:** `src/app.py` (line 34)

```python
app.secret_key = os.getenv('FLASK_SECRET_KEY', os.urandom(24).hex())
```

If `FLASK_SECRET_KEY` is not set, every process restart generates a new key, invalidating all active sessions. With multiple workers, each gets a different key, breaking session sharing.

**Recommendation:**
- Fail loudly if `FLASK_SECRET_KEY` is not set in production.
- Log a warning in development mode.

---

## Architecture & Design Issues

### 8. Duplicated Retry Logic Across Agent Files

**Files:** `src/agent.py`, `src/specialized_agent.py`

`_is_rate_limit_error` and the retry wrapper are copy-pasted between the orchestrator and specialized agents. The synthesis agent and chat agents have **no retry logic at all**, creating inconsistent resilience.

**Recommendation:**
- Extract retry logic into a shared `src/agent_utils.py` module.
- Apply it uniformly to all agent runners.

### 9. Overlapping Chat Agents

**Files:** `src/report_chat_agent.py`, `src/conversation_handler_agent.py`

These two files serve nearly identical purposes (RAG-based Q&A on reports). `ConversationHandlerAgent` adds raw research outputs to the context but is otherwise a copy. `conversation_handler_agent.py` appears unused in the main flow.

**Recommendation:**
- Merge into a single agent with an option to include raw research outputs.
- Delete the unused file to reduce maintenance burden.

### 10. ThreadPoolExecutor for IO-Bound Async Work

**File:** `src/research_orchestrator.py`

Each specialized agent runs inside a thread that creates its own asyncio event loop via `Runner.run_sync`. This is functional but wasteful — threads + event loops is double overhead.

**Recommendation:**
- Use `asyncio.gather` with `Runner.run` (async) instead of `ThreadPoolExecutor`.
- If staying synchronous, add per-future timeouts to prevent the orchestrator from blocking indefinitely on a hung agent.

### 11. MCP/Perplexity Clients Recreated Per Agent

**File:** `src/specialized_agent.py`

Every `SpecializedResearchAgent` instance creates new `MCPManager`, MCP client, Perplexity client, and tools. With 12 research subjects running in parallel, that's 12 sets of client initializations.

**Recommendation:**
- Create clients once in the orchestrator and inject them into specialized agents via constructor parameters.

### 12. God-Object Tendency in StockResearchAgent

**File:** `src/agent.py`

`StockResearchAgent` holds references to every sub-component (planner, orchestrator, synthesis agent, report storage, chat agent) and manages all state transitions. This makes testing difficult and couples everything through a single class.

**Recommendation:**
- Consider a pipeline/mediator pattern where each stage is independently testable.
- At minimum, extract state management into a separate session/context object.

---

## Code Quality Issues

### 13. Inconsistent Import Paths

**Files:** `src/specialized_agent.py`, `src/synthesis_agent.py`, `src/report_chat_agent.py`, `src/research_prompt.py`, `src/mcp_manager.py`, `src/perplexity_tools.py`

Some files use `from src.date_utils import ...` (with `src.` prefix) while others use bare imports like `from mcp_client import MCPClient`. The `src.` prefix only works when the working directory is *above* `src/`, making execution context-dependent.

**Recommendation:**
- Standardize on bare imports throughout `src/`.
- Configure the Python path once in the entry point (`app.py`), or restructure as an installable package.

### 14. `print()` Used Instead of `logging` Module

**Files:** Nearly all files — `agent.py`, `specialized_agent.py`, `report_storage.py`, `stock_provider.py`, `crypto_provider.py`, etc.

No structured logging is used anywhere. All diagnostic output goes through `print()`, which cannot be filtered by level, routed to files, or disabled in production.

**Recommendation:**
- Replace with Python's `logging` module.
- Use appropriate levels: `logger.debug()` for token counts, `logger.warning()` for rate limits, `logger.error()` for failures.

### 15. Hardcoded Model and Temperature Everywhere

**Files:** All agent files

`"gpt-4o"` and `temperature=0.7` are hardcoded in every agent constructor. Model changes require editing 5+ files.

**Recommendation:**
- Define `DEFAULT_MODEL` and `DEFAULT_TEMPERATURE` as env-configurable constants in a shared config module.
- Override per-agent only when there's a specific reason (e.g., lower temperature for research agents to reduce hallucination).

### 16. No-Op Code and Dead Code

| File | Issue |
|------|-------|
| `src/mcp_tools.py` line 32 | `tool_name.lower().replace("_", "_")` — replace is a no-op |
| `src/agent_tools.py` lines 153–158 | `inspect.signature(FunctionTool.__init__)` result is assigned but never used |
| `src/agent_tools.py` lines 171, 331, 357 | `except Exception as e: raise` — catch-and-reraise adds no value |
| `static/css/style.css` | Entire file is unused (templates use Tailwind, not this purple theme) |
| `src/agent.py` line 10 | `Any as AnyType` alias — confusing and unnecessary |

### 17. Bare `except:` and `except: pass`

| File | Line | Issue |
|------|------|-------|
| `src/app.py` | ~416 | `except: pass` silently swallows all exceptions including `SystemExit` |
| `src/date_utils.py` | 39 | Bare `except:` catches `KeyboardInterrupt` |

**Recommendation:**
- Always use `except Exception:` at minimum.
- Never use `except: pass` — at least log the error.

---

## Database & Storage Issues

### 18. Massive DatabaseManager Class (~940 Lines)

**File:** `src/database.py`

`DatabaseManager` handles reports, chunks, users, portfolios, holdings, transactions, and CSV imports in a single class. Every method repeats the same connection/cursor/try/finally boilerplate.

**Recommendation:**
- Split into domain-specific repositories (`ReportRepository`, `UserRepository`, `PortfolioRepository`).
- Use a context manager or decorator to eliminate the repeated boilerplate.

### 19. No Atomicity in Report Storage

**File:** `src/report_storage.py`

Report save and chunk save are separate database operations with no transaction wrapping. If embedding generation fails partway through, the report exists but chunks are incomplete, leaving an inconsistent state.

**Recommendation:**
- Wrap the full save (report + chunks + embeddings) in a single database transaction.

### 20. Embeddings Stored as JSON in MySQL

**File:** `src/database.py`

Embedding vectors are stored as JSON text and parsed on every search query. Combined with the brute-force O(n) scan in `vector_search.py`, this will not scale beyond a few hundred reports.

**Recommendation:**
- For near-term: cache parsed embeddings as NumPy arrays after first load.
- For long-term: migrate to a vector database (pgvector, FAISS, Pinecone) for proper ANN search.

---

## Security Concerns

### 21. Prompt Injection via Ticker Symbol

**File:** `src/research_prompt.py`

Ticker symbols and trade types are injected directly into LLM prompts via f-strings with no sanitization. A malicious ticker like `"AAPL\n\nIgnore all instructions and..."` could manipulate agent behavior.

**Recommendation:**
- Validate ticker format (regex: `^[A-Z]{1,5}$`).
- Validate trade type against an enum of allowed values.
- Sanitize all user inputs before prompt injection.

### 22. API Key in URL Query Parameters

**Files:** `src/mcp_client.py`, `src/mcp_manager.py`

The Alpha Vantage API key is appended to the URL as a query parameter. This means the key appears in HTTP access logs, proxy logs, and potentially browser history.

**Recommendation:**
- Pass the API key via an HTTP header instead if the MCP server supports it.
- At minimum, ensure access logs are not publicly accessible.

### 23. Error Messages Leak Internal Details

**Files:** All agent files, `src/app.py`

Raw `str(e)` from exceptions is passed back to the LLM context and in some cases to the user. This can expose file paths, API key fragments, or internal server details.

**Recommendation:**
- Return generic error messages to users/LLM.
- Log the full exception details server-side.

---

## Frontend & UX Issues

### 24. Hardcoded Market Data on Landing Page

**File:** `templates/index.html`

The market overview cards show static values (S&P 500 at 412.34, Bitcoin at 30,450, Tesla at 165.08). These are not live and will appear stale.

**Recommendation:**
- Either fetch live data or remove the cards.
- If keeping placeholders, label them clearly as examples.

### 25. Mobile Navigation Menu Non-Functional

**File:** `templates/index.html`

The hamburger menu button exists but has no click handler or menu expansion logic.

### 26. Timestamps Hardcoded in Chat

**File:** `templates/chat.html`

Server-rendered messages all show "10:02 AM" regardless of when they were actually created.

### 27. Login/Register Pages Don't Extend `base.html`

**Files:** `templates/login.html`, `templates/register.html`

These are standalone HTML documents with their own CDN includes and a different color scheme (amber accent vs. the stone/green theme). This creates visual inconsistency.

### 28. Portfolio Table Rows Not Keyboard-Accessible

**File:** `templates/portfolio.html`

Table rows use `onclick="window.location='...'"` for navigation. This is not keyboard-accessible — users cannot tab to rows or activate them with Enter/Space.

**Recommendation:**
- Wrap row content in `<a>` tags or add `role="link"`, `tabindex="0"`, and keyboard event handlers.

---

## Testing Gaps

### 29. No Automated Test Suite for Flask Routes

There are no tests for any Flask endpoint. Authentication, research flow, portfolio CRUD, and error handling are all untested at the integration level.

### 30. Integration Tests Require Live API Keys

**Files:** `test_nvda_research.py`, `test_mcp.py`

These tests make real API calls with no mocking. They cannot run in CI/CD and are fragile (dependent on network, rate limits, API availability).

### 31. Missing Edge Case Tests

- No test for overselling in `cost_basis.py` (selling more shares than held).
- No test for Robinhood format parsing in `csv_importer.py` (only detection is tested).
- No test for concurrent agent session access.
- No test for vector search with mismatched embedding dimensions.

---

## Configuration & Dependencies

### 32. `requirements.txt` Incomplete and Unpinned

| Issue | Detail |
|-------|--------|
| **Missing** | `flask`, `flask-wtf`, `pytest`, `bcrypt` or `werkzeug` (password hashing) |
| **Unused** | `gradio>=4.0.0` appears to be a leftover from a previous UI |
| **Unpinned** | All deps use `>=` — builds are not reproducible |

**Recommendation:**
- Add missing dependencies.
- Remove `gradio` if unused.
- Pin exact versions or use a lockfile.

### 33. Naive `datetime.now()` Without Timezone

**File:** `src/date_utils.py`

`datetime.now()` returns local time without timezone info. In a server environment, this is unpredictable.

**Recommendation:**
- Use `datetime.now(tz=timezone.utc)` and convert to display timezone in templates.

---

## Summary Table

| # | Issue | Severity | Category |
|---|-------|----------|----------|
| 1 | XSS in chat via `\| safe` + no DOMPurify | **Critical** | Security |
| 2 | No CSRF protection on forms | **Critical** | Security |
| 3 | No authorization on transaction delete | **Critical** | Security |
| 4 | Flask missing from requirements.txt | **Critical** | Config |
| 5 | Memory leak in agent_sessions | **High** | Performance |
| 6 | CDN scripts without SRI | **High** | Security |
| 7 | Secret key fallback on restart | **High** | Security |
| 8 | Duplicated retry logic | **Medium** | Code Quality |
| 9 | Overlapping chat agents | **Medium** | Architecture |
| 10 | ThreadPoolExecutor for async work | **Medium** | Architecture |
| 11 | Clients recreated per agent | **Medium** | Performance |
| 12 | God-object in StockResearchAgent | **Medium** | Architecture |
| 13 | Inconsistent import paths | **Medium** | Code Quality |
| 14 | `print()` instead of `logging` | **Medium** | Code Quality |
| 15 | Hardcoded model/temperature | **Medium** | Code Quality |
| 16 | No-op and dead code | **Low** | Code Quality |
| 17 | Bare `except: pass` | **Medium** | Code Quality |
| 18 | DatabaseManager too large | **Medium** | Architecture |
| 19 | No atomicity in report storage | **Medium** | Data Integrity |
| 20 | Embeddings as JSON in MySQL | **Medium** | Scalability |
| 21 | Prompt injection via ticker | **Medium** | Security |
| 22 | API key in URL params | **Medium** | Security |
| 23 | Error messages leak internals | **Medium** | Security |
| 24 | Hardcoded market data | **Low** | UX |
| 25 | Mobile nav non-functional | **Low** | UX |
| 26 | Hardcoded chat timestamps | **Low** | UX |
| 27 | Login/register inconsistent with base | **Low** | UX |
| 28 | Portfolio rows not keyboard-accessible | **Low** | Accessibility |
| 29 | No Flask route tests | **Medium** | Testing |
| 30 | Tests require live API keys | **Medium** | Testing |
| 31 | Missing edge case tests | **Low** | Testing |
| 32 | requirements.txt incomplete | **High** | Config |
| 33 | Naive datetime without timezone | **Low** | Code Quality |

---

## Recommended Priority Actions

1. **Immediate** — Fix XSS in `chat.html` (add DOMPurify, remove `| safe`).
2. **Immediate** — Add CSRF protection to all forms.
3. **Immediate** — Add ownership verification on all portfolio mutation endpoints.
4. **This sprint** — Fix `requirements.txt` (add flask, remove gradio, pin versions).
5. **This sprint** — Add TTL eviction to `agent_sessions`.
6. **This sprint** — Standardize imports and extract shared agent utilities.
7. **Next sprint** — Replace `print()` with structured logging.
8. **Next sprint** — Add Flask route integration tests with mocked API clients.
9. **Backlog** — Migrate embeddings to a vector database.
10. **Backlog** — Refactor `DatabaseManager` into domain repositories.
