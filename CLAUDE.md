# StockIntel - AI Stock Research Agent

## Project Overview

StockIntel is a Flask-based web application that uses OpenAI's Agents SDK to generate comprehensive stock research reports. It features parallel specialized agents for different research topics, RAG-lite chat with reports, and PDF export.

## Tech Stack

- **Backend**: Python 3.12, Flask
- **AI**: OpenAI Agents SDK (`openai-agents`), GPT-4o
- **Database**: MySQL with connection pooling
- **Frontend**: Jinja2 templates, Tailwind CSS, vanilla JavaScript
- **PDF Generation**: WeasyPrint + Markdown

## Architecture

```
User Request → Flask App → StockResearchAgent (Orchestrator)
                                    ↓
                          ResearchOrchestrator
                                    ↓
                    ┌───────────────┼───────────────┐
                    ↓               ↓               ↓
            Specialized     Specialized     Specialized
              Agent 1         Agent 2         Agent N
                    ↓               ↓               ↓
                    └───────────────┼───────────────┘
                                    ↓
                           SynthesisAgent
                                    ↓
                    ReportStorage (MySQL + Embeddings)
```

## Key Files

| File | Purpose |
|------|---------|
| `src/app.py` | Flask routes, session management |
| `src/agent.py` | Main `StockResearchAgent` class, orchestration |
| `src/research_orchestrator.py` | Parallel research execution via ThreadPoolExecutor |
| `src/specialized_agent.py` | Individual research topic agents |
| `src/synthesis_agent.py` | Combines research into final report |
| `src/research_subjects.py` | Defines research topics (financials, competition, etc.) |
| `src/research_prompt.py` | System prompts and orchestration instructions |
| `src/database.py` | MySQL connection pool, schema, CRUD operations |
| `src/report_storage.py` | Service layer for reports with chunking/embeddings |
| `src/report_chat_agent.py` | RAG-lite Q&A with stored reports |
| `src/pdf_generator.py` | PDF generation via WeasyPrint |

## Templates

- `templates/base.html` - Base layout with Tailwind config
- `templates/index.html` - Landing page with research form
- `templates/chat.html` - Live chat interface for agent interaction
- `templates/reports.html` - Report history with filtering/pagination
- `templates/report_view.html` - Single report view with PDF/share actions

## Development Commands

```bash
# Setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run
cd src && python app.py
# Server runs at http://127.0.0.1:5000

# Initialize database schema (happens automatically on first run)
python -c "from src.database import get_database_manager; get_database_manager()"
```

## Environment Variables (.env)

```bash
# Required
OPENAI_API_KEY=sk-...
MYSQL_USER=your_user
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=stock_research

# Optional
MYSQL_HOST=localhost
MYSQL_PORT=3306
FLASK_SECRET_KEY=random_secret

# Agent tuning
ORCHESTRATOR_MAX_OUTPUT_TOKENS=600
ORCHESTRATOR_MAX_TURNS=6
ORCHESTRATOR_MAX_HISTORY_MESSAGES=4
RESEARCH_MAX_WORKERS=3
AGENT_RATE_LIMIT_MAX_RETRIES=3
```

## Code Patterns

### Database Access
Always use `get_database_manager()` singleton. Connections are pooled and auto-returned.

```python
from database import get_database_manager
db = get_database_manager()
report = db.get_report(report_id)
```

### Agent Creation
Use `create_agent()` factory function which handles initialization.

```python
from agent import create_agent
agent = create_agent()
response = agent.start_research("AAPL", "Investment")
```

### Flask Sessions
Agent instances are keyed by session ID in `agent_sessions` dict. Session state stored in Flask's session object (conversation history, current ticker, report ID).

### Parallel Research
`ResearchOrchestrator.run_parallel_research()` uses ThreadPoolExecutor with configurable worker count (default 3) to run specialized agents concurrently.

## Database Schema

**reports** table:
- `report_id` (PK), `ticker`, `trade_type`, `report_text`, `metadata` (JSON), `created_at`

**report_chunks** table:
- `chunk_id` (PK), `report_id` (FK), `chunk_text`, `section`, `chunk_index`, `embedding` (JSON)

## Common Issues

1. **WeasyPrint not found**: Run `pip install weasyprint markdown`
2. **MySQL connection errors**: Check MYSQL_* env vars are set
3. **Rate limits**: Adjust `AGENT_RATE_LIMIT_*` and `RESEARCH_MAX_WORKERS` env vars
