# Deployment Guide — StockIntel

Steps required to run the app locally and to deploy it to production.

---

## 1. Prerequisites

- **Python 3.10+**
- **MySQL** (server running, accessible)
- **API keys**: Gemini, Perplexity, Alpha Vantage (see Environment Variables below)

---

## 2. Environment Variables

Create a `.env` file in the project root (or set these in your host’s environment).

### Required

| Variable | Description |
|---------|-------------|
| `GEMINI_API_KEY` | Google GenAI API key |
| `PERPLEXITY_API_KEY` | Perplexity Sonar API key |
| `ALPHA_VANTAGE_API_KEY` | Alpha Vantage API key |
| `MYSQL_HOST` | MySQL host (e.g. `localhost` or your DB host) |
| `MYSQL_USER` | MySQL user |
| `MYSQL_PASSWORD` | MySQL password |
| `MYSQL_DATABASE` | Database name (e.g. `stock_research`) |
| `FLASK_SECRET_KEY` | Secret for session signing. **Must be set in production** — use a long random string; if unset, a new key is generated on each restart and sessions break. |

### Optional

| Variable | Description |
|----------|-------------|
| `MYSQL_PORT` | MySQL port (default `3306`) |
| `RESEARCH_MAX_WORKERS` | ThreadPoolExecutor concurrency (default `3`) |
| `PLANNER_MAX_SUBJECTS` | Max subjects for planner (default `8`) |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID (see Redirect URI section below) |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret |

---

## 3. Google OAuth — Redirect URI (Google Cloud Console)

To use “Sign in with Google,” configure OAuth 2.0 in [Google Cloud Console](https://console.cloud.google.com/) and set the **Authorized redirect URIs** for your OAuth client.

### What to put in the “URI” field

The redirect URI is the **full URL** where Google sends the user after they approve sign-in. The app’s callback path is `/login/google/callback`.

| Environment | Authorized redirect URI to add |
|-------------|--------------------------------|
| **Local**   | `http://localhost:5000/login/google/callback` |
| **Production** | `https://<your-domain>/login/google/callback` |

Examples for production:

- `https://stockintel.example.com/login/google/callback`
- `https://app.example.com/login/google/callback`

### Steps in Google Cloud Console

1. Open **APIs & Services** → **Credentials**.
2. Create or edit an **OAuth 2.0 Client ID** (application type: **Web application**).
3. Under **Authorized redirect URIs**, add:
   - For local: `http://localhost:5000/login/google/callback`
   - For production: `https://<your-domain>/login/google/callback` (HTTPS required for non-localhost).
4. Save. Copy **Client ID** and **Client secret** into `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env` (or your production env).

### When deploying

- Add the **production** redirect URI to the same OAuth client (you can have both local and production URIs).
- Ensure the production URL uses **HTTPS**; Google will reject `http://` for non-localhost.
- If the OAuth consent screen is in “Testing,” add test users or publish the app for broader access; add your production domain to authorized domains if required.

---

## 4. Database Setup

1. **Create the database** (if it does not exist):

   ```bash
   python recreate_schema.py
   ```

   This creates `MYSQL_DATABASE` if missing and initializes all tables (including users with `google_id` and nullable `password_hash`).

2. **Or only initialize schema** (database already exists):

   ```bash
   python init_db.py
   ```

   This uses `get_database_manager()`, which runs `init_schema()` and applies any inline migrations (e.g. adding `google_id` to existing `users` tables).

---

## 5. MCP Configuration

For Alpha Vantage data:

1. Copy `mcp.json.example` to `mcp.json`.
2. Set the MCP server endpoint and Alpha Vantage API key in `mcp.json`.

---

## 6. Install Dependencies and Run

```bash
# From project root
pip install -r requirements.txt

# Run the Flask app
python src/app.py
```

Default: app listens on `http://127.0.0.1:5000`. Open that URL in a browser.

### WeasyPrint system dependencies (PDF export)

WeasyPrint requires Pango and HarfBuzz system libraries. If the PDF download returns a 500 error with `cannot load library 'libpango-1.0-0'`, install the missing libraries:

**macOS (Anaconda Python)**

```bash
conda install -c conda-forge pango harfbuzz
```

**macOS (Homebrew Python / pyenv)**

```bash
brew install pango harfbuzz
```

**Linux (Debian/Ubuntu)**

```bash
apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b
```

**Linux (production server / Docker)**

Add to your Dockerfile or server provisioning script:

```dockerfile
RUN apt-get update && apt-get install -y \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b \
    libcairo2 libgdk-pixbuf2.0-0 libffi-dev \
    && rm -rf /var/lib/apt/lists/*
```

---

## 7. Production Deployment Checklist

- [ ] Set **FLASK_SECRET_KEY** to a fixed, random value (do not leave unset).
- [ ] Set **GOOGLE_CLIENT_ID** and **GOOGLE_CLIENT_SECRET** and add the **production redirect URI** in Google Cloud Console (see section 3).
- [ ] Use **HTTPS** for the public site; production redirect URI must be `https://...`.
- [ ] Point **MYSQL_*** to the production MySQL instance (host, user, password, database).
- [ ] Run **schema init** against the production DB once (`python recreate_schema.py` or `init_db.py` after DB exists).
- [ ] Run the app with **debug=False** and bind to the correct host/port (e.g. via Gunicorn/uWSGI behind a reverse proxy; avoid `debug=True` in production).
- [ ] Restrict **MYSQL** access (firewall, user grants) and keep `.env` and secrets out of version control.
- [ ] Install **WeasyPrint system dependencies** on the server (`libpango`, `libharfbuzz`, `libcairo`) — see section 6 for platform-specific commands.

---

## 8. Summary

| Step | Local | Production |
|------|--------|------------|
| Env vars | `.env` with required + optional (incl. Google OAuth if used) | Same vars in host env or secrets manager |
| Redirect URI | `http://localhost:5000/login/google/callback` in Google Console | `https://<domain>/login/google/callback` in Google Console |
| Database | `recreate_schema.py` or `init_db.py` | Same, run once against prod DB |
| Run | `python src/app.py` | WSGI server (e.g. Gunicorn) with `debug=False`, HTTPS in front |
