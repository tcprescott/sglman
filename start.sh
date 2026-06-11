#!/usr/bin/env bash

# use path of this example as working directory; enables starting this script from anywhere
cd "$(dirname "$0")"

# load .env file if it exists
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi


if [ "$1" = "prod" ]; then
    echo "Starting Uvicorn server in production mode..."
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