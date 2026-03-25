from jose import JWTError, jwt
from fastapi import HTTPException
from starlette.status import HTTP_401_UNAUTHORIZED
from app.config import settings


def verify_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )