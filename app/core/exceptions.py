from fastapi import HTTPException
from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
)


class BadRequestError(HTTPException):
    def __init__(self, detail: str = "Bad request"):
        super().__init__(status_code=HTTP_400_BAD_REQUEST, detail=detail)


class NotFoundError(HTTPException):
    def __init__(self, detail: str = "Not found"):
        super().__init__(status_code=HTTP_404_NOT_FOUND, detail=detail)


class ForbiddenError(HTTPException):
    def __init__(self, detail: str = "Forbidden"):
        super().__init__(status_code=HTTP_403_FORBIDDEN, detail=detail)