# StockIntel

## ⚡ URGENT MISSION (Active Development Priority)

**Re-design the entire agentic research flow.**

Goals:
- Rethink how specialized agents are orchestrated, what they research, and how results are synthesized
- Evaluate replacing or augmenting the current RAG-lite chat with **NotebookLM integration** (Google NotebookLM API or export pipeline) for deeper, source-grounded Q&A on generated reports
- Consider whether the current `ThreadPoolExecutor` parallel approach is the right model, or if a more dynamic agent-routing architecture fits better
- Keep the Flask + MySQL foundation; redesign the AI layer on top of it

Open questions to resolve during this work:
1. How does NotebookLM integrate — direct API, PDF upload pipeline, or export + link?
2. Should synthesis be a single agent or a multi-step critique/refine loop?
3. What research subjects and data sources give the highest signal for stock analysis?

---

An AI-powered multi-agent stock research platform that orchestrates specialized research agents, integrates financial data APIs with real-time web research, and provides an interactive chat interface for exploring investment opportunities.

## Tech Stack

| Layer            | Technology                      | Notes                                    |
|-----------------|--------------------------------|------------------------------------------|
| Language         | Python 3                       |                                          |
| Web Framework    | Flask                          | Jinja2 templates, session-based auth     |
| AI / LLM        | OpenAI Agents SDK              | `openai-agents >= 0.2.0`                |
| LLM Model       | GPT-4o                         | All agents                               |
| Embeddings       | OpenAI `text-embedding-3-small`| 1536 dimensions                          |
| Financial Data   | Alpha Vantage MCP              | HTTP MCP server, 6 tools                 |
| Web Research     | Perplexity Sonar API           | AsyncOpenAI client                       |
| Crypto Prices    | CoinGecko API                  | Free tier, batch endpoint                |
| Database         | MySQL                          | InnoDB, utf8mb4, connection pooling      |
| Vector Search    | NumPy                          | Cosine similarity (no external vector DB)|
| PDF Generation   | WeasyPrint                     | Markdown → HTML → PDF                    |
| Frontend CSS     | Tailwind CSS (CDN)             | Dark mode first, custom design tokens    |
| Markdown (server)| Python `markdown`              | Tables, fenced code, nl2br extensions    |
| Markdown (client)| marked.js v12                  | Client-side rendering in chat            |
| Async Bridge     | nest-asyncio                   | Enables async in Flask sync context      |

## Project Structure

```
Stock Portfolio Agent/
│
├── OVERVIEW.md              ← Comprehensive project overview and architecture
├── CLAUDE.md                ← This file — project reference for AI assistants
├── AGENTS.md                ← Cursor AI rules and MCP integration patterns
├── CODE_REVIEW.md           ← Code review notes
├── TOOL_SELECTION.md        ← MCP tool documentation
├── PERPLEXITY_UPGRADE_PLAN.md ← Perplexity integration roadmap
├── PORTFOLIO_IMPLEMENTATION_PLAN.md ← Portfolio feature design
├── requirements.txt         ← Python dependencies
├── mcp.json.example         ← MCP server configuration template
├── init_db.py               ← Database schema initializer
├── recreate_schema.py       ← Database recreator (creates DB if missing)
├── test_cost_basis.py       ← Cost basis unit tests
├── test_csv_importer.py     ← CSV importer unit tests
├── test_mcp.py              ← MCP integration tests
├── test_nvda_research.py    ← End-to-end research test
├── test_setup.py            ← Test environment setup
│
├── src/
│   ├── __init__.py
│   ├── app.py                       ← Flask routes (auth, research, portfolio, reports)
│   ├── database.py                  ← MySQL connection pool, schema, all CRUD operations
│   │
│   │  ── Agent Layer ──
│   ├── agent.py                     ← StockResearchAgent orchestrator
│   ├── agent_tools.py               ← Tool wrappers for Agents SDK
│   ├── planner_agent.py             ← Research plan builder (subject selection + prioritization)
│   ├── research_orchestrator.py     ← Parallel agent coordinator (ThreadPoolExecutor)
│   ├── specialized_agent.py         ← Per-subject deep research agents
│   ├── synthesis_agent.py           ← Report synthesis from research outputs
│   ├── report_chat_agent.py         ← RAG-lite Q&A agent over report chunks
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
│   ├── report_chunker.py            ← Semantic text chunking (~600 tokens)
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
│       ├── base_provider.py         ← Abstract provider with TTL cache (60s)
│       ├── stock_provider.py        ← Alpha Vantage stock prices
│       ├── crypto_provider.py       ← CoinGecko crypto prices (30+ symbols)
│       └── provider_factory.py      ← Auto-detect stock vs. crypto routing
│
├── templates/
│   ├── base.html                    ← Base layout (Tailwind config, dark mode, fonts)
│   ├── index.html                   ← Landing page (hero, market cards, briefing)
│   ├── chat.html                    ← AI chat interface (AJAX, markdown rendering)
│   ├── portfolio.html               ← Portfolio dashboard (summary, holdings table)
│   ├── reports.html                 ← Report history (filters, pagination)
│   ├── report_view.html             ← Full report view with rendered markdown
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

## Architecture

### Research Pipeline

```
User submits ticker + trade type
        │
        ▼
  1. ORCHESTRATOR AGENT          GPT-4o, max 600 tokens, 6 turns
     Asks 1-2 clarifying Qs      Single tool: generate_report
        │
        ▼
  2. PLANNER AGENT               GPT-4o, temp 0.3, JSON output
     Selects research subjects    max 1200 tokens, 1 turn
     Generates per-subject        Fallback: all eligible subjects
     focus hints from context
        │
        ▼
  3. RESEARCH ORCHESTRATOR       ThreadPoolExecutor, max_workers=3
     Runs N specialized agents    Priority-ordered execution
     in parallel
        │
        ├── Specialized Agent 1   GPT-4o, max 1500 tokens, 8 turns
        ├── Specialized Agent 2   Tools: 6 MCP + 1 Perplexity
        └── Specialized Agent 3   Rate-limit retry (3x, exp backoff)
        │
        ▼
  4. SYNTHESIS AGENT             GPT-4o, max 8000 tokens, temp 0.7
     Consolidates all research    10 turns, dynamic section structure
     into structured report       Trade-type framing
        │
        ▼
  5. STORAGE & EMBEDDING
     Save report → MySQL
     Chunk report (~600 tokens)
     Embed chunks → 1536-dim
     Store embeddings for RAG
```

### Agent Inventory

| Agent                | Model  | Max Tokens | Max Turns | Tools                    | Role                               |
|----------------------|--------|------------|-----------|--------------------------|-------------------------------------|
| Orchestrator         | GPT-4o | 600        | 6         | `generate_report`        | Conversation + delegation           |
| Planner              | GPT-4o | 1200       | 1 (JSON)  | None                     | Subject selection + prioritization  |
| Specialized (×N)     | GPT-4o | 1500       | 8         | 6 MCP + 1 Perplexity     | Deep research per subject           |
| Synthesis            | GPT-4o | 8000       | 10        | None                     | Report generation                   |
| Report Chat (RAG)    | GPT-4o | default    | 5         | None                     | Q&A grounded in report chunks       |
| Conversation Handler | GPT-4o | default    | 5         | None                     | Post-report Q&A (RAG + raw output)  |

### Data Sources

**Alpha Vantage MCP** (6 tools via HTTP MCP server):

| Tool                | Function         | Data                             |
|--------------------|------------------|----------------------------------|
| `get_overview`     | OVERVIEW         | Company fundamentals, ratios     |
| `get_income_stmt`  | INCOME_STATEMENT | Revenue, margins, EPS            |
| `get_balance_sheet`| BALANCE_SHEET    | Assets, liabilities, equity      |
| `get_cash_flow`    | CASH_FLOW        | FCF, CapEx, operating cash flow  |
| `get_earnings`     | EARNINGS         | Quarterly EPS actual vs estimate |
| `get_news`         | NEWS_SENTIMENT   | News articles with sentiment     |

**Perplexity Sonar API** — real-time web research with focus types (news, analysis, general, financial). Default 10s timeout, async execution.

**CoinGecko API** — crypto prices with batch endpoint, symbol-to-coin-ID mapping for 30+ cryptos.

### 12 Research Subjects

Each subject has a structured prompt template. Eligibility varies by trade type.

| #  | Subject              | Description                                              | Day | Swing | Investment |
|----|----------------------|----------------------------------------------------------|-----|-------|------------|
| 1  | Company Overview     | Business model, economic engine, market position         | ✓   | ✓     | ✓          |
| 2  | News & Catalysts     | Near-term events, sentiment, analyst activity            | ✓   | ✓     | ✓          |
| 3  | Technical / Price Action | Support/resistance, volume, momentum                 | ✓   | ✓     |            |
| 4  | Earnings & Financials | Earnings quality, guidance, balance sheet health        | ✓   | ✓     | ✓          |
| 5  | Sector & Macro       | Industry cycle, rotation, peer performance               | ✓   | ✓     | ✓          |
| 6  | Revenue Breakdown    | Segment, geography, channel decomposition                |     | ✓     | ✓          |
| 7  | Growth Drivers       | TAM, penetration, product pipeline                       |     | ✓     | ✓          |
| 8  | Valuation & Peers    | Multiples vs. peers and historical ranges                |     |       | ✓          |
| 9  | Margin Structure     | Margin tree, unit economics, operating leverage          |     | ✓     | ✓          |
| 10 | Competitive Position | Moat framework, market share, pricing power              |     |       | ✓          |
| 11 | Risk Factors         | Tiered risk matrix with probabilities and mitigants      |     | ✓     | ✓          |
| 12 | Management Quality   | Capital allocation, insider alignment                    |     |       | ✓          |

### Session & State Management

- Flask sessions store `user_id`, `username`, `session_id`, conversation history, and current research context.
- Agent instances cached in a global `agent_sessions` dict keyed by session ID.
- Each user gets an isolated `StockResearchAgent` instance with its own conversation history, current ticker, trade type, and report state.

### Error Handling & Resilience

- **Rate limit retry** — orchestrator and specialized agents use exponential backoff (2s base, 3 retries) for OpenAI 429 errors.
- **Planner fallback** — if the planner LLM call fails or returns invalid JSON, all eligible subjects are researched with empty focus hints.
- **Graceful storage failure** — if report storage fails, the report still renders in the UI; only RAG chat is disabled.
- **Per-agent error isolation** — if a specialized agent fails, the error is captured and remaining agents continue.

## Product Features

### User Authentication
- Session-based auth with registration and login.
- Passwords hashed via `werkzeug.security` (PBKDF2).
- Per-user data isolation — reports and portfolios scoped to authenticated user.
- `login_required` decorator on all protected routes.

### Landing Page (Markets)
- Hero section with ticker search bar and trade type dropdown.
- Market overview cards (S&P 500, Bitcoin, Tesla) with sparkline SVGs.
- Today's Briefing — news article cards with category tags.

### Report Library
- Searchable, filterable history of all generated reports.
- Filter by ticker, trade type, sort order. Paginated (12 per page).
- Full report view with rendered markdown (tables, code blocks, lists).
- **PDF export** via WeasyPrint with print-optimized CSS.
- **Resume chat** — open any past report in the chat interface.

### RAG-Powered Report Chat
- Reports chunked into ~600-token semantic segments.
- Chunks embedded via OpenAI `text-embedding-3-small` (1536 dimensions).
- User questions embedded and matched via cosine similarity.
- Top-k relevant chunks injected as context for the chat agent.

### Portfolio Tracker
- **Manual transaction entry** — buy/sell with quantity, price, date, fees, notes.
- **CSV import** — auto-detects Coinbase, Robinhood, or generic CSV formats.
- **Dashboard** — summary cards (total value, cost basis, unrealized P&L, allocation) + holdings table.
- **Holding detail view** — full transaction history per symbol with delete capability.
- **Cost basis** — simple average method, recalculated on every transaction change.
- **Live prices** — Alpha Vantage for stocks, CoinGecko for crypto, TTL-based caching (60s).
- **Asset auto-detection** — known crypto symbols (BTC, ETH, SOL, etc.) route to CoinGecko; everything else to Alpha Vantage.

### Page Routes

| Page              | Route                        | Purpose                                |
|-------------------|------------------------------|----------------------------------------|
| Landing / Markets | `/`                          | Hero search, market overview, briefing |
| Chat              | `/chat`                      | AI conversation + report generation    |
| Portfolio         | `/portfolio`                 | Holdings dashboard with P&L            |
| Reports           | `/reports`                   | Filterable report history              |
| Report View       | `/report/<id>`               | Full rendered report + PDF export      |
| Holding Detail    | `/portfolio/holding/<symbol>`| Transaction history per asset          |

Supporting pages: Login, Register, Add Transaction, Import CSV.

## Data Model

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

Database tables: `users`, `reports`, `report_chunks`, `portfolios`, `holdings`, `transactions`, `csv_imports`.

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
OPENAI_API_KEY=your_openai_key
PERPLEXITY_API_KEY=your_perplexity_key
ALPHA_VANTAGE_API_KEY=your_alpha_vantage_key
MYSQL_HOST=localhost
MYSQL_USER=your_user
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=stock_research
```

## MCP Configuration

Copy `mcp.json.example` to `mcp.json` and configure the Alpha Vantage MCP server.

## Development Guidelines

### General Guidelines
- keep everything simple, do not over-engineer things
- in case there's new feature / major behaviral change of the app - update CLAUDE.md 
- if you see something in the code while reviewing files that can be better - suggest at in your final response.


### Agent Patterns
- Use OpenAI Agents SDK for all agent implementations.
- Agents should have focused responsibilities (single-purpose).
- Use `Runner.run()` for agent execution with turn limits.
- Handle async operations with `nest_asyncio` for Flask compatibility.
- Planner agent outputs structured JSON; always implement fallback for invalid output.
- Specialized agents get exactly one research subject and focus hint from the planner.

### MCP Tool Usage
- Access tools via `mcp_tools.py` wrapper.
- Available tools documented in `TOOL_SELECTION.md`.
- Always handle API rate limits gracefully (exponential backoff).

### Database Operations
- Use `database.py` for all MySQL operations.
- Reports stored with metadata (JSON) and chunk-based organization.
- Embeddings stored as JSON arrays in `report_chunks` for vector search.

### Trade Types
Research depth varies by trade type:
- **Day Trade** — Intraday catalysts, price action, momentum (5 subjects).
- **Swing Trade** — Near-term thesis, 1-14 day horizon, earnings focus (9 subjects).
- **Investment** — Full fundamental deep-dive, moat, valuation (all 12 subjects).

### Portfolio Module
- Use `PortfolioService` for all portfolio operations.
- Cost basis uses simple average method.
- Asset type auto-detected from symbol (BTC, ETH, SOL → crypto).
- Database tables: `portfolios`, `holdings`, `transactions`, `csv_imports`.

### Design System
- Dark mode first (`<html class="dark">`), full light mode support.
- Fonts: Nunito (headings), Inter (body), Material Symbols Outlined (icons).
- Design tokens: `primary` #d6d3d1, `background-dark` #0c0a09, `surface-dark` #1c1917, `accent-up` #22c55e, `accent-down` #ef4444.
- Patterns: glassmorphism (backdrop-blur), hover microinteractions, responsive mobile-first.

## Key Documentation

- `OVERVIEW.md` — Comprehensive project overview, architecture diagrams, data model schemas
- `AGENTS.md` — Cursor rules for AI development
- `CODE_REVIEW.md` — Code review notes
- `TOOL_SELECTION.md` — MCP tool documentation
- `PERPLEXITY_UPGRADE_PLAN.md` — Perplexity integration roadmap
- `PORTFOLIO_IMPLEMENTATION_PLAN.md` — Portfolio feature design
