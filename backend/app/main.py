import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis import Redis
from sqlalchemy import text
from starlette.exceptions import HTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.brand import router as brand_router
from app.config import get_settings
from app.db import engine
from app.generation import router as generation_router
from app.knowledge import router as knowledge_router
from app.posts import router as posts_router
from app.recheck import router as recheck_router
from app.topic_suggestions import router as topic_suggestions_router
from app.write_guard import write_rejection

app = FastAPI(title="Social Platform", version="0.1.0")
app.include_router(brand_router)
app.include_router(knowledge_router)
app.include_router(generation_router)
app.include_router(posts_router)
app.include_router(recheck_router)
app.include_router(topic_suggestions_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
    expose_headers=["X-Request-ID"],
)
app.add_middleware(
    TrustedHostMiddleware, allowed_hosts=get_settings().allowed_hosts, www_redirect=False
)
logger = logging.getLogger(__name__)


def error(request: Request, status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {"code": code, "message": message, "request_id": request.state.request_id}
        },
        headers={"X-Request-ID": request.state.request_id},
    )


@app.middleware("http")
async def reject_cross_site_writes(request: Request, call_next):
    # Runs inside request_context, so rejections carry the request ID; never reaches a handler.
    rejection = write_rejection(
        request.method, request.headers, get_settings().cors_origins, request.url.path
    )
    if rejection is None:
        return await call_next(request)
    status, code = rejection
    return error(request, status, code, code)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.request_id = str(uuid4())
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("unhandled_request_error", extra={"request_id": request.state.request_id})
        return error(request, 500, "internal_error", "An unexpected error occurred.")
    response.headers["X-Request-ID"] = request.state.request_id
    return response


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return error(request, exc.status_code, "http_error", str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return error(request, 422, "validation_error", "The request contains invalid values.")


@app.get("/health/live")
def live():
    return {"status": "alive"}


@app.get("/health/ready")
def ready(request: Request):
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1 FROM alembic_version"))
        with Redis.from_url(
            get_settings().redis_url, socket_connect_timeout=2, socket_timeout=2
        ) as redis:
            redis.ping()
    except Exception:
        return error(request, 503, "dependencies_unavailable", "Required services are unavailable.")
    return {"status": "ready"}


# Local scope is server-owned. Never enable these unauthenticated endpoints in production.
if get_settings().environment == "development":
    from app.dev import router

    app.include_router(router)
