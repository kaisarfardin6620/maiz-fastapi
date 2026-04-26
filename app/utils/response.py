from typing import Any, Optional, TypeVar, Generic
from pydantic import BaseModel

T = TypeVar("T")

class APIResponse(BaseModel, Generic[T]):
    success: bool
    message: str
    data: Optional[T] = None

def success_response(data: Any = None, message: str = "Success") -> dict:
    return {"success": True, "message": message, "data": data}

def error_response(message: str = "Error", data: Any = None) -> dict:
    return {"success": False, "message": message, "data": data}