import os
import urllib.parse

from dotenv import load_dotenv

load_dotenv()

username = os.environ.get("DB_USERNAME", '')
password = os.environ.get("DB_PASSWORD", '')
host = os.environ.get("DB_HOST")
port = os.environ.get("DB_PORT")
dbname = os.environ.get("DB_NAME")

if not all([host, port, dbname]):
    raise ValueError("Database configuration is incomplete. Please set DB_HOST, DB_PORT, and DB_NAME environment variables.")

if os.environ.get("ENVIRONMENT", "development").strip().lower() == "production" and not (username.strip() and password.strip()):
    raise ValueError("DB_USERNAME and DB_PASSWORD must be set in production.")

TORTOISE_ORM = {
    "connections": {
        "default": f"postgres://{username}:{urllib.parse.quote_plus((password).encode())}@{host}:{port}/{dbname}"
    },
    "apps": {
        "models": {
            "models": ["models", "aerich.models"],
            "default_connection": "default",
        },
    },
}