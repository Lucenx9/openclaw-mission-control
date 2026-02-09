# ruff: noqa

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest

from app.services import agent_provisioning
from app.services.gateway_agents import (
    gateway_agent_session_key_for_id,
    gateway_openclaw_agent_id_for_id,
)


def test_slugify_normalizes_and_trims():
    assert agent_provisioning._slugify("Hello, World") == "hello-world"
    assert agent_provisioning._slugify("  A   B  ") == "a-b"


def test_slugify_falls_back_to_uuid_hex(monkeypatch):
    class _FakeUuid:
        hex = "deadbeef"

    monkeypatch.setattr(agent_provisioning, "uuid4", lambda: _FakeUuid())
    assert agent_provisioning._slugify("!!!") == "deadbeef"


def test_agent_id_from_session_key_parses_agent_prefix():
    assert agent_provisioning._agent_id_from_session_key(None) is None
    assert agent_provisioning._agent_id_from_session_key("") is None
    assert agent_provisioning._agent_id_from_session_key("not-agent") is None
    assert agent_provisioning._agent_id_from_session_key("agent:") is None
    assert agent_provisioning._agent_id_from_session_key("agent:riya:main") == "riya"


def test_agent_id_from_session_key_ignores_gateway_main_session_key():
    session_key = gateway_agent_session_key_for_id(uuid4())
    assert agent_provisioning._agent_id_from_session_key(session_key) is None


def test_extract_agent_id_supports_lists_and_dicts():
    assert agent_provisioning._extract_agent_id(["", "  ", "abc"]) == "abc"
    assert agent_provisioning._extract_agent_id([{"agent_id": "xyz"}]) == "xyz"

    payload = {
        "defaultAgentId": "dflt",
        "agents": [{"id": "ignored"}],
    }
    assert agent_provisioning._extract_agent_id(payload) == "dflt"

    payload2 = {
        "agents": [{"id": ""}, {"agentId": "foo"}],
    }
    assert agent_provisioning._extract_agent_id(payload2) == "foo"


def test_extract_agent_id_returns_none_for_unknown_shapes():
    assert agent_provisioning._extract_agent_id("nope") is None
    assert agent_provisioning._extract_agent_id({"agents": "not-a-list"}) is None


@dataclass
class _AgentStub:
    name: str
    openclaw_session_id: str | None = None
    heartbeat_config: dict | None = None
    is_board_lead: bool = False
    id: UUID = field(default_factory=uuid4)
    identity_profile: dict | None = None
    identity_template: str | None = None
    soul_template: str | None = None


def test_agent_key_uses_session_key_when_present(monkeypatch):
    agent = _AgentStub(name="Alice", openclaw_session_id="agent:alice:main")
    assert agent_provisioning._agent_key(agent) == "alice"

    monkeypatch.setattr(agent_provisioning, "_slugify", lambda value: "slugged")
    agent2 = _AgentStub(name="Alice", openclaw_session_id=None)
    assert agent_provisioning._agent_key(agent2) == "slugged"


@dataclass
class _GatewayStub:
    id: UUID
    name: str
    url: str
    token: str | None
    workspace_root: str
    main_session_key: str


@pytest.mark.asyncio
async def test_provision_main_agent_uses_dedicated_openclaw_agent_id(monkeypatch):
    gateway_id = uuid4()
    session_key = gateway_agent_session_key_for_id(gateway_id)
    gateway = _GatewayStub(
        id=gateway_id,
        name="Acme",
        url="ws://gateway.example/ws",
        token=None,
        workspace_root="/tmp/openclaw",
        main_session_key=session_key,
    )
    agent = _AgentStub(name="Acme Gateway Agent", openclaw_session_id=session_key)
    captured: dict[str, object] = {}

    async def _fake_ensure_session(*args, **kwargs):
        return None

    async def _fake_patch_gateway_agent_list(agent_id, workspace_path, heartbeat, config):
        captured["patched_agent_id"] = agent_id
        captured["workspace_path"] = workspace_path

    async def _fake_supported_gateway_files(config):
        return set()

    async def _fake_gateway_agent_files_index(agent_id, config):
        captured["files_index_agent_id"] = agent_id
        return {}

    def _fake_render_agent_files(*args, **kwargs):
        return {}

    async def _fake_set_agent_files(*args, **kwargs):
        return None

    monkeypatch.setattr(agent_provisioning, "ensure_session", _fake_ensure_session)
    monkeypatch.setattr(agent_provisioning, "_patch_gateway_agent_list", _fake_patch_gateway_agent_list)
    monkeypatch.setattr(agent_provisioning, "_supported_gateway_files", _fake_supported_gateway_files)
    monkeypatch.setattr(
        agent_provisioning,
        "_gateway_agent_files_index",
        _fake_gateway_agent_files_index,
    )
    monkeypatch.setattr(agent_provisioning, "_render_agent_files", _fake_render_agent_files)
    monkeypatch.setattr(agent_provisioning, "_set_agent_files", _fake_set_agent_files)

    await agent_provisioning.provision_main_agent(
        agent,
        agent_provisioning.MainAgentProvisionRequest(
            gateway=gateway,
            auth_token="secret-token",
            user=None,
            session_key=session_key,
        ),
    )

    expected_agent_id = gateway_openclaw_agent_id_for_id(gateway_id)
    assert captured["patched_agent_id"] == expected_agent_id
    assert captured["files_index_agent_id"] == expected_agent_id
