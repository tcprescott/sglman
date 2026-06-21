# Dockerfile for SGLMan (FastAPI + NiceGUI)
FROM python:3.12-slim

# Set workdir
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y build-essential libpq-dev && rm -rf /var/lib/apt/lists/*

# Copy poetry files and install dependencies
COPY pyproject.toml poetry.lock ./
# --only main keeps test/dev tooling out of the runtime image (smaller image,
# smaller attack surface).
RUN pip install --no-cache-dir poetry && poetry config virtualenvs.create false && poetry install --only main --no-interaction --no-ansi

# Copy app code
COPY . .

# Run as an unprivileged user rather than root
RUN useradd --create-home --uid 10001 appuser \
    && chmod +x start.sh \
    && chown -R appuser:appuser /app
USER appuser

# Expose port (default: 8000)
EXPOSE 8000

# Entrypoint
CMD ["./start.sh", "prod"]
