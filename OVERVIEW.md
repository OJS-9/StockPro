# StockIntel — Project Overview

StockIntel is an AI-powered multi-agent stock research platform that orchestrates specialized research agents, integrates financial data APIs with real-time web research, and provides an interactive chat interface for exploring investment opportunities. It also includes a portfolio tracker supporting both equities and crypto assets.

---

## Table of Contents

1. [Product Features](#product-features)
2. [Architecture](#architecture)
3. [Design](#design)

---

## Product Features

### AI-Powered Research Reports

The core product is an intelligent research pipeline. A user enters a stock ticker and selects a trade type — **Investment**, **Swing Trade**, or **Day Trade** — and the system produces a comprehensive, data-backed research report tailored to that horizon.

- **Adaptive Depth**: Research depth scales with trade type. An Investment report covers 12 subjects (valuation, competitive moat, management quality, etc.) while a Day Trade report focuses on price action, news catalysts, and sector context.
- **Dual Data Sources**: Every report blends quantitative financial data from Alpha Vantage (income statements, balance sheets, earnings, news sentiment) with qualitative web research from Perplexity Sonar (analyst opinions, industry trends, breaking news).
- **Conversational Pre-Research**: Before generating a report, the orchestrator agent asks 1–2 clarifying questions to tailor research to the user's specific angle (e.g., "Are you focused on their AI segment or the hardware business?").
- **Interactive Follow-Up Chat**: After a report is generated, users can ask follow-up questions. A RAG-lite system retrieves the most relevant report chunks via vector similarity and feeds them into the LLM for grounded answers.

### Portfolio Tracking

A full-featured portfolio module lets users track holdings across stocks and cryptocurrencies.

- **Manual Transaction Entry**: Add buy/sell transactions with quantity, price, fees, and notes.
- **CSV Import**: Bulk-import transaction history from Coinbase, Robinhood, or a generic CSV format. The importer auto-detects the source format from column headers.
- **Real-Time Pricing**: Stock prices fetched via Alpha Vantage; crypto prices via CoinGecko. Prices are cached with a configurable TTL to respect rate limits.
- **Cost Basis Calculation**: Simple average cost method applied chronologically across all transactions per holding.
- **Portfolio Dashboard**: Summary cards showing total market value, cost basis, unrealized P&L (absolute and percentage), and asset allocation breakdown (stocks vs. crypto). Each holding is clickable for a detail view with full transaction history.

### User Authentication

Session-based authentication with registration, login, and logout. Portfolios are scoped to individual users.

### Market Landing Page

A branded landing page with a hero search form, static market overview cards (S&P 500, Bitcoin, Tesla), and a curated news briefing section to orient users before they dive into research.

---

## Architecture

### High-Level Pipeline

```
User Request
    │
    ▼
StockResearchAgent (orchestrator)
    │  ── asks 1–2 clarifying questions
    │  ── calls generate_report tool
    │
    ▼
PlannerAgent
    │  ── selects & prioritizes research subjects
    │  ── outputs ResearchPlan (structured JSON)
    │
    ▼
ResearchOrchestrator
    │  ── ThreadPoolExecutor (up to 3 concurrent workers)
    │
    ├──▶ SpecializedAgent: Earnings & Financials ──┐
    ├──▶ SpecializedAgent: Growth Drivers ─────────┤
    └──▶ SpecializedAgent: Competitive Position ───┤
         ...                                       │
    ◄──────────────────────────────────────────────┘
    │  research_outputs: {subject_id → text}
    │
    ▼
SynthesisAgent
    │  ── consolidates all outputs into final report
    │  ── adaptive section structure per plan
    │
    ▼
ReportStorage Pipeline
    │  ── ReportChunker (600-token semantic chunks)
    │  ── EmbeddingService (text-embedding-3-small, 1536d)
    │  ── DatabaseManager (MySQL — report + chunks + embeddings)
    │
    ▼
ReportChatAgent (RAG-lite follow-up Q&A)
    │  ── VectorSearch (cosine similarity over stored chunks)
    │  ── injects top-k chunks into LLM prompt
    │
    ▼
User sees report + can ask follow-up questions
```

### Agent System

All agents are built on the **OpenAI Agents SDK** (`openai-agents`). Each agent has a single, focused responsibility.

| Agent | Role | Tools | Output Tokens |
|---|---|---|---|
| **StockResearchAgent** | Orchestrate conversation and trigger report generation | `generate_report` (single tool) | 600 |
| **PlannerAgent** | Select and prioritize research subjects for a given ticker + trade type | None (structured JSON response) | — |
| **SpecializedResearchAgent** | Deep-dive into one research subject using financial data + web search | 6 MCP tools + Perplexity | 1,500 |
| **SynthesisAgent** | Merge all specialized outputs into a cohesive report | None (pure synthesis) | 8,000 |
| **ReportChatAgent** | Answer follow-up questions using RAG retrieval | None (prompt injection) | — |
| **ConversationHandlerAgent** | Enhanced Q&A using both report chunks and raw research outputs | None (prompt injection) | — |

**Execution flow details:**

1. **Orchestrator** receives the user's ticker and trade type. It holds a short conversation (max 6 turns, 4 history messages) to clarify intent, then invokes `generate_report`.
2. **PlannerAgent** makes a single LLM call (no tools) to return a `ResearchPlan` — a structured object containing selected subject IDs, focus hints per subject, and trade context. If the LLM response fails to parse, a fallback plan using default priorities is used.
3. **ResearchOrchestrator** fans out subjects to `SpecializedResearchAgent` instances via `ThreadPoolExecutor` (default 3 workers, configurable via `RESEARCH_MAX_WORKERS` env var). Each agent runs up to 8 turns, calling MCP and Perplexity tools to gather data. Failures in individual agents are isolated — partial results are still passed to synthesis.
4. **SynthesisAgent** receives the full `ResearchPlan` plus all research outputs. It dynamically builds report sections based on which subjects were actually researched, preserving all specific metrics and data points.
5. The final report text is stored, chunked, embedded, and persisted to MySQL for future retrieval.

### Research Subjects

Twelve research subjects are defined, each with a prompt template and trade-type eligibility:

| # | Subject | Day Trade | Swing Trade | Investment |
|---|---|---|---|---|
| 1 | Company Overview | yes | yes | yes |
| 2 | News & Catalysts | yes | yes | yes |
| 3 | Technical / Price Action | yes | yes | — |
| 4 | Earnings & Financials | — | yes | yes |
| 5 | Sector & Macro | yes | yes | — |
| 6 | Revenue Breakdown | — | yes | yes |
| 7 | Growth Drivers | — | yes | yes |
| 8 | Valuation | — | — | yes |
| 9 | Margin Structure | — | yes | yes |
| 10 | Competitive Position | — | — | yes |
| 11 | Risk Factors | — | yes | yes |
| 12 | Management Quality | — | — | yes |

Each subject carries a priority per trade type (1=high, 2=medium, 3=low). The PlannerAgent selects a subset and reorders them based on what matters most for the user's specific query.

### Data Integration Layer

**Alpha Vantage MCP (6 tools)**

The platform connects to Alpha Vantage through a Model Context Protocol HTTP server. The `MCPClient` communicates via JSON-RPC, with retry logic, rate limiting, and a hardcoded fallback tool list if discovery fails.

| Tool | Data |
|---|---|
| `OVERVIEW` | Company profile, sector, market cap, ratios |
| `INCOME_STATEMENT` | Revenue, expenses, net income (annual + quarterly) |
| `BALANCE_SHEET` | Assets, liabilities, equity |
| `CASH_FLOW` | Operating, investing, financing cash flows |
| `EARNINGS` | EPS actuals vs. estimates |
| `NEWS_SENTIMENT` | News articles with sentiment scores |

Tool outputs are truncated (max 5 series items, max 5 news items) before passing to agents to manage context window usage.

**Perplexity Sonar API**

Real-time web research for qualitative insights. Queries are formatted by focus type — `news`, `analysis`, `financial`, or `general` — with a 10-second timeout. The Perplexity client uses `AsyncOpenAI` for non-blocking requests.

**CoinGecko API**

Crypto prices for the portfolio module. Includes a mapping of 50+ common crypto symbols to CoinGecko IDs and supports batch price fetching.

### Report Storage & Retrieval (RAG Pipeline)

```
Report Text
    │
    ▼
ReportChunker
    │  ── splits by markdown headers (section-aware)
    │  ── 600-token chunks with 100-token overlap
    │  ── sentence boundary awareness
    │
    ▼
EmbeddingService
    │  ── OpenAI text-embedding-3-small (1536 dimensions)
    │  ── batch processing (up to 100 chunks)
    │
    ▼
DatabaseManager
    │  ── stores chunks with section labels + embedding vectors (JSON)
    │
    ▼
VectorSearch
    ── cosine similarity via NumPy
    ── top-k retrieval with similarity scores
    ── optional section filtering
```

### Database Schema

Seven MySQL tables organized around two domains:

**Research Domain**
- `reports` — report metadata (ticker, trade type, full text, JSON metadata)
- `report_chunks` — semantic chunks with section labels and embedding vectors

**Portfolio Domain**
- `users` — authentication (username, email, password hash)
- `portfolios` — named portfolios scoped to users
- `holdings` — aggregated position per symbol with cost basis
- `transactions` — individual buy/sell records
- `csv_imports` — import audit log with success/error counts

Relationships: `users 1→N portfolios 1→N holdings 1→N transactions`, `portfolios 1→N csv_imports`, `reports 1→N report_chunks`. All child tables use CASCADE deletes.

### Portfolio Data Flow

```
User adds transaction / imports CSV
    │
    ▼
PortfolioService
    │  ── validates input, auto-detects asset type
    │  ── persists transaction via DatabaseManager
    │  ── recalculates holding (simple average cost basis)
    │
    ▼
DataProviderFactory
    │  ── routes to StockDataProvider (Alpha Vantage) or CryptoDataProvider (CoinGecko)
    │  ── price caching with configurable TTL
    │
    ▼
Portfolio Dashboard
    ── total market value, cost basis, unrealized P&L
    ── per-holding current price + gain/loss
    ── allocation breakdown (stocks vs. crypto)
```

---

## Design

### Technology Stack

| Layer | Technology |
|---|---|
| Backend framework | Flask (Python 3.10+) |
| AI / LLM | OpenAI Agents SDK, GPT-4o |
| Embeddings | OpenAI `text-embedding-3-small` |
| Financial data | Alpha Vantage MCP (HTTP, JSON-RPC) |
| Web research | Perplexity Sonar API |
| Crypto prices | CoinGecko API |
| Database | MySQL with connection pooling (pool_size=5) |
| Vector search | NumPy cosine similarity |
| Frontend | Jinja2 templates, Tailwind CSS (CDN), Marked.js |
| Async | `nest_asyncio` for Flask compatibility, `AsyncOpenAI` for API calls |

### Application Structure

```
src/
├── agent.py                    # Orchestrator agent
├── planner_agent.py            # Research planning
├── specialized_agent.py        # Per-subject research agents
├── synthesis_agent.py          # Report consolidation
├── research_orchestrator.py    # Parallel execution coordinator
├── research_subjects.py        # 12 subject definitions
├── research_plan.py            # ResearchPlan dataclass
├── research_prompt.py          # Prompt templates
├── conversation_handler_agent.py  # Enhanced post-report Q&A
├── report_chat_agent.py        # RAG-lite Q&A
├── agent_tools.py              # Agents SDK tool wrappers
├── mcp_client.py               # Alpha Vantage MCP HTTP client
├── mcp_manager.py              # MCP configuration manager
├── mcp_tools.py                # MCP tool execution
├── perplexity_client.py        # Perplexity Sonar client
├── perplexity_tools.py         # Perplexity tool wrapper
├── report_storage.py           # Storage pipeline orchestrator
├── report_chunker.py           # Semantic text chunking
├── embedding_service.py        # OpenAI embeddings client
├── vector_search.py            # Cosine similarity search
├── database.py                 # MySQL operations & schema
├── date_utils.py               # Datetime context utilities
├── app.py                      # Flask routes & session management
├── portfolio/
│   ├── portfolio_service.py    # Portfolio business logic
│   ├── cost_basis.py           # Simple average cost calculator
│   └── csv_importer.py         # Multi-format CSV parser
└── data_providers/
    ├── base_provider.py        # Abstract provider with caching
    ├── stock_provider.py       # Alpha Vantage stock prices
    ├── crypto_provider.py      # CoinGecko crypto prices
    └── provider_factory.py     # Auto-detect stock vs crypto

templates/
├── base.html                   # Shared layout (Tailwind, dark mode)
├── index.html                  # Landing page with search
├── chat.html                   # AI research chat interface
├── portfolio.html              # Portfolio dashboard
├── holding_detail.html         # Per-holding detail + transactions
├── add_transaction.html        # Manual transaction form
├── import_csv.html             # CSV import with drag-and-drop
├── login.html                  # Login form
└── register.html               # Registration form
```

### Design Patterns

**Multi-Agent Orchestration**
The system follows a hierarchical multi-agent pattern: a lightweight orchestrator delegates planning to a planner agent, fans research out to specialized agents in parallel, and passes all results to a synthesis agent. Each agent has a narrow scope and limited turn budget, keeping token usage predictable.

**Adapter Layer for External APIs**
MCP tools and Perplexity queries are wrapped into `FunctionTool` objects that conform to the Agents SDK interface. Output truncation is applied at the adapter level to prevent context window overflow. This decouples the agent logic from the specifics of each data source.

**RAG-Lite Retrieval**
Instead of a dedicated vector database, the system stores embedding vectors as JSON blobs in MySQL and performs cosine similarity search in-process with NumPy. This keeps the infrastructure simple while still enabling semantic retrieval for follow-up Q&A.

**Graceful Degradation**
Fallbacks are built into multiple layers: the MCP client falls back to a hardcoded tool list if discovery fails; the planner agent returns a default plan if the LLM response doesn't parse; individual specialized agent failures don't block the rest of the pipeline. Rate limit errors trigger exponential backoff retries.

**Service Layer Separation**
Portfolio operations are encapsulated in `PortfolioService`, which sits between Flask routes and the database. The data provider abstraction (`BaseDataProvider` → `StockDataProvider` / `CryptoDataProvider`) with a factory allows the system to transparently handle stocks and crypto through the same interface.

**Session-Scoped Agent Instances**
Flask sessions hold per-user agent instances, preserving conversation state across requests without a separate state store. History is truncated to the most recent 4 messages to bound memory usage.

### UI / UX Design

- **Dark Theme**: All pages use a stone-toned dark palette (`stone-950` background, `stone-900` surfaces) with warm accent colors for interactive elements.
- **Tailwind CSS**: Utility-first styling via CDN with a custom theme configuration for consistent spacing, colors, and typography.
- **Typography**: Manrope for headings, Inter/Noto Sans for body text — optimized for readability on dark backgrounds.
- **Chat Interface**: Messages render as styled bubbles with full markdown support (headings, tables, code blocks, lists) via Marked.js. AJAX submission with streaming-style loading indicators keeps the experience fluid.
- **Portfolio Dashboard**: Summary cards at the top with color-coded P&L (green/red), a sortable holdings table, and clickable rows for drill-down into individual holding details and transaction history.
- **CSV Import**: Drag-and-drop file upload with format auto-detection and preview. Supported formats are clearly documented inline.
- **Responsive Layout**: Tailwind's responsive utilities ensure the interface works across desktop and tablet viewports.

### Configuration & Environment

All secrets are managed via `.env` (never committed). The application requires:

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | LLM calls + embeddings |
| `PERPLEXITY_API_KEY` | Web research queries |
| `ALPHA_VANTAGE_API_KEY` | Financial data via MCP |
| `MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE` | Database connection |

MCP server configuration lives in `mcp.json` (copied from `mcp.json.example`).

### Testing

The project includes targeted test suites:

- **`test_cost_basis.py`** — 15+ cases covering averaging, partial sells, fees, crypto decimals, out-of-order transactions
- **`test_csv_importer.py`** — 20+ cases for format detection, parsing, and error handling across Coinbase/Robinhood/generic formats
- **`test_mcp.py`** — MCP connection, tool discovery, and execution smoke tests
- **`test_nvda_research.py`** — End-to-end research pipeline test for NVDA
- **`test_setup.py`** — Environment validation (Python version, dependencies, config files)

Tests run via `python -m pytest test_*.py` from the project root.
