# StockPro -- Product Overview

StockPro is an AI-powered multi-agent stock research platform for retail investors. It orchestrates specialized research agents, integrates financial data APIs with real-time web research, and provides an interactive chat interface for exploring investment opportunities. Includes portfolio tracking (equities + crypto), watchlists with price alerts, a Telegram bot, and a report library with PDF export.

---

## Product Features

### AI-Driven Stock Research
- User enters a ticker and trade type on the home page
- Orchestrator agent asks 1-2 clarifying questions via popup modal
- User optionally selects/deselects research subjects, then answers questions
- Background pipeline: planner selects subjects, parallel specialized agents run deep research, synthesis agent produces a structured report
- Report stored with vector embeddings for follow-up RAG chat
- Research progress shown via inline nav indicator with polling

### Trade Type Framing

| Trade Type | Focus | Eligible Subjects |
|---|---|---|
| Day Trade | Intraday catalysts, price action, momentum | 5 |
| Swing Trade | Near-term thesis (1-14 days), earnings | 10 |
| Investment | Full fundamental deep-dive, moat, valuation | 10 |

### RAG-Powered Report Chat
- Reports chunked into ~600-token semantic segments
- Embedded via `gemini-embedding-001` (3072-D)
- Two-phase retrieval: report chunks first, research chunks if score low
- Top-k chunks injected as context for Q&A

### Report Library
- Filterable by ticker, trade type, sort order
- Full markdown rendering (tables, code blocks, lists)
- PDF export via WeasyPrint
- Resume chat on any past report

### Portfolio Tracker
- Multiple named portfolios per user
- Manual transaction entry (buy/sell with quantity, price, fees, notes)
- CSV import (auto-detects Coinbase, Robinhood, generic formats)
- Dashboard with summary cards (total value, cost basis, P&L, allocation)
- Per-holding detail view with transaction history
- Simple average cost basis, recalculated on every change
- Live prices: Nimble agents / Alpha Vantage / yfinance for stocks, CoinGecko for crypto
- Monthly portfolio history with disk-cached snapshots

### Watchlists
- CRUD for lists, sections, items, and pinned symbols
- Price enrichment from cache (15-min background refresh)
- News recap filtered by watchlist tickers
- Earnings calendar lookups

### Price Alerts
- Above/below triggers evaluated on each price_cache upsert
- Cooldown prevents repeat notifications (default 1 hour)
- Notifications stored in DB and sent via Telegram

### Ticker Notes
- Per-symbol rich text notes via Quill editor
- Multiple notes per ticker with titles

### News Briefing
- Nimble agent-based aggregation (Bloomberg, WSJ, Morningstar)
- In-memory TTL cache

### Telegram Bot
- `/connect` links Telegram to a StockPro account
- `/research` triggers research from chat

### Waitlist
- Email capture via ConvertKit integration
- Thank-you page after signup

---

## Architecture

### Research Pipeline

```
planner_node -> parallel specialized_node (LangGraph Send()) -> quality_gate_node -> synthesis_node -> storage_node
```

- **Planner**: single Gemini call, selects/prioritizes subjects, outputs ResearchPlan
- **Specialized**: ReAct agent per subject (yfinance + MCP NEWS_SENTIMENT + Nimble tools)
- **Quality gate**: filters errored subjects, aborts if >50% failed
- **Synthesis**: merges outputs, position-aware framing, max 8000 tokens, truncation retry
- **Storage**: chunks -> embeddings -> PostgreSQL

### Agents

| Agent | Model | File | Role |
|---|---|---|---|
| Orchestrator | gemini-2.5-flash | `orchestrator_graph.py` | ReAct conversation, triggers research |
| Planner | gemini-2.5-flash | `agents/planner_node.py` | Subject selection |
| Specialized (xN) | gemini-2.5-pro | `agents/specialized_node.py` | Per-subject research |
| Synthesis | gemini-2.5-pro | `agents/synthesis_node.py` | Report generation |
| Report chat | gemini-2.5-flash | `agents/chat_agent.py` | RAG Q&A |

All agents use **LangGraph** with **LangChain** (`create_react_agent`, `ChatGoogleGenerativeAI`). Model names are configurable via env vars.

### Data Sources

- **yfinance** (primary for fundamentals): analyst recs, ownership, options, financials
- **Alpha Vantage MCP** (6 tools via JSON-RPC, only NEWS_SENTIMENT active in agents): company overview, financials, earnings, news sentiment
- **Nimble SDK**: web search, URL extraction, Perplexity synthesis agent
- **Nimble agents**: MarketWatch and Seeking Alpha for real-time stock prices
- **CoinGecko**: crypto prices, 50+ symbol mappings

### Database (PostgreSQL / Supabase)

Tables: users, reports, report_chunks, portfolios, holdings, transactions, csv_imports, watchlists, price_cache, alerts, notifications, ticker_notes, telegram_connect_tokens

- Identity: Clerk user ID in `users.user_id`
- RLS policies enforce user scoping via `auth.jwt()->>'sub'`
- Sensitive fields (email, telegram_chat_id) encrypted with AES-256-GCM
- Schema managed by `database.py` (`init_schema`), not Supabase migrations

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Flask (Python 3.10+), Flask-CORS, Flask-Limiter, Flask-WTF, flask-sock |
| AI/LLM | LangGraph + LangChain, langchain-google-genai (ChatGoogleGenerativeAI) |
| Embeddings | Google GenAI gemini-embedding-001 (3072-D) |
| Database | PostgreSQL via psycopg2 (Supabase-hosted, ThreadedConnectionPool) |
| Auth | Clerk (clerk-backend-api + ClerkJS) |
| Vector search | NumPy cosine similarity |
| PDF | WeasyPrint |
| Telegram | python-telegram-bot |
| Frontend (current) | Jinja2 templates, Tailwind CSS CDN, Marked.js, Quill |
| Frontend (next-gen) | React 19 + Vite 8 + TypeScript + Tailwind v4 |

---

## Pages

| Page | Route | Description |
|---|---|---|
| Home (auth) | `/` | Hero search, research popup, market overview |
| Home (public) | `/` (unauthenticated) | Marketing landing, waitlist CTA |
| Chat | `/chat` | Orchestrator conversation + report generation |
| Reports | `/reports` | Filterable report history |
| Report view | `/report/<id>` | Full rendered report with PDF export |
| Ticker | `/ticker/<symbol>` | Per-symbol hub: reports + Quill notes |
| Portfolio list | `/portfolio` | All portfolios with overall recap |
| Portfolio detail | `/portfolio/<id>` | Holdings, history, summary |
| Holding detail | `/portfolio/<id>/holding/<symbol>` | Transaction list |
| Add transaction | `/portfolio/<id>/add` | Buy/sell form |
| Import CSV | `/portfolio/<id>/import` | Drag-and-drop CSV upload |
| Watchlist | `/watchlist` | Lists, sections, items, price alerts |
| Waitlist | `/waitlist` | Email signup |
| Auth | `/sign-in`, `/sign-up` | Clerk-mounted components |

---

*Last updated: April 2026*
