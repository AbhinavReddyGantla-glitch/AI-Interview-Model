import httpx
import logging
from app.core.config import settings

logger = logging.getLogger("app.services.webhook")

def send_external_evaluation(payload: dict) -> bool:
    """
    Sends full evaluation data to the coaching/improvement team webhook.
    Includes candidate profile, scores, learning roadmap, and per-question breakdown.
    """
    url = settings.EXTERNAL_EVALUATION_URL
    if not url:
        logger.warning("EXTERNAL_EVALUATION_URL is not configured. Webhook skipped.")
        return False

    headers = {"Content-Type": "application/json"}
    if settings.EXTERNAL_WEBHOOK_SECRET:
        headers["X-Webhook-Secret"] = settings.EXTERNAL_WEBHOOK_SECRET

    try:
        logger.info(f"Triggering coaching team webhook to: {url}")
        response = httpx.post(url, json=payload, headers=headers, timeout=15.0)

        if response.status_code in [200, 201, 202]:
            logger.info(f"Coaching team webhook succeeded: {response.status_code}")
            return True
        logger.error(f"Coaching team webhook returned status: {response.status_code}")
        return False
    except Exception as e:
        logger.error(f"Error calling coaching team webhook: {e}")
        return False
