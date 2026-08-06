"""Application error hierarchy and RFC 9457 problem-detail responses."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

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


class InvalidTokenError(AppError):
    """Invalid/expired one-time token (reset, invitation)."""

    status_code = 400
    code = "invalid_token"
    message_key = "error.invalid_token"


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
            headers=_error_headers(exc),
        )


def _error_headers(exc: AppError) -> dict[str, str] | None:
    if exc.status_code == 401:
        return {"WWW-Authenticate": "Bearer"}
    # RFC 9110: a 429 tells the caller when to come back, in a header a
    # generic HTTP client can honour without parsing the body.
    retry_after = getattr(exc, "retry_after", None)
    if exc.status_code == 429 and retry_after is not None:
        return {"Retry-After": str(retry_after)}
    return None


# --- The error contract, published (API-001) --------------------------------
#
# The platform has always RETURNED RFC 9457 problem details. It has never
# DOCUMENTED them: the OpenAPI schema declared exactly one non-2xx response —
# FastAPI's automatic 422 — so a generated client had no type for 401, 403,
# 404, 409 or 429 and no way to know they were possible.
#
# For an internal API that is untidy. For a public SaaS it is a defect: every
# client generator produces code that treats an error body as an unknown
# shape, and every integrator discovers the real contract by causing errors in
# production.
#
# These declarations are applied centrally (see `problem_responses` and its
# use in `main.create_app`), not repeated on 177 routes — a per-route list is
# a list that drifts.


class ProblemDetail(BaseModel):
    """RFC 9457 problem details — the shape of every error this API returns."""

    type: str = Field(
        description="A URI identifying the error class. Stable; safe to branch on.",
        examples=["https://docs.lacteva.example/errors/conflict"],
    )
    title: str = Field(description="The error code, in a fixed vocabulary.", examples=["conflict"])
    status: int = Field(description="The HTTP status code, repeated for convenience.")
    detail: str = Field(
        description=(
            "A human-readable explanation, TRANSLATED into the caller's locale. "
            "Display it; never branch on it — it changes with language."
        )
    )
    extra: dict | None = Field(
        default=None,
        description=(
            "Machine-readable specifics, when the error class has any: the "
            "conflicting field, the pricing resolution stage, the retry budget."
        ),
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "type": "https://docs.lacteva.example/errors/conflict",
                "title": "conflict",
                "status": 409,
                "detail": "A published rate card cannot be modified.",
                "extra": {"rate_card_id": "…", "status": "published"},
            }
        }
    }


_PROBLEM = {"application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemDetail"}}}

#: Codes ANY authenticated operation can return.
UNIVERSAL_PROBLEMS: dict[int | str, dict] = {
    401: {"description": "No credentials, or a token that does not verify.", "content": _PROBLEM},
    403: {
        "description": "Authenticated, but lacking the required permission.",
        "content": _PROBLEM,
    },
    422: {"description": "The request body or parameters failed validation.", "content": _PROBLEM},
    429: {
        "description": (
            "Rate limit exceeded. `Retry-After` says when to come back; honour it "
            "rather than retrying immediately."
        ),
        "content": _PROBLEM,
    },
}

#: Adds when the operation addresses a specific resource.
NOT_FOUND_PROBLEM: dict[int | str, dict] = {
    404: {
        "description": (
            "No such resource IN THIS TENANT. A resource that exists for another "
            "tenant is a 404, never a 403 — the API does not reveal that it exists."
        ),
        "content": _PROBLEM,
    }
}

#: Adds when the operation mutates.
CONFLICT_PROBLEM: dict[int | str, dict] = {
    409: {
        "description": (
            "The operation contradicts the resource's current state — a duplicate "
            "unique value, or a state transition the lifecycle does not allow. "
            "Retrying without changing anything will fail identically."
        ),
        "content": _PROBLEM,
    }
}


def problem_responses(*, not_found: bool = False, conflict: bool = False) -> dict:
    """The error responses for one operation."""
    responses = dict(UNIVERSAL_PROBLEMS)
    if not_found:
        responses |= NOT_FOUND_PROBLEM
    if conflict:
        responses |= CONFLICT_PROBLEM
    return responses
