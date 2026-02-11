# ruff: noqa: S101
"""Regression tests for agent model-assignment update normalization."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from unittest.mock import AsyncMock

from app.services.openclaw.provisioning_db import AgentLifecycleService


class _NoAutoflush:
    def __init__(self, session: "_SessionStub") -> None:
        self._session = session

    def __enter__(self) -> None:
        self._session.in_no_autoflush = True
        return None

    def __exit__(self, exc_type, exc, tb) -> bool:
        self._session.in_no_autoflush = False
        return False


class _SessionStub:
    def __init__(self, valid_ids: set[UUID]) -> None:
        self.valid_ids = valid_ids
        self.in_no_autoflush = False
        self.commits = 0

    @property
    def no_autoflush(self) -> _NoAutoflush:
        return _NoAutoflush(self)

    async def exec(self, _statement: Any) -> list[UUID]:
        if not self.in_no_autoflush:
            raise AssertionError("Expected normalize query to run under no_autoflush.")
        return list(self.valid_ids)

    def add(self, _model: Any) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def refresh(self, _model: Any) -> None:
        return None


@dataclass
class _AgentStub:
    gateway_id: UUID
    board_id: UUID | None = None
    is_board_lead: bool = False
    openclaw_session_id: str | None = None
    primary_model_id: UUID | None = None
    fallback_model_ids: list[str] | None = None
    updated_at: datetime | None = None
    heartbeat_config: dict[str, Any] | None = field(
        default_factory=lambda: {"interval_seconds": 5},
    )


@pytest.mark.asyncio
async def test_normalize_agent_model_assignments_uses_no_autoflush() -> None:
    primary = uuid4()
    fallback = uuid4()
    session = _SessionStub({primary, fallback})
    service = AgentLifecycleService(session)  # type: ignore[arg-type]

    normalized_primary, normalized_fallback = await service.normalize_agent_model_assignments(
        gateway_id=uuid4(),
        primary_model_id=primary,
        fallback_model_ids=[primary, fallback],
    )

    assert normalized_primary == primary
    assert normalized_fallback == [str(fallback)]


@pytest.mark.asyncio
async def test_apply_agent_update_mutations_coerces_fallback_ids_to_strings(monkeypatch) -> None:
    primary = uuid4()
    fallback = uuid4()
    session = _SessionStub({primary, fallback})
    service = AgentLifecycleService(session)  # type: ignore[arg-type]
    monkeypatch.setattr(service, "get_main_agent_gateway", AsyncMock(return_value=None))

    agent = _AgentStub(gateway_id=uuid4())
    updates: dict[str, Any] = {
        "primary_model_id": primary,
        "fallback_model_ids": [primary, fallback, fallback],
    }

    await service.apply_agent_update_mutations(agent=agent, updates=updates, make_main=None)  # type: ignore[arg-type]

    assert updates["fallback_model_ids"] == [str(primary), str(fallback)]
    assert agent.primary_model_id == primary
    assert agent.fallback_model_ids == [str(fallback)]
    assert session.commits == 1
