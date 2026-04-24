from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.database import connect_db, close_db
from app.routers import chat, navigation, venue, media, search_history

@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    yield
    await close_db()

app = FastAPI(title="Maiz AI", version="1.0.0", lifespan=lifespan)
app.include_router(chat.router)
app.include_router(navigation.router)
app.include_router(venue.router)
app.include_router(media.router)
app.include_router(search_history.router)


@app.get("/health")
async def health():
    return {"status": "ok"}