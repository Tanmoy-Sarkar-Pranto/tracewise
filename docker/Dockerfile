FROM python:3.12-slim

RUN pip install uv

# Create non-root user
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Copy dependency manifest first for layer caching
COPY pyproject.toml ./
RUN uv sync --extra dev

# Copy source after deps are installed
COPY . .

# Fix ownership
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# No --reload here: use docker-compose command override for dev
CMD ["uv", "run", "uvicorn", "tests.testapp.main:app", "--host", "0.0.0.0", "--port", "8000"]
