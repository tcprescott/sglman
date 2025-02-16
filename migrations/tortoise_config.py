import urllib.parse
import yaml

import config

TORTOISE_ORM = {
    "connections": {
        "default": f"mysql://{config.DATABASE['username']}:{urllib.parse.quote_plus(config.DATABASE['password'])}@{config.DATABASE['host']}:{config.DATABASE['port']}/{config.DATABASE['dbname']}"
    },
    "apps": {
        "models": {
            "models": ["models", "aerich.models"],
            "default_connection": "default",
        },
    },
}