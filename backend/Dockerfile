# 이사이상무 backend — FastAPI on Python 3.12 slim
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps
# Cache bust: 2026-04-15 — openai 1.55 → 2.31 (httpx 0.28 호환)
ARG DEPS_CACHEBUST=2026-04-15-openai231
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --upgrade --force-reinstall -r /app/backend/requirements.txt

# App code & curated data
COPY backend/app /app/backend/app
COPY backend/data/indexes /app/backend/data/indexes
COPY backend/data/raw/holidays_2026.json /app/backend/data/raw/holidays_2026.json

# Runtime
ENV PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT}"]
