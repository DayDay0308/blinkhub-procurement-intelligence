"""One error format for every failure, so the frontend handles errors in one place:

{"error": {"code": "NOT_FOUND", "message": "...", "details": ...}}
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

log = logging.getLogger(__name__)


class AppError(Exception):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "BAD_REQUEST"

    def __init__(self, message: str, details: object | None = None):
        super().__init__(message)
        self.message = message
        self.details = details


class NotFound(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "NOT_FOUND"


class Conflict(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "CONFLICT"


class Unauthorized(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "UNAUTHORIZED"


class Forbidden(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "FORBIDDEN"


def _body(code: str, message: str, details: object | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError):
        headers = {"WWW-Authenticate": "Bearer"} if isinstance(exc, Unauthorized) else None
        return JSONResponse(
            _body(exc.code, exc.message, exc.details), exc.status_code, headers=headers
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        details = [
            {"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]}
            for e in exc.errors()
        ]
        return JSONResponse(
            _body("VALIDATION_ERROR", "Some fields are invalid.", details),
            422,
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error(_: Request, exc: IntegrityError):
        # Database constraints are the last line of defence for business rules.
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        log.warning("integrity_error constraint=%s", constraint)
        return JSONResponse(
            _body("CONFLICT", "This change breaks a data rule.", {"constraint": constraint}),
            status.HTTP_409_CONFLICT,
        )

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        log.exception("unhandled_error")
        return JSONResponse(
            _body("INTERNAL_ERROR", "Something went wrong."),
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
