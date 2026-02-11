"""API routes for gateway model registry and provider-auth management."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.deps import require_org_admin
from app.db.session import get_session
from app.schemas.common import OkResponse
from app.schemas.llm_models import (
    GatewayModelPullResult,
    GatewayModelSyncResult,
    LlmModelCreate,
    LlmModelRead,
    LlmModelUpdate,
    LlmProviderAuthCreate,
    LlmProviderAuthRead,
    LlmProviderAuthUpdate,
)
from app.services.openclaw.model_registry_service import GatewayModelRegistryService
from app.services.organizations import OrganizationContext

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

router = APIRouter(prefix="/model-registry", tags=["model-registry"])

SESSION_DEP = Depends(get_session)
ORG_ADMIN_DEP = Depends(require_org_admin)
GATEWAY_ID_QUERY = Query(default=None)


@router.get("/provider-auth", response_model=list[LlmProviderAuthRead])
async def list_provider_auth(
    gateway_id: UUID | None = GATEWAY_ID_QUERY,
    session: AsyncSession = SESSION_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> list[LlmProviderAuthRead]:
    """List provider auth records for the active organization."""
    service = GatewayModelRegistryService(session)
    return await service.list_provider_auth(ctx=ctx, gateway_id=gateway_id)


@router.post("/provider-auth", response_model=LlmProviderAuthRead)
async def create_provider_auth(
    payload: LlmProviderAuthCreate,
    session: AsyncSession = SESSION_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> LlmProviderAuthRead:
    """Create a provider auth record and sync gateway config."""
    service = GatewayModelRegistryService(session)
    return await service.create_provider_auth(payload=payload, ctx=ctx)


@router.patch("/provider-auth/{provider_auth_id}", response_model=LlmProviderAuthRead)
async def update_provider_auth(
    provider_auth_id: UUID,
    payload: LlmProviderAuthUpdate,
    session: AsyncSession = SESSION_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> LlmProviderAuthRead:
    """Patch a provider auth record and sync gateway config."""
    service = GatewayModelRegistryService(session)
    return await service.update_provider_auth(
        provider_auth_id=provider_auth_id,
        payload=payload,
        ctx=ctx,
    )


@router.delete("/provider-auth/{provider_auth_id}", response_model=OkResponse)
async def delete_provider_auth(
    provider_auth_id: UUID,
    session: AsyncSession = SESSION_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> OkResponse:
    """Delete a provider auth record and sync gateway config."""
    service = GatewayModelRegistryService(session)
    await service.delete_provider_auth(provider_auth_id=provider_auth_id, ctx=ctx)
    return OkResponse()


@router.get("/models", response_model=list[LlmModelRead])
async def list_models(
    gateway_id: UUID | None = GATEWAY_ID_QUERY,
    session: AsyncSession = SESSION_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> list[LlmModelRead]:
    """List gateway model catalog entries for the active organization."""
    service = GatewayModelRegistryService(session)
    return await service.list_models(ctx=ctx, gateway_id=gateway_id)


@router.post("/models", response_model=LlmModelRead)
async def create_model(
    payload: LlmModelCreate,
    session: AsyncSession = SESSION_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> LlmModelRead:
    """Create a model catalog entry and sync gateway config."""
    service = GatewayModelRegistryService(session)
    return await service.create_model(payload=payload, ctx=ctx)


@router.patch("/models/{model_id}", response_model=LlmModelRead)
async def update_model(
    model_id: UUID,
    payload: LlmModelUpdate,
    session: AsyncSession = SESSION_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> LlmModelRead:
    """Patch a model catalog entry and sync gateway config."""
    service = GatewayModelRegistryService(session)
    return await service.update_model(model_id=model_id, payload=payload, ctx=ctx)


@router.delete("/models/{model_id}", response_model=OkResponse)
async def delete_model(
    model_id: UUID,
    session: AsyncSession = SESSION_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> OkResponse:
    """Delete a model catalog entry and sync gateway config."""
    service = GatewayModelRegistryService(session)
    await service.delete_model(model_id=model_id, ctx=ctx)
    return OkResponse()


@router.post("/gateways/{gateway_id}/sync", response_model=GatewayModelSyncResult)
async def sync_gateway_models(
    gateway_id: UUID,
    session: AsyncSession = SESSION_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> GatewayModelSyncResult:
    """Push provider auth + model catalog + agent model links to a gateway."""
    service = GatewayModelRegistryService(session)
    gateway = await service.require_gateway(
        gateway_id=gateway_id,
        organization_id=ctx.organization.id,
    )
    return await service.sync_gateway_config(
        gateway=gateway,
        organization_id=ctx.organization.id,
    )


@router.post("/gateways/{gateway_id}/pull", response_model=GatewayModelPullResult)
async def pull_gateway_models(
    gateway_id: UUID,
    session: AsyncSession = SESSION_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> GatewayModelPullResult:
    """Pull provider auth + model catalog + agent model links from a gateway."""
    service = GatewayModelRegistryService(session)
    gateway = await service.require_gateway(
        gateway_id=gateway_id,
        organization_id=ctx.organization.id,
    )
    return await service.pull_gateway_config(
        gateway=gateway,
        organization_id=ctx.organization.id,
    )
