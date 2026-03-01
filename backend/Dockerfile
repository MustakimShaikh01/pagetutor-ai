# ============================================================
# PageTutor AI - Backend Dockerfile
# Author: Mustakim Shaikh (https://github.com/MustakimShaikh01)
#
# Multi-stage build:
#   Stage 1 (builder): Install Python deps with pip
#   Stage 2 (runtime): Minimal image with no build tools
#
# Optimization:
#   - Non-root user for security
#   - .dockerignore excludes unnecessary files
#   - Layer caching for requirements.txt
# ============================================================

# Stage 1: Build dependencies
FROM python:3.11-slim AS builder

# Install system dependencies for audio/video/PDF processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libmagic1 \
    libmagic-dev \
    ffmpeg \
    libsndfile1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy requirements first (cache layer optimization)
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --user -r requirements.txt


# Stage 2: Production runtime
FROM python:3.11-slim AS runtime

# Runtime system deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libmagic1 \
    ffmpeg \
    libsndfile1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user (security best practice)
RUN groupadd -r pagetutor && useradd -r -g pagetutor pagetutor

# Copy Python packages from builder
COPY --from=builder /root/.local /home/pagetutor/.local

WORKDIR /app

# Copy application source
COPY --chown=pagetutor:pagetutor . .

# Switch to non-root user
USER pagetutor

# Add local packages to PATH
ENV PATH=/home/pagetutor/.local/bin:$PATH
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose API port
EXPOSE 8000

# Run uvicorn with production settings
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--loop", "uvloop", \
     "--http", "httptools", \
     "--log-level", "info", \
     "--access-log"]
