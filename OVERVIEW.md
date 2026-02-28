# StockIntel — Project Overview

StockIntel is an AI-powered multi-agent stock research platform that orchestrates specialized research agents, integrates financial data APIs with real-time web research, and provides an interactive chat interface for exploring investment opportunities. It also includes a portfolio tracker supporting both equities and crypto assets.

---

## Table of Contents

1. [Product Features](#product-features)
2. [Architecture](#architecture)
3. [Design](#design)
4. [Data Model](#data-model)
5. [Technology Stack](#technology-stack)
6. [File Map](#file-map)

---

## Product Features

### 1. AI-Driven Stock Research App

The core product is a web app gathering al necessry feattures for trading and investing in stocks and crypto. the app contains an **agentic research pipeline** that generates institutional-grade equity research reports from a single ticker input, a portfolio overview page, repots history page, and recent news and a watchlist page. the app has a user managemnet system so each user is exposed only to his own data.

**How it works for the user:**

1. User logs in ,reaches main page and can browse news, watch his watchilist and initiate a research.
2. in order to initate a research, the user enters a stock ticker (e.g. `AAPL`, `NVDA`, `BTC-USD`) and select a trade type.
3. An orchestrator agent asks 1-2 clarifying questions to understand the user's thesis and goals.
4. Behind the scenes, a planner agent selects the most relevant research subjects, then parallel specialized agents execute deep research using financial APIs and real-time web search.
5. A synthesis agent consolidates all findings into a structured, citation-rich report.
6. The report is stored with vector embeddings for follow-up Q&A.
7. the user is free to generate another report, see his portfolio and each position status or browse past reports.

**Trade type framing** adjusts the depth and focus of the entire pipeline:

| Trade Type   | Focus                                      | Eligible Subjects |
|-------------|--------------------------------------------|--------------------|
| Day Trade   | Intraday catalysts, price action, momentum | 5 subjects         |
| Swing Trade | Near-term thesis (1-14 days), earnings     | 9 subjects         |
| Investment  | Full fundamental deep-dive, moat, valuation| 12 subjects        |

**12 Research Subjects** — each with a structured prompt template:

| # | Subject              | Description                                                    |
|---|----------------------|----------------------------------------------------------------|
| 1 | Company Overview     | Business model, economic engine, market position               |
| 2 | News & Catalysts     | Near-term events, sentiment, analyst activity                  |
| 3 | Technical / Price Action | Support/resistance, volume, momentum (Day/Swing only)      |
| 4 | Earnings & Financials | Earnings quality, guidance credibility, balance sheet health  |
| 5 | Sector & Macro       | Industry cycle, rotation dynamics, peer performance            |
| 6 | Revenue Breakdown    | Segment, geography, channel decomposition with growth trends   |
| 7 | Growth Drivers       | TAM, penetration, product pipeline, sector-specific KPIs       |
| 8 | Valuation & Peers    | Multiples vs. peers and historical ranges (Investment only)    |
| 9 | Margin Structure     | Margin tree, unit economics, operating leverage                |
| 10| Competitive Position | Moat framework, market share, pricing power (Investment only)  |
| 11| Risk Factors         | Tiered risk matrix with probabilities and mitigants            |
| 12| Management Quality   | Capital allocation track record, insider alignment (Investment)|

### 2. RAG-Powered Report Chat

After a report is generated, users can ask follow-up questions through a **retrieval-augmented generation (RAG)** chat interface:

- Reports are chunked into ~600-token semantic segments.
- Each chunk is embedded via OpenAI `text-embedding-3-small` (1536 dimensions).
- User questions are embedded and matched against chunks via cosine similarity.
- Top-k relevant chunks are injected as context into a chat agent that answers strictly from the report content.

### 3. Report Library

A searchable, filterable history of all generated reports:

- Filter by ticker, trade type, and sort order.
- Paginated browse (12 per page) with markdown preview.
- Full report view with rendered markdown (tables, code blocks, lists).
- **PDF export** via WeasyPrint with print-optimized CSS.
- **Resume chat** — open any past report in the chat interface to continue Q&A.

### 4. Portfolio Tracker

A full portfolio management module for tracking stocks and crypto:

- **Manual transaction entry** — buy/sell with quantity, price, date, fees, and notes.
- **CSV import** — auto-detects Coinbase, Robinhood, or generic CSV formats with flexible date parsing and currency symbol handling.
- **Dashboard** — summary cards (total value, cost basis, unrealized P&L, allocation) and a holdings table with per-holding P&L.
- **Holding detail view** — full transaction history per symbol with delete capability.
- **Cost basis** — simple average method, recalculated on every transaction change.
- **Live prices** — Alpha Vantage for stocks, CoinGecko for crypto, with TTL-based caching (60s).
- **Asset auto-detection** — known crypto symbols (BTC, ETH, SOL, etc.) route to CoinGecko; everything else goes to Alpha Vantage.

### 5. User Authentication

Session-based authentication with registration and login:

- Passwords hashed via `werkzeug.security` (PBKDF2).
- Per-user data isolation — reports and portfolios are scoped to the authenticated user.
- `login_required` decorator on all protected routes.

---

## Architecture

### High-Level System Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            Flask Web App                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐             │
│  │  Auth    │  │  Research │  │ Portfolio │  │  Reports   │             │
│  │  Routes  │  │  Routes  │  │  Routes   │  │  Routes    │             │
│  └────┬─────┘  └────┬─────┘  └────┬──────┘  └─────┬──────┘             │
└───────┼──────────────┼────────────┼────────────────┼────────────────────┘
        │              │            │                │
        ▼              ▼            ▼                ▼
┌──────────────┐ ┌───────────────────────────┐ ┌──────────────────────┐
│   Database   │ │   Agent Orchestration      │ │   Report Services    │
│   Manager    │ │                            │ │                      │
│              │ │  Orchestrator Agent         │ │  ReportStorage       │
│  • Users     │ │       │                    │ │  ReportChunker       │
│  • Reports   │ │       ▼                    │ │  EmbeddingService    │
│  • Chunks    │ │  Planner Agent              │ │  VectorSearch        │
│  • Portfolios│ │       │                    │ │  PDFGenerator        │
│  • Holdings  │ │       ▼                    │ │                      │
│  • Txns      │ │  Research Orchestrator      │ └──────────────────────┘
│              │ │       │
└──────────────┘ │  ┌────┴────┬────────┐      │
                 │  ▼         ▼        ▼      │
                 │ Agent 1  Agent 2  Agent 3  │  (ThreadPoolExecutor)
                 │  │         │        │      │
                 │  └────┬────┴────┬───┘      │
                 │       ▼         ▼          │
                 │  ┌─────────┐ ┌──────────┐  │
                 │  │Alpha    │ │Perplexity│  │
                 │  │Vantage  │ │Sonar API │  │
                 │  │MCP      │ │          │  │
                 │  └─────────┘ └──────────┘  │
                 │       │                    │
                 │       ▼                    │
                 │  Synthesis Agent            │
                 │       │                    │
                 │       ▼                    │
                 │  Store + Embed + Chunk      │
                 └───────────────────────────┘
```

### Research Pipeline — Step by Step

```
User submits ticker + trade type
        │
        ▼
┌──────────────────────────────────┐
│  1. ORCHESTRATOR AGENT           │  GPT-4o, max 600 output tokens
│     Asks 1-2 clarifying Qs      │  max 6 turns, 4 history messages
│     Decides when to generate     │  Single tool: generate_report
└──────────────┬───────────────────┘
               │  (user answers questions)
               ▼
┌──────────────────────────────────┐
│  2. PLANNER AGENT                │  GPT-4o, structured JSON output
│     Selects research subjects    │  temperature 0.3 (deterministic)
│     Generates per-subject focus  │  max 1200 tokens
│     hints from user context      │  Fallback: all eligible subjects
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────┐
│  3. RESEARCH ORCHESTRATOR        │  ThreadPoolExecutor
│     Runs up to 3 agents in       │  max_workers = 3
│     parallel, priority-ordered   │
│     ┌─────────────────────────┐  │
│     │ Specialized Agent (×N)  │  │  GPT-4o, max 8 turns
│     │ Tools: MCP + Perplexity │  │  max 1500 output tokens
│     │ Each agent: 1 subject   │  │  Rate-limit retry (3x, exp backoff)
│     └─────────────────────────┘  │
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────┐
│  4. SYNTHESIS AGENT              │  GPT-4o, max 8000 output tokens
│     Integrates all research      │  temperature 0.7
│     Dynamic section structure    │  max 10 turns
│     Trade-type framing           │
│     Detail preservation rules    │
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────┐
│  5. STORAGE & EMBEDDING          │
│     Save report → MySQL          │
│     Chunk report (600 tokens)    │
│     Embed chunks → 1536-dim      │
│     Store embeddings for RAG     │
└──────────────────────────────────┘
```

### Agent Architecture

All agents are built on the **OpenAI Agents SDK** (`openai-agents`):

| Agent                | Model   | Max Tokens | Max Turns | Tools                      | Role                                |
|----------------------|---------|------------|-----------|----------------------------|------------------------------------|
| Orchestrator         | GPT-4o  | 600        | 6         | `generate_report`          | Conversation + delegation          |
| Planner              | GPT-4o  | 1200       | 1 (JSON)  | None                       | Subject selection + prioritization |
| Specialized (×N)     | GPT-4o  | 1500       | 8         | 6 MCP + 1 Perplexity       | Deep research per subject          |
| Synthesis            | GPT-4o  | 8000       | 10        | None                       | Report generation                  |
| Report Chat (RAG)    | GPT-4o  | default    | 5         | None                       | Q&A grounded in report chunks      |
| Conversation Handler | GPT-4o  | default    | 5         | None                       | Post-report Q&A (RAG + raw output) |

### Data Sources

**Alpha Vantage MCP** (6 tools via HTTP MCP server):

| Tool                | Function          | Data                              |
|--------------------|-------------------|-----------------------------------|
| `get_overview`     | OVERVIEW          | Company fundamentals, ratios      |
| `get_income_stmt`  | INCOME_STATEMENT  | Revenue, margins, EPS             |
| `get_balance_sheet`| BALANCE_SHEET     | Assets, liabilities, equity       |
| `get_cash_flow`    | CASH_FLOW         | FCF, CapEx, operating cash flow   |
| `get_earnings`     | EARNINGS          | Quarterly EPS actual vs. estimate |
| `get_news`         | NEWS_SENTIMENT    | News articles with sentiment      |

**Perplexity Sonar API** — real-time web research with focus types (news, analysis, general, financial). Default 10s timeout, async execution.

**CoinGecko API** — crypto prices with batch endpoint, symbol-to-coin-ID mapping for 30+ cryptos.

### Session & State Management

- Flask sessions store `user_id`, `username`, `session_id`, conversation history, and current research context.
- Agent instances are cached in a global `agent_sessions` dict keyed by session ID.
- Each user gets an isolated `StockResearchAgent` instance that maintains its own conversation history, current ticker, trade type, and report state.

### Error Handling & Resilience

- **Rate limit retry** — both the orchestrator and specialized agents use exponential backoff (2s base, 3 retries) for OpenAI 429 errors.
- **Planner fallback** — if the planner LLM call fails or returns invalid JSON, all eligible subjects are researched with empty focus hints.
- **Graceful storage failure** — if report storage fails, the report still renders in the UI; only RAG chat is disabled.
- **Per-agent error isolation** — if a specialized agent fails, the error is captured and the remaining agents continue.

---

## Design

### UI Framework

- **Tailwind CSS** via CDN with custom configuration.
- **Dark mode first** — `<html class="dark">` with full light mode support.
- **Typography** — Nunito (display headings), Inter (body text), Material Symbols Outlined (icons).
- **Design tokens** defined in Tailwind config:

| Token              | Value       | Usage                      |
|-------------------|-------------|----------------------------|
| `primary`         | `#d6d3d1`   | Brand accent, links, CTAs  |
| `background-dark` | `#0c0a09`   | Page background (dark)     |
| `surface-dark`    | `#1c1917`   | Card/panel background      |
| `border-dark`     | `#292524`   | Borders, dividers          |
| `accent-up`       | `#22c55e`   | Positive/gain indicators   |
| `accent-down`     | `#ef4444`   | Negative/loss indicators   |

### Page Layout

**6 main views**, all extending `base.html`:

| Page              | Route                        | Purpose                                |
|-------------------|------------------------------|----------------------------------------|
| Landing / Markets | `/`                          | Hero search, market overview, briefing |
| Chat              | `/chat`                      | AI conversation + report generation    |
| Portfolio         | `/portfolio`                 | Holdings dashboard with P&L            |
| Reports           | `/reports`                   | Filterable report history              |
| Report View       | `/report/<id>`               | Full rendered report                   |
| Holding Detail    | `/portfolio/holding/<symbol>`| Transaction history per asset          |

**Supporting pages:** Login, Register, Add Transaction, Import CSV.

### Landing Page

The landing page (`index.html`) features:

- **Hero section** — gradient background with inline SVG chart art, ticker search bar with trade type dropdown, and a primary CTA button.
- **Market Overview** — 3 cards (S&P 500, Bitcoin, Tesla) with mini sparkline SVGs, color-coded gain/loss badges, and hover animations.
- **Today's Briefing** — 3 news article cards with category tags, source attribution, and hover lift effects.
- **Footer** — brand, copyright, and legal links.

### Chat Interface

The chat (`chat.html`) provides:

- Message history rendered as user/assistant bubbles.
- AJAX form submission for seamless conversation flow.
- Client-side markdown rendering via `marked.js`.
- Loading indicators during agent processing.
- Auto-scroll to latest message.

### Design Patterns

- **Glassmorphism** — search bar and overlays use `backdrop-blur-md` with semi-transparent backgrounds.
- **Hover microinteractions** — cards lift (`-translate-y-1`), borders glow, sparklines increase opacity.
- **Responsive** — mobile-first with `@container` queries and `md:`/`lg:` breakpoints.
- **Accessible** — `aria-label` on inputs, semantic HTML, sufficient color contrast.

---

## Data Model

### Entity Relationship

```
users
  │
  ├──< reports (user_id FK, ON DELETE SET NULL)
  │      │
  │      └──< report_chunks (report_id FK, CASCADE)
  │
  └──< portfolios (user_id FK, ON DELETE SET NULL)
         │
         └──< holdings (portfolio_id FK, CASCADE)
                │
                └──< transactions (holding_id FK, CASCADE)

csv_imports ──> portfolios (portfolio_id FK, CASCADE)
```

### Table Schemas

**`users`**
| Column        | Type         | Constraints                |
|---------------|-------------|----------------------------|
| user_id       | VARCHAR(36) | PK                         |
| username      | VARCHAR(80) | NOT NULL, UNIQUE           |
| email         | VARCHAR(120)| NOT NULL, UNIQUE           |
| password_hash | VARCHAR(255)| NOT NULL                   |
| created_at    | TIMESTAMP   | DEFAULT CURRENT_TIMESTAMP  |

**`reports`**
| Column      | Type         | Constraints                          |
|-------------|-------------|--------------------------------------|
| report_id   | VARCHAR(36) | PK                                   |
| user_id     | VARCHAR(36) | FK → users, nullable                 |
| ticker      | VARCHAR(10) | NOT NULL, indexed                    |
| trade_type  | VARCHAR(50) | NOT NULL                             |
| report_text | TEXT        | NOT NULL                             |
| metadata    | JSON        | Nullable (trade context, subjects)   |
| created_at  | TIMESTAMP   | DEFAULT CURRENT_TIMESTAMP, indexed   |

**`report_chunks`**
| Column      | Type         | Constraints                      |
|-------------|-------------|----------------------------------|
| chunk_id    | VARCHAR(36) | PK                               |
| report_id   | VARCHAR(36) | FK → reports (CASCADE), indexed  |
| chunk_text  | TEXT        | NOT NULL                         |
| section     | VARCHAR(100)| Nullable, indexed                |
| chunk_index | INT         | NOT NULL                         |
| embedding   | JSON        | Nullable (1536-dim float array)  |
| created_at  | TIMESTAMP   | DEFAULT CURRENT_TIMESTAMP        |

**`portfolios`**
| Column       | Type         | Constraints                |
|-------------|-------------|----------------------------|
| portfolio_id | VARCHAR(36) | PK                         |
| name         | VARCHAR(100)| DEFAULT 'My Portfolio'     |
| description  | TEXT        | Nullable                   |
| user_id      | VARCHAR(36) | FK → users, nullable       |
| created_at   | TIMESTAMP   | DEFAULT CURRENT_TIMESTAMP  |
| updated_at   | TIMESTAMP   | ON UPDATE CURRENT_TIMESTAMP|

**`holdings`**
| Column          | Type           | Constraints                            |
|----------------|----------------|----------------------------------------|
| holding_id      | VARCHAR(36)    | PK                                     |
| portfolio_id    | VARCHAR(36)    | FK → portfolios (CASCADE), indexed     |
| symbol          | VARCHAR(20)    | NOT NULL, indexed                      |
| asset_type      | ENUM           | 'stock' / 'crypto'                    |
| total_quantity  | DECIMAL(18,8)  | DEFAULT 0                              |
| average_cost    | DECIMAL(18,8)  | DEFAULT 0                              |
| total_cost_basis| DECIMAL(18,2)  | DEFAULT 0                              |
| created_at      | TIMESTAMP      | DEFAULT CURRENT_TIMESTAMP              |
| updated_at      | TIMESTAMP      | ON UPDATE CURRENT_TIMESTAMP            |

**`transactions`**
| Column           | Type           | Constraints                        |
|-----------------|----------------|------------------------------------|
| transaction_id   | VARCHAR(36)    | PK                                 |
| holding_id       | VARCHAR(36)    | FK → holdings (CASCADE), indexed   |
| transaction_type | ENUM           | 'buy' / 'sell'                    |
| quantity         | DECIMAL(18,8)  | NOT NULL                           |
| price_per_unit   | DECIMAL(18,8)  | NOT NULL                           |
| fees             | DECIMAL(18,2)  | DEFAULT 0                          |
| transaction_date | TIMESTAMP      | NOT NULL, indexed                  |
| notes            | TEXT           | Nullable                           |
| import_source    | VARCHAR(50)    | Nullable ('manual', 'coinbase', etc.)|
| created_at       | TIMESTAMP      | DEFAULT CURRENT_TIMESTAMP          |

**`csv_imports`**
| Column        | Type         | Constraints                    |
|--------------|-------------|--------------------------------|
| import_id     | VARCHAR(36) | PK                             |
| portfolio_id  | VARCHAR(36) | FK → portfolios (CASCADE)      |
| filename      | VARCHAR(255)| NOT NULL                       |
| row_count     | INT         | NOT NULL                       |
| success_count | INT         | NOT NULL                       |
| error_count   | INT         | NOT NULL                       |
| errors_json   | JSON        | Nullable                       |
| imported_at   | TIMESTAMP   | DEFAULT CURRENT_TIMESTAMP      |

---

## Technology Stack

| Layer            | Technology                        | Version / Notes                        |
|-----------------|-----------------------------------|----------------------------------------|
| Language         | Python 3                          |                                        |
| Web Framework    | Flask                             | Jinja2 templates, session-based auth   |
| AI / LLM        | OpenAI Agents SDK                 | `openai-agents >= 0.2.0`              |
| LLM Model       | GPT-4o                            | All agents                             |
| Embeddings       | OpenAI `text-embedding-3-small`   | 1536 dimensions                        |
| Financial Data   | Alpha Vantage MCP                 | HTTP MCP server, 6 tools               |
| Web Research     | Perplexity Sonar API              | AsyncOpenAI client                     |
| Crypto Prices    | CoinGecko API                     | Free tier, batch endpoint              |
| Database         | MySQL                             | InnoDB, utf8mb4, connection pooling    |
| Vector Search    | NumPy                             | Cosine similarity (no external DB)     |
| PDF Generation   | WeasyPrint                        | Markdown → HTML → PDF                  |
| Frontend CSS     | Tailwind CSS (CDN)                | Dark mode, custom tokens               |
| Markdown (server)| Python `markdown`                 | Tables, fenced code, nl2br extensions  |
| Markdown (client)| marked.js                         | v12, client-side rendering in chat     |
| Async Bridge     | nest-asyncio                      | Enables async in Flask sync context    |

---

## File Map

```
Stock Portfolio Agent/
│
├── OVERVIEW.md              ← You are here
├── CLAUDE.md                ← Project reference (structure, commands, guidelines)
├── AGENTS.md                ← Cursor AI rules and MCP integration patterns
├── requirements.txt         ← Python dependencies
├── mcp.json.example         ← MCP server configuration template
├── init_db.py               ← Database schema initializer
├── recreate_schema.py       ← Database recreator (creates DB if missing)
│
├── src/
│   ├── app.py                       ← Flask routes (auth, research, portfolio, reports)
│   ├── database.py                  ← MySQL connection pool, schema, CRUD operations
│   │
│   │  ── Agent Layer ──
│   ├── agent.py                     ← StockResearchAgent orchestrator
│   ├── agent_tools.py               ← Tool wrappers for Agents SDK
│   ├── planner_agent.py             ← Research plan builder (subject selection)
│   ├── research_orchestrator.py     ← Parallel agent coordinator
│   ├── specialized_agent.py         ← Per-subject research agents
│   ├── synthesis_agent.py           ← Report synthesis from research outputs
│   ├── report_chat_agent.py         ← RAG-lite Q&A agent
│   ├── conversation_handler_agent.py← Post-report conversation (RAG + raw output)
│   │
│   │  ── Research Config ──
│   ├── research_subjects.py         ← 12 subject definitions with prompt templates
│   ├── research_plan.py             ← ResearchPlan dataclass
│   ├── research_prompt.py           ← System prompt templates and utilities
│   │
│   │  ── Data Integration ──
│   ├── mcp_client.py                ← Alpha Vantage MCP HTTP client
│   ├── mcp_manager.py               ← MCP server connection manager
│   ├── mcp_tools.py                 ← MCP tool execution wrappers
│   ├── perplexity_client.py         ← Perplexity Sonar API client
│   ├── perplexity_tools.py          ← Perplexity research functions
│   │
│   │  ── Report Pipeline ──
│   ├── report_storage.py            ← Report persistence (save + chunk + embed)
│   ├── report_chunker.py            ← Semantic text chunking (600 tokens)
│   ├── embedding_service.py         ← OpenAI embeddings client
│   ├── vector_search.py             ← Cosine similarity search over chunks
│   ├── pdf_generator.py             ← WeasyPrint PDF export
│   │
│   │  ── Utilities ──
│   ├── date_utils.py                ← Datetime context for agent prompts
│   │
│   │  ── Portfolio Module ──
│   ├── portfolio/
│   │   ├── __init__.py              ← Module exports
│   │   ├── portfolio_service.py     ← Portfolio business logic (CRUD, summary, import)
│   │   ├── cost_basis.py            ← Simple average cost basis calculator
│   │   └── csv_importer.py          ← Multi-format CSV parser (Coinbase, Robinhood, generic)
│   │
│   │  ── Data Providers ──
│   └── data_providers/
│       ├── __init__.py              ← Module exports
│       ├── base_provider.py         ← Abstract provider with TTL cache
│       ├── stock_provider.py        ← Alpha Vantage stock prices
│       ├── crypto_provider.py       ← CoinGecko crypto prices
│       └── provider_factory.py      ← Auto-detect stock vs. crypto routing
│
├── templates/
│   ├── base.html                    ← Base layout (Tailwind config, dark mode, fonts)
│   ├── index.html                   ← Landing page (hero, market cards, briefing)
│   ├── chat.html                    ← AI chat interface (AJAX, markdown rendering)
│   ├── portfolio.html               ← Portfolio dashboard (summary, holdings table)
│   ├── reports.html                 ← Report history (filters, pagination)
│   ├── report_view.html             ← Full report view with markdown
│   ├── add_transaction.html         ← Manual transaction form
│   ├── import_csv.html              ← CSV upload page
│   ├── holding_detail.html          ← Per-holding transaction history
│   ├── login.html                   ← Login page
│   └── register.html                ← Registration page
│
└── static/
    └── css/
        └── style.css                ← Legacy CSS (most styling via Tailwind)
```

---

*Last updated: February 2026*
