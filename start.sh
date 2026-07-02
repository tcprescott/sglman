#!/usr/bin/env bash

# use path of this example as working directory; enables starting this script from anywhere
cd "$(dirname "$0")"

# load .env file if it exists (auto-export each assignment; avoids word-splitting)
if [ -f .env ]; then
    set -a
    . ./.env
    set +a
fi


if [ "$1" = "prod" ]; then
    echo "Starting Uvicorn server in production mode..."
    # Force production security posture (hidden API docs, HSTS, strict
    # STORAGE_SECRET/DB-credential checks, mock-mode refusal) rather than
    # depending on the operator's .env to set it.
    export ENVIRONMENT=production
    poetry run uvicorn main:app --workers 1 --log-level info --port 8000 --host 0.0.0.0
elif [ "$1" = "dev" ]; then
    echo "Starting Uvicorn server in development mode..."
    poetry run uvicorn main:app --reload --log-level info --port 8000
elif [ "$1" = "mock" ]; then
    echo "Starting Uvicorn server in development mode with mocked Discord and Challonge..."
    # Mock bypasses are refused unless we're explicitly not in production.
    export ENVIRONMENT=development
    export MOCK_DISCORD=true
    export MOCK_CHALLONGE=true
    poetry run uvicorn main:app --reload --log-level info --port 8000
else
    echo "Invalid parameter. Use 'prod', 'dev', or 'mock'."
    exit 1
fi