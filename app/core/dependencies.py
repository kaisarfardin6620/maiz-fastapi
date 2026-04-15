from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_404_NOT_FOUND
from bson import ObjectId

from app.core.auth import verify_token
from app.database import get_db

bearer_scheme = HTTPBearer()


async def resolve_user_from_token(token: str) -> dict:
    payload = verify_token(token)

    user_id = payload.get("id") or payload.get("_id") or payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    try:
        object_id = ObjectId(str(user_id))
    except Exception:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Invalid token subject")

    db = get_db()
    user = await db["users"].find_one({"_id": object_id, "isDeleted": {"$ne": True}})

    if not user:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="User not found")

    if user.get("status") == "blocked":
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Account is blocked")

    return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    return await resolve_user_from_token(credentials.credentials)