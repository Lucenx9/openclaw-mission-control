"""Schemas for LLM provider auth, model catalog, and gateway sync payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import field_validator
from sqlmodel import Field, SQLModel

from app.schemas.common import NonEmptyStr

RUNTIME_ANNOTATION_TYPES = (datetime, UUID, NonEmptyStr)


def _normalize_provider(value: object) -> str | object:
    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized or value
    return value


def _normalize_config_path(value: object) -> str | object:
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or value
    return value


def _default_provider_config_path(provider: str) -> str:
    return f"providers.{provider}.apiKey"


class LlmProviderAuthBase(SQLModel):
    """Shared provider auth fields."""

    gateway_id: UUID
    provider: NonEmptyStr
    config_path: NonEmptyStr | None = None

    @field_validator("provider", mode="before")
    @classmethod
    def normalize_provider(cls, value: object) -> str | object:
        return _normalize_provider(value)

    @field_validator("config_path", mode="before")
    @classmethod
    def normalize_config_path(cls, value: object) -> str | object:
        return _normalize_config_path(value)


class LlmProviderAuthCreate(LlmProviderAuthBase):
    """Payload used to create a provider auth record."""

    secret: NonEmptyStr


class LlmProviderAuthUpdate(SQLModel):
    """Payload used to patch an existing provider auth record."""

    provider: NonEmptyStr | None = None
    config_path: NonEmptyStr | None = None
    secret: NonEmptyStr | None = None

    @field_validator("provider", mode="before")
    @classmethod
    def normalize_provider(cls, value: object) -> str | object:
        return _normalize_provider(value)

    @field_validator("config_path", mode="before")
    @classmethod
    def normalize_config_path(cls, value: object) -> str | object:
        return _normalize_config_path(value)


class LlmProviderAuthRead(SQLModel):
    """Public provider auth payload (secret value is never returned)."""

    id: UUID
    organization_id: UUID
    gateway_id: UUID
    provider: str
    config_path: str
    has_secret: bool = True
    created_at: datetime
    updated_at: datetime


class LlmModelBase(SQLModel):
    """Shared gateway model catalog fields."""

    gateway_id: UUID
    provider: NonEmptyStr
    model_id: NonEmptyStr
    display_name: NonEmptyStr
    settings: dict[str, Any] | None = None

    @field_validator("provider", mode="before")
    @classmethod
    def normalize_provider(cls, value: object) -> str | object:
        return _normalize_provider(value)


class LlmModelCreate(LlmModelBase):
    """Payload used to create a model catalog entry."""


class LlmModelUpdate(SQLModel):
    """Payload used to patch an existing model catalog entry."""

    provider: NonEmptyStr | None = None
    model_id: NonEmptyStr | None = None
    display_name: NonEmptyStr | None = None
    settings: dict[str, Any] | None = None

    @field_validator("provider", mode="before")
    @classmethod
    def normalize_provider(cls, value: object) -> str | object:
        return _normalize_provider(value)


class LlmModelRead(SQLModel):
    """Public model catalog entry payload."""

    id: UUID
    organization_id: UUID
    gateway_id: UUID
    provider: str
    model_id: str
    display_name: str
    settings: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class GatewayModelSyncResult(SQLModel):
    """Summary of model/provider config sync operations for a gateway."""

    gateway_id: UUID
    provider_auth_patched: int
    model_catalog_patched: int
    agent_models_patched: int
    sessions_patched: int
    errors: list[str] = Field(default_factory=list)


class GatewayModelPullResult(SQLModel):
    """Summary of model/provider config pull operations for a gateway."""

    gateway_id: UUID
    provider_auth_imported: int
    model_catalog_imported: int
    agent_models_imported: int
    errors: list[str] = Field(default_factory=list)


__all__ = [
    "GatewayModelPullResult",
    "GatewayModelSyncResult",
    "LlmModelCreate",
    "LlmModelRead",
    "LlmModelUpdate",
    "LlmProviderAuthCreate",
    "LlmProviderAuthRead",
    "LlmProviderAuthUpdate",
]
