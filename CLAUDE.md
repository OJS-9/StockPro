# StockPro

An AI-powered multi-agent stock research platform that orchestrates specialized research agents, integrates financial data APIs with real-time web research, and provides an interactive chat interface for exploring investment opportunities. Includes a portfolio tracker for equities and crypto.

---

## Working instructions
- after every change that adds / change something about the app, from a feature to a new window - update the CLAUDE,md in order to keep knowledge updated.
- follow the design system rules and color scheme as detailed
- Keep things simp;e - NEVER over-engineer it, always simplify, no unnecessery defensive progarmming of extra features.
- be concise, keep README short and simple - DO NOT USE EMOGIJES NOT MATTER WHAT.

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Flask (Python 3.10+) |
| AI / LLM | Google GenAI SDK (`google-genai`), Gemini 3.1 Pro / 3 Flash |
| Embeddings | Gemini `gemini-embedding-001` (3072d) |
| Financial data | Alpha Vantage MCP (HTTP, JSON-RPC) |
| Web research | Nimble SDK API (web search, extraction, Perplexity agent) |
| Crypto prices | CoinGecko API |
| Database | MySQL (connection pool, pool_size=5) |
| Vector search | NumPy cosine similarity (brute-force) |
| Frontend | Jinja2 templates, Tailwind CSS (CDN), Marked.js |
| Async compat | `nest_asyncio` for Flask |

## Project Structure

```
src/
├── __init__.py
├── orchestrator_graph.py          # LangGraph orchestrator session (replaces StockResearchAgent/agent.py)
├── agents/
│   ├── __init__.py
│   ├── planner_node.py            # Research planning node
│   ├── specialized_node.py        # Per-subject research nodes
│   ├── synthesis_node.py          # Report synthesis node
│   └── chat_agent.py              # RAG-lite Q&A on generated reports
├── research_graph.py              # LangGraph StateGraph for full pipeline
├── research_subjects.py           # 12 subject definitions with trade-type eligibility
├── research_plan.py               # ResearchPlan dataclass
├── research_prompt.py             # System prompts and templates
├── langsmith_service.py           # LangSmith StepEmitter + SSE integration
├── mcp_client.py                  # Alpha Vantage MCP HTTP client (JSON-RPC)
├── mcp_manager.py                 # MCP server configuration
├── mcp_tools.py                   # MCP tool execution wrapper
├── nimble_client.py               # Nimble SDK API client (web search, extraction, Perplexity agent)
├── report_storage.py              # Storage pipeline orchestrator
├── report_chunker.py              # Semantic text chunking (600-token, 100-overlap)
├── embedding_service.py           # OpenAI embeddings client
├── vector_search.py               # Cosine similarity search over stored chunks
├── database.py                    # MySQL operations & schema (~940 lines)
├── date_utils.py                  # Datetime context utilities
├── app.py                         # Flask routes, session management, auth (now uses OrchestratorSession)
├── portfolio/
│   ├── __init__.py
│   ├── portfolio_service.py       # Portfolio business logic
│   ├── cost_basis.py              # Simple average cost calculator
│   └── csv_importer.py            # Multi-format CSV parser (Coinbase, Robinhood, generic)
└── data_providers/
    ├── __init__.py
    ├── base_provider.py           # Abstract provider with caching
    ├── stock_provider.py          # Nimble-first stock prices (MarketWatch) + Alpha Vantage fallback
    ├── crypto_provider.py         # CoinGecko crypto prices
    └── provider_factory.py        # Auto-detect stock vs crypto

templates/
├── base.html                      # Shared layout (Tailwind, dark stone theme)
├── index.html                     # Landing page with hero search
├── chat.html                      # AI research chat interface (markdown via Marked.js)
├── portfolio_list.html            # Portfolio list page (overall recap, per-card summary, empty state + create modal)
├── portfolio.html                 # Portfolio detail dashboard (single portfolio view)
├── holding_detail.html            # Per-holding detail + transactions
├── add_transaction.html           # Manual transaction form
├── import_csv.html                # CSV import with drag-and-drop
├── login.html                     # Login form (standalone, not extending base.html)
└── register.html                  # Registration form (standalone)

static/css/
└── style.css                      # Unused (templates use Tailwind CDN)
```

## Architecture

### Research UX Flow (Popup Q&A)

Ticker submit on home page → popup modal (questions fetched via single Gemini call at `POST /popup_start`) → user answers all questions at once → popup closes → "Generating report..." toast → background generation thread (`POST /start_generation`) → polling via `GET /api/report_status/<session_id>` every 3s → "Report Ready" toast → click → `/report/<report_id>`.

Module-level `_generation_status` dict in `app.py` tracks per-session state (`in_progress` / `ready` / `error`).

### Research Pipeline

```
User Request (popup answers submitted)
    │
    ▼
Background Thread (app.py start_generation)
    │  ── calls agent.generate_report(context=Q&A string)
    │
    ▼
PlannerAgent
    │  ── single LLM call (no tools), structured JSON response
    │  ── selects & prioritizes research subjects
    │  ── outputs ResearchPlan dataclass
    │  ── fallback to full eligible subject list on parse failure
    │
    ▼
ResearchOrchestrator
    │  ── ThreadPoolExecutor (3 workers, configurable via RESEARCH_MAX_WORKERS)
    │  ── each worker calls gemini_runner.run_agent() synchronously
    │
    ├──▶ SpecializedAgent: subject A ──┐
    ├──▶ SpecializedAgent: subject B ──┤
    └──▶ SpecializedAgent: subject C ──┤
         ...                           │
    ◄──────────────────────────────────┘
    │  research_outputs: {subject_id → text}
    │  (individual agent failures isolated — partial results pass through)
    │
    ▼
SynthesisAgent
    │  ── receives ResearchPlan + all research outputs
    │  ── builds report sections dynamically per plan
    │  ── max 8,000 output tokens
    │  ── before specialization, a per-run USD spend budget may reduce
    │     `effective_max_turns` / `effective_max_output_tokens` to keep
    │     estimated cost within budget (best-effort preflight)
    │
    ▼
ReportStorage Pipeline
    │  ── ReportChunker → EmbeddingService → DatabaseManager
    │  ── 600-token chunks, 100-token overlap, section-aware splitting
    │  ── text-embedding-004 (768d), stored as JSON in MySQL
    │
    ▼
ReportChatAgent (RAG-lite follow-up Q&A)
    ── VectorSearch (cosine similarity over stored chunks)
    ── injects top-k chunks into LLM prompt
```

### Agent Inventory

| Component | File | Model | Role | Tools / Integration | Output Tokens |
|---|---|---|---|---|---|
| OrchestratorSession | `orchestrator_graph.py` | gemini-2.5-flash (via LangChain) | Orchestrate conversation, ask clarifying questions, trigger research graph | Calls `run_research` tool in `research_graph.py` | ~600 per turn (configured) |
| Planner node | `agents/planner_node.py` | gemini-3-flash-preview | Select & prioritize research subjects | None (JSON-like state updates) | ~1,200 |
| Specialized node | `agents/specialized_node.py` | gemini-3.1-pro-preview | Deep-dive one subject | 6 MCP + Perplexity tools | ~1,500 |
| Synthesis node | `agents/synthesis_node.py` | gemini-3.1-pro-preview | Merge outputs into cohesive report | None (synthesis) | ~8,000 |
| ReportChatAgent | `agents/chat_agent.py` | gemini-3-flash-preview | RAG Q&A on stored report chunks | Vector search over `report_chunks` | — |

### Research Subjects (12 total)

| # | Subject | ID | Day Trade | Swing Trade | Investment |
|---|---|---|---|---|---|
| 1 | Company Overview | `company_overview` | yes | yes | yes |
| 2 | News & Catalysts | `news_catalysts` | yes | yes | yes |
| 3 | Technical / Price Action | `technical_price_action` | yes | yes | — |
| 4 | Earnings & Financials | `earnings_financials` | — | yes | yes |
| 5 | Sector & Macro Context | `sector_macro` | yes | yes | — |
| 6 | Revenue Breakdown | `revenue_breakdown` | — | yes | yes |
| 7 | Growth Drivers | `growth_drivers` | — | yes | yes |
| 8 | Valuation & Peers | `valuation` | — | — | yes |
| 9 | Margin Structure | `margin_structure` | — | yes | yes |
| 10 | Competitive Position | `competitive_position` | — | — | yes |
| 11 | Risk Factors | `risk_factors` | — | yes | yes |
| 12 | Management Quality | `management_quality` | — | — | yes |

Each subject carries a priority per trade type (1=high, 2=medium, 3=low). The PlannerAgent selects a subset and reorders based on user context. Subject eligibility count: Day Trade=5, Swing Trade=10, Investment=10.

### Data Sources

**Alpha Vantage MCP (6 tools via JSON-RPC)**

| Tool | Data |
|---|---|
| `OVERVIEW` | Company profile, sector, market cap, ratios |
| `INCOME_STATEMENT` | Revenue, expenses, net income (annual + quarterly) |
| `BALANCE_SHEET` | Assets, liabilities, equity |
| `CASH_FLOW` | Operating, investing, financing cash flows |
| `EARNINGS` | EPS actuals vs. estimates |
| `NEWS_SENTIMENT` | News articles with sentiment scores |

Tool outputs are truncated (max 5 series items, max 5 news items) before passing to agents.

**Nimble SDK API** — web search (`POST /v1/search`), URL extraction (`POST /v1/extract`), and Perplexity synthesis (`POST /v1/agents/run` with `agent="perplexity"`). Exposed to specialized agents as `nimble_web_search`, `nimble_extract`, and `perplexity_research` tools. Requires `NIMBLE_API_KEY` env var.
`NimbleClient.run_agent()` also normalizes Nimble’s inconsistent `data.parsing` shapes (list vs dict) into a consistent list for app consumption.

**CoinGecko API** — crypto prices for portfolio module, 50+ symbol-to-ID mappings, batch price fetching.

### Database Schema (7 MySQL tables)

**Research domain:** `reports` (metadata + full text), `report_chunks` (chunks + embeddings as JSON)

**Portfolio domain:** `users` (auth: username, email, password_hash nullable, google_id for OAuth), `portfolios` (per-user), `holdings` (aggregated positions), `transactions` (buy/sell records), `csv_imports` (audit log)

Relationships: `users 1→N portfolios 1→N holdings 1→N transactions`, `reports 1→N report_chunks`. All child tables use CASCADE deletes.

## Commands

```bash
# Run the Flask app
python src/app.py

# Initialize database
python init_db.py

# Recreate database schema (creates DB if missing)
python recreate_schema.py

# Run all tests
python -m pytest test_*.py

# Run specific test suites
python -m pytest test_cost_basis.py
python -m pytest test_csv_importer.py
python -m pytest test_mcp.py
python -m pytest test_nvda_research.py
```

## Environment Variables

Required in `.env`:
```
GEMINI_API_KEY=
ALPHA_VANTAGE_API_KEY=
MYSQL_HOST=localhost
MYSQL_USER=
MYSQL_PASSWORD=
MYSQL_DATABASE=stock_research
FLASK_SECRET_KEY=           # REQUIRED in production — random key per restart if unset
```

Optional:
```
RESEARCH_MAX_WORKERS=3      # ThreadPoolExecutor concurrency
PLANNER_MAX_SUBJECTS=8     # Max subjects shown to PlannerAgent
GOOGLE_CLIENT_ID=          # Google OAuth (Authlib). Redirect URI: .../login/google/callback
GOOGLE_CLIENT_SECRET=      # From Google Cloud Console OAuth 2.0 credentials
NIMBLE_API_KEY=            # Nimble web search + extraction. Get from app.nimbleway.com
NIMBLE_TIMEOUT_SECONDS=30  # Request timeout for Nimble API calls (default 30)

# Per-run USD spend budget (best-effort preflight; requires USD/token rates)
RESEARCH_SPEND_BUDGET_USD_DEFAULT=         # Default estimated USD budget for a single research run
GEMINI_INPUT_USD_PER_1K_TOKENS=           # USD per 1K input tokens (used for budget estimation)
GEMINI_OUTPUT_USD_PER_1K_TOKENS=          # USD per 1K output tokens (used for budget estimation)
RESEARCH_SPEND_BUDGET_USD_MIN_MAX_TURNS=2
RESEARCH_SPEND_BUDGET_USD_MIN_MAX_OUTPUT_TOKENS=512
USER_BUDGET_USD_OVERRIDES_JSON=          # Optional JSON: {"user_id_string":"budget_usd", ...}
```

## Auth

Clerk-based auth with Flask session sync. Routes: `/sign-in`, `/sign-up`, `/sign-out`, `/auth/sso-callback`. The SSO callback route is required for "Continue with Google": after OAuth, Clerk redirects to `/auth/sso-callback`, where ClerkJS runs `handleRedirectCallback()` to set the `__session` cookie on the app origin, then the user is redirected to `/` (or `next`). Add the callback URL to Clerk Dashboard allowed redirect URLs if needed (e.g. `http://localhost:5000/auth/sso-callback`, `https://<domain>/auth/sso-callback`).

## MCP Configuration

Copy `mcp.json.example` to `mcp.json` and configure the Alpha Vantage MCP server endpoint and API key.

## Design System

### Color Palette (Tailwind custom config in `base.html`)

| Token | Hex | Tailwind Equivalent | Usage |
|---|---|---|---|
| `primary` | `#d6d3d1` | stone-300 | Brand color, logo tint, CTA buttons, links, active tab pills |
| `background-light` | `#fafaf9` | stone-50 | Light mode page background |
| `background-dark` | `#0c0a09` | stone-950 | Dark mode page background, code block backgrounds |
| `surface-dark` | `#1c1917` | stone-900 | Cards, chat bubbles, input fields, table headers |
| `border-dark` | `#292524` | stone-800 | Card borders, dividers, markdown `hr` / `th` / `td` borders |
| `accent-up` | `#22c55e` | green-500 | Positive P&L, bullish indicators, inline code text, chart uptrends |
| `accent-down` | `#ef4444` | red-500 | Negative P&L, bearish indicators, chart downtrends, error states |

Additional colors used directly via Tailwind utilities:
- `stone-400` / `stone-500` — secondary text, timestamps, muted labels
- `orange-500` — Bitcoin/crypto icon accent on landing page
- `blue-500/10` — finance article card gradient on landing page
- `red-900/40`, `red-700` — error banners (login/register)
- `green-400` — hover state for portfolio "Add Transaction" button

### Typography

| Role | Font Family | Weight Range | Where |
|---|---|---|---|
| Display (headings, brand) | **Nunito** | 400–800 | `font-display` class — page titles, card headings, hero text, prices |
| Body (UI text) | **Inter** | 400–700 | `font-body` class — paragraphs, labels, nav links, descriptions |
| Loaded but secondary | Manrope, Noto Sans | — | Referenced in CDN link; Manrope may be used in older templates |

**Login/Register pages use a different type stack** (standalone, not extending `base.html`):
- Display: **Space Grotesk** (700)
- Body: **Inter** (400–600)

### Border Radius

| Token | Value | Typical usage |
|---|---|---|
| Default | `1rem` (16px) | Inputs, small cards, badges |
| `rounded-2xl` | 1rem | Chat bubbles, search bar, form containers |
| `rounded-3xl` | 1.5rem | Landing page market cards, news article cards |
| `rounded-xl` | 0.75rem | Portfolio summary cards, icon containers |
| `rounded-lg` | 0.5rem | Buttons, badges, tag pills |
| `rounded-full` | 9999px | Avatar circles, pill buttons (Sign Up, Log Out) |

### Component Patterns

**Cards** — `bg-surface-dark rounded-3xl p-6 border border-border-dark` with subtle hover effects (`hover:border-accent-up/50`, `hover:shadow-2xl`, `hover:-translate-y-1`). Landing page cards include a decorative blurred circle (`bg-accent-up/5 rounded-full blur-3xl`) and a bottom SVG sparkline.

**Buttons** — Primary: `bg-primary text-background-dark font-bold rounded-xl` with `hover:brightness-110`. Secondary: `bg-surface-dark border border-border-dark text-white`. Pill style: `rounded-full h-10 px-4`.

**Chat bubbles** — Both user and AI: `bg-surface-dark rounded-2xl px-4 py-3 max-w-3xl`. User avatar: `bg-primary/20 rounded-full`. AI avatar: `bg-surface-dark rounded-full` with `smart_toy` icon.

**Header/Nav** — Sticky, backdrop blur (`bg-background-dark/95 backdrop-blur-md`), bottom border `border-b-border-dark`. Nav links use `hover:text-primary` transition. On viewports below `md`, a hamburger button opens a slide-out drawer (right) with the same links and auth; close via overlay click, close button, Escape, or link click.

**Hero search bar** — `bg-surface-dark/90 backdrop-blur-md border border-border-dark rounded-2xl` with `focus-within:ring-2 ring-primary/50`.

### Inconsistencies to Resolve

- **Login/Register pages** are standalone HTML (not extending `base.html`) with an `amber-400` accent (`#fbbf24`) instead of the `primary` stone-300 used everywhere else. Font is Space Grotesk instead of Nunito. This creates a visual break in the user flow.
- **`static/css/style.css`** contains an unused purple-themed stylesheet — the app exclusively uses Tailwind via CDN.
- **Icons**: Material Symbols Outlined loaded from Google Fonts CDN. Used for all UI icons (`search`, `arrow_forward`, `smart_toy`, `person`, `menu`, `add`, `trending_up`, etc.).

## Development Guidelines

### General Guidelines
- keep everything simple, do not over-engineer things
- in case there's new feature / major behaviral change of the app - update CLAUDE.md 
- if you see something in the code while reviewing files that can be better - suggest at in your final response.


### Agent Patterns
- All agents use the **OpenAI Agents SDK** (`openai-agents`) — use `Runner.run()` with turn limits
- Each agent has a single, focused responsibility
- Async compatibility in Flask via `nest_asyncio`
- Retry logic exists in `agent.py` and `specialized_agent.py` but is duplicated — extract to shared module
- `conversation_handler_agent.py` overlaps with `report_chat_agent.py` — consolidate

### MCP Tool Usage
- Access tools via `mcp_tools.py` wrapper, documented in `TOOL_SELECTION.md`
- MCP client uses JSON-RPC over HTTP with fallback to hardcoded tool list
- Handle API rate limits gracefully (Alpha Vantage free tier: 5 calls/min)

### Database Operations
- All MySQL access through `database.py` (`DatabaseManager`)
- Reports stored with metadata and chunk-based organization
- Embeddings stored as JSON text — parsed on every search (scaling concern beyond ~100 reports)
- No transaction wrapping for report + chunk + embedding saves (atomicity gap)

### Trade Types
Research depth scales with trade horizon:
- **Day Trade**: 5 subjects — price action, news, sector context
- **Swing Trade**: 10 subjects — adds earnings, revenue, margins, risks
- **Investment**: 10 subjects — full deep-dive including valuation, moat, management

### Portfolio Module
- `PortfolioService` encapsulates all portfolio operations
- Users can create multiple named portfolios; `GET /portfolio` shows the list (with overall recap: combined value, P&L and %, total holdings; each card shows that portfolio’s value, P&L %, and holdings count), `GET /portfolio/<id>` shows a detail view
- All portfolio sub-routes are scoped to portfolio_id: `/portfolio/<id>/add`, `/portfolio/<id>/import`, `/portfolio/<id>/holding/<symbol>`, `/portfolio/<id>/transaction/<txn_id>/delete`
- Cost basis: simple average method, applied chronologically
- Asset type auto-detected from symbol (BTC, ETH, etc. → crypto)
- Price providers: `StockDataProvider` (Nimble MarketWatch agent first, Alpha Vantage fallback) / `CryptoDataProvider` (CoinGecko) via factory
- Database tables: `portfolios`, `holdings`, `transactions`, `csv_imports`

### Known Code Quality Issues
- `print()` used everywhere instead of `logging` module
- Model `"gpt-4o"` and `temperature=0.7` hardcoded across all agent files
- Inconsistent import paths (`src.` prefix vs. bare imports)
- Bare `except: pass` in `app.py` and `date_utils.py`
- Dead code: no-op string replace in `mcp_tools.py`, unused inspect call in `agent_tools.py`, unused `style.css`
- `requirements.txt` is incomplete (missing `flask`) and has unused deps (`gradio`)

## Testing

| Test file | Scope |
|---|---|
| `test_cost_basis.py` | 15+ cases — averaging, partial sells, fees, crypto decimals |
| `test_csv_importer.py` | 20+ cases — format detection, parsing, error handling |
| `test_mcp.py` | MCP connection, tool discovery, execution (requires live API key) |
| `test_nvda_research.py` | End-to-end research pipeline (requires live API keys) |
| `test_setup.py` | Environment validation (Python version, deps, config files) |

**Testing gaps:** No Flask route tests, no mocked API tests (CI-unfriendly), no edge cases for overselling in cost_basis or concurrent agent sessions.

## Key Documentation

| File | Purpose |
|---|---|
| `OVERVIEW.md` | Full product and architecture reference |
| `DEPLOYMENT.md` | Deployment steps, env vars, Google OAuth redirect URIs (local and production) |
| `CODE_REVIEW.md` | 33-issue code review with severity and recommendations |
| `AGENTS.md` | Cursor rules for AI-assisted development |
| `TOOL_SELECTION.md` | Alpha Vantage MCP tool documentation |
| `PERPLEXITY_UPGRADE_PLAN.md` | Perplexity integration roadmap |
| `PORTFOLIO_IMPLEMENTATION_PLAN.md` | Portfolio feature design |


## Latest Code Review Findings (Priority)

A comprehensive code review was completed on 2026-02-27 (`CODE_REVIEW.md`). The codebase is architecturally sound but has **critical security vulnerabilities** and significant code quality issues that must be resolved before any feature work.

**Immediate (blocking):**
1. Fix XSS in `chat.html` — add DOMPurify, remove `| safe` on unsanitized markdown
2. Add CSRF protection to all forms (Flask-WTF or manual tokens)
3. Add ownership verification on all portfolio mutation endpoints (transaction delete has no auth check)
4. Fix `requirements.txt` — add `flask`, `flask-wtf`, `pytest`, `bcrypt`; remove unused `gradio`; pin versions

**High priority:**
5. Add TTL eviction to `agent_sessions` dict in `app.py` (memory leak — sessions never expire)
6. Add SRI attributes to all CDN `<script>`/`<link>` tags in `base.html`
7. Fail loudly if `FLASK_SECRET_KEY` is not set (current fallback generates a random key per restart)

**Architecture debt (next sprint):**
8. Extract shared retry logic from `agent.py` and `specialized_agent.py` into `agent_utils.py`
9. Merge `report_chat_agent.py` and `conversation_handler_agent.py` into a single agent
10. Replace `print()` with `logging` module across all files
11. Centralize model/temperature config instead of hardcoding `"gpt-4o"` / `0.7` in every agent
12. Refactor `DatabaseManager` (~940 lines) into domain-specific repositories

See `CODE_REVIEW.md` for the full 33-issue list with severity ratings and recommendations.
