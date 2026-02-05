# Multi-stage Dockerfile for Agentic AI Scam Honeypot Backend

# ============================================================================
# Build Stage
# ============================================================================
FROM python:3.11-slim-bullseye as builder

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Install system dependencies for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt

# ============================================================================
# Runtime Stage
# ============================================================================
FROM python:3.11-slim-bullseye

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd -m -u 1000 -s /bin/bash appuser

# Copy virtual environment from builder
COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv

# Create application directory
WORKDIR /app
COPY --chown=appuser:appuser . .

# Create models directory with proper permissions
RUN mkdir -p models && chown -R appuser:appuser models

# Switch to non-root user
USER appuser

# Expose port (default 8000)
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# NOTE: This Dockerfile builds a CPU-only image. If you need GPU support,
# use the provided `Dockerfile.gpu` which is based on an NVIDIA CUDA runtime
# and accepts a build-arg `TORCH_WHEEL_URL` for installing a CUDA-enabled
# PyTorch wheel at build time.

# Copy entrypoint script that honors API_WORKERS and LOG_LEVEL
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Default entrypoint will read environment variables at runtime.
ENTRYPOINT ["/app/entrypoint.sh"]

