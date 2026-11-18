import logging
from contextlib import asynccontextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy.exc import SQLAlchemyError

# Compatibility patch for FastAPI >= 0.163 with prometheus-fastapi-instrumentator
try:
    from fastapi.routing import _IncludedRouter
    if not hasattr(_IncludedRouter, "path"):
        _IncludedRouter.path = property(lambda self: getattr(self.include_context, "prefix", ""))
    if not hasattr(_IncludedRouter, "routes"):
        _IncludedRouter.routes = property(lambda self: getattr(self.original_router, "routes", []))
except (ImportError, AttributeError):
    pass

import app.core.metrics  # noqa: F401 (registers custom Prometheus metrics)
from app.api.v1 import (
    admin,
    ai,
    auth,
    exercises,
    files,
    notes,
    progress,
    quizzes,
    recommendations,
    submissions,
    users,
)
from app.core.config import settings
from app.core.scheduler import start_scheduler, stop_scheduler
from app.db.base import Base
from app.db.session import engine
from app.models import (  # noqa: F401  (registers the tables)
    exercise,
    note,
    project_file,
    quiz,
    submission,
    test_case,
    user,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.environment.lower() != "testing":
        # Automatically apply database migrations on startup if alembic.ini is present
        alembic_ini_path = Path("alembic.ini")
        if not alembic_ini_path.exists():
            alembic_ini_path = Path(__file__).resolve().parents[2] / "backend" / "alembic.ini"
        if alembic_ini_path.exists():
            try:
                alembic_cfg = Config(str(alembic_ini_path))
                command.upgrade(alembic_cfg, "head")
                logger.info("Alembic database migrations applied successfully on startup.")
            except Exception as exc:
                logger.warning("Could not apply Alembic migrations on startup: %s", exc)
                try:
                    Base.metadata.create_all(bind=engine)
                except Exception as e:
                    logger.warning("Could not auto-create tables: %s", e)
        else:
            try:
                Base.metadata.create_all(bind=engine)
            except Exception as exc:
                logger.warning("Could not auto-create tables on startup: %s", exc)
        start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(
    title="AI Cloud Lab API",
    description="Backend API for the AI Cloud Lab project",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    return response


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    logger.error("Database error processing request %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "A database error occurred. Please try again later."},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled server exception on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )

app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(exercises.router, prefix="/api/v1")
app.include_router(submissions.router, prefix="/api/v1")
app.include_router(progress.router, prefix="/api/v1")
app.include_router(notes.router, prefix="/api/v1")
app.include_router(ai.router, prefix="/api/v1")
app.include_router(recommendations.router, prefix="/api/v1")
app.include_router(quizzes.router, prefix="/api/v1")
app.include_router(files.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")

# Prometheus metrics instrumentation
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}


@app.get("/", tags=["Root"])
def root():
    return {
        "message": "Welcome to AI Cloud Lab API",
        "docs": "/docs",
        "health": "/health",
        "metrics": "/metrics",
    }
