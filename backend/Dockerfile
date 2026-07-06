# -*- coding: utf-8 -*-
# ============================================================
# Backend Dockerfile — FastAPI + Chroma + LLM Agent orchestration
# ============================================================
FROM python:3.10-slim

WORKDIR /app

# Install runtime system libraries needed by:
#   chromadb / onnxruntime / hnswlib  (build tools)
#   weasyprint                        (pango, cairo, gdk-pixbuf)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source (excludes are in .dockerignore)
COPY . .

# Ensure runtime directories exist
RUN mkdir -p /app/uploads /app/chroma_db

EXPOSE 8000

# Default: mock LLM — no API key needed, system works out of the box.
# Override via docker-compose environment variables when ready.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
