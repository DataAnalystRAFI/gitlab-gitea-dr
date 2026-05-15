import pytest
from src.webhook_sender import WebhookSender
from src.models import WebhookConfig, HealthPayload


class TestWebhookSender:
    @pytest.mark.asyncio
    async def test_no_url_returns_false(self) -> None:
        config = WebhookConfig(url="")
        sender = WebhookSender(config)
        result = await sender.send(HealthPayload(timestamp="2026-01-01T00:00:00Z"))
        assert result is False

    def test_default_retry_and_timeout(self) -> None:
        config = WebhookConfig(url="https://hooks.example.com/dr")
        assert config.retry_count == 3
        assert config.timeout_secs == 10

    @pytest.mark.asyncio
    async def test_send_with_invalid_url_returns_false(self) -> None:
        config = WebhookConfig(url="http://localhost:1")
        sender = WebhookSender(config)
        result = await sender.send(HealthPayload(timestamp="2026-01-01T00:00:00Z"))
        assert result is False
