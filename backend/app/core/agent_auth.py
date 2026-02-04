from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fastapi import Depends, Header, HTTPException, status
from sqlmodel import Session, col, select

from app.core.agent_tokens import verify_agent_token
from app.db.session import get_session
from app.models.agents import Agent


@dataclass
class AgentAuthContext:
    actor_type: Literal["agent"]
    agent: Agent


def _find_agent_for_token(session: Session, token: str) -> Agent | None:
    agents = list(session.exec(select(Agent).where(col(Agent.agent_token_hash).is_not(None))))
    for agent in agents:
        if agent.agent_token_hash and verify_agent_token(token, agent.agent_token_hash):
            return agent
    return None


def get_agent_auth_context(
    agent_token: str | None = Header(default=None, alias="X-Agent-Token"),
    session: Session = Depends(get_session),
) -> AgentAuthContext:
    if not agent_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    agent = _find_agent_for_token(session, agent_token)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return AgentAuthContext(actor_type="agent", agent=agent)


def get_agent_auth_context_optional(
    agent_token: str | None = Header(default=None, alias="X-Agent-Token"),
    session: Session = Depends(get_session),
) -> AgentAuthContext | None:
    if not agent_token:
        return None
    agent = _find_agent_for_token(session, agent_token)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return AgentAuthContext(actor_type="agent", agent=agent)
