#!/usr/bin/env python3
import yaml
from tortoise import Tortoise
from fastapi import FastAPI
import frontend
import api
from contextlib import asynccontextmanager
from migrations.tortoise_config import TORTOISE_ORM

async def init_db():
    await Tortoise.init(config=TORTOISE_ORM)
    await Tortoise.generate_schemas()

async def close_db():
    await Tortoise.close_connections()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_db()

app = FastAPI(lifespan=lifespan)
app.include_router(
    api.router,
    prefix='/api',
    tags=['api'],
)

frontend.init(app)

if __name__ == '__main__':
    print('Please start the app with the "uvicorn" command as shown in the start.sh script')