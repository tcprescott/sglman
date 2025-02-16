#!/usr/bin/env python3
import yaml
from sqlalchemy import create_engine
from alembic import command, config

app_config = yaml.load(open('config.yaml'), Loader=yaml.SafeLoader)
engine = create_engine(
    f"mysql+pymysql://{app_config['database']['username']}:{app_config['database']['password']}@{app_config['database']['host']}/{app_config['database']['dbname']}",
    echo=True
)

cfg = config.Config('alembic.ini')

with engine.connect() as connection:
    cfg.attributes['connection'] = connection
    command.upgrade(cfg, 'head')

from fastapi import FastAPI
import frontend
import api

app = FastAPI()
app.include_router(
    api.router,
    prefix='/api',
    tags=['api'],
)

frontend.init(app)

if __name__ == '__main__':
    print('Please start the app with the "uvicorn" command as shown in the start.sh script')