# ruff: noqa: INP001

from __future__ import annotations

import pytest

from app.services.webhooks import dispatch


@pytest.mark.parametrize(
    ("payload_event", "payload_value", "expected"),
    [
        ("check_run", {"action": "completed", "check_run": {"status": "completed", "conclusion": "success"}}, True),
        ("check_run", {"action": "completed", "check_run": {"status": "completed", "conclusion": None}}, True),
        ("check_run", {"action": "created", "check_run": {"status": "queued"}}, True),
        ("check_run", {"action": "completed", "check_run": {"status": "completed", "conclusion": "failure"}}, False),
        (
            "workflow_run",
            {"action": "completed", "workflow_run": {"status": "completed", "conclusion": "success"}},
            True,
        ),
        (
            "workflow_run",
            {"action": "completed", "workflow_run": {"status": "completed", "conclusion": "cancelled"}},
            False,
        ),
        (
            "check_suite",
            {"action": "completed", "check_suite": {"status": "completed", "conclusion": "timed_out"}},
            False,
        ),
        (
            "check_suite",
            {"action": "completed", "check_suite": {"status": "completed", "conclusion": "neutral"}},
            True,
        ),
        # Non-target events should not be suppressed by this helper.
        ("pull_request", {"action": "opened"}, False),
        (None, {"action": "opened"}, False),
        # Non-dict payloads: don't suppress (we can't reason about it).
        ("check_run", "raw", False),
    ],
)
def test_should_suppress_routine_delivery(
    monkeypatch: pytest.MonkeyPatch,
    payload_event: str | None,
    payload_value: object,
    expected: bool,
) -> None:
    monkeypatch.setattr(dispatch.settings, "webhook_dispatch_suppress_routine_events", True)
    assert (
        dispatch._should_suppress_routine_delivery(
            payload_event=payload_event,
            payload_value=payload_value,
        )
        is expected
    )


def test_suppression_disabled_via_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dispatch.settings, "webhook_dispatch_suppress_routine_events", False)
    assert (
        dispatch._should_suppress_routine_delivery(
            payload_event="check_run",
            payload_value={
                "action": "completed",
                "check_run": {"status": "completed", "conclusion": "success"},
            },
        )
        is False
    )
