# ruff: noqa: S101
"""Tests for gateway model-registry pull helper normalization."""

from __future__ import annotations

from app.services.openclaw.model_registry_service import (
    _extract_config_data,
    _get_nested_path,
    _infer_provider_for_model,
    _model_config,
    _model_settings,
    _normalize_provider,
    _parse_agent_model_value,
)


def test_get_nested_path_resolves_existing_value() -> None:
    source = {"providers": {"openai": {"apiKey": "sk-test"}}}

    assert _get_nested_path(source, ["providers", "openai", "apiKey"]) == "sk-test"
    assert _get_nested_path(source, ["providers", "anthropic", "apiKey"]) is None


def test_normalize_provider_trims_and_lowercases() -> None:
    assert _normalize_provider("  OpenAI ") == "openai"
    assert _normalize_provider("") is None
    assert _normalize_provider(123) is None


def test_infer_provider_for_model_prefers_prefix_delimiter() -> None:
    assert _infer_provider_for_model("openai/gpt-5") == "openai"
    assert _infer_provider_for_model("anthropic:claude-sonnet") == "anthropic"
    assert _infer_provider_for_model("gpt-5") == "unknown"


def test_model_settings_only_accepts_dict_payloads() -> None:
    settings = _model_settings({"provider": "openai", "temperature": 0.2})

    assert settings == {"provider": "openai", "temperature": 0.2}
    assert _model_settings("not-a-dict") is None


def test_parse_agent_model_value_normalizes_primary_and_fallbacks() -> None:
    primary, fallback = _parse_agent_model_value(
        {
            "primary": " openai/gpt-5 ",
            "fallbacks": [
                "openai/gpt-4.1",
                "openai/gpt-5",
                "openai/gpt-4.1",
                " ",
                123,
            ],
        },
    )

    assert primary == "openai/gpt-5"
    assert fallback == ["openai/gpt-4.1"]


def test_parse_agent_model_value_accepts_legacy_fallback_key() -> None:
    primary, fallback = _parse_agent_model_value(
        {
            "primary": "openai/gpt-5",
            "fallback": ["openai/gpt-4.1", "openai/gpt-4.1"],
        },
    )

    assert primary == "openai/gpt-5"
    assert fallback == ["openai/gpt-4.1"]


def test_parse_agent_model_value_accepts_string_primary() -> None:
    primary, fallback = _parse_agent_model_value("  openai/gpt-5  ")

    assert primary == "openai/gpt-5"
    assert fallback == []


def test_model_config_uses_fallbacks_key() -> None:
    assert _model_config("openai/gpt-5", ["openai/gpt-4.1"]) == {
        "primary": "openai/gpt-5",
        "fallbacks": ["openai/gpt-4.1"],
    }


def test_extract_config_data_prefers_parsed_when_config_is_raw_string() -> None:
    config_data, base_hash = _extract_config_data(
        {
            "config": '{"agents":{"list":[{"id":"a1"}]}}',
            "parsed": {"agents": {"list": [{"id": "a1"}]}},
            "hash": "abc123",
        },
    )

    assert isinstance(config_data, dict)
    assert config_data.get("agents") == {"list": [{"id": "a1"}]}
    assert base_hash == "abc123"


def test_extract_config_data_parses_json_string_when_parsed_absent() -> None:
    config_data, base_hash = _extract_config_data(
        {
            "config": '{"providers":{"openai":{"apiKey":"sk-test"}}}',
            "hash": "def456",
        },
    )

    assert config_data.get("providers") == {"openai": {"apiKey": "sk-test"}}
    assert base_hash == "def456"
