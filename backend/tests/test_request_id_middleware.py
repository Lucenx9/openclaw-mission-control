from __future__ import annotations

import pytest

from app.core.error_handling import REQUEST_ID_HEADER, RequestIdMiddleware


@pytest.mark.asyncio
async def test_request_id_middleware_passes_through_non_http_scope() -> None:
    called = False

    async def app(scope, receive, send):  # type: ignore[no-untyped-def]
        nonlocal called
        called = True

    middleware = RequestIdMiddleware(app)

    scope = {"type": "websocket", "headers": []}
    await middleware(scope, lambda: None, lambda message: None)  # type: ignore[arg-type]

    assert called is True


@pytest.mark.asyncio
async def test_request_id_middleware_ignores_blank_client_header_and_generates_one() -> None:
    captured_request_id: str | None = None
    response_headers: list[tuple[bytes, bytes]] = []

    async def app(scope, receive, send):  # type: ignore[no-untyped-def]
        nonlocal captured_request_id
        captured_request_id = scope.get("state", {}).get("request_id")
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def send(message):  # type: ignore[no-untyped-def]
        if message["type"] == "http.response.start":
            response_headers.extend(list(message.get("headers") or []))

    middleware = RequestIdMiddleware(app)

    scope = {
        "type": "http",
        "headers": [(REQUEST_ID_HEADER.lower().encode("latin-1"), b"   ")],
    }
    await middleware(scope, lambda: None, send)

    assert isinstance(captured_request_id, str) and captured_request_id
    # Header should reflect the generated id, not the blank one.
    values = [v for k, v in response_headers if k.lower() == REQUEST_ID_HEADER.lower().encode("latin-1")]
    assert values == [captured_request_id.encode("latin-1")]


@pytest.mark.asyncio
async def test_request_id_middleware_does_not_duplicate_existing_header() -> None:
    sent_start = False
    start_headers: list[tuple[bytes, bytes]] | None = None

    async def app(scope, receive, send):  # type: ignore[no-untyped-def]
        # Simulate an app that already sets the request id header.
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(REQUEST_ID_HEADER.lower().encode("latin-1"), b"already")],
            }
        )
        await send({"type": "http.response.body", "body": b"ok"})

    async def send(message):  # type: ignore[no-untyped-def]
        nonlocal sent_start, start_headers
        if message["type"] == "http.response.start":
            sent_start = True
            start_headers = list(message.get("headers") or [])

    middleware = RequestIdMiddleware(app)

    scope = {"type": "http", "headers": []}
    await middleware(scope, lambda: None, send)

    assert sent_start is True
    assert start_headers is not None

    # Ensure the middleware did not append a second copy.
    values = [v for k, v in start_headers if k.lower() == REQUEST_ID_HEADER.lower().encode("latin-1")]
    assert values == [b"already"]
