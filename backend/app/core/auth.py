from __future__ import annotations

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.core.logger import get_logger
from app.core.config import settings


api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)


async def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    logger = get_logger("api.auth")

    if not api_key:
        logger.warning("Missing API key in request")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if api_key != settings.API_SECRET_KEY:
        try:
            masked = f"{api_key[:8]}..."
        except Exception:
            masked = "<invalid>"
        logger.warning(f"Invalid API key attempt: {masked}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    logger.debug("API key validated successfully")
    return api_key


async def get_current_api_key(api_key: str = Security(verify_api_key)) -> str:
    return api_key
