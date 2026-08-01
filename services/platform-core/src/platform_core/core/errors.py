"""Application error hierarchy and RFC 9457 problem-detail responses."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from platform_core.core.i18n import translate


class AppError(Exception):
    status_code = 500
    code = "internal_error"
    message_key = "error.internal"

    def __init__(self, detail: str | None = None):
        self.detail = detail
        super().__init__(detail or self.code)


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    message_key = "error.not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    message_key = "error.conflict"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"
    message_key = "error.unauthorized"


class InvalidCredentialsError(UnauthorizedError):
    code = "invalid_credentials"
    message_key = "error.invalid_credentials"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"
    message_key = "error.forbidden"


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "type": f"https://docs.lacteva.example/errors/{exc.code}",
                "title": exc.code,
                "status": exc.status_code,
                "detail": translate(exc.message_key),
                "extra": exc.detail,
            },
            media_type="application/problem+json",
            headers={"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None,
        )
