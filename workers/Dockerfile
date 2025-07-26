FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies including DataLad dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    git \
    git-annex \
    curl \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

# Install DataLad
RUN pip install datalad

# Copy dependency files
COPY pyproject.toml ./

# Install Python dependencies
RUN uv sync --frozen

# Copy application code
COPY . .

# Set Python path
ENV PYTHONPATH=/app

# Default command
CMD ["celery", "-A", "app.worker", "worker", "--loglevel=info"]