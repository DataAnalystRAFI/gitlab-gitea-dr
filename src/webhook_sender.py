from __future__ import annotations

import asyncio
import logging
import httpx
from src.models import WebhookConfig, HealthPayload, EventType

logger = logging.getLogger(__name__)


class WebhookSender:
    def __init__(self, config: WebhookConfig) -> None:
        self.config = config

    async def send(self, payload: HealthPayload) -> bool:
        if not self.config.url:
            logger.warning("No webhook URL configured, skipping notification")
            return False

        payload.event = EventType.HEALTH_ALERT if payload.alerts else EventType.HEALTH_SUMMARY

        last_error: Exception | None = None
        for attempt in range(1, self.config.retry_count + 1):
            try:
                async with httpx.AsyncClient(timeout=self.config.timeout_secs) as client:
                    resp = await client.post(
                        self.config.url,
                        json=payload.model_dump(mode="json"),
                        headers={"Content-Type": "application/json"},
                    )
                    if resp.is_success:
                        logger.info(
                            "Webhook sent successfully (attempt %d/%d): %s",
                            attempt, self.config.retry_count, resp.status_code,
                        )
                        return True
                    logger.warning(
                        "Webhook returned %d (attempt %d/%d)",
                        resp.status_code, attempt, self.config.retry_count,
                    )
                    last_error = Exception(f"HTTP {resp.status_code}: {resp.text[:200]}")
            except Exception as e:
                logger.warning(
                    "Webhook attempt %d/%d failed: %s",
                    attempt, self.config.retry_count, e,
                )
                last_error = e

            if attempt < self.config.retry_count:
                await asyncio.sleep(self.config.retry_delay_secs)

        logger.error(
            "Webhook failed after %d attempts: %s",
            self.config.retry_count, last_error,
        )
        return False
