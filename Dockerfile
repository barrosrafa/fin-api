FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

COPY pyproject.toml README.md ./
RUN uv pip install --system -e .

COPY app ./app

EXPOSE 8000

# Default entrypoint runs the HTTP server (dynamically binds to $PORT or 8000)
CMD ["python", "-m", "app.cli", "serve", "--host", "0.0.0.0"]
