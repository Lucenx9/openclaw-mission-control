from __future__ import annotations

import re
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import update
from sqlmodel import Session, col, select

from app.api.deps import ActorContext, require_admin_auth, require_admin_or_agent
from app.core.agent_tokens import generate_agent_token, hash_agent_token, verify_agent_token
from app.core.auth import AuthContext
from app.core.config import settings
from app.db.session import get_session
from app.integrations.openclaw_gateway import GatewayConfig as GatewayClientConfig
from app.integrations.openclaw_gateway import OpenClawGatewayError, ensure_session, send_message
from app.models.activity_events import ActivityEvent
from app.models.agents import Agent
from app.models.boards import Board
from app.models.gateways import Gateway
from app.schemas.agents import (
    AgentCreate,
    AgentDeleteConfirm,
    AgentHeartbeat,
    AgentHeartbeatCreate,
    AgentProvisionConfirm,
    AgentRead,
    AgentUpdate,
)
from app.services.activity_log import record_activity
from app.services.agent_provisioning import (
    DEFAULT_HEARTBEAT_CONFIG,
    send_provisioning_message,
    send_update_message,
)

router = APIRouter(prefix="/agents", tags=["agents"])

OFFLINE_AFTER = timedelta(minutes=10)
AGENT_SESSION_PREFIX = "agent"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or uuid4().hex


def _build_session_key(agent_name: str) -> str:
    return f"{AGENT_SESSION_PREFIX}:{_slugify(agent_name)}:main"


def _workspace_path(agent_name: str, workspace_root: str | None) -> str:
    if not workspace_root:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Gateway workspace_root is required",
        )
    root = workspace_root.rstrip("/")
    return f"{root}/workspace-{_slugify(agent_name)}"


def _require_board(session: Session, board_id: UUID | str | None) -> Board:
    if not board_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="board_id is required",
        )
    board = session.get(Board, board_id)
    if board is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Board not found")
    return board


def _require_gateway(session: Session, board: Board) -> tuple[Gateway, GatewayClientConfig]:
    if not board.gateway_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Board gateway_id is required",
        )
    gateway = session.get(Gateway, board.gateway_id)
    if gateway is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Board gateway_id is invalid",
        )
    if not gateway.main_session_key:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Gateway main_session_key is required",
        )
    if not gateway.url:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Gateway url is required",
        )
    if not gateway.workspace_root:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Gateway workspace_root is required",
        )
    return gateway, GatewayClientConfig(url=gateway.url, token=gateway.token)


async def _ensure_gateway_session(
    agent_name: str,
    config: GatewayClientConfig,
) -> tuple[str, str | None]:
    session_key = _build_session_key(agent_name)
    try:
        await ensure_session(session_key, config=config, label=agent_name)
        return session_key, None
    except OpenClawGatewayError as exc:
        return session_key, str(exc)


def _with_computed_status(agent: Agent) -> Agent:
    now = datetime.utcnow()
    if agent.status in {"deleting", "updating"}:
        return agent
    if agent.last_seen_at is None:
        agent.status = "provisioning"
    elif now - agent.last_seen_at > OFFLINE_AFTER:
        agent.status = "offline"
    return agent


def _record_heartbeat(session: Session, agent: Agent) -> None:
    record_activity(
        session,
        event_type="agent.heartbeat",
        message=f"Heartbeat received from {agent.name}.",
        agent_id=agent.id,
    )


def _record_instruction_failure(session: Session, agent: Agent, error: str, action: str) -> None:
    action_label = action.replace("_", " ").capitalize()
    record_activity(
        session,
        event_type=f"agent.{action}.failed",
        message=f"{action_label} message failed: {error}",
        agent_id=agent.id,
    )


def _record_wakeup_failure(session: Session, agent: Agent, error: str) -> None:
    record_activity(
        session,
        event_type="agent.wakeup.failed",
        message=f"Wakeup message failed: {error}",
        agent_id=agent.id,
    )


async def _send_wakeup_message(
    agent: Agent, config: GatewayClientConfig, verb: str = "provisioned"
) -> None:
    session_key = agent.openclaw_session_id or _build_session_key(agent.name)
    await ensure_session(session_key, config=config, label=agent.name)
    message = (
        f"Hello {agent.name}. Your workspace has been {verb}.\n\n"
        "Start the agent, run BOOT.md, and if BOOTSTRAP.md exists run it once "
        "then delete it. Begin heartbeats after startup."
    )
    await send_message(message, session_key=session_key, config=config, deliver=True)


@router.get("", response_model=list[AgentRead])
def list_agents(
    session: Session = Depends(get_session),
    auth: AuthContext = Depends(require_admin_auth),
) -> list[Agent]:
    agents = list(session.exec(select(Agent)))
    return [_with_computed_status(agent) for agent in agents]


@router.post("", response_model=AgentRead)
async def create_agent(
    payload: AgentCreate,
    session: Session = Depends(get_session),
    auth: AuthContext = Depends(require_admin_auth),
) -> Agent:
    board = _require_board(session, payload.board_id)
    gateway, client_config = _require_gateway(session, board)
    data = payload.model_dump()
    if data.get("identity_template") == "":
        data["identity_template"] = None
    if data.get("soul_template") == "":
        data["soul_template"] = None
    agent = Agent.model_validate(data)
    agent.status = "provisioning"
    raw_token = generate_agent_token()
    agent.agent_token_hash = hash_agent_token(raw_token)
    if agent.heartbeat_config is None:
        agent.heartbeat_config = DEFAULT_HEARTBEAT_CONFIG.copy()
    provision_token = generate_agent_token()
    agent.provision_confirm_token_hash = hash_agent_token(provision_token)
    agent.provision_requested_at = datetime.utcnow()
    agent.provision_action = "provision"
    session_key, session_error = await _ensure_gateway_session(agent.name, client_config)
    agent.openclaw_session_id = session_key
    session.add(agent)
    session.commit()
    session.refresh(agent)
    if session_error:
        record_activity(
            session,
            event_type="agent.session.failed",
            message=f"Session sync failed for {agent.name}: {session_error}",
            agent_id=agent.id,
        )
    else:
        record_activity(
            session,
            event_type="agent.session.created",
            message=f"Session created for {agent.name}.",
            agent_id=agent.id,
        )
    session.commit()
    try:
        await send_provisioning_message(
            agent, board, gateway, raw_token, provision_token, auth.user
        )
        record_activity(
            session,
            event_type="agent.provision.requested",
            message=f"Provisioning requested for {agent.name}.",
            agent_id=agent.id,
        )
    except OpenClawGatewayError as exc:
        _record_instruction_failure(session, agent, str(exc), "provision")
        session.commit()
    except Exception as exc:  # pragma: no cover - unexpected provisioning errors
        _record_instruction_failure(session, agent, str(exc), "provision")
        session.commit()
    return agent


@router.get("/{agent_id}", response_model=AgentRead)
def get_agent(
    agent_id: str,
    session: Session = Depends(get_session),
    auth: AuthContext = Depends(require_admin_auth),
) -> Agent:
    agent = session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return _with_computed_status(agent)


@router.patch("/{agent_id}", response_model=AgentRead)
async def update_agent(
    agent_id: str,
    payload: AgentUpdate,
    session: Session = Depends(get_session),
    auth: AuthContext = Depends(require_admin_auth),
) -> Agent:
    agent = session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    updates = payload.model_dump(exclude_unset=True)
    if "status" in updates:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="status is controlled by agent heartbeat",
        )
    if updates.get("identity_template") == "":
        updates["identity_template"] = None
    if updates.get("soul_template") == "":
        updates["soul_template"] = None
    if not updates:
        return _with_computed_status(agent)
    if "board_id" in updates:
        _require_board(session, updates["board_id"])
    for key, value in updates.items():
        setattr(agent, key, value)
    agent.updated_at = datetime.utcnow()
    if agent.heartbeat_config is None:
        agent.heartbeat_config = DEFAULT_HEARTBEAT_CONFIG.copy()
    session.add(agent)
    session.commit()
    session.refresh(agent)
    board = _require_board(session, agent.board_id)
    gateway, client_config = _require_gateway(session, board)
    session_key = agent.openclaw_session_id or _build_session_key(agent.name)
    try:
        await ensure_session(session_key, config=client_config, label=agent.name)
        if not agent.openclaw_session_id:
            agent.openclaw_session_id = session_key
            session.add(agent)
            session.commit()
            session.refresh(agent)
    except OpenClawGatewayError as exc:
        _record_instruction_failure(session, agent, str(exc), "update")
        session.commit()
    raw_token = generate_agent_token()
    provision_token = generate_agent_token()
    agent.agent_token_hash = hash_agent_token(raw_token)
    agent.provision_confirm_token_hash = hash_agent_token(provision_token)
    agent.provision_requested_at = datetime.utcnow()
    agent.provision_action = "update"
    agent.status = "updating"
    session.add(agent)
    session.commit()
    session.refresh(agent)
    try:
        await send_update_message(agent, board, gateway, raw_token, provision_token, auth.user)
        record_activity(
            session,
            event_type="agent.update.requested",
            message=f"Update requested for {agent.name}.",
            agent_id=agent.id,
        )
        session.commit()
    except OpenClawGatewayError as exc:
        _record_instruction_failure(session, agent, str(exc), "update")
        session.commit()
    except Exception as exc:  # pragma: no cover - unexpected provisioning errors
        _record_instruction_failure(session, agent, str(exc), "update")
        session.commit()
    return _with_computed_status(agent)


@router.post("/{agent_id}/heartbeat", response_model=AgentRead)
def heartbeat_agent(
    agent_id: str,
    payload: AgentHeartbeat,
    session: Session = Depends(get_session),
    actor: ActorContext = Depends(require_admin_or_agent),
) -> Agent:
    agent = session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if actor.actor_type == "agent" and actor.agent and actor.agent.id != agent.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    if payload.status:
        agent.status = payload.status
    elif agent.status == "provisioning":
        agent.status = "online"
    agent.last_seen_at = datetime.utcnow()
    agent.updated_at = datetime.utcnow()
    _record_heartbeat(session, agent)
    session.add(agent)
    session.commit()
    session.refresh(agent)
    return _with_computed_status(agent)


@router.post("/heartbeat", response_model=AgentRead)
async def heartbeat_or_create_agent(
    payload: AgentHeartbeatCreate,
    session: Session = Depends(get_session),
    actor: ActorContext = Depends(require_admin_or_agent),
) -> Agent:
    agent = session.exec(select(Agent).where(Agent.name == payload.name)).first()
    if agent is None:
        if actor.actor_type == "agent":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        board = _require_board(session, payload.board_id)
        gateway, client_config = _require_gateway(session, board)
        agent = Agent(
            name=payload.name,
            status="provisioning",
            board_id=board.id,
            heartbeat_config=DEFAULT_HEARTBEAT_CONFIG.copy(),
        )
        raw_token = generate_agent_token()
        agent.agent_token_hash = hash_agent_token(raw_token)
        provision_token = generate_agent_token()
        agent.provision_confirm_token_hash = hash_agent_token(provision_token)
        agent.provision_requested_at = datetime.utcnow()
        agent.provision_action = "provision"
        session_key, session_error = await _ensure_gateway_session(agent.name, client_config)
        agent.openclaw_session_id = session_key
        session.add(agent)
        session.commit()
        session.refresh(agent)
        if session_error:
            record_activity(
                session,
                event_type="agent.session.failed",
                message=f"Session sync failed for {agent.name}: {session_error}",
                agent_id=agent.id,
            )
        else:
            record_activity(
                session,
                event_type="agent.session.created",
                message=f"Session created for {agent.name}.",
                agent_id=agent.id,
            )
        session.commit()
        try:
            await send_provisioning_message(
                agent, board, gateway, raw_token, provision_token, actor.user
            )
            record_activity(
                session,
                event_type="agent.provision.requested",
                message=f"Provisioning requested for {agent.name}.",
                agent_id=agent.id,
            )
        except OpenClawGatewayError as exc:
            _record_instruction_failure(session, agent, str(exc), "provision")
            session.commit()
        except Exception as exc:  # pragma: no cover - unexpected provisioning errors
            _record_instruction_failure(session, agent, str(exc), "provision")
            session.commit()
    elif actor.actor_type == "agent" and actor.agent and actor.agent.id != agent.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    elif agent.agent_token_hash is None and actor.actor_type == "user":
        raw_token = generate_agent_token()
        agent.agent_token_hash = hash_agent_token(raw_token)
        if agent.heartbeat_config is None:
            agent.heartbeat_config = DEFAULT_HEARTBEAT_CONFIG.copy()
        provision_token = generate_agent_token()
        agent.provision_confirm_token_hash = hash_agent_token(provision_token)
        agent.provision_requested_at = datetime.utcnow()
        agent.provision_action = "provision"
        session.add(agent)
        session.commit()
        session.refresh(agent)
        try:
            board = _require_board(session, str(agent.board_id) if agent.board_id else None)
            gateway, client_config = _require_gateway(session, board)
            await send_provisioning_message(
                agent, board, gateway, raw_token, provision_token, actor.user
            )
            record_activity(
                session,
                event_type="agent.provision.requested",
                message=f"Provisioning requested for {agent.name}.",
                agent_id=agent.id,
            )
        except OpenClawGatewayError as exc:
            _record_instruction_failure(session, agent, str(exc), "provision")
            session.commit()
        except Exception as exc:  # pragma: no cover - unexpected provisioning errors
            _record_instruction_failure(session, agent, str(exc), "provision")
            session.commit()
    elif not agent.openclaw_session_id:
        board = _require_board(session, str(agent.board_id) if agent.board_id else None)
        gateway, client_config = _require_gateway(session, board)
        session_key, session_error = await _ensure_gateway_session(agent.name, client_config)
        agent.openclaw_session_id = session_key
        if session_error:
            record_activity(
                session,
                event_type="agent.session.failed",
                message=f"Session sync failed for {agent.name}: {session_error}",
                agent_id=agent.id,
            )
        else:
            record_activity(
                session,
                event_type="agent.session.created",
                message=f"Session created for {agent.name}.",
                agent_id=agent.id,
            )
        session.commit()
    if payload.status:
        agent.status = payload.status
    elif agent.status == "provisioning":
        agent.status = "online"
    agent.last_seen_at = datetime.utcnow()
    agent.updated_at = datetime.utcnow()
    _record_heartbeat(session, agent)
    session.add(agent)
    session.commit()
    session.refresh(agent)
    return _with_computed_status(agent)


@router.delete("/{agent_id}")
def delete_agent(
    agent_id: str,
    session: Session = Depends(get_session),
    auth: AuthContext = Depends(require_admin_auth),
) -> dict[str, bool]:
    agent = session.get(Agent, agent_id)
    if agent is None:
        return {"ok": True}
    if agent.status == "deleting" and agent.delete_confirm_token_hash:
        return {"ok": True}

    board = _require_board(session, str(agent.board_id) if agent.board_id else None)
    gateway, client_config = _require_gateway(session, board)
    raw_token = generate_agent_token()
    agent.delete_confirm_token_hash = hash_agent_token(raw_token)
    agent.delete_requested_at = datetime.utcnow()
    agent.status = "deleting"
    agent.updated_at = datetime.utcnow()
    session.add(agent)
    record_activity(
        session,
        event_type="agent.delete.requested",
        message=f"Delete requested for {agent.name}.",
        agent_id=agent.id,
    )
    session.commit()

    async def _gateway_cleanup_request() -> None:
        main_session = gateway.main_session_key
        if not main_session:
            raise OpenClawGatewayError("Gateway main_session_key is required")
        workspace_path = _workspace_path(agent.name, gateway.workspace_root)
        base_url = settings.base_url or "REPLACE_WITH_BASE_URL"
        cleanup_message = (
            "Cleanup request for deleted agent.\n\n"
            f"Agent name: {agent.name}\n"
            f"Agent id: {agent.id}\n"
            f"Session key: {agent.openclaw_session_id or _build_session_key(agent.name)}\n"
            f"Workspace path: {workspace_path}\n\n"
            "Actions:\n"
            "1) Remove the workspace directory.\n"
            "2) Delete the agent session from the gateway.\n"
            "3) Confirm deletion by calling:\n"
            f"   POST {base_url}/api/v1/agents/{agent.id}/delete/confirm\n"
            '   Body: {"token": "' + raw_token + '"}\n'
            "Reply NO_REPLY."
        )
        await ensure_session(main_session, config=client_config, label="Main Agent")
        await send_message(
            cleanup_message,
            session_key=main_session,
            config=client_config,
            deliver=False,
        )

    try:
        import asyncio

        asyncio.run(_gateway_cleanup_request())
    except OpenClawGatewayError as exc:
        _record_instruction_failure(session, agent, str(exc), "delete")
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Gateway cleanup request failed: {exc}",
        ) from exc

    return {"ok": True}


@router.post("/{agent_id}/provision/confirm")
def confirm_provision_agent(
    agent_id: str,
    payload: AgentProvisionConfirm,
    session: Session = Depends(get_session),
) -> dict[str, bool]:
    agent = session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if not agent.provision_confirm_token_hash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Provisioning confirmation not requested.",
        )
    if not verify_agent_token(payload.token, agent.provision_confirm_token_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token.")
    if agent.board_id is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
    board = _require_board(session, str(agent.board_id))
    _, client_config = _require_gateway(session, board)

    action = payload.action or agent.provision_action or "provision"
    verb = "updated" if action == "update" else "provisioned"

    try:
        import asyncio

        asyncio.run(_send_wakeup_message(agent, client_config, verb=verb))
    except OpenClawGatewayError as exc:
        _record_wakeup_failure(session, agent, str(exc))
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Wakeup message failed: {exc}",
        ) from exc

    agent.provision_confirm_token_hash = None
    agent.provision_requested_at = None
    agent.provision_action = None
    if action == "update":
        agent.status = "online"
    agent.updated_at = datetime.utcnow()
    session.add(agent)
    record_activity(
        session,
        event_type=f"agent.{action}.confirmed",
        message=f"{action.capitalize()} confirmed for {agent.name}.",
        agent_id=agent.id,
    )
    record_activity(
        session,
        event_type="agent.wakeup.sent",
        message=f"Wakeup message sent to {agent.name}.",
        agent_id=agent.id,
    )
    session.commit()
    return {"ok": True}


@router.post("/{agent_id}/delete/confirm")
def confirm_delete_agent(
    agent_id: str,
    payload: AgentDeleteConfirm,
    session: Session = Depends(get_session),
) -> dict[str, bool]:
    agent = session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if agent.status != "deleting":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Agent is not pending deletion.",
        )
    if not agent.delete_confirm_token_hash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Delete confirmation not requested.",
        )
    if not verify_agent_token(payload.token, agent.delete_confirm_token_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token.")

    record_activity(
        session,
        event_type="agent.delete.confirmed",
        message=f"Deleted agent {agent.name}.",
        agent_id=None,
    )
    session.execute(
        update(ActivityEvent).where(col(ActivityEvent.agent_id) == agent.id).values(agent_id=None)
    )
    session.delete(agent)
    session.commit()
    return {"ok": True}
