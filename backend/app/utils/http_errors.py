"""Helpers for raising structured HTTP errors."""

from fastapi import HTTPException


def api_error(status_code: int, message: str, code: int, data=None) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"message": message, "code": code, "data": data},
    )
