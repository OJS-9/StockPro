# Deployment Guide -- StockPro

---

## 1. Prerequisites

- **Python 3.10+**
- **PostgreSQL** (Supabase-hosted or local)
- **Node.js 18+** (for React SPA development only)
- **API keys**: Gemini, Alpha Vantage (see Environment Variables below)
- **Clerk account**: publishable key, secret key, JWT public key

---

## 2. Environment Variables

Create a `.env` file in the project root. See `.env.example` for the full template.

### Required

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string (Supabase pooler recommended, port 6543) |
| `CLERK_SECRET_KEY` | Clerk backend secret key |
| `CLERK_PUBLISHABLE_KEY` | Clerk publishable key (used by ClerkJS in templates) |
| `CLERK_JWT_KEY` | Clerk JWT public key (PEM format, for backend JWT verification) |
| `GEMINI_API_KEY` | Google GenAI API key (research agents + embeddings) |
| `FLASK_SECRET_KEY` | Secret for session signing. Must be fixed in production. |
| `ENCRYPTION_KEY` | 64-char hex string for AES-256-GCM field encryption. Generate: `python -c "import secrets; print(secrets.token_hex(32))"` |

### Optional

| Variable | Description |
|---|---|
| `PORT` | Flask port (default 5000) |
| `FLASK_HOST` | Bind address (default 127.0.0.1; use 0.0.0.0 for LAN) |
| `ALPHA_VANTAGE_API_KEY` | Alpha Vantage MCP (NEWS_SENTIMENT tool) |
| `NIMBLE_API_KEY` | Nimble web search + extraction |
| `TELEGRAM_BOT_TOKEN` | Telegram bot for alerts and /research |
| `LANGCHAIN_TRACING_V2` / `LANGSMITH_API_KEY` | LangSmith tracing (optional) |
| `SUPABASE_URL` / `SUPABASE_KEY` | If using supabase-py client directly |
| `STOCKPRO_FREE_TIER_REPORT_LIMIT` | Monthly report cap per user (default 3, 0 = unlimited) |

See `.env.example` for rate limits, research tuning, model overrides, spend budget, Alpaca, and ConvertKit vars.

---

## 3. Clerk Authentication

StockPro uses Clerk for auth. Routes: `/sign-in`, `/sign-up`, `/sign-out`, `/auth/sso-callback`.

### SSO Callback (required for Google OAuth)

After OAuth, Clerk redirects to `/auth/sso-callback` where ClerkJS sets the session cookie, then redirects to `/`.

**Add these redirect URLs in Clerk Dashboard:**

| Environment | Redirect URL |
|---|---|
| Local | `http://localhost:5000/auth/sso-callback` |
| Production | `https://<your-domain>/auth/sso-callback` |

---

## 4. Database Setup

StockPro uses PostgreSQL (Supabase-hosted). Schema is managed by `src/database.py`.

```bash
# Create/recreate all tables
python scripts/recreate_schema.py

# Or initialize schema only (if DB already exists)
python scripts/init_db.py
```

Use the Supabase **connection pooler** URI (transaction mode, port 6543) for the Flask app.

---

## 5. MCP Configuration

For Alpha Vantage data tools:

1. Copy `mcp.json.example` to `mcp.json`
2. Set the MCP server endpoint and Alpha Vantage API key

---

## 6. Install and Run

### Backend (Flask)

```bash
pip install -r requirements.txt
python src/app.py
```

Default: `http://127.0.0.1:5000`

### Frontend (React SPA -- development only)

```bash
cd stockpro-web
npm install
npm run dev
```

Dev server on `http://localhost:3000`, proxies `/api`, `/stream`, `/ws` to Flask on port 5000.

React SPA requires `VITE_CLERK_PUBLISHABLE_KEY` in `stockpro-web/.env`.

### WeasyPrint System Dependencies (PDF export)

WeasyPrint requires Pango and HarfBuzz. If PDF export returns a 500 error:

| Platform | Command |
|---|---|
| macOS (Homebrew) | `brew install pango harfbuzz` |
| macOS (Conda) | `conda install -c conda-forge pango harfbuzz` |
| Linux (Debian/Ubuntu) | `apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b` |

For Docker, add to Dockerfile:
```dockerfile
RUN apt-get update && apt-get install -y \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b \
    libcairo2 libgdk-pixbuf2.0-0 libffi-dev \
    && rm -rf /var/lib/apt/lists/*
```

---

## 7. Production Checklist

- [ ] Set `FLASK_SECRET_KEY` to a fixed random value
- [ ] Set `ENCRYPTION_KEY` to a fixed 64-char hex string
- [ ] Configure Clerk keys and add production SSO callback URL
- [ ] Point `DATABASE_URL` to production Supabase instance
- [ ] Run schema init once: `python scripts/recreate_schema.py`
- [ ] Run with `debug=False` behind a WSGI server (Gunicorn) + reverse proxy
- [ ] Use HTTPS -- Clerk and session cookies require it in production
- [ ] Install WeasyPrint system dependencies on the server
- [ ] Restrict database access (firewall, user grants)
- [ ] Keep `.env` out of version control

---

*Last updated: April 2026*
