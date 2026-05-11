FROM python:3.11-slim AS base

# System deps for WeasyPrint (PDF generation) and psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    libcairo2 \
    libglib2.0-0 \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the app (React SPA's dist/ is pre-built by GitHub Actions; see
# .github/workflows/build-frontend.yml). Railway no longer runs Node at deploy
# time — keeps the image small and avoids the prerender-plugin build hangs.
COPY . .

EXPOSE ${PORT:-5000}

CMD ["sh", "-c", "gunicorn -w 4 --threads 2 -k gthread -t 600 --pythonpath src --bind 0.0.0.0:${PORT:-5000} --access-logfile - --access-logformat '[pid=%(p)s] \"%(r)s\" %(s)s' app:app"]
