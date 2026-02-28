# Code Review — Stock Portfolio Agent

**Date:** February 27, 2026
**Reviewer:** AI Code Review
**Scope:** Full codebase — 33 source files, 9 templates, 5 test files, configuration, and dependencies

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Critical Vulnerabilities](#1-critical-vulnerabilities)
3. [High Severity Issues](#2-high-severity-issues)
4. [Architecture & Design](#3-architecture--design-issues)
5. [Code Quality](#4-code-quality-issues)
6. [Database Layer](#5-database-layer)
7. [MCP & External Integrations](#6-mcp--external-integrations)
8. [Portfolio Module](#7-portfolio-module)
9. [Frontend & Templates](#8-frontend--templates)
10. [Testing](#9-testing-gaps)
11. [Dependencies & Configuration](#10-dependencies--configuration)
12. [Summary Table](#summary-table)
13. [Recommended Action Plan](#recommended-action-plan)

---

## Executive Summary

The Stock Portfolio Agent is a well-architected multi-agent research platform with clear separation of concerns: a planning stage selects research subjects, an orchestrator fans out to specialized agents, a synthesis agent consolidates findings, and a RAG-based chat layer enables follow-up Q&A. The Flask web layer, portfolio module, and data provider abstraction are all cleanly structured.

However, the review identified **4 critical security vulnerabilities** (XSS, CSRF, IDOR), **significant code duplication** across agent files, **a broken module** (`conversation_handler_agent.py`), **missing dependencies** in `requirements.txt`, and **scaling concerns** in the vector search and session management layers. The findings below are organized by severity and domain.

---

## 1. Critical Vulnerabilities

### 1.1 Stored XSS via Markdown Rendering

**Files:** `templates/chat.html` (line 83), `templates/report_view.html` (line 158)

The chat template chains `| markdown | safe`, which converts AI-generated text to HTML and then disables Jinja2's auto-escaping:

```html
{{ message.content | markdown | safe }}
```

The `markdown` filter in `app.py` (lines 62–66) wraps output in `Markup()`, which also bypasses escaping. If an AI response contains `<script>alert('xss')</script>` — possible via prompt injection or a poisoned API data source — it executes in every user's browser.

A second XSS vector exists on the client side: `chat.html` line 323 uses `marked.parse(content)` and injects the result via `.innerHTML` with no sanitization library. The `marked` library does not sanitize HTML by default.

**Fix:**
- Add `bleach` to dependencies and sanitize the markdown filter output with an HTML tag allowlist.
- Add DOMPurify on the client side: `innerHTML = DOMPurify.sanitize(marked.parse(content))`.

---

### 1.2 No CSRF Protection on Any Form

**Files:** Every template with a `<form>` element — `index.html`, `chat.html`, `login.html`, `register.html`, `add_transaction.html`, `import_csv.html`, `holding_detail.html`

No CSRF tokens exist anywhere. All POST endpoints are vulnerable to cross-site request forgery. An attacker could craft a page that deletes transactions, imports malicious CSV data, or initiates research on behalf of an authenticated user.

**Fix:**
- Integrate `Flask-WTF` and add `{{ form.hidden_tag() }}` or `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">` to every form.

---

### 1.3 Missing Authorization on Portfolio Mutations (IDOR)

**File:** `app.py` (lines 646–674), `portfolio_service.py`

The `delete_transaction` route verifies the transaction exists but never checks that it belongs to the logged-in user's portfolio. Any authenticated user can delete any transaction by ID. The same pattern applies to other portfolio operations — `portfolio_service.py` methods accept `portfolio_id` directly without ownership verification.

**Fix:**
- Add a `verify_portfolio_ownership(user_id, portfolio_id)` check before every mutation.
- In the database layer, include `user_id` in portfolio SELECT queries (currently `get_portfolio` omits `user_id` from its SELECT on line 604).

---

### 1.4 Broken Module — `conversation_handler_agent.py`

**File:** `src/conversation_handler_agent.py` (line 15)

```python
from research_prompt import get_conversation_handler_instructions
```

The function `get_conversation_handler_instructions` does not exist in `research_prompt.py`. This import raises `ImportError` at module load time, meaning the entire module is non-functional. No other file imports `ConversationHandlerAgent`, so this hasn't surfaced as a runtime crash, but it is dead/broken code.

**Fix:**
- Either implement `get_conversation_handler_instructions` in `research_prompt.py`, or delete `conversation_handler_agent.py` if it's been superseded by `report_chat_agent.py`.

---

## 2. High Severity Issues

### 2.1 Memory Leak in Agent Sessions

**File:** `app.py` (line 96)

```python
agent_sessions = {}
```

This global dict grows unboundedly. Every unique Flask session creates a `StockResearchAgent` (which holds references to planner, orchestrator, synthesis agent, report storage, and chat agent) that is never evicted. Over hours/days of traffic, this will exhaust memory.

**Fix:** Use `cachetools.TTLCache` with a max size and TTL (e.g., 30 minutes), or clean up agents when sessions expire.

---

### 2.2 Unstable Secret Key

**File:** `app.py` (line 38)

```python
app.secret_key = os.getenv('FLASK_SECRET_KEY', os.urandom(24).hex())
```

If the env var is not set, a new random key is generated on every process restart, invalidating all sessions. In a multi-worker deployment, each worker gets a different key — sessions randomly fail depending on which worker handles the request.

**Fix:** Fail loudly if `FLASK_SECRET_KEY` is not set (raise on startup).

---

### 2.3 Duplicate `login_required` Decorator

**File:** `app.py` (lines 41–48 and 124–131)

The `login_required` decorator is defined identically in two places. The second definition silently shadows the first. This is a copy-paste artifact.

**Fix:** Delete the duplicate.

---

### 2.4 Internal Error Details Leaked to Users

**Files:** `app.py` (lines 205, 292, 366, 408, and many others)

```python
error = f'Registration failed: {str(e)}'
```

`str(e)` on database exceptions can contain table names, column names, query fragments, and MySQL version info. These are stored in `session['status_message']` and rendered to the user.

**Fix:** Return generic user-facing messages. Log the full exception server-side with `app.logger.error()`.

---

### 2.5 No Rate Limiting on Auth Endpoints

**File:** `app.py`

`/login` and `/register` have no throttling. Brute-force password attacks and account creation spam are unrestricted.

**Fix:** Add `Flask-Limiter` with appropriate rate limits (e.g., 5 login attempts per minute per IP).

---

### 2.6 CDN Scripts Without Subresource Integrity

**File:** `templates/base.html`

Tailwind CSS, `marked.js`, and Google Fonts are loaded from CDNs without `integrity` attributes. A CDN compromise injects malicious code into every page.

**Fix:** Add `integrity="sha384-..."` and `crossorigin="anonymous"` to all CDN `<script>` and `<link>` tags, or self-host.

---

### 2.7 No File Size Limit on CSV Upload

**File:** `app.py` (line 576)

No `MAX_CONTENT_LENGTH` is configured on the Flask app. A multi-GB upload would exhaust server memory. The only validation is `accept=".csv"` on the client (advisory, easily bypassed).

**Fix:** Add `app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024` (16 MB) or similar.

---

## 3. Architecture & Design Issues

### 3.1 God-Object Orchestrator

**File:** `agent.py`

`StockResearchAgent` holds references to every sub-component (planner, orchestrator, synthesis agent, report storage, chat agent, embedding service, vector search) and manages all state transitions. This makes isolated testing impractical and tightly couples the entire pipeline through one class.

**Suggestion:** Extract a pipeline/mediator that composes independently testable stages.

---

### 3.2 Agent Recreated on Every Call

**File:** `agent.py` (lines 241–247)

`_get_agent_response` creates a brand-new `Agent` instance on every invocation just to update the instructions string. The `self.agent` set in `_initialize_agent()` is never used for actual execution.

**Suggestion:** Parameterize instructions without rebuilding the agent, or clarify that the stored agent is a template.

---

### 3.3 ThreadPoolExecutor for IO-Bound Async Work

**File:** `research_orchestrator.py`

Each specialized agent is submitted to a `ThreadPoolExecutor`, but inside the thread it calls `Runner.run_sync()`, which creates its own asyncio event loop. Threads + event loops is double overhead.

Additionally, there is **no per-future timeout**. If one agent hangs, the entire orchestrator blocks indefinitely on `as_completed`.

**Suggestion:**
- Use `asyncio.gather` with `Runner.run` (async) instead.
- At minimum, add `future.result(timeout=120)` to prevent indefinite hangs.

---

### 3.4 MCP/Perplexity Clients Recreated Per Subject

**File:** `specialized_agent.py` (lines 47–52)

Every `SpecializedResearchAgent` creates its own `MCPManager`, `MCPClient`, and `PerplexityClient`. With 8–12 subjects running in parallel, that's 8–12 redundant client initializations.

**Fix:** Create clients once in the orchestrator and inject them.

---

### 3.5 Two Overlapping Chat Agents

**Files:** `report_chat_agent.py`, `conversation_handler_agent.py`

Both serve nearly identical purposes (RAG-based Q&A on reports). `conversation_handler_agent.py` adds raw research outputs but is broken (see 1.4) and appears unused. This creates confusion about which module is canonical.

**Fix:** Merge into a single agent or delete the unused one.

---

### 3.6 Planner Can Never Exclude Subjects

**File:** `planner_agent.py` (lines 173–177)

After the LLM returns its selection, the code appends any omitted subjects back. This means the LLM can never actually exclude a subject, making the "intelligent selection" aspect illusory.

**Suggestion:** Allow the LLM to exclude subjects and respect that decision, or document that the planner only reorders/prioritizes.

---

### 3.7 Perplexity Errors Returned as Strings, Not Raised

**File:** `perplexity_client.py` (lines 94–100)

```python
except Exception as e:
    return f"[Perplexity error] Research request failed: {e}"
```

Errors are returned as normal string responses. Callers cannot distinguish success from failure without parsing the string prefix. Error messages get fed to the LLM as if they were valid research content.

**Fix:** Raise exceptions and let callers handle them, or return a structured result type with a `status` field.

---

## 4. Code Quality Issues

### 4.1 Duplicated Retry Logic

**Files:** `agent.py` (~lines 452–485), `specialized_agent.py` (~lines 340–370)

`_is_rate_limit_error` and the retry wrapper are copy-pasted. The synthesis agent and chat agents have **no retry logic at all**.

**Fix:** Extract into a shared `agent_utils.py` and apply uniformly.

---

### 4.2 Duplicated Result Extraction Pattern

**Files:** `agent.py`, `specialized_agent.py`, `synthesis_agent.py`, `report_chat_agent.py`, `conversation_handler_agent.py`

The following block appears 5 times:

```python
if hasattr(result, 'final_output'):
    response_text = result.final_output
elif hasattr(result, 'output'):
    response_text = result.output
```

**Fix:** Create a shared `extract_agent_output(result) -> str` utility.

---

### 4.3 Inconsistent Import Paths

**Files:** `mcp_manager.py`, `perplexity_tools.py`, `research_prompt.py` use `from src.module import ...`; `mcp_tools.py`, `report_storage.py`, `vector_search.py` use `from module import ...`

The `src.` prefix only works when the working directory is above `src/`. Other imports only work from within `src/`. This creates fragile, launch-context-dependent behavior.

**Fix:** Pick one convention (bare imports + configure `PYTHONPATH` in the entry point) and apply consistently.

---

### 4.4 `print()` Instead of `logging` Everywhere

**Files:** Nearly all — `agent.py`, `specialized_agent.py`, `report_storage.py`, `stock_provider.py`, `crypto_provider.py`, `embedding_service.py`, `mcp_manager.py`, `database.py`

No structured logging exists. All diagnostic output uses `print()`, which can't be filtered, routed, or disabled in production.

**Fix:** Configure Python's `logging` module once in `app.py` and use `logger.debug()`, `logger.info()`, `logger.warning()`, `logger.error()` throughout.

---

### 4.5 Hardcoded Model and Temperature

**Files:** `agent.py`, `specialized_agent.py`, `synthesis_agent.py`, `report_chat_agent.py`, `planner_agent.py`

`"gpt-4o"` and `temperature=0.7` are hardcoded in every agent constructor. Changing models requires editing 5+ files.

**Fix:** Define `DEFAULT_MODEL` and `DEFAULT_TEMPERATURE` as env-configurable constants in a shared config module.

---

### 4.6 Dead Code and No-Ops

| File | Issue |
|------|-------|
| `app.py` lines 41–48 | Duplicate `login_required` decorator (shadowed by second definition) |
| `mcp_tools.py` line 32 | `.replace("_", "_")` — replaces underscores with underscores |
| `agent_tools.py` lines 152–158 | `inspect.signature(FunctionTool.__init__)` result assigned but never used |
| `agent_tools.py` lines 169–171, 331, 355–357 | `except Exception as e: raise` — catch-and-reraise with no additional logic |
| `agent_tools.py` line 7 | `asyncio` imported but never used |
| `agent.py` line 10 | `Any as AnyType` — confusing and unnecessary alias |
| `research_prompt.py` lines 7–74 | `get_system_instructions()` — no callers found |
| `research_prompt.py` lines 77–128 | `get_specialized_agent_instructions()` — superseded by `specialized_agent.py`'s own method |
| `research_subjects.py` lines 454–459 | `get_research_subjects()` — marked deprecated, no callers |
| `static/css/style.css` | Entire 350-line stylesheet unused (app uses Tailwind) |
| `mcp_manager.py` lines 11–12 | Commented-out import identical to active import |

---

### 4.7 Bare `except` and Swallowed Errors

| File | Line | Issue |
|------|------|-------|
| `app.py` | ~463 | `except: pass` — catches `SystemExit`, `KeyboardInterrupt`, swallows everything |
| `date_utils.py` | 39 | `except:` — bare except on timezone detection |
| `mcp_client.py` | 123 | `except Exception: pass` — silently swallows tool discovery failures |
| `agent_tools.py` | 157 | `except: pass` — silently swallows introspection error |

**Fix:** Use `except Exception:` at minimum. Log swallowed errors.

---

### 4.8 Ticker Extraction Regex Is Unreliable

**File:** `agent.py` (lines 294–304)

```python
match = re.search(r"\b([A-Z]{1,5})\b", content)
```

This matches any 1–5 uppercase word: "YOU", "NOT", "TRADE", "FOCUS", etc. Since `self.current_ticker` is already stored as an instance attribute, this method is both broken and unnecessary.

**Fix:** Use `self.current_ticker` directly.

---

### 4.9 Trade Type Strings as Magic Strings

`"Day Trade"`, `"Swing Trade"`, `"Investment"` appear as raw strings in 30+ locations across 8+ files. A typo silently breaks behavior with no error.

**Fix:** Create a `TradeType` enum or module-level constants.

---

## 5. Database Layer

### 5.1 ~940-Line God Class

**File:** `database.py`

`DatabaseManager` handles reports, chunks, users, portfolios, holdings, transactions, and CSV imports in one class. Every method repeats the same ~10-line connection/cursor/try/finally boilerplate (25+ methods × 10 lines = ~250 lines of pure duplication).

**Fix:**
- Extract a `@contextmanager` for connection lifecycle.
- Split into domain-specific repositories (`ReportRepository`, `UserRepository`, `PortfolioRepository`).

---

### 5.2 Duplicate `CREATE TABLE users` in Schema Init

**File:** `database.py` (lines 65–75 and 126–136)

The exact same DDL runs twice per `init_schema()`. `IF NOT EXISTS` makes it benign but it's clearly a copy-paste artifact.

---

### 5.3 `cursor` May Be Undefined in `finally` Blocks

Many methods follow this pattern:

```python
connection = None
try:
    connection = self.get_connection()
    cursor = connection.cursor(dictionary=True)
    ...
finally:
    cursor.close()  # ← UnboundLocalError if cursor was never assigned
```

Some methods correctly initialize `cursor = None` and check before closing. Most do not.

---

### 5.4 Password Hash Exposed in General User Queries

**File:** `database.py` (lines 679–685, 700–706)

Both `get_user_by_username` and `get_user_by_id` SELECT and return `password_hash`. While needed for login verification, the hash leaks if these dicts are logged, serialized, or passed to templates.

**Fix:** Create a dedicated `verify_password(username, password)` method. Exclude `password_hash` from general user lookups.

---

### 5.5 No Connection Timeouts

The MySQL config (lines 23–32) sets no `connect_timeout`, `read_timeout`, or `write_timeout`. A stalled MySQL server hangs the application indefinitely.

---

### 5.6 f-String SQL with `sort_order`

**File:** `database.py` (line 427)

```python
ORDER BY created_at {sort_order}
```

The `sort_order` is validated against `ASC`/`DESC` on line 412, so this is technically safe. But the pattern of interpolating variables into SQL strings sets a bad precedent. Defense-in-depth would use a mapping or conditional instead of f-string interpolation.

---

### 5.7 `save_chunks` Uses Loop of Individual INSERTs

**File:** `database.py` (lines 465–480)

For a report with 50+ chunks, this issues 50+ individual INSERT statements. `cursor.executemany()` or a multi-row INSERT would be significantly faster.

---

### 5.8 Thread-Unsafe Singleton

**File:** `database.py` (lines 1055–1061)

```python
def get_database_manager():
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager
```

Classic TOCTOU race condition. Two threads can both see `None` and both initialize. Needs `threading.Lock`.

---

### 5.9 Precision Mismatch in Holdings Table

**File:** `database.py` (line 176)

`total_cost_basis` is `DECIMAL(18,2)` but `average_cost` and `total_quantity` are both `DECIMAL(18,8)`. Their product can require more than 2 decimal places, causing silent truncation.

---

### 5.10 No Atomicity in Report Storage

**File:** `report_storage.py`

`store_report` saves the report to DB (line 51), then chunks, then creates embeddings, then saves chunks. If embedding creation fails partway, the report exists but chunks are incomplete. No transaction wrapping or rollback.

---

## 6. MCP & External Integrations

### 6.1 API Key in URL Query Parameters

**Files:** `mcp_client.py` (lines 62–67), `mcp_manager.py` (lines 70–77)

The Alpha Vantage API key is appended to every URL as a query parameter. It appears in HTTP access logs, proxy logs, `requests` exception messages, and the `mcp_url` stored on the client instance.

---

### 6.2 Hardcoded Fallback Tool Definitions

**File:** `mcp_client.py` (lines 128–218)

90 lines of hardcoded tool schemas serve as a fallback when tool discovery fails. These schemas can silently drift from the actual MCP server's capabilities.

---

### 6.3 Tool Name Mismatch

**File:** `mcp_manager.py` (line 157) uses `"COMPANY_OVERVIEW"`, but `mcp_client.py` fallback (line 130) and `mcp_tools.py` (line 71) use `"OVERVIEW"`. This mismatch will cause runtime failures when the convenience method hits a server that only recognizes one name.

---

### 6.4 Silent Tool Discovery Failure

**File:** `mcp_client.py` (lines 123–124)

```python
except Exception:
    pass
```

If `tools/list` fails, the client silently falls through to hardcoded definitions with no log message.

---

### 6.5 Blocking `time.sleep()` in Retry

**File:** `mcp_client.py` (line 84)

Synchronous `time.sleep()` in the retry loop blocks the Flask worker thread during backoff, stalling other requests.

---

### 6.6 Truncation Is Opaque to the LLM

**File:** `agent_tools.py`

`MAX_SERIES_ITEMS = 5`, `MAX_NEWS_ITEMS = 5` — tool output is truncated but the agent has no indication data was clipped. This can cause the LLM to draw conclusions from incomplete data.

**Fix:** Append a note like `"[15 more items truncated]"` after truncation.

---

## 7. Portfolio Module

### 7.1 Overselling Not Prevented

**Files:** `cost_basis.py` (line 83), `portfolio_service.py` (line 244)

Selling more shares than held produces negative `total_quantity` and nonsensical `total_cost`. No validation or error.

---

### 7.2 No Sell Quantity Validation

**File:** `portfolio_service.py` (line 244)

`add_transaction` validates that `transaction_type` is `buy` or `sell` but does not check that sell quantity <= current holding quantity.

---

### 7.3 Race Condition on Holding Creation

**File:** `portfolio_service.py` (lines 249–254)

Two concurrent `add_transaction` calls for the same symbol both see `holding is None`, both try to create a new holding, and one fails on the unique constraint.

---

### 7.4 Sequential Batch Price Fetching

**File:** `stock_provider.py` (lines 114–131)

`get_prices_batch` fetches prices one-by-one with no delay between calls. Alpha Vantage free tier allows 5 calls/minute. A portfolio with 10+ stocks immediately exceeds this limit.

---

### 7.5 Full CoinGecko Coin List Fetched in Memory

**File:** `crypto_provider.py` (lines 79–88)

On first cache miss outside `SYMBOL_MAP`, the entire CoinGecko coin list (~14,000 entries) is fetched and held in memory. Linear search is used for lookups instead of dict-based O(1) access.

---

### 7.6 Fallback Price Estimates Are Misleading

**File:** `stock_provider.py`

The 50-day moving average fallback (line 92) and the MarketCap/SharesOutstanding division (lines 98–107) are displayed as "current price" with no indicator that they're estimates. Users could make financial decisions based on stale or rough approximations.

---

### 7.7 Ambiguous Date Parsing in CSV Import

**File:** `csv_importer.py` (lines 229–247)

US format (`%m/%d/%Y`) is always tried before EU format (`%d/%m/%Y`). A date like `03/04/2024` is always parsed as March 4, even if the user intended April 3. There's no disambiguation or warning.

---

### 7.8 `sys.path` Manipulation

**Files:** `portfolio_service.py` (line 13), `stock_provider.py` (line 11)

```python
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

Modifying the global import path at module load time is fragile and a code smell. Should be resolved with proper package structure or `PYTHONPATH`.

---

## 8. Frontend & Templates

### 8.1 Hardcoded Market Data on Landing Page

**File:** `templates/index.html` (lines 125–200)

S&P 500 (412.34), Bitcoin (30,450), Tesla (165.08) are static HTML. These are stale and misleading.

---

### 8.2 Hardcoded Timestamps in Chat

**File:** `templates/chat.html` (lines 43, 59, 80)

All server-rendered messages show "10:02 AM" regardless of actual creation time.

---

### 8.3 Mobile Navigation Menu Non-Functional

**File:** `templates/index.html` (line 37)

The hamburger menu icon has no click handler. Mobile users see a menu button that does nothing.

---

### 8.4 Login/Register Pages Don't Extend `base.html`

**Files:** `templates/login.html`, `templates/register.html`

These are standalone HTML documents with their own CDN includes and a different color scheme (amber accent vs. stone/green theme). Visual inconsistency with the rest of the app.

---

### 8.5 Portfolio Rows Not Keyboard-Accessible

**File:** `templates/portfolio.html` (line 115)

```html
onclick="window.location='...'"
```

Table rows use JavaScript click handlers instead of `<a>` tags. Not keyboard-navigable — users can't tab to rows or activate with Enter.

---

### 8.6 No Email Validation on Registration

**File:** `app.py` (line 186)

Only checks for non-empty string. `"not-an-email"` passes validation.

---

### 8.7 `Decimal()` Construction Without Validation

**File:** `app.py` (lines 514–517)

```python
quantity = Decimal(request.form.get('quantity', '0'))
```

If a user submits `quantity=abc`, `Decimal("abc")` raises `InvalidOperation` caught by the outer `except Exception`, producing an opaque error message.

---

### 8.8 Session Cookie Size Limit

Flask's default session stores data in a signed cookie (~4 KB max). `conversation_history` grows with every message and can exceed this, causing silent data loss. Should use server-side sessions.

---

### 8.9 Manual Flash Message Reimplementation

**File:** `app.py`

Uses `session['status_message']` / `session.pop('status_message', None)` throughout instead of Flask's built-in `flash()` / `get_flashed_messages()`. More boilerplate, no category support.

---

### 8.10 Tailwind CDN in Production

**File:** `templates/base.html` (line 7)

`cdn.tailwindcss.com` is explicitly documented by Tailwind as "not for production." It loads a large runtime compiler. Should use a build step for production CSS.

---

## 9. Testing Gaps

### 9.1 No Flask Route Tests

There are zero tests for any Flask endpoint. Authentication, research flow, portfolio CRUD, error handling, and authorization are all untested at the integration level.

### 9.2 Integration Tests Require Live API Keys

**Files:** `test_nvda_research.py`, `test_mcp.py`

These make real API calls with no mocking. They can't run in CI/CD, are non-deterministic, and incur real API costs.

### 9.3 Test Setup References Stale Dependencies

**File:** `test_setup.py` (line 65)

Checks for `gradio` package (no longer used) instead of `flask`.

### 9.4 Missing Edge Case Coverage

| Module | Missing Test |
|--------|-------------|
| `cost_basis.py` | Overselling (sell qty > held qty) |
| `cost_basis.py` | Negative prices or quantities |
| `csv_importer.py` | Robinhood format parsing (only detection tested) |
| `csv_importer.py` | CSV with BOM (byte order mark from Excel exports) |
| `csv_importer.py` | Very large files (memory/performance) |
| `portfolio_service.py` | No tests at all |
| `data_providers/` | No tests at all |
| `app.py` routes | No tests at all |
| `database.py` | No tests at all |
| `vector_search.py` | Mismatched embedding dimensions |

---

## 10. Dependencies & Configuration

### 10.1 `requirements.txt` — Missing and Stale Dependencies

```
openai>=1.0.0
openai-agents>=0.2.0
gradio>=4.0.0          # ← UNUSED — app migrated to Flask
python-dotenv>=1.0.0
requests>=2.31.0
mysql-connector-python>=8.0.0
numpy>=1.24.0
nest-asyncio>=1.6.0
weasyprint>=60.0
markdown>=3.5.1
```

| Issue | Detail |
|-------|--------|
| **Missing** | `flask` — the entire app framework |
| **Missing** | `werkzeug` — password hashing utilities |
| **Missing** | `bleach` — needed for XSS fix |
| **Missing** | `flask-wtf` — needed for CSRF fix |
| **Missing** | `pytest` — used by all test files |
| **Unused** | `gradio>=4.0.0` — ~200 MB dead dependency |
| **Unpinned** | All deps use `>=` — builds are not reproducible |
| **Undocumented** | `weasyprint` requires system libraries (Pango, Cairo, GDK-Pixbuf) |

---

### 10.2 Naive `datetime.now()` Without Timezone

**File:** `date_utils.py` (line 22)

Returns local server time with no timezone info. For a financial application where market hours (US Eastern) matter, this can mislead agents about market status.

---

### 10.3 Embedding Dimension Hardcoded

**File:** `embedding_service.py` (line 87)

```python
embeddings.append([0.0] * 1536)
```

The zero-vector fallback uses hardcoded dimension `1536`. If the model is changed to `text-embedding-3-large` (3072 dimensions), this produces dimension mismatches downstream. Should use `self.get_embedding_dimension()`.

---

### 10.4 Chunk Size Uses Characters, Not Tokens

**File:** `report_chunker.py` (lines 19–21)

```python
self.chunk_size_chars = chunk_size * 4  # Approximate: 1 token ≈ 4 characters
```

The 1:4 ratio is a rough average for English prose. Financial data with numbers, symbols, and abbreviations averages closer to 1:3, meaning chunks are larger than intended in token count.

---

### 10.5 Infinite Loop Risk in Chunker

**File:** `report_chunker.py`

If `overlap_chars >= chunk_size_chars` (e.g., `overlap=600, chunk_size=600`), the chunking loop on line 153 never advances `start` forward, causing an infinite loop. No validation of these parameters.

---

## Summary Table

| # | Issue | Severity | Category |
|---|-------|----------|----------|
| 1.1 | Stored XSS via markdown rendering | **Critical** | Security |
| 1.2 | No CSRF protection on any form | **Critical** | Security |
| 1.3 | IDOR — no authorization on portfolio mutations | **Critical** | Security |
| 1.4 | `conversation_handler_agent.py` broken import | **Critical** | Bug |
| 2.1 | Memory leak in agent_sessions | **High** | Performance |
| 2.2 | Unstable secret key on restart | **High** | Security |
| 2.3 | Duplicate `login_required` decorator | **High** | Code Quality |
| 2.4 | Internal error details leaked to users | **High** | Security |
| 2.5 | No rate limiting on auth endpoints | **High** | Security |
| 2.6 | CDN scripts without SRI | **High** | Security |
| 2.7 | No file size limit on CSV upload | **High** | Security |
| 3.1 | God-object orchestrator | **Medium** | Architecture |
| 3.2 | Agent recreated on every call | **Medium** | Performance |
| 3.3 | ThreadPoolExecutor with no timeout | **Medium** | Reliability |
| 3.4 | Clients recreated per subject | **Medium** | Performance |
| 3.5 | Two overlapping chat agents | **Medium** | Architecture |
| 3.6 | Planner can never exclude subjects | **Medium** | Design |
| 3.7 | Perplexity errors returned as strings | **Medium** | Error Handling |
| 4.1 | Duplicated retry logic | **Medium** | Code Quality |
| 4.2 | Duplicated result extraction (×5) | **Medium** | Code Quality |
| 4.3 | Inconsistent `src.` import paths | **Medium** | Code Quality |
| 4.4 | `print()` instead of `logging` | **Medium** | Code Quality |
| 4.5 | Hardcoded model/temperature | **Medium** | Configuration |
| 4.6 | Dead code and no-ops (11 instances) | **Low** | Code Quality |
| 4.7 | Bare `except: pass` (4 instances) | **Medium** | Error Handling |
| 4.8 | Ticker extraction regex unreliable | **Medium** | Bug |
| 4.9 | Trade types as magic strings | **Low** | Code Quality |
| 5.1 | 940-line DatabaseManager god class | **Medium** | Architecture |
| 5.2 | Duplicate `CREATE TABLE users` | **Low** | Code Quality |
| 5.3 | `cursor` undefined in `finally` blocks | **Medium** | Bug |
| 5.4 | Password hash in general user queries | **Medium** | Security |
| 5.5 | No MySQL connection timeouts | **Medium** | Reliability |
| 5.6 | f-string SQL with sort_order | **Low** | Security |
| 5.7 | Loop of individual INSERTs for chunks | **Low** | Performance |
| 5.8 | Thread-unsafe singleton | **Medium** | Concurrency |
| 5.9 | Precision mismatch in cost basis column | **Low** | Data Integrity |
| 5.10 | No atomicity in report storage | **Medium** | Data Integrity |
| 6.1 | API key in URL query parameters | **Medium** | Security |
| 6.2 | Hardcoded fallback tool definitions | **Low** | Maintainability |
| 6.3 | Tool name mismatch (OVERVIEW vs COMPANY_OVERVIEW) | **Medium** | Bug |
| 6.4 | Silent tool discovery failure | **Medium** | Error Handling |
| 6.5 | Blocking `time.sleep()` in retry | **Medium** | Performance |
| 6.6 | Truncation opaque to LLM | **Low** | Design |
| 7.1 | Overselling not prevented | **Medium** | Validation |
| 7.2 | No sell quantity validation | **Medium** | Validation |
| 7.3 | Race condition on holding creation | **Medium** | Concurrency |
| 7.4 | Sequential batch price fetching | **Medium** | Performance |
| 7.5 | Full CoinGecko coin list in memory | **Low** | Performance |
| 7.6 | Fallback prices shown without indicator | **Medium** | UX |
| 7.7 | Ambiguous US/EU date parsing | **Medium** | Bug |
| 7.8 | `sys.path` manipulation | **Low** | Code Quality |
| 8.1 | Hardcoded stale market data | **Low** | UX |
| 8.2 | Hardcoded chat timestamps | **Low** | UX |
| 8.3 | Mobile nav non-functional | **Low** | UX |
| 8.4 | Login/register don't extend base.html | **Low** | Consistency |
| 8.5 | Portfolio rows not keyboard-accessible | **Low** | Accessibility |
| 8.6 | No email validation | **Low** | Validation |
| 8.7 | Decimal parsing without validation | **Low** | Error Handling |
| 8.8 | Session cookie size limit | **Medium** | Reliability |
| 8.9 | Manual flash message reimplementation | **Low** | Code Quality |
| 8.10 | Tailwind CDN in production | **Low** | Performance |
| 9.1 | No Flask route tests | **Medium** | Testing |
| 9.2 | Integration tests require live API keys | **Medium** | Testing |
| 9.3 | Test setup references stale deps | **Low** | Testing |
| 9.4 | Missing edge case test coverage | **Medium** | Testing |
| 10.1 | requirements.txt incomplete/stale | **High** | Configuration |
| 10.2 | Naive datetime without timezone | **Low** | Code Quality |
| 10.3 | Embedding dimension hardcoded | **Medium** | Bug |
| 10.4 | Chunk size in chars, not tokens | **Low** | Accuracy |
| 10.5 | Infinite loop risk in chunker | **Medium** | Bug |

---

## Recommended Action Plan

### Immediate (This Week)

1. **Fix XSS** — Add `bleach` sanitization to the markdown filter. Add DOMPurify to client-side rendering. Remove `| safe` from `chat.html`.
2. **Add CSRF protection** — Install `Flask-WTF`, add tokens to every form.
3. **Add authorization checks** — Verify portfolio ownership on all mutation endpoints.
4. **Fix `requirements.txt`** — Add `flask`, `werkzeug`, `flask-wtf`, `bleach`, `pytest`. Remove `gradio`.
5. **Delete or fix `conversation_handler_agent.py`** — broken import makes the entire module non-functional.
6. **Delete duplicate `login_required`** in `app.py`.

### This Sprint

7. **Add TTL eviction to `agent_sessions`** — prevent memory leak.
8. **Fail on missing `FLASK_SECRET_KEY`** — remove the silent random fallback.
9. **Add `MAX_CONTENT_LENGTH`** to Flask config.
10. **Add rate limiting** on `/login` and `/register`.
11. **Standardize imports** — pick bare imports, remove all `from src.` prefixes.
12. **Extract shared agent utilities** — retry logic, result extraction, model config.
13. **Add per-future timeouts** to `research_orchestrator.py`.

### Next Sprint

14. **Replace `print()` with structured `logging`** throughout.
15. **Inject MCP/Perplexity clients** into specialized agents instead of recreating per subject.
16. **Add connection timeouts** to MySQL config.
17. **Wrap report storage in a transaction** for atomicity.
18. **Add basic Flask route tests** with mocked API clients.
19. **Remove dead code** — unused CSS, deprecated functions, no-op string operations.
20. **Validate chunk parameters** — guard against infinite loop when overlap >= chunk_size.

### Backlog

21. Refactor `DatabaseManager` into domain repositories with a connection context manager.
22. Migrate vector storage from JSON-in-MySQL to a proper vector database.
23. Replace Tailwind CDN with a production build step.
24. Add server-side sessions (Redis/DB) to avoid cookie size limits.
25. Create a `TradeType` enum and eliminate magic strings.
26. Add proper package structure to eliminate `sys.path` manipulation.
