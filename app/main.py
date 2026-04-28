import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import db_instance, get_mongo_client
from app.mcp.router import router as mcp_router
from app.redis_client import redis_client
from app.routers import chat, media, navigation

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        client = get_mongo_client()
        await client.admin.command("ping")
        db_instance.client = client
        app.state.mongodb_client = client
        logger.info("MongoDB connection established")

        await redis_client.ping()
        logger.info("Redis connection established")
    except Exception:
        logger.exception("Failed to connect to databases")
        raise

    yield

    if db_instance.client:
        db_instance.client.close()
    await redis_client.aclose()


app = FastAPI(title="Maiz AI", version="1.0.0", lifespan=lifespan)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url)
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": "An unexpected error occurred."},
    )


allow_all_origins = "*" in settings.CORS_ALLOW_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS,
    allow_credentials=not allow_all_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(navigation.router)
app.include_router(media.router)
app.include_router(mcp_router)


@app.get("/health")
async def health():
    return {"status": "ok"}