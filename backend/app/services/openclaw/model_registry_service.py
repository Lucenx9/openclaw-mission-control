"""Gateway-scoped model registry and provider-auth synchronization service."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select

from app.core.time import utcnow
from app.models.agents import Agent
from app.models.gateways import Gateway
from app.models.llm import LlmModel, LlmProviderAuth
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
from app.services.openclaw.db_service import OpenClawDBService
from app.services.openclaw.gateway_rpc import GatewayConfig as GatewayClientConfig
from app.services.openclaw.gateway_rpc import OpenClawGatewayError, openclaw_call
from app.services.openclaw.internal.agent_key import agent_key as board_agent_key
from app.services.openclaw.provisioning import _heartbeat_config, _workspace_path
from app.services.openclaw.shared import GatewayAgentIdentity
from app.services.organizations import OrganizationContext


def _set_nested_path(target: dict[str, object], path: list[str], value: object) -> None:
    node: dict[str, object] = target
    for key in path[:-1]:
        next_node = node.get(key)
        if not isinstance(next_node, dict):
            next_node = {}
            node[key] = next_node
        node = next_node
    node[path[-1]] = value


def _get_nested_path(source: dict[str, object], path: list[str]) -> object | None:
    node: object = source
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def _normalize_provider(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    provider = value.strip().lower()
    return provider or None


def _infer_provider_for_model(model_id: str) -> str:
    candidate = model_id.strip()
    if not candidate:
        return "unknown"
    for delimiter in ("/", ":"):
        if delimiter in candidate:
            prefix = candidate.split(delimiter, 1)[0].strip().lower()
            if prefix:
                return prefix
    return "unknown"


def _model_settings(raw_value: object) -> dict[str, Any] | None:
    if not isinstance(raw_value, dict):
        return None
    return dict(raw_value)


def _parse_agent_model_value(raw_value: object) -> tuple[str | None, list[str]]:
    primary_value: str | None
    if isinstance(raw_value, str):
        primary_value = raw_value.strip() or None
        return primary_value, []
    if not isinstance(raw_value, dict):
        return None, []
    primary_raw = raw_value.get("primary")
    primary_value = primary_raw.strip() if isinstance(primary_raw, str) else None
    if not primary_value:
        primary_value = None
    fallback_raw = raw_value.get("fallbacks")
    if fallback_raw is None:
        fallback_raw = raw_value.get("fallback")
    fallback_values: list[str] = []
    if isinstance(fallback_raw, list):
        for item in fallback_raw:
            if not isinstance(item, str):
                continue
            value = item.strip()
            if not value:
                continue
            if primary_value and value == primary_value:
                continue
            if value in fallback_values:
                continue
            fallback_values.append(value)
    return primary_value, fallback_values


def _parse_model_uuid(value: object) -> UUID | None:
    if value is None:
        return None
    candidate = str(value).strip()
    if not candidate:
        return None
    try:
        return UUID(candidate)
    except ValueError:
        return None


def _model_config(primary: str | None, fallback: list[str]) -> dict[str, object] | None:
    if not primary and not fallback:
        return None
    value: dict[str, object] = {}
    if primary:
        value["primary"] = primary
    if fallback:
        value["fallbacks"] = fallback
    return value


def _json_to_dict(raw: object) -> dict[str, object] | None:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return None
    candidate = raw.strip()
    if not candidate:
        return {}
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None


def _extract_config_data(cfg: dict[str, object]) -> tuple[dict[str, object], str | None]:
    # Prefer parsed config over raw serialized content when both are present.
    parsed_config = _json_to_dict(cfg.get("parsed"))
    if parsed_config is not None:
        return parsed_config, cfg.get("hash") if isinstance(cfg.get("hash"), str) else None
    raw_config = _json_to_dict(cfg.get("config"))
    if raw_config is not None:
        return raw_config, cfg.get("hash") if isinstance(cfg.get("hash"), str) else None
    # Some gateways return the parsed config object at top-level.
    if any(key in cfg for key in ("agents", "providers", "channels")):
        return cfg, cfg.get("hash") if isinstance(cfg.get("hash"), str) else None
    raise OpenClawGatewayError("config.get returned invalid config")


def _constraint_name_from_error(exc: IntegrityError) -> str | None:
    diag = getattr(getattr(exc, "orig", None), "diag", None)
    if diag is None:
        return None
    constraint = getattr(diag, "constraint_name", None)
    if isinstance(constraint, str) and constraint:
        return constraint
    return None


def _is_constraint_violation(exc: IntegrityError, constraint_name: str) -> bool:
    if _constraint_name_from_error(exc) == constraint_name:
        return True
    return constraint_name in str(getattr(exc, "orig", exc))


class GatewayModelRegistryService(OpenClawDBService):
    """Manage provider auth + model catalogs and sync them into gateway config."""

    MODEL_UNIQUE_CONSTRAINT = "uq_llm_models_gateway_model_id"
    PROVIDER_AUTH_UNIQUE_CONSTRAINT = "uq_llm_provider_auth_gateway_provider_path"

    async def require_gateway(
        self,
        *,
        gateway_id: UUID,
        organization_id: UUID,
    ) -> Gateway:
        gateway = (
            await Gateway.objects.by_id(gateway_id)
            .filter(col(Gateway.organization_id) == organization_id)
            .first(self.session)
        )
        if gateway is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gateway not found")
        return gateway

    async def list_provider_auth(
        self,
        *,
        ctx: OrganizationContext,
        gateway_id: UUID | None,
    ) -> list[LlmProviderAuthRead]:
        statement = select(LlmProviderAuth).where(
            col(LlmProviderAuth.organization_id) == ctx.organization.id,
        )
        if gateway_id is not None:
            statement = statement.where(col(LlmProviderAuth.gateway_id) == gateway_id)
        statement = statement.order_by(
            col(LlmProviderAuth.provider).asc(),
            col(LlmProviderAuth.created_at).desc(),
        )
        rows = list(await self.session.exec(statement))
        return [self._to_provider_auth_read(item) for item in rows]

    async def create_provider_auth(
        self,
        *,
        payload: LlmProviderAuthCreate,
        ctx: OrganizationContext,
    ) -> LlmProviderAuthRead:
        gateway = await self.require_gateway(
            gateway_id=payload.gateway_id,
            organization_id=ctx.organization.id,
        )
        config_path = payload.config_path or f"providers.{payload.provider}.apiKey"
        existing = (
            await self.session.exec(
                select(LlmProviderAuth)
                .where(col(LlmProviderAuth.organization_id) == ctx.organization.id)
                .where(col(LlmProviderAuth.gateway_id) == gateway.id)
                .where(col(LlmProviderAuth.provider) == payload.provider)
                .where(col(LlmProviderAuth.config_path) == config_path),
            )
        ).first()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Provider auth already exists for this gateway/provider/path.",
            )
        record = LlmProviderAuth(
            organization_id=ctx.organization.id,
            gateway_id=gateway.id,
            provider=payload.provider,
            config_path=config_path,
            secret=payload.secret,
        )
        self.session.add(record)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if _is_constraint_violation(exc, self.PROVIDER_AUTH_UNIQUE_CONSTRAINT):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Provider auth already exists for this gateway/provider/path.",
                ) from exc
            raise
        await self.session.refresh(record)
        await self.sync_gateway_config(gateway=gateway, organization_id=ctx.organization.id)
        return self._to_provider_auth_read(record)

    async def update_provider_auth(
        self,
        *,
        provider_auth_id: UUID,
        payload: LlmProviderAuthUpdate,
        ctx: OrganizationContext,
    ) -> LlmProviderAuthRead:
        record = await LlmProviderAuth.objects.by_id(provider_auth_id).first(self.session)
        if record is None or record.organization_id != ctx.organization.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Provider auth not found"
            )
        updates = payload.model_dump(exclude_unset=True)
        if "provider" in updates:
            updates["provider"] = str(updates["provider"]).strip().lower()
        if "config_path" in updates and updates["config_path"] is not None:
            updates["config_path"] = str(updates["config_path"]).strip()
        if (
            "provider" in updates
            and "config_path" not in updates
            and (record.config_path == f"providers.{record.provider}.apiKey")
        ):
            updates["config_path"] = f"providers.{updates['provider']}.apiKey"
        candidate_provider = str(updates.get("provider", record.provider)).strip().lower()
        candidate_path = str(updates.get("config_path", record.config_path)).strip()
        duplicate = (
            await self.session.exec(
                select(LlmProviderAuth.id)
                .where(col(LlmProviderAuth.organization_id) == ctx.organization.id)
                .where(col(LlmProviderAuth.gateway_id) == record.gateway_id)
                .where(col(LlmProviderAuth.provider) == candidate_provider)
                .where(col(LlmProviderAuth.config_path) == candidate_path)
                .where(col(LlmProviderAuth.id) != record.id),
            )
        ).first()
        if duplicate is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Provider auth already exists for this gateway/provider/path.",
            )
        for key, value in updates.items():
            setattr(record, key, value)
        record.updated_at = utcnow()
        self.session.add(record)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if _is_constraint_violation(exc, self.PROVIDER_AUTH_UNIQUE_CONSTRAINT):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Provider auth already exists for this gateway/provider/path.",
                ) from exc
            raise
        await self.session.refresh(record)
        await self.sync_gateway_config(
            gateway=await self.require_gateway(
                gateway_id=record.gateway_id,
                organization_id=ctx.organization.id,
            ),
            organization_id=ctx.organization.id,
        )
        return self._to_provider_auth_read(record)

    async def delete_provider_auth(
        self,
        *,
        provider_auth_id: UUID,
        ctx: OrganizationContext,
    ) -> None:
        record = await LlmProviderAuth.objects.by_id(provider_auth_id).first(self.session)
        if record is None or record.organization_id != ctx.organization.id:
            return
        gateway_id = record.gateway_id
        await self.session.delete(record)
        await self.session.commit()
        await self.sync_gateway_config(
            gateway=await self.require_gateway(
                gateway_id=gateway_id,
                organization_id=ctx.organization.id,
            ),
            organization_id=ctx.organization.id,
        )

    async def list_models(
        self,
        *,
        ctx: OrganizationContext,
        gateway_id: UUID | None,
    ) -> list[LlmModelRead]:
        statement = select(LlmModel).where(col(LlmModel.organization_id) == ctx.organization.id)
        if gateway_id is not None:
            statement = statement.where(col(LlmModel.gateway_id) == gateway_id)
        statement = statement.order_by(col(LlmModel.provider).asc(), col(LlmModel.model_id).asc())
        rows = list(await self.session.exec(statement))
        return [LlmModelRead.model_validate(item, from_attributes=True) for item in rows]

    async def create_model(
        self,
        *,
        payload: LlmModelCreate,
        ctx: OrganizationContext,
    ) -> LlmModelRead:
        gateway = await self.require_gateway(
            gateway_id=payload.gateway_id,
            organization_id=ctx.organization.id,
        )
        existing = (
            await self.session.exec(
                select(LlmModel.id)
                .where(col(LlmModel.organization_id) == ctx.organization.id)
                .where(col(LlmModel.gateway_id) == gateway.id)
                .where(col(LlmModel.model_id) == payload.model_id),
            )
        ).first()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Model already exists in this gateway catalog.",
            )
        model = LlmModel(
            organization_id=ctx.organization.id,
            gateway_id=gateway.id,
            provider=payload.provider,
            model_id=payload.model_id,
            display_name=payload.display_name,
            settings=payload.settings,
        )
        self.session.add(model)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if _is_constraint_violation(exc, self.MODEL_UNIQUE_CONSTRAINT):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Model already exists in this gateway catalog.",
                ) from exc
            raise
        await self.session.refresh(model)
        await self.sync_gateway_config(gateway=gateway, organization_id=ctx.organization.id)
        return LlmModelRead.model_validate(model, from_attributes=True)

    async def update_model(
        self,
        *,
        model_id: UUID,
        payload: LlmModelUpdate,
        ctx: OrganizationContext,
    ) -> LlmModelRead:
        model = await LlmModel.objects.by_id(model_id).first(self.session)
        if model is None or model.organization_id != ctx.organization.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
        updates = payload.model_dump(exclude_unset=True)
        if "provider" in updates and updates["provider"] is not None:
            updates["provider"] = str(updates["provider"]).strip().lower()
        if "model_id" in updates and updates["model_id"] is not None:
            candidate_model_id = str(updates["model_id"]).strip()
            updates["model_id"] = candidate_model_id
            duplicate = (
                await self.session.exec(
                    select(LlmModel.id)
                    .where(col(LlmModel.organization_id) == ctx.organization.id)
                    .where(col(LlmModel.gateway_id) == model.gateway_id)
                    .where(col(LlmModel.model_id) == candidate_model_id)
                    .where(col(LlmModel.id) != model.id),
                )
            ).first()
            if duplicate is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Model already exists in this gateway catalog.",
                )
        for key, value in updates.items():
            setattr(model, key, value)
        model.updated_at = utcnow()
        self.session.add(model)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if _is_constraint_violation(exc, self.MODEL_UNIQUE_CONSTRAINT):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Model already exists in this gateway catalog.",
                ) from exc
            raise
        await self.session.refresh(model)
        await self.sync_gateway_config(
            gateway=await self.require_gateway(
                gateway_id=model.gateway_id,
                organization_id=ctx.organization.id,
            ),
            organization_id=ctx.organization.id,
        )
        return LlmModelRead.model_validate(model, from_attributes=True)

    async def delete_model(
        self,
        *,
        model_id: UUID,
        ctx: OrganizationContext,
    ) -> None:
        model = await LlmModel.objects.by_id(model_id).first(self.session)
        if model is None or model.organization_id != ctx.organization.id:
            return
        gateway_id = model.gateway_id
        removed_id = model.id
        await self.session.delete(model)
        await self.session.commit()

        agents = await Agent.objects.filter_by(gateway_id=gateway_id).all(self.session)
        changed = False
        for agent in agents:
            agent_changed = False
            if agent.primary_model_id == removed_id:
                agent.primary_model_id = None
                agent_changed = True
            raw_fallback = agent.fallback_model_ids or []
            if not isinstance(raw_fallback, list):
                continue
            filtered = []
            for item in raw_fallback:
                parsed = _parse_model_uuid(item)
                if parsed is None or parsed == removed_id:
                    continue
                filtered.append(str(parsed))
            if filtered != raw_fallback:
                agent.fallback_model_ids = filtered or None
                agent_changed = True
            if agent_changed:
                agent.updated_at = utcnow()
                self.session.add(agent)
                changed = True
        if changed:
            await self.session.commit()

        await self.sync_gateway_config(
            gateway=await self.require_gateway(
                gateway_id=gateway_id,
                organization_id=ctx.organization.id,
            ),
            organization_id=ctx.organization.id,
        )

    async def pull_gateway_config(
        self,
        *,
        gateway: Gateway,
        organization_id: UUID,
    ) -> GatewayModelPullResult:
        """Import provider auth, model catalog, and agent model links from gateway config."""
        if gateway.organization_id != organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gateway not found")
        if not gateway.url:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Gateway URL is not configured.",
            )

        config = GatewayClientConfig(url=gateway.url, token=gateway.token)
        result = GatewayModelPullResult(
            gateway_id=gateway.id,
            provider_auth_imported=0,
            model_catalog_imported=0,
            agent_models_imported=0,
            errors=[],
        )

        try:
            cfg = await openclaw_call("config.get", config=config)
            if not isinstance(cfg, dict):
                raise OpenClawGatewayError("config.get returned invalid payload")
            config_data, _ = _extract_config_data(cfg)
        except OpenClawGatewayError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Gateway model pull failed: {exc}",
            ) from exc

        has_db_changes = False
        has_pending_models = False

        provider_auth_rows = await LlmProviderAuth.objects.filter_by(
            organization_id=organization_id,
            gateway_id=gateway.id,
        ).all(self.session)
        provider_auth_by_key: dict[tuple[str, str], LlmProviderAuth] = {
            (item.provider, item.config_path): item for item in provider_auth_rows
        }

        for provider_auth_item in provider_auth_rows:
            path = [part.strip() for part in provider_auth_item.config_path.split(".") if part.strip()]
            if not path:
                continue
            pulled_secret_value = _get_nested_path(config_data, path)
            if not isinstance(pulled_secret_value, str):
                continue
            secret = pulled_secret_value.strip()
            if not secret or secret == provider_auth_item.secret:
                continue
            provider_auth_item.secret = secret
            provider_auth_item.updated_at = utcnow()
            self.session.add(provider_auth_item)
            result.provider_auth_imported += 1
            has_db_changes = True

        providers_data = config_data.get("providers")
        if isinstance(providers_data, dict):
            for raw_provider, raw_provider_config in providers_data.items():
                provider = _normalize_provider(raw_provider)
                if not provider:
                    continue
                pulled_secret: str | None = None
                config_path: str | None = None
                if isinstance(raw_provider_config, dict):
                    raw_api_key = raw_provider_config.get("apiKey")
                    if isinstance(raw_api_key, str):
                        api_key = raw_api_key.strip()
                        if api_key:
                            pulled_secret = api_key
                            config_path = f"providers.{provider}.apiKey"
                elif isinstance(raw_provider_config, str):
                    secret = raw_provider_config.strip()
                    if secret:
                        pulled_secret = secret
                        config_path = f"providers.{provider}"
                if not pulled_secret or not config_path:
                    continue
                provider_key = (provider, config_path)
                existing = provider_auth_by_key.get(provider_key)
                if existing is None:
                    record = LlmProviderAuth(
                        organization_id=organization_id,
                        gateway_id=gateway.id,
                        provider=provider,
                        config_path=config_path,
                        secret=pulled_secret,
                    )
                    self.session.add(record)
                    provider_auth_by_key[provider_key] = record
                    result.provider_auth_imported += 1
                    has_db_changes = True
                    continue
                if existing.secret == pulled_secret:
                    continue
                existing.secret = pulled_secret
                existing.updated_at = utcnow()
                self.session.add(existing)
                result.provider_auth_imported += 1
                has_db_changes = True

        existing_models = await LlmModel.objects.filter_by(
            organization_id=organization_id,
            gateway_id=gateway.id,
        ).all(self.session)
        models_by_model_id: dict[str, LlmModel] = {item.model_id: item for item in existing_models}

        catalog_models_data: dict[str, object] = {}
        agents_data = config_data.get("agents")
        if isinstance(agents_data, dict):
            defaults_data = agents_data.get("defaults")
            if isinstance(defaults_data, dict):
                raw_models = defaults_data.get("models")
                if isinstance(raw_models, dict):
                    catalog_models_data = raw_models

        for raw_model_id, raw_model_config in catalog_models_data.items():
            if not isinstance(raw_model_id, str):
                result.errors.append("Skipped one catalog model: model id is not a string.")
                continue
            model_id = raw_model_id.strip()
            if not model_id:
                result.errors.append("Skipped one catalog model: model id is empty.")
                continue

            settings = _model_settings(raw_model_config)
            provider_from_settings = (
                _normalize_provider(settings.get("provider")) if settings is not None else None
            )
            provider = provider_from_settings or _infer_provider_for_model(model_id)
            display_name = model_id
            if settings:
                for display_key in ("display_name", "displayName", "name"):
                    candidate = settings.get(display_key)
                    if isinstance(candidate, str) and candidate.strip():
                        display_name = candidate.strip()
                        break

            existing_model = models_by_model_id.get(model_id)
            if existing_model is None:
                model = LlmModel(
                    organization_id=organization_id,
                    gateway_id=gateway.id,
                    provider=provider,
                    model_id=model_id,
                    display_name=display_name,
                    settings=settings,
                )
                self.session.add(model)
                models_by_model_id[model_id] = model
                result.model_catalog_imported += 1
                has_db_changes = True
                has_pending_models = True
                continue

            model_changed = False
            if existing_model.provider != provider:
                existing_model.provider = provider
                model_changed = True
            if existing_model.display_name != display_name:
                existing_model.display_name = display_name
                model_changed = True
            if existing_model.settings != settings:
                existing_model.settings = settings
                model_changed = True
            if model_changed:
                existing_model.updated_at = utcnow()
                self.session.add(existing_model)
                result.model_catalog_imported += 1
                has_db_changes = True

        agents = await Agent.objects.filter_by(gateway_id=gateway.id).all(self.session)
        agents_by_openclaw_id: dict[str, Agent] = {}
        for agent in agents:
            if agent.board_id is None:
                agent_id = GatewayAgentIdentity.openclaw_agent_id(gateway)
            else:
                agent_id = board_agent_key(agent)
            agents_by_openclaw_id[agent_id] = agent

        raw_agents_list: list[object] = []
        if isinstance(agents_data, dict):
            raw_agent_values = agents_data.get("list") or []
            if isinstance(raw_agent_values, list):
                raw_agents_list = raw_agent_values

        assignments_by_agent: dict[UUID, tuple[str | None, list[str]]] = {}
        assignment_model_ids: set[str] = set()
        for raw_entry in raw_agents_list:
            if not isinstance(raw_entry, dict):
                continue
            raw_agent_id = raw_entry.get("id")
            if not isinstance(raw_agent_id, str):
                continue
            agent_id = raw_agent_id.strip()
            if not agent_id:
                continue
            resolved_agent = agents_by_openclaw_id.get(agent_id)
            if resolved_agent is None:
                continue
            if "model" not in raw_entry:
                continue
            primary_model_id, fallback_model_ids = _parse_agent_model_value(raw_entry.get("model"))
            assignments_by_agent[resolved_agent.id] = (primary_model_id, fallback_model_ids)
            if primary_model_id:
                assignment_model_ids.add(primary_model_id)
            assignment_model_ids.update(fallback_model_ids)

        for model_id in assignment_model_ids:
            if model_id in models_by_model_id:
                continue
            model = LlmModel(
                organization_id=organization_id,
                gateway_id=gateway.id,
                provider=_infer_provider_for_model(model_id),
                model_id=model_id,
                display_name=model_id,
                settings=None,
            )
            self.session.add(model)
            models_by_model_id[model_id] = model
            result.model_catalog_imported += 1
            has_db_changes = True
            has_pending_models = True

        if has_pending_models:
            await self.session.flush()

        changed_agents = 0
        for agent in agents:
            model_assignment = assignments_by_agent.get(agent.id)
            if model_assignment is None:
                continue
            primary_model_key, fallback_model_keys = model_assignment

            primary_model_uuid: UUID | None = None
            if primary_model_key:
                primary_model = models_by_model_id.get(primary_model_key)
                if primary_model is None:
                    result.errors.append(
                        f"Skipped primary model '{primary_model_key}' for agent '{agent.name}'.",
                    )
                else:
                    primary_model_uuid = primary_model.id

            fallback_values: list[str] = []
            for model_key in fallback_model_keys:
                resolved_model = models_by_model_id.get(model_key)
                if resolved_model is None:
                    result.errors.append(
                        f"Skipped fallback model '{model_key}' for agent '{agent.name}'.",
                    )
                    continue
                if primary_model_uuid is not None and resolved_model.id == primary_model_uuid:
                    continue
                fallback_id = str(resolved_model.id)
                if fallback_id in fallback_values:
                    continue
                fallback_values.append(fallback_id)
            normalized_fallback_model_ids: list[str] | None = fallback_values or None

            current_fallback_values: list[str] = []
            for raw_value in agent.fallback_model_ids or []:
                parsed = _parse_model_uuid(raw_value)
                if parsed is None:
                    continue
                value = str(parsed)
                if value in current_fallback_values:
                    continue
                current_fallback_values.append(value)
            current_fallback_model_ids = current_fallback_values or None

            if (
                agent.primary_model_id == primary_model_uuid
                and current_fallback_model_ids == normalized_fallback_model_ids
            ):
                continue
            agent.primary_model_id = primary_model_uuid
            agent.fallback_model_ids = normalized_fallback_model_ids
            agent.updated_at = utcnow()
            self.session.add(agent)
            changed_agents += 1
            has_db_changes = True

        result.agent_models_imported = changed_agents
        if has_db_changes:
            await self.session.commit()
        return result

    async def sync_gateway_config(
        self,
        *,
        gateway: Gateway,
        organization_id: UUID,
    ) -> GatewayModelSyncResult:
        if gateway.organization_id != organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gateway not found")
        if not gateway.url:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Gateway URL is not configured.",
            )

        config = GatewayClientConfig(url=gateway.url, token=gateway.token)
        provider_auth = await LlmProviderAuth.objects.filter_by(
            organization_id=organization_id,
            gateway_id=gateway.id,
        ).all(self.session)
        model_catalog = await LlmModel.objects.filter_by(
            organization_id=organization_id,
            gateway_id=gateway.id,
        ).all(self.session)
        agents = await Agent.objects.filter_by(gateway_id=gateway.id).all(self.session)
        model_id_map = {model.id: model.model_id for model in model_catalog}
        default_primary_model: str | None = None

        result = GatewayModelSyncResult(
            gateway_id=gateway.id,
            provider_auth_patched=0,
            model_catalog_patched=0,
            agent_models_patched=0,
            sessions_patched=0,
            errors=[],
        )

        try:
            cfg = await openclaw_call("config.get", config=config)
            if not isinstance(cfg, dict):
                raise OpenClawGatewayError("config.get returned invalid payload")
            config_data, base_hash = _extract_config_data(cfg)

            patch: dict[str, object] = {}
            for provider_auth_item in provider_auth:
                path = [
                    part.strip()
                    for part in provider_auth_item.config_path.split(".")
                    if part.strip()
                ]
                if not path:
                    result.errors.append(
                        f"Skipped provider auth {provider_auth_item.id}: config_path is empty.",
                    )
                    continue
                _set_nested_path(patch, path, provider_auth_item.secret)
                result.provider_auth_patched += 1

            if model_catalog:
                models_patch: dict[str, object] = {}
                for model in model_catalog:
                    value = dict(model.settings or {})
                    # Gateway model objects reject provider metadata; store provider in DB only.
                    value.pop("provider", None)
                    models_patch[model.model_id] = value
                _set_nested_path(patch, ["agents", "defaults", "models"], models_patch)
                result.model_catalog_patched = len(model_catalog)

                existing_primary = None
                agents_section = config_data.get("agents")
                if isinstance(agents_section, dict):
                    defaults_section = agents_section.get("defaults")
                    if isinstance(defaults_section, dict):
                        model_section = defaults_section.get("model")
                        if isinstance(model_section, dict):
                            candidate = model_section.get("primary")
                            if isinstance(candidate, str) and candidate:
                                existing_primary = candidate
                if existing_primary in models_patch:
                    default_primary_model = existing_primary
                else:
                    first_model = model_catalog[0].model_id
                    _set_nested_path(
                        patch,
                        ["agents", "defaults", "model", "primary"],
                        first_model,
                    )
                    default_primary_model = first_model

            raw_agents_list: list[object] = []
            agents_section = config_data.get("agents")
            if isinstance(agents_section, dict):
                raw_agents_list = agents_section.get("list") or []
            if not isinstance(raw_agents_list, list):
                raw_agents_list = []

            existing_entries: dict[str, dict[str, object]] = {}
            passthrough_entries: list[object] = []
            for raw_entry in raw_agents_list:
                if not isinstance(raw_entry, dict):
                    passthrough_entries.append(raw_entry)
                    continue
                entry_id = raw_entry.get("id")
                if isinstance(entry_id, str) and entry_id:
                    existing_entries[entry_id] = dict(raw_entry)
                else:
                    passthrough_entries.append(raw_entry)

            updated_entries: list[object] = []
            for agent in agents:
                if agent.board_id is None:
                    agent_id = GatewayAgentIdentity.openclaw_agent_id(gateway)
                else:
                    agent_id = board_agent_key(agent)
                agent_entry = existing_entries.pop(agent_id, None)
                if agent_entry is None:
                    agent_entry = {
                        "id": agent_id,
                        "workspace": _workspace_path(agent, gateway.workspace_root),
                        "heartbeat": _heartbeat_config(agent),
                    }

                primary_model_id = (
                    model_id_map.get(agent.primary_model_id) if agent.primary_model_id else None
                )
                fallback_values: list[str] = []
                for raw_value in agent.fallback_model_ids or []:
                    parsed = _parse_model_uuid(raw_value)
                    if parsed is None:
                        continue
                    mapped = model_id_map.get(parsed)
                    if not mapped:
                        continue
                    if primary_model_id and mapped == primary_model_id:
                        continue
                    if mapped in fallback_values:
                        continue
                    fallback_values.append(mapped)
                model_value = _model_config(primary_model_id, fallback_values)
                if model_value is None:
                    agent_entry.pop("model", None)
                else:
                    agent_entry["model"] = model_value
                    result.agent_models_patched += 1
                updated_entries.append(agent_entry)

            for remaining in existing_entries.values():
                updated_entries.append(remaining)
            updated_entries.extend(passthrough_entries)
            _set_nested_path(patch, ["agents", "list"], updated_entries)

            params: dict[str, object] = {"raw": json.dumps(patch)}
            if base_hash:
                params["baseHash"] = base_hash
            await openclaw_call("config.patch", params, config=config)
        except OpenClawGatewayError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Gateway model sync failed: {exc}",
            ) from exc

        for agent in agents:
            primary = model_id_map.get(agent.primary_model_id) if agent.primary_model_id else None
            if not primary:
                primary = default_primary_model
            if not primary:
                continue
            session_key = (agent.openclaw_session_id or "").strip()
            if not session_key:
                continue
            try:
                await openclaw_call(
                    "sessions.patch",
                    {
                        "key": session_key,
                        "label": agent.name,
                        "model": primary,
                    },
                    config=config,
                )
                result.sessions_patched += 1
            except OpenClawGatewayError as exc:
                result.errors.append(f"{agent.name}: {exc}")
        return result

    @staticmethod
    def _to_provider_auth_read(record: LlmProviderAuth) -> LlmProviderAuthRead:
        return LlmProviderAuthRead(
            id=record.id,
            organization_id=record.organization_id,
            gateway_id=record.gateway_id,
            provider=record.provider,
            config_path=record.config_path,
            has_secret=bool(record.secret),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
