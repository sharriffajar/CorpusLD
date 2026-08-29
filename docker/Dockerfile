# ==============================================================================
# CorpusLD Studio - Production Multi-Stage Dockerfile
# ==============================================================================

FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-lock.txt ./
RUN pip install --no-cache-dir --user -r requirements-lock.txt

# Final Runtime Image
FROM python:3.11-slim AS runtime

WORKDIR /app

# Install minimal OS dependencies for PDF parsing & HTTP healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder stage
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Copy application source code
COPY config.py server.py cli.py ./
COPY json_ld_extractor/ ./json_ld_extractor/
COPY corpusld_engine/ ./corpusld_engine/
COPY services/ ./services/
COPY routes/ ./routes/
COPY frontend/ ./frontend/

# Create persistent storage directories
RUN mkdir -p /app/uploads /app/qdrant_db

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
