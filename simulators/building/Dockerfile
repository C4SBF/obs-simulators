FROM python:3.12-slim-bookworm

# Set working directory
WORKDIR /app

# Enable bytecode compilation for uv
ENV UV_COMPILE_BYTECODE=1

# Install system dependencies for building Python packages (if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        && rm -rf /var/lib/apt/lists/*

# Install uv from PyPI
RUN pip install --no-cache-dir uv

# Copy dependency files for caching
COPY pyproject.toml uv.lock ./

# Sync dependencies with uv (if you use uv.lock for frozen dependencies)
RUN uv sync --frozen --no-install-project

# Copy application code
COPY . .

# Default entrypoint
ENTRYPOINT ["uv", "run", "building-simulator", "--"]
CMD ["--equipment", "ahu"]
