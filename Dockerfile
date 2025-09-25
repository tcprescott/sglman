# Dockerfile for SGLMan (FastAPI + NiceGUI)
FROM python:3.12-slim

# Set workdir
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y build-essential libmariadb-dev && rm -rf /var/lib/apt/lists/*

# Copy poetry files and install dependencies
COPY pyproject.toml poetry.lock ./
RUN pip install --no-cache-dir poetry && poetry config virtualenvs.create false && poetry install --no-interaction --no-ansi

# Copy app code
COPY . .

# Expose port (default: 8080)
EXPOSE 8080

# Entrypoint
CMD ["./start.sh", "prod"]
