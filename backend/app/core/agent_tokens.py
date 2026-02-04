from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

ITERATIONS = 200_000
SALT_BYTES = 16


def generate_agent_token() -> str:
    return secrets.token_urlsafe(32)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("utf-8").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_agent_token(token: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", token.encode("utf-8"), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${_b64encode(salt)}${_b64encode(digest)}"


def verify_agent_token(token: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt_b64, digest_b64 = stored_hash.split("$")
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    try:
        iterations_int = int(iterations)
    except ValueError:
        return False
    salt = _b64decode(salt_b64)
    expected_digest = _b64decode(digest_b64)
    candidate = hashlib.pbkdf2_hmac("sha256", token.encode("utf-8"), salt, iterations_int)
    return hmac.compare_digest(candidate, expected_digest)
