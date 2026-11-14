import time
import uuid
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from app.core.config import settings
from app.core.logging_config import setup_logging

# Initialize logging
setup_logging(settings.LOG_LEVEL)
logger = logging.getLogger("app.main")

# Initialize FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    description="API-first AI Interview Evaluation Platform backend.",
    version="1.0.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# Set CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this to restrict origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ══════════════════════════════════════════════════════════════
# Request Logging Middleware: Request ID, Status Code, & Duration
# ══════════════════════════════════════════════════════════════
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    req_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:8]
    start_time = time.perf_counter()
    try:
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start_time) * 1000
        response.headers["X-Request-ID"] = req_id
        logger.info(
            "[%s] %s %s -> %d (%.2fms)",
            req_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response
    except Exception as exc:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.exception(
            "[%s] %s %s failed with uncaught exception after %.2fms: %s",
            req_id,
            request.method,
            request.url.path,
            duration_ms,
            exc,
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "An internal server error occurred. Please try again.",
                "code": "INTERNAL_SERVER_ERROR",
                "request_id": req_id,
            },
            headers={"X-Request-ID": req_id},
        )

# ══════════════════════════════════════════════════════════════
# Global JSON Exception Handlers: Never Return Plain Text Errors
# ══════════════════════════════════════════════════════════════
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    headers = getattr(exc, "headers", None) or {}
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": f"HTTP_{exc.status_code}"},
        headers=headers,
    )

@app.exception_handler(StarletteHTTPException)
async def starlette_http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": f"HTTP_{exc.status_code}"},
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "code": "VALIDATION_ERROR"},
    )

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled global exception on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An internal server error occurred. Please try again.",
            "code": "INTERNAL_SERVER_ERROR",
        },
    )

# Include main API router
from app.api.v1.api import api_router
app.include_router(api_router, prefix=settings.API_V1_STR)

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Database seeding on startup
from app.database.session import SessionLocal
from app.services.seeder import seed_questions

@app.on_event("startup")
def on_startup():
    logger.info("Application starting up... running database seeds.")
    db = SessionLocal()
    try:
        seed_questions(db)
    except Exception as e:
        logger.error(f"Error seeding database on startup: {e}")
    finally:
        db.close()

@app.get("/health", tags=["Health"])
def health_check() -> dict:
    """
    Health check endpoint to verify backend service is running.
    """
    logger.info("Health check endpoint accessed")
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "environment": settings.APP_ENV,
    }

@app.get("/", tags=["Root"])
def read_root() -> FileResponse:
    """
    Serve the frontend homepage.
    """
    return FileResponse("app/static/index.html")

