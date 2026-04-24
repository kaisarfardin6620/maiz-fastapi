from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from app.database import connect_db, close_db
from app.config import settings
from app.mcp import router as mcp_router
from app.routers import chat, navigation, venue, media, search_history


logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await connect_db()
        logger.info("MongoDB connection established")
    except Exception:
        logger.exception("Failed to connect to MongoDB")
        raise
    yield
    await close_db()

app = FastAPI(title="Maiz AI", version="1.0.0", lifespan=lifespan)
allow_all_origins = len(settings.CORS_ALLOW_ORIGINS) == 1 and settings.CORS_ALLOW_ORIGINS[0] == "*"
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS,
    allow_credentials=not allow_all_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(navigation.router)
app.include_router(venue.router)
app.include_router(media.router)
app.include_router(search_history.router)
app.include_router(mcp_router)


@app.get("/health")
async def health():
    return {"status": "ok"}