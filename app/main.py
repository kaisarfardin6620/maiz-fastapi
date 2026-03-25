from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.database import connect_db, close_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    yield
    await close_db()


app = FastAPI(title="Maiz AI", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}