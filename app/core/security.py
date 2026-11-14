import secrets
import logging
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader
from app.core.config import settings

logger = logging.getLogger("app.core.security")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str | None = Security(api_key_header)) -> str:
    """
    Validates the X-API-Key header for SaaS API access.
    Skips validation when API_KEY is not configured (development mode).
    """
    if not settings.API_KEY:
        return "dev-mode"

    if not api_key or not secrets.compare_digest(api_key, settings.API_KEY):
        logger.warning("Invalid or missing API key in request")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key. Provide a valid X-API-Key header.",
        )
    return api_key
