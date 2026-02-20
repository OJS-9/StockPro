f# Stock Portfolio Agent

An AI-powered multi-agent stock research platform that orchestrates specialized research agents, integrates financial data APIs with real-time web research, and provides an interactive chat interface for exploring investment opportunities.

## Tech Stack

- **Backend**: Python 3, Flask
- **AI/LLM**: OpenAI Agents SDK, GPT-4o, OpenAI Embeddings
- **Financial Data**: Alpha Vantage MCP (6 core tools)
- **Web Research**: Perplexity Sonar API
- **Database**: MySQL
- **Vector Search**: NumPy (cosine similarity)

## Project Structure

```
src/
├── agent.py                 # Main orchestrator agent (StockResearchAgent)
├── agent_tools.py           # Tool wrappers for Agents SDK
├── app.py                   # Flask web application routes
├── database.py              # MySQL database operations
├── mcp_client.py            # Alpha Vantage MCP HTTP client
├── mcp_manager.py           # MCP server configuration
├── mcp_tools.py             # MCP tool execution wrapper
├── perplexity_client.py     # Perplexity Sonar API client
├── perplexity_tools.py      # Perplexity research functions
├── research_orchestrator.py # Parallel research coordination
├── research_prompt.py       # System prompts and templates
├── research_subjects.py     # Research focus areas (12 subjects)
├── specialized_agent.py     # Topic-focused research agents
├── synthesis_agent.py       # Report synthesis from research
├── report_chat_agent.py     # RAG-lite Q&A agent
├── report_storage.py        # Report persistence layer
├── report_chunker.py        # Text segmentation for embeddings
├── embedding_service.py     # OpenAI embeddings client
├── vector_search.py         # Cosine similarity search
├── date_utils.py            # Datetime context utilities
├── portfolio/               # Portfolio tracking module
│   ├── __init__.py
│   ├── cost_basis.py        # Simple average cost calculation
│   ├── csv_importer.py      # CSV import (Coinbase, Robinhood, generic)
│   └── portfolio_service.py # Portfolio business logic
└── data_providers/          # Price data providers
    ├── __init__.py
    ├── base_provider.py     # Abstract provider interface
    ├── stock_provider.py    # Alpha Vantage stock prices
    ├── crypto_provider.py   # CoinGecko crypto prices
    └── provider_factory.py  # Auto-detect stock vs crypto

templates/                   # Flask Jinja2 templates
├── portfolio.html           # Portfolio dashboard
├── add_transaction.html     # Manual transaction form
├── import_csv.html          # CSV import page
└── holding_detail.html      # Holding details & transactions
static/css/                  # Stylesheets
```

## Architecture

### Research Pipeline
```
User Request → Orchestrator Agent → Parallel Specialized Agents → Synthesis Agent → Chat Interface
```

### Key Components

1. **StockResearchAgent** (`src/agent.py`)
   - Main orchestrator using OpenAI Agents SDK
   - Config: max 600 output tokens, max 6 turns, max 4 history messages
   - Single tool: `generate_report_tool`

2. **ResearchOrchestrator** (`src/research_orchestrator.py`)
   - Coordinates up to 3 concurrent specialized agents
   - 12 research subjects: Products, Revenue, Value Props, Buying Process, Pricing, Competitive Landscape, Market Trends, Growth Drivers, Unit Economics, Risk Factors, Management, Future Outlook

3. **Data Sources**
   - **Alpha Vantage MCP**: OVERVIEW, INCOME_STATEMENT, BALANCE_SHEET, CASH_FLOW, EARNINGS, NEWS_SENTIMENT
   - **Perplexity Sonar**: Real-time web research for qualitative insights

4. **ReportChatAgent** (`src/report_chat_agent.py`)
   - RAG-lite retrieval using vector similarity
   - Interactive follow-up Q&A on generated reports

5. **Portfolio Module** (`src/portfolio/`)
   - Track stocks and crypto holdings
   - Simple average cost basis calculation
   - Manual transaction entry + CSV import (Coinbase, Robinhood, generic)
   - CoinGecko API for crypto prices, Alpha Vantage for stocks

## Commands

```bash
# Run the Flask app
python src/app.py

# Initialize database
python init_db.py

# Recreate database schema
python recreate_schema.py

# Run tests
python -m pytest test_*.py
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

Copy `mcp.json.example` to `mcp.json` and configure Alpha Vantage MCP server.

## Development Guidelines

### Agent Patterns
- Use OpenAI Agents SDK for all agent implementations
- Agents should have focused responsibilities (single-purpose)
- Use `Runner.run()` for agent execution with turn limits
- Handle async operations with `nest_asyncio` for Flask compatibility

### MCP Tool Usage
- Access tools via `mcp_tools.py` wrapper
- Available tools documented in `TOOL_SELECTION.md`
- Always handle API rate limits gracefully

### Database Operations
- Use `database.py` for all MySQL operations
- Reports stored with metadata and chunk-based organization
- Embeddings stored for vector search retrieval

### Trade Types
Research depth varies by trade type:
- **Day Trade**: Quick technical analysis
- **Swing Trade**: Medium-term fundamentals
- **Investment**: Comprehensive deep-dive

### Portfolio Module
- Use `PortfolioService` for all portfolio operations
- Cost basis uses simple average method
- Asset type auto-detected from symbol (BTC, ETH → crypto)
- Database tables: `portfolios`, `holdings`, `transactions`, `csv_imports`

## Key Documentation

- `AGENTS.md` - Cursor rules for AI development
- `TOOL_SELECTION.md` - MCP tool documentation
- `PERPLEXITY_UPGRADE_PLAN.md` - Integration roadmap
- `PORTFOLIO_IMPLEMENTATION_PLAN.md` - Portfolio feature design
