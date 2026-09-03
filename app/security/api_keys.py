from __future__ import annotations

import hashlib
import hmac
import secrets

RAW_KEY_PREFIX = "cax_"
KEY_ID_PREFIX = "cak_"


def generate_raw_api_key() -> str:
    """Generate a high-entropy raw API key.

    ``secrets.token_urlsafe(32)`` yields >= 256 bits of randomness.
    """
    return f"{RAW_KEY_PREFIX}{secrets.token_urlsafe(32)}"


def generate_key_id() -> str:
    """Generate a non-secret identifier used to reference a key (e.g. in logs)."""
    return f"{KEY_ID_PREFIX}{secrets.token_hex(4)}"


def hash_api_key(raw_key: str, pepper: str) -> str:
    """HMAC-SHA-256(pepper, raw_key), hex-encoded, for storage/lookup."""
    if not pepper:
        raise ValueError("API_KEY_PEPPER must not be empty")
    digest = hmac.new(pepper.encode("utf-8"), raw_key.encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()


def verify_api_key(raw_key: str, pepper: str, expected_hash: str) -> bool:
    """Constant-time comparison of a freshly computed hash against the stored one."""
    computed = hash_api_key(raw_key, pepper)
    return hmac.compare_digest(computed, expected_hash)
