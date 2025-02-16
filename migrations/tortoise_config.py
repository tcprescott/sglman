import urllib.parse
import yaml

app_config = yaml.load(open('config.yaml'), Loader=yaml.SafeLoader)

TORTOISE_ORM = {
    "connections": {
        "default": f"mysql://{app_config['database']['username']}:{urllib.parse.quote_plus(app_config['database']['password'])}@{app_config['database']['host']}:{app_config['database']['port']}/{app_config['database']['dbname']}"
    },
    "apps": {
        "models": {
            "models": ["models", "aerich.models"],
            "default_connection": "default",
        },
    },
}