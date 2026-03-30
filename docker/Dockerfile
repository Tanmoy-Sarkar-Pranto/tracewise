FROM python:3.12-slim

RUN pip install uv

# Keep venv outside /app so the dev volume mount doesn't overwrite it
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV UV_LINK_MODE=copy

# Create non-root user, /app, and /opt/venv — all as root, then hand over
RUN useradd -m -u 1000 appuser \
    && mkdir -p /app /opt/venv \
    && chown appuser:appuser /app /opt/venv

USER appuser
WORKDIR /app

# Install dependencies first (without the project itself) for layer caching
COPY --chown=appuser:appuser pyproject.toml ./
RUN uv sync --extra dev --no-install-project

# Copy source, then install the project itself
COPY --chown=appuser:appuser . .
RUN uv sync --extra dev

EXPOSE 8000

# No --reload here: use docker-compose command override for dev
CMD ["uv", "run", "uvicorn", "tests.testapp.main:app", "--host", "0.0.0.0", "--port", "8000"]
