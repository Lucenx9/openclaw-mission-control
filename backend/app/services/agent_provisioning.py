from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from app.core.config import settings
from app.integrations.openclaw_gateway import GatewayConfig as GatewayClientConfig
from app.integrations.openclaw_gateway import ensure_session, send_message
from app.models.agents import Agent
from app.models.boards import Board
from app.models.gateways import Gateway
from app.models.users import User

TEMPLATE_FILES = [
    "AGENTS.md",
    "BOOT.md",
    "BOOTSTRAP.md",
    "HEARTBEAT.md",
    "IDENTITY.md",
    "SOUL.md",
    "TOOLS.md",
    "USER.md",
]

DEFAULT_HEARTBEAT_CONFIG = {"every": "10m", "target": "none"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _templates_root() -> Path:
    return _repo_root() / "templates"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or uuid4().hex


def _agent_key(agent: Agent) -> str:
    session_key = agent.openclaw_session_id or ""
    if session_key.startswith("agent:"):
        parts = session_key.split(":")
        if len(parts) >= 2 and parts[1]:
            return parts[1]
    return _slugify(agent.name)


def _heartbeat_config(agent: Agent) -> dict[str, Any]:
    if agent.heartbeat_config:
        return agent.heartbeat_config
    return DEFAULT_HEARTBEAT_CONFIG.copy()


def _template_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(_templates_root()),
        autoescape=select_autoescape(default=True),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )


def _read_templates(
    context: dict[str, str], overrides: dict[str, str] | None = None
) -> dict[str, str]:
    env = _template_env()
    templates: dict[str, str] = {}
    override_map = overrides or {}
    for name in TEMPLATE_FILES:
        path = _templates_root() / name
        override = override_map.get(name)
        if override:
            templates[name] = env.from_string(override).render(**context).strip()
            continue
        if not path.exists():
            templates[name] = ""
            continue
        template = env.get_template(name)
        templates[name] = template.render(**context).strip()
    return templates


def _render_file_block(name: str, content: str) -> str:
    body = content if content else f"# {name}\n\nTODO: add content\n"
    return f"\n{name}\n```md\n{body}\n```\n"


def _workspace_path(agent_name: str, workspace_root: str) -> str:
    if not workspace_root:
        raise ValueError("gateway_workspace_root is required")
    root = workspace_root
    root = root.rstrip("/")
    return f"{root}/workspace-{_slugify(agent_name)}"


def _build_context(
    agent: Agent,
    board: Board,
    gateway: Gateway,
    auth_token: str,
    user: User | None,
) -> dict[str, str]:
    if not gateway.workspace_root:
        raise ValueError("gateway_workspace_root is required")
    if not gateway.main_session_key:
        raise ValueError("gateway_main_session_key is required")
    agent_id = str(agent.id)
    workspace_root = gateway.workspace_root
    workspace_path = _workspace_path(agent.name, workspace_root)
    session_key = agent.openclaw_session_id or ""
    base_url = settings.base_url or "REPLACE_WITH_BASE_URL"
    main_session_key = gateway.main_session_key
    return {
        "agent_name": agent.name,
        "agent_id": agent_id,
        "board_id": str(board.id),
        "session_key": session_key,
        "workspace_path": workspace_path,
        "base_url": base_url,
        "auth_token": auth_token,
        "main_session_key": main_session_key,
        "workspace_root": workspace_root,
        "user_name": (user.name or "") if user else "",
        "user_preferred_name": (user.preferred_name or "") if user else "",
        "user_pronouns": (user.pronouns or "") if user else "",
        "user_timezone": (user.timezone or "") if user else "",
        "user_notes": (user.notes or "") if user else "",
        "user_context": (user.context or "") if user else "",
    }


def _build_file_blocks(context: dict[str, str], agent: Agent) -> str:
    overrides: dict[str, str] = {}
    if agent.identity_template:
        overrides["IDENTITY.md"] = agent.identity_template
    if agent.soul_template:
        overrides["SOUL.md"] = agent.soul_template
    templates = _read_templates(context, overrides=overrides)
    return "".join(_render_file_block(name, templates.get(name, "")) for name in TEMPLATE_FILES)


def build_provisioning_message(
    agent: Agent,
    board: Board,
    gateway: Gateway,
    auth_token: str,
    confirm_token: str,
    user: User | None,
) -> str:
    context = _build_context(agent, board, gateway, auth_token, user)
    file_blocks = _build_file_blocks(context, agent)
    heartbeat_snippet = json.dumps(
        {
            "id": _agent_key(agent),
            "workspace": context["workspace_path"],
            "heartbeat": _heartbeat_config(agent),
        },
        indent=2,
        sort_keys=True,
    )
    return (
        "Provision a new OpenClaw agent workspace.\n\n"
        f"Agent name: {context['agent_name']}\n"
        f"Agent id: {context['agent_id']}\n"
        f"Session key: {context['session_key']}\n"
        f"Workspace path: {context['workspace_path']}\n\n"
        f"Base URL: {context['base_url']}\n"
        f"Auth token: {context['auth_token']}\n\n"
        "Steps:\n"
        "0) IMPORTANT: Do NOT replace or repurpose the main agent. Keep "
        f"{context['main_session_key']} unchanged and its workspace intact.\n"
        "1) Create the workspace directory.\n"
        "2) Write the files below with the exact contents.\n"
        "3) Update TOOLS.md if BASE_URL/AUTH_TOKEN must change.\n"
        "4) Leave BOOTSTRAP.md in place; the agent should run it on first start and delete it.\n"
        "5) Register agent id in OpenClaw so it uses this workspace path "
        "(never overwrite the main agent session).\n"
        "   IMPORTANT: Use the configured gateway workspace root. "
        "Workspace path must be <root>/workspace-<slug>.\n"
        "6) Add/update the per-agent heartbeat config in the gateway config "
        "for this agent (merge into agents.list entry):\n"
        "```json\n"
        f"{heartbeat_snippet}\n"
        "```\n"
        "Note: if any agents.list entry defines heartbeat, only those agents "
        "run heartbeats.\n"
        "7) After provisioning completes, confirm by calling:\n"
        f"   POST {context['base_url']}/api/v1/agents/{context['agent_id']}/provision/confirm\n"
        f'   Body: {{"token": "{confirm_token}", "action": "provision"}}\n\n'
        "Files:" + file_blocks
    )


def build_update_message(
    agent: Agent,
    board: Board,
    gateway: Gateway,
    auth_token: str,
    confirm_token: str,
    user: User | None,
) -> str:
    context = _build_context(agent, board, gateway, auth_token, user)
    file_blocks = _build_file_blocks(context, agent)
    heartbeat_snippet = json.dumps(
        {
            "id": _agent_key(agent),
            "workspace": context["workspace_path"],
            "heartbeat": _heartbeat_config(agent),
        },
        indent=2,
        sort_keys=True,
    )
    return (
        "Update an existing OpenClaw agent workspace.\n\n"
        f"Agent name: {context['agent_name']}\n"
        f"Agent id: {context['agent_id']}\n"
        f"Session key: {context['session_key']}\n"
        f"Workspace path: {context['workspace_path']}\n\n"
        f"Base URL: {context['base_url']}\n"
        f"Auth token: {context['auth_token']}\n\n"
        "Steps:\n"
        "0) IMPORTANT: Do NOT replace or repurpose the main agent. Keep "
        f"{context['main_session_key']} unchanged and its workspace intact.\n"
        "1) Locate the existing workspace directory (do NOT create a new one or change its path).\n"
        "2) Overwrite the files below with the exact contents.\n"
        "3) Update TOOLS.md with the new BASE_URL/AUTH_TOKEN/SESSION_KEY values.\n"
        "4) Do NOT create a new agent or session; update the existing one in place.\n"
        "5) Keep BOOTSTRAP.md only if it already exists; do not recreate it if missing.\n\n"
        "   IMPORTANT: Use the configured gateway workspace root. "
        "Workspace path must be <root>/workspace-<slug>.\n"
        "6) Update the per-agent heartbeat config in the gateway config for this agent:\n"
        "```json\n"
        f"{heartbeat_snippet}\n"
        "```\n"
        "Note: if any agents.list entry defines heartbeat, only those agents "
        "run heartbeats.\n"
        "7) After the update completes (and only after files are written), confirm by calling:\n"
        f"   POST {context['base_url']}/api/v1/agents/{context['agent_id']}/provision/confirm\n"
        f'   Body: {{"token": "{confirm_token}", "action": "update"}}\n'
        "   Mission Control will send the hello message only after this confirmation.\n\n"
        "Files:" + file_blocks
    )


async def send_provisioning_message(
    agent: Agent,
    board: Board,
    gateway: Gateway,
    auth_token: str,
    confirm_token: str,
    user: User | None,
) -> None:
    if not gateway.url:
        return
    if not gateway.main_session_key:
        raise ValueError("gateway_main_session_key is required")
    main_session = gateway.main_session_key
    client_config = GatewayClientConfig(url=gateway.url, token=gateway.token)
    await ensure_session(main_session, config=client_config, label="Main Agent")
    message = build_provisioning_message(agent, board, gateway, auth_token, confirm_token, user)
    await send_message(message, session_key=main_session, config=client_config, deliver=False)


async def send_update_message(
    agent: Agent,
    board: Board,
    gateway: Gateway,
    auth_token: str,
    confirm_token: str,
    user: User | None,
) -> None:
    if not gateway.url:
        return
    if not gateway.main_session_key:
        raise ValueError("gateway_main_session_key is required")
    main_session = gateway.main_session_key
    client_config = GatewayClientConfig(url=gateway.url, token=gateway.token)
    await ensure_session(main_session, config=client_config, label="Main Agent")
    message = build_update_message(agent, board, gateway, auth_token, confirm_token, user)
    await send_message(message, session_key=main_session, config=client_config, deliver=False)
