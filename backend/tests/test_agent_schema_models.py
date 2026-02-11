# ruff: noqa: S101
"""Tests for agent model-assignment schema normalization."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.agents import AgentCreate


def test_agent_create_normalizes_fallback_model_ids() -> None:
    model_a = uuid4()
    model_b = uuid4()

    payload = AgentCreate(
        name="Worker",
        fallback_model_ids=[str(model_a), str(model_b), str(model_a)],
    )

    assert payload.fallback_model_ids == [model_a, model_b]


def test_agent_create_rejects_non_list_fallback_model_ids() -> None:
    with pytest.raises(ValidationError):
        AgentCreate(name="Worker", fallback_model_ids="not-a-list")
