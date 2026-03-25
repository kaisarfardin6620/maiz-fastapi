from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_404_NOT_FOUND
from bson import ObjectId

from app.core.auth import verify_token
from app.database import get_db

bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    token = credentials.credentials
    payload = verify_token(token)

    user_id = payload.get("id") or payload.get("_id") or payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    db = get_db()
    user = await db["users"].find_one({"_id": ObjectId(user_id), "isDeleted": {"$ne": True}})

    if not user:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="User not found")

    if user.get("status") == "blocked":
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Account is blocked")

    return user