from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings

def get_mongo_client() -> AsyncIOMotorClient:
    return AsyncIOMotorClient(
        settings.MONGODB_URI,
        maxPoolSize=settings.MONGODB_MAX_POOL_SIZE,
        minPoolSize=settings.MONGODB_MIN_POOL_SIZE,
        serverSelectionTimeoutMS=settings.MONGODB_SERVER_SELECTION_TIMEOUT_MS,
    )

class Database:
    client: AsyncIOMotorClient = None

db_instance = Database()

def get_db():
    if db_instance.client is None:
        raise RuntimeError("Database client is not initialized")
    return db_instance.client[settings.MONGODB_DB_NAME]