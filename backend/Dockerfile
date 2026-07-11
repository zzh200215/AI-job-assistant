# -*- coding: utf-8 -*-
# ============================================================
# Backend Dockerfile — FastAPI + Chroma + LLM Agent orchestration
# Production-hardened: multi-stage, non-root user, healthcheck
# ============================================================

# ---- Stage 1: builder (compile dependencies) ----
FROM python:3.10-slim-bookworm AS builder

WORKDIR /build

# Install build tools needed by chromadb / onnxruntime / hnswlib
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ---- Stage 2: runtime ----
FROM python:3.10-slim-bookworm

# Install runtime libraries needed by weasyprint (pango, cairo, gdk-pixbuf)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root runtime user
RUN groupadd -r app --gid=1000 && useradd -r -g app --uid=1000 app

WORKDIR /app

# Copy Python environment from builder
COPY --from=builder /root/.local /home/app/.local
ENV PATH=/home/app/.local/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Copy application source
COPY --chown=app:app . .

# Ensure runtime directories exist and are writable by app user
RUN mkdir -p /app/uploads /app/chroma_db \
    && chown -R app:app /app /home/app

USER app

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/').read()"

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
