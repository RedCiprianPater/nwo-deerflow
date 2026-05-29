# =============================================================================
# NWO Deer-Flow · execution service · Dockerfile
# =============================================================================
# Builds the FastAPI service that actually runs Deer-Flow jobs.
#
# Render uses $PORT at runtime; we bind uvicorn to it. Locally:
#   docker build -t nwo-deerflow .
#   docker run -p 8001:8001 -e PORT=8001 -e OPENAI_API_KEY=sk-... nwo-deerflow
# =============================================================================

FROM python:3.11-slim

# System deps. Add build-essential / git here later if the real Deer-Flow
# harness needs to compile anything or pull from a git source.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY server.py .

# Render injects PORT; default to 8001 for local runs
ENV PORT=8001
EXPOSE 8001

# Healthcheck hits the liveness route
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://localhost:${PORT}/healthz" || exit 1

# Shell form so ${PORT} expands at runtime
CMD uvicorn server:app --host 0.0.0.0 --port ${PORT}
