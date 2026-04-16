FROM python:3.11-slim AS base

# System deps for WeasyPrint (PDF generation) and psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    libcairo2 \
    libglib2.0-0 \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 20 for React build
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# React build
COPY stockpro-web/package.json stockpro-web/package-lock.json stockpro-web/
RUN cd stockpro-web && npm ci

COPY stockpro-web/ stockpro-web/
RUN cd stockpro-web && npm run build

# Copy the rest of the app
COPY . .

EXPOSE ${PORT:-5000}

CMD ["python", "src/app.py"]
