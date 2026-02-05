from __future__ import annotations

import json
import re
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.api.deps import get_board_or_404, require_admin_auth
from app.core.agent_tokens import generate_agent_token, hash_agent_token
from app.core.auth import AuthContext
from app.db.session import get_session
from app.integrations.openclaw_gateway import GatewayConfig as GatewayClientConfig
from app.integrations.openclaw_gateway import (
    OpenClawGatewayError,
    ensure_session,
    get_chat_history,
    send_message,
)
from app.models.agents import Agent
from app.models.board_onboarding import BoardOnboardingSession
from app.models.boards import Board
from app.models.gateways import Gateway
from app.schemas.board_onboarding import (
    BoardOnboardingAnswer,
    BoardOnboardingConfirm,
    BoardOnboardingRead,
    BoardOnboardingStart,
)
from app.schemas.boards import BoardRead
from app.services.agent_provisioning import DEFAULT_HEARTBEAT_CONFIG, provision_agent

router = APIRouter(prefix="/boards/{board_id}/onboarding", tags=["board-onboarding"])

def _extract_json(text: str) -> dict[str, object] | None:
    try:
        return json.loads(text.strip())
    except Exception:
        pass
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except Exception:
            pass
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last > first:
        try:
            return json.loads(text[first : last + 1])
        except Exception:
            return None
    return None


def _extract_text(content: object) -> str | None:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for entry in content:
            if isinstance(entry, dict) and entry.get("type") == "text":
                text = entry.get("text")
                if isinstance(text, str):
                    return text
    if isinstance(content, dict):
        text = content.get("text")
        if isinstance(text, str):
            return text
    return None


def _get_assistant_messages(history: object) -> list[str]:
    messages: list[str] = []
    if isinstance(history, dict):
        history = history.get("messages")
    if not isinstance(history, list):
        return messages
    for msg in history:
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "assistant":
            continue
        text = _extract_text(msg.get("content"))
        if text:
            messages.append(text)
    return messages


def _gateway_config(session: Session, board: Board) -> tuple[Gateway, GatewayClientConfig]:
    if not board.gateway_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
    gateway = session.get(Gateway, board.gateway_id)
    if gateway is None or not gateway.url or not gateway.main_session_key:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
    return gateway, GatewayClientConfig(url=gateway.url, token=gateway.token)


def _build_session_key(agent_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", agent_name.lower()).strip("-")
    return f"agent:{slug or uuid4().hex}:main"


def _lead_agent_name(board: Board) -> str:
    return f"{board.name} Lead"


async def _ensure_lead_agent(
    session: Session,
    board: Board,
    gateway: Gateway,
    config: GatewayClientConfig,
    auth: AuthContext,
) -> Agent:
    existing = session.exec(
        select(Agent)
        .where(Agent.board_id == board.id)
        .where(Agent.is_board_lead.is_(True))
    ).first()
    if existing:
        return existing

    agent = Agent(
        name=_lead_agent_name(board),
        status="provisioning",
        board_id=board.id,
        is_board_lead=True,
        heartbeat_config=DEFAULT_HEARTBEAT_CONFIG.copy(),
        identity_profile={
            "role": "Board Lead",
            "communication_style": "direct, concise, practical",
            "emoji": ":compass:",
        },
    )
    raw_token = generate_agent_token()
    agent.agent_token_hash = hash_agent_token(raw_token)
    agent.provision_requested_at = datetime.utcnow()
    agent.provision_action = "provision"
    agent.openclaw_session_id = _build_session_key(agent.name)
    session.add(agent)
    session.commit()
    session.refresh(agent)

    try:
        await provision_agent(agent, board, gateway, raw_token, auth.user, action="provision")
        await ensure_session(agent.openclaw_session_id, config=config, label=agent.name)
        await send_message(
            (
                f"Hello {agent.name}. Your workspace has been provisioned.\n\n"
                "Start the agent, run BOOT.md, and if BOOTSTRAP.md exists run it once "
                "then delete it. Begin heartbeats after startup."
            ),
            session_key=agent.openclaw_session_id,
            config=config,
            deliver=True,
        )
    except OpenClawGatewayError:
        # Best-effort provisioning. Board confirmation should still succeed.
        pass
    return agent


@router.get("", response_model=BoardOnboardingRead)
def get_onboarding(
    board: Board = Depends(get_board_or_404),
    session: Session = Depends(get_session),
    auth: AuthContext = Depends(require_admin_auth),
) -> BoardOnboardingSession:
    onboarding = session.exec(
        select(BoardOnboardingSession)
        .where(BoardOnboardingSession.board_id == board.id)
        .order_by(BoardOnboardingSession.created_at.desc())
    ).first()
    if onboarding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return onboarding


@router.post("/start", response_model=BoardOnboardingRead)
async def start_onboarding(
    payload: BoardOnboardingStart,
    board: Board = Depends(get_board_or_404),
    session: Session = Depends(get_session),
    auth: AuthContext = Depends(require_admin_auth),
) -> BoardOnboardingSession:
    onboarding = session.exec(
        select(BoardOnboardingSession)
        .where(BoardOnboardingSession.board_id == board.id)
        .where(BoardOnboardingSession.status == "active")
    ).first()
    if onboarding:
        return onboarding

    gateway, config = _gateway_config(session, board)
    session_key = gateway.main_session_key
    prompt = (
        "BOARD ONBOARDING REQUEST\n\n"
        f"Board Name: {board.name}\n"
        "You are the main agent. Ask the user 3-6 focused questions to clarify their goal.\n"
        "Return questions as JSON: {\"question\": \"...\", \"options\": [...]}.\n"
        "When you have enough info, return JSON: {\"status\": \"complete\", \"board_type\": \"goal\"|\"general\", "
        "\"objective\": \"...\", \"success_metrics\": {...}, \"target_date\": \"YYYY-MM-DD\"}."
    )

    try:
        await ensure_session(session_key, config=config, label="Main Agent")
        await send_message(prompt, session_key=session_key, config=config, deliver=False)
    except OpenClawGatewayError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    onboarding = BoardOnboardingSession(
        board_id=board.id,
        session_key=session_key,
        status="active",
        messages=[{"role": "user", "content": prompt, "timestamp": datetime.utcnow().isoformat()}],
    )
    session.add(onboarding)
    session.commit()
    session.refresh(onboarding)
    return onboarding


@router.post("/answer", response_model=BoardOnboardingRead)
async def answer_onboarding(
    payload: BoardOnboardingAnswer,
    board: Board = Depends(get_board_or_404),
    session: Session = Depends(get_session),
    auth: AuthContext = Depends(require_admin_auth),
) -> BoardOnboardingSession:
    onboarding = session.exec(
        select(BoardOnboardingSession)
        .where(BoardOnboardingSession.board_id == board.id)
        .order_by(BoardOnboardingSession.created_at.desc())
    ).first()
    if onboarding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    _, config = _gateway_config(session, board)
    answer_text = payload.answer
    if payload.other_text:
        answer_text = f"{payload.answer}: {payload.other_text}"

    messages = onboarding.messages or []
    messages.append(
        {"role": "user", "content": answer_text, "timestamp": datetime.utcnow().isoformat()}
    )

    try:
        await ensure_session(onboarding.session_key, config=config, label="Main Agent")
        await send_message(
            answer_text, session_key=onboarding.session_key, config=config, deliver=False
        )
        history = await get_chat_history(onboarding.session_key, config=config)
    except OpenClawGatewayError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    assistant_messages = _get_assistant_messages(history)
    if assistant_messages:
        last = assistant_messages[-1]
        messages.append(
            {"role": "assistant", "content": last, "timestamp": datetime.utcnow().isoformat()}
        )
        parsed = _extract_json(last)
        if parsed and parsed.get("status") == "complete":
            onboarding.draft_goal = parsed
            onboarding.status = "completed"

    onboarding.messages = messages
    onboarding.updated_at = datetime.utcnow()
    session.add(onboarding)
    session.commit()
    session.refresh(onboarding)
    return onboarding


@router.post("/confirm", response_model=BoardRead)
async def confirm_onboarding(
    payload: BoardOnboardingConfirm,
    board: Board = Depends(get_board_or_404),
    session: Session = Depends(get_session),
    auth: AuthContext = Depends(require_admin_auth),
) -> Board:
    onboarding = session.exec(
        select(BoardOnboardingSession)
        .where(BoardOnboardingSession.board_id == board.id)
        .order_by(BoardOnboardingSession.created_at.desc())
    ).first()
    if onboarding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    board.board_type = payload.board_type
    board.objective = payload.objective
    board.success_metrics = payload.success_metrics
    board.target_date = payload.target_date
    board.goal_confirmed = True
    board.goal_source = "lead_agent_onboarding"

    onboarding.status = "confirmed"
    onboarding.updated_at = datetime.utcnow()

    gateway, config = _gateway_config(session, board)
    session.add(board)
    session.add(onboarding)
    session.commit()
    session.refresh(board)
    await _ensure_lead_agent(session, board, gateway, config, auth)
    return board
