from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from fastapi import Depends
from app.api import routes
from app.core import get_logger
from app.core.config import settings, utcnow
from app.models.model_loader import get_model_loader
from app.core.auth import get_current_api_key

app = FastAPI(title="Agentic AI Scam Honeypot", version="0.1.0")
logger = get_logger(__name__)

# ============================================================================
# CORS Configuration
# ============================================================================

if settings.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info(f"CORS enabled for origins: {settings.CORS_ORIGINS}")

# ============================================================================
# Routes
# ============================================================================

app.include_router(routes.router, dependencies=[Depends(get_current_api_key)])
# Include alias router that exposes non-versioned endpoints (e.g. /api/voice-detection)
app.include_router(routes.alias_router)

# ============================================================================
# Exception Handlers
# ============================================================================


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors to return a 400-style ErrorResponse."""
    logger.warning(f"Request validation error: {exc}")
    # Build concise message from validation errors
    errors = exc.errors() if hasattr(exc, "errors") else None
    if errors:
        msg = "; ".join([f"{e.get('loc')}: {e.get('msg')}" for e in errors])
    else:
        msg = str(exc)
    
    from app.schemas.response import ErrorResponse
    payload = ErrorResponse(message=msg).dict()
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=payload)


# ============================================================================
# Health Check
# ============================================================================


@app.get("/health", tags=["health"])
def health_check():
    """Health check endpoint."""
    logger.debug("Health check requested")
    return {
        "status": "success",
        "message": "Service is healthy",
        "timestamp": utcnow(),
    }


# ============================================================================
# Startup/Shutdown Events
# ============================================================================


@app.on_event("startup")
async def startup_event():
    """Initialize application on startup."""
    logger.info("Starting Agentic AI Scam Honeypot backend...")
    logger.info(f"Device: {settings.DEVICE}")
    logger.info(f"Demo Mode: {settings.DEMO_MODE}")

    if not settings.DEMO_MODE:
        logger.info("Preloading models...")
        try:
            model_loader = get_model_loader()
            model_loader.validate_all_models()
            logger.info("All models loaded successfully")
        except Exception as e:
            logger.error(f"Model loading failed: {e}", exc_info=True)
            logger.warning(
                "API will attempt lazy loading on first request"
            )
    else:
        logger.info("Demo mode enabled - skipping model preload")


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up on shutdown."""
    logger.info("Shutting down Agentic AI Scam Honeypot backend...")

    # Optional: Clear agent sessions
    try:
        from app.pipeline.agent import get_agentic_controller

        agent = get_agentic_controller()
        agent.clear_old_sessions(max_age_seconds=0)
        logger.info("Cleared all agent sessions")
    except Exception as e:
        logger.warning(f"Session cleanup failed: {e}")
