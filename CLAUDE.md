# StockPro

AI-powered multi-agent stock research platform with portfolio tracking, watchlists, price alerts, and a Telegram bot. Built for retail investors who want institutional-grade research on any ticker.

## NEVER / ALWAYS / CRITICAL

**CRITICAL: Read before every session.** These are hard-won rules from real bugs.

- NEVER use MySQL or reference MySQL anywhere -- the database is **PostgreSQL** (Supabase). The codebase was migrated; stale MySQL references are bugs.
- NEVER query `WHERE email = ?` directly -- email is AES-encrypted. Use `get_user_by_email()` which matches on `email_hash` (HMAC-SHA256).
- NEVER log or print decrypted sensitive values. Use `encrypt()`/`decrypt()` from `src/encryption.py` for any new personal data column.
- NEVER add a Supabase table without RLS. Patterns in `docs/SUPABASE.md`. Scope via `auth.jwt()->>'sub'`.
- NEVER use OpenAI Agents SDK -- this project uses **LangGraph + LangChain**. Old docs/comments referencing OpenAI agents are stale.
- NEVER add emojis to code, docs, commit messages, or UI copy.
- ALWAYS update this file after adding a feature, new page, or changing architecture.
- ALWAYS keep design tokens in sync between `templates/base.html` and `stockpro-web/src/index.css`.
- ALWAYS match the mockups in `stockpro-web/mockups/` for visual decisions -- they are the design source of truth.
- CRITICAL: `database.py` uses `psycopg2` + `ThreadedConnectionPool`. Never import `mysql` or `sqlalchemy`.
- CRITICAL: Agent tools are registered in `langchain_tools.py`. yfinance is primary for fundamentals. MCP is only used for `NEWS_SENTIMENT`. Don't re-add other MCP tools to agents without a reason.

## Maintenance

Keep under ~250 lines. Add: new gotchas, architecture shifts, new subsystems. Push detail to `docs/`. Don't dump API docs, SQL examples, or route listings.

## Tech Stack

- **Backend**: Flask (Python 3.10+), Flask-CORS, Flask-Limiter, Flask-WTF, flask-sock
- **AI/LLM**: LangGraph + LangChain, `langchain-google-genai` (ChatGoogleGenerativeAI)
- **Embeddings**: `gemini-embedding-001` (3072-D) via google-genai SDK
- **Database**: PostgreSQL via psycopg2 (Supabase-hosted, ThreadedConnectionPool)
- **Auth**: Clerk (backend: `clerk-backend-api`, frontend: ClerkJS / `@clerk/clerk-react`)
- **Data**: yfinance (primary), Alpha Vantage MCP, Nimble SDK, CoinGecko
- **Frontend**: React 19 + Vite + TypeScript + Tailwind v4 + React Router 7 + React Query (SPA in `stockpro-web/`)
- **Legacy**: `templates/` Jinja2 files exist but are no longer the live UI — do not add features there
- **Other**: WeasyPrint (PDF), python-telegram-bot, nest_asyncio, LangSmith tracing

## Project Layout

```
src/
  app.py                    # Flask routes, Clerk auth, CSRF, CORS, rate limiting
  orchestrator_graph.py     # LangGraph ReAct orchestrator (create_react_agent)
  research_graph.py         # StateGraph: planner -> fan-out -> quality gate -> synthesis -> storage
  database.py               # PostgreSQL ops, schema, connection pool
  encryption.py             # AES-256-GCM field encryption + HMAC lookups
  langchain_tools.py        # StructuredTools: yfinance + MCP + Nimble
  agents/                   # planner_node, specialized_node, synthesis_node, chat_agent
  portfolio/                # portfolio_service, cost_basis, csv_importer, history_service
  data_providers/           # stock_provider, crypto_provider, provider_factory
  watchlist/                # watchlist_service, price_refresh, news_recap, earnings_calendar
  alerts/                   # price alert evaluation + Telegram notify
  realtime/                 # WebSocket price snapshots
  brokerage/                # Alpaca paper trading (Phase 2)

stockpro-web/               # React SPA -- Phase 2 frontend rewrite
  src/main.tsx              # ClerkProvider, QueryClient, BrowserRouter, Toaster
  src/App.tsx               # Route table (all placeholders for now)
  src/index.css             # Tailwind v4 @theme design tokens
  src/api/client.ts         # useApiClient() -- authenticated fetch with Clerk Bearer
  mockups/                  # 14 HTML mockups: visual spec for every screen

templates/                  # Legacy Jinja2 (dead UI, do not extend)
scripts/                    # DB init, migrations, telegram bot, CI smoke tests
tests/                      # 40 pytest files
```

## Coding Conventions

- **Keep it simple** -- no unnecessary abstractions, no defensive programming "just in case"
- **One responsibility per module** -- each agent, service, and provider does one thing
- **Error isolation in agents** -- individual specialized agent failures must not crash the pipeline. Partial results pass through.
- **Price provider fallback chain** -- Nimble agent -> Alpha Vantage -> yfinance (stocks) or CoinGecko (crypto). Don't skip levels.
- **Encryption pattern** -- `encrypt()` on write, `decrypt()` on read, `_hash` sibling for searchable fields
- **Flask routes** -- use `@login_required` decorator (Clerk JWT), CSRF via Flask-WTF on form POSTs
- **React SPA** -- `useApiClient()` for all API calls (auto-attaches Clerk Bearer token)
- **Tests** -- `pytest.ini` sets `testpaths = tests`, `pythonpath = src`. Run: `python -m pytest`

## Architecture

### Research Pipeline

`planner_node` -> parallel `specialized_node` (LangGraph `Send()`) -> `quality_gate_node` -> `synthesis_node` -> `storage_node`

- **Planner**: single LLM call, picks/prioritizes from 12 subjects (see `research_subjects.py`)
- **Specialized**: ReAct agent per subject with yfinance + MCP + Nimble tools
- **Quality gate**: min output length, >50% failure aborts
- **Synthesis**: merges outputs, position-aware framing, max 8000 tokens, truncation retry
- **Storage**: chunks (600-token, 100-overlap) -> embeddings -> PostgreSQL

### Agent Models

| Agent | Default model | Env override |
|---|---|---|
| Orchestrator | gemini-2.5-flash | `ORCHESTRATOR_MODEL` |
| Planner | gemini-2.5-flash | `PLANNER_MODEL` |
| Specialized | gemini-2.5-pro | `SPECIALIZED_AGENT_MODEL` |
| Synthesis | gemini-2.5-pro | `SYNTHESIS_AGENT_MODEL` |
| Report chat (RAG) | gemini-2.5-flash | `CHAT_AGENT_MODEL` |

### Key Subsystems

- **Portfolio**: multiple per user, simple average cost basis, auto-detect stock vs crypto
- **Watchlist**: lists/sections/items/pins, 15-min background price refresh, news recap
- **Alerts**: evaluate on price_cache upsert, cooldown prevents spam, in-app toast/dropdown (Telegram bot currently OFF)
- **Social sentiment**: Reddit + X community signals shown on TickerPage Public View (live, lead feature)
- **Report chat**: two-phase RAG (report chunks first, research chunks if score low)
- **News**: Nimble agent-based briefing, in-memory TTL cache

## React SPA (stockpro-web/)

- **State**: live production UI. ~32 routes implemented (Landing, Home, PortfolioDetail, Watchlist, TickerPage with Reddit+X sentiment, Chat, Alerts, Analytics, Settings, etc.)
- **Dev**: `npm run dev` on port 3000, proxies `/api`, `/stream`, `/ws` to Flask :5000
- **Mockups**: 14 HTML files in `mockups/` -- the design source of truth for every screen
- **Design tokens**: `primary` (#d6d3d1), `background-dark` (#0c0a09), `surface-dark` (#1c1917), `border-dark` (#292524), `accent-up` (#22c55e), `accent-down` (#ef4444)
- **Fonts**: Nunito (display), Inter (body). Icons: Material Symbols Outlined.
- **Patterns**: dark cards with border-dark, sticky blurred nav, pill buttons, rounded-2xl bubbles

### Build & deploy: dist/ is tracked in git

CRITICAL: `stockpro-web/dist/` is **committed to the repo**. Railway serves it directly -- no Node/CI build at deploy time. `vite-prerender-plugin` runs at build time to produce a prerendered `dist/index.html` (~33KB) so AI crawlers (GPTBot, PerplexityBot, ClaudeBot) see real content instead of an empty `<div id="root"></div>`. The plugin is pure Node (uses `react-dom/server` `renderToString` via dynamic `import()` of the bundled prerender entry -- no Puppeteer/Chromium). We build locally because Railway/CI runners don't need the prerendered output.

**Known issue (see #95):** the prerender step currently hangs after the bundle phase. Workaround: `npm run build:fast` (sets `SKIP_PRERENDER=1`) skips prerender and finishes in ~300ms. While unfixed, AI crawlers lose the prerendered Landing/About/Press HTML.

**After any change to `stockpro-web/src/**` or `index.html`:**
```bash
cd stockpro-web && npm run build       # full build with prerender (currently broken, see #95)
cd stockpro-web && npm run build:fast  # bundle only, SEO degraded
git add stockpro-web/dist && git commit -m "..."
```
Forgetting this ships code where humans see new copy but bots see the old prerendered HTML. The Landing page FAQ Q&A and the FAQPage JSON-LD in `index.html` must stay in sync (both consumed by AI engines).

## Database

- PostgreSQL via Supabase. Schema defined in `database.py` (`init_schema`).
- **Tables**: users, reports, report_chunks, portfolios, holdings, transactions, csv_imports, watchlists, price_cache, alerts, notifications, ticker_notes, telegram_connect_tokens
- **Identity**: `users.user_id` = Clerk user ID. RLS via `auth.jwt()->>'sub'`.
- **Encrypted fields**: `users.email`, `users.telegram_chat_id`. Lookups via `email_hash`.

## Auth

- Clerk-based. Routes: `/sign-in`, `/sign-up`, `/sign-out`, `/auth/sso-callback`
- SSO callback required for Google OAuth -- add redirect URL in Clerk Dashboard
- Backend verifies JWTs via `clerk-backend-api`

## Commands

```bash
python src/app.py                    # Flask app
cd stockpro-web && npm run dev       # React dev (port 3000)
python scripts/recreate_schema.py    # Recreate DB schema
python -m pytest                     # Run all tests
# Telegram bot is currently OFF — do not start unless explicitly re-enabling
```

## Env Vars

**Required** (`.env`):
- `DATABASE_URL` -- Supabase PostgreSQL connection string
- `CLERK_SECRET_KEY`, `CLERK_PUBLISHABLE_KEY`, `CLERK_JWT_KEY`
- `GEMINI_API_KEY`
- `FLASK_SECRET_KEY`
- `ENCRYPTION_KEY` -- 64-char hex (`python -c "import secrets; print(secrets.token_hex(32))"`)

**Optional** -- see `.env.example` for full list: `PORT`, `FLASK_HOST`, rate limits (`STOCKPRO_RATE_LIMIT_*`), research tuning (`RESEARCH_MAX_WORKERS`, model overrides, spend budget), integrations (`ALPHA_VANTAGE_API_KEY`, `NIMBLE_API_KEY`, `TELEGRAM_BOT_TOKEN`, `LANGSMITH_API_KEY`), Phase 2 (`APCA_API_*`, `CONVERTKIT_*`).

## Docs (progressive disclosure)

- `docs/OVERVIEW.md` -- full product/architecture reference
- `docs/DEPLOYMENT.md` -- deployment, env vars, OAuth redirect URIs
- `docs/SUPABASE.md` -- RLS patterns, SQL examples, Supabase config
- `docs/TOOL_SELECTION.md` -- Alpha Vantage MCP tool docs
- `docs/AGENTS.md` -- Cursor rules for AI dev
- `docs/plans/` -- dated implementation plans

## Testing

40 files under `tests/` (pytest). Covers: Flask routes, Clerk auth, CSRF, research pipeline, budget, portfolio math, CSV import, watchlist, alerts, pricing/WebSocket, Telegram, MCP, utilities. Config in `pytest.ini`.
