"""FastAPI entrypoint: middleware (request IDs, access log, error handling), routers, static UI."""
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError

from .api import insights, items, knowledge, meetings
from .config import settings
from .db import Base, SessionLocal, engine
from .logging_setup import get_logger, request_id_var, setup_logging
from .services.ai_client import provider_info

setup_logging()
log = get_logger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    if settings.seed_on_start:
        from .seed import seed_if_empty

        with SessionLocal() as db:
            seed_if_empty(db)
    log.info("app.started", env=settings.env, db=settings.database_url.split(":")[0], ai=provider_info(), log_file=settings.log_file)
    yield
    log.info("app.stopped")


app = FastAPI(title=settings.app_name, version="1.0.0", description="Capture decisions, hand over context, close the loop.", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Request-ID"])


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Assign a correlation ID (or reuse the caller's) and log one access line per API request."""
    incoming = request.headers.get("X-Request-ID", "")
    rid = incoming if 0 < len(incoming) <= 64 and incoming.replace("-", "").isalnum() else uuid.uuid4().hex[:16]
    token = request_id_var.set(rid)
    start = time.perf_counter()
    try:
        response = await call_next(request)
        duration = int((time.perf_counter() - start) * 1000)
        response.headers["X-Request-ID"] = rid
        if request.url.path.startswith("/api"):
            level = log.warning if response.status_code >= 400 else log.info
            level("http.request", method=request.method, path=request.url.path, status=response.status_code, duration_ms=duration)
        return response
    finally:
        request_id_var.reset(token)


def _error(status: int, message: str, details=None):
    return JSONResponse(status_code=status, content={"error": message, "details": details, "request_id": request_id_var.get()})


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return _error(exc.status_code, str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    details = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
    log.info("validation.failed", path=request.url.path, fields=[d["field"] for d in details])
    msg = "; ".join(f"{d['field'] or 'body'}: {d['message']}" for d in details[:3])
    return _error(422, f"Invalid input — {msg}", details)


@app.exception_handler(SQLAlchemyError)
async def db_error(request: Request, exc: SQLAlchemyError):
    log.error("db.error", path=request.url.path, error_type=type(exc).__name__, exc_info=exc)
    return _error(500, "A database error occurred. Please try again.")


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.error("unhandled.error", path=request.url.path, method=request.method, error_type=type(exc).__name__, exc_info=exc)
    return _error(500, "Something went wrong on our side. Quote the request ID if you report it.")


app.include_router(meetings.router)
app.include_router(items.router)
app.include_router(knowledge.router)
app.include_router(insights.router)


# ---- Serve the built React app (single deployable unit) ----
static_dir = Path(settings.static_dir)
if static_dir.exists():
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404, "Not found")
        target = static_dir / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        return FileResponse(static_dir / "index.html")
