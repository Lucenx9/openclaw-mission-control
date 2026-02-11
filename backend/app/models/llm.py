"""Models for gateway-scoped LLM provider auth and model catalog records."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field

from app.core.time import utcnow
from app.models.base import QueryModel

RUNTIME_ANNOTATION_TYPES = (datetime,)


class LlmProviderAuth(QueryModel, table=True):
    """Provider auth settings to write into a specific gateway config."""

    __tablename__ = "llm_provider_auth"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    gateway_id: UUID = Field(foreign_key="gateways.id", index=True)
    provider: str = Field(index=True)
    config_path: str
    secret: str
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class LlmModel(QueryModel, table=True):
    """Gateway model catalog entries available for agent assignment."""

    __tablename__ = "llm_models"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    gateway_id: UUID = Field(foreign_key="gateways.id", index=True)
    provider: str = Field(index=True)
    model_id: str = Field(index=True)
    display_name: str
    settings: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
