"""Webhook queue persistence and delivery helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from typing import cast

import redis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class QueuedWebhookDelivery:
    """Payload metadata stored for deferred webhook lead dispatch."""

    board_id: UUID
    webhook_id: UUID
    payload_id: UUID
    payload_event: str | None
    received_at: datetime
    attempts: int = 0

    def to_json(self) -> str:
        return json.dumps(
            {
                "board_id": str(self.board_id),
                "webhook_id": str(self.webhook_id),
                "payload_id": str(self.payload_id),
                "payload_event": self.payload_event,
                "received_at": self.received_at.isoformat(),
                "attempts": self.attempts,
            },
            sort_keys=True,
        )


def _redis_client() -> redis.Redis:
    return redis.Redis.from_url(settings.webhook_redis_url)


def enqueue_webhook_delivery(payload: QueuedWebhookDelivery) -> bool:
    """Persist webhook metadata in a Redis queue for batch dispatch."""
    try:
        client = _redis_client()
        client.lpush(settings.webhook_queue_name, payload.to_json())
        logger.info(
            "webhook.queue.enqueued",
            extra={
                "board_id": str(payload.board_id),
                "webhook_id": str(payload.webhook_id),
                "payload_id": str(payload.payload_id),
                "attempt": payload.attempts,
            },
        )
        return True
    except Exception as exc:
        logger.warning(
            "webhook.queue.enqueue_failed",
            extra={
                "board_id": str(payload.board_id),
                "webhook_id": str(payload.webhook_id),
                "payload_id": str(payload.payload_id),
                "error": str(exc),
            },
        )
        return False


def dequeue_webhook_delivery() -> QueuedWebhookDelivery | None:
    """Pop one queued webhook delivery payload."""
    client = _redis_client()
    raw = cast(str | bytes | None, client.rpop(settings.webhook_queue_name))
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        payload: dict[str, Any] = json.loads(raw)
        event = payload.get("payload_event")
        if event is not None:
            event = str(event)
        return QueuedWebhookDelivery(
            board_id=UUID(payload["board_id"]),
            webhook_id=UUID(payload["webhook_id"]),
            payload_id=UUID(payload["payload_id"]),
            payload_event=event,
            received_at=datetime.fromisoformat(payload["received_at"]),
            attempts=int(payload.get("attempts", 0)),
        )
    except Exception as exc:
        logger.error(
            "webhook.queue.dequeue_failed",
            extra={"raw_payload": str(raw), "error": str(exc)},
        )
        raise


def _requeue_with_attempt(payload: QueuedWebhookDelivery) -> None:
    payload = QueuedWebhookDelivery(
        board_id=payload.board_id,
        webhook_id=payload.webhook_id,
        payload_id=payload.payload_id,
        payload_event=payload.payload_event,
        received_at=payload.received_at,
        attempts=payload.attempts + 1,
    )
    enqueue_webhook_delivery(payload)


def requeue_if_failed(payload: QueuedWebhookDelivery) -> bool:
    """Requeue payload delivery with capped retries.

    Returns True if requeued.
    """
    if payload.attempts >= settings.webhook_dispatch_max_retries:
        logger.warning(
            "webhook.queue.drop_failed_delivery",
            extra={
                "board_id": str(payload.board_id),
                "webhook_id": str(payload.webhook_id),
                "payload_id": str(payload.payload_id),
                "attempts": payload.attempts,
            },
        )
        return False
    _requeue_with_attempt(payload)
    return True
