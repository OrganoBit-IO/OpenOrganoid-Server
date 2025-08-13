FROM python:3.12-slim

# Set working directory to api subdirectory
WORKDIR /app/api

# Install system dependencies including DataLad requirements
RUN apt-get update && apt-get install -y \
    git \
    git-annex \
    curl \
    wget \
    build-essential \
    libpq-dev \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster dependency management
RUN pip install uv

# Copy api dependency files first
COPY api/pyproject.toml api/uv.lock ./

# Install dependencies (uv will create .venv automatically)
RUN uv sync --frozen

# Copy api application code
COPY api/ .

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash openorganoid && \
    chown -R openorganoid:openorganoid /app

# Switch to non-root user
USER openorganoid

# Configure git for DataLad operations
RUN git config --global user.name "OpenOrganoid System" && \
    git config --global user.email "system@openorganoid.com" && \
    git config --global init.defaultBranch main

# Create necessary directories
RUN mkdir -p /app/data/datalad /app/data/storage /app/data/uploads

# Expose port (Railway automatically detects this)
EXPOSE 8000

# Set Python path to include api directory and activate venv
ENV PYTHONPATH=/app/api
ENV PATH="/app/api/.venv/bin:$PATH"

# Health check - use PORT environment variable
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Use gunicorn for production deployment - Railway provides PORT env var
CMD gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:${PORT:-8000} --timeout 120