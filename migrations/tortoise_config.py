import urllib.parse
import os

from dotenv import load_dotenv

load_dotenv()

username = os.environ.get("DB_USERNAME", '')
password = os.environ.get("DB_PASSWORD", '')
host = os.environ.get("DB_HOST")
port = os.environ.get("DB_PORT")
dbname = os.environ.get("DB_NAME")

if not all([host, port, dbname]):
    raise ValueError("Database configuration is incomplete. Please set DB_HOST, DB_PORT, and DB_NAME environment variables.")

TORTOISE_ORM = {
    "connections": {
        "default": f"mysql://{username}:{urllib.parse.quote_plus((password).encode())}@{host}:{port}/{dbname}"
    },
    "apps": {
        "models": {
            "models": ["models", "aerich.models"],
            "default_connection": "default",
        },
    },
}