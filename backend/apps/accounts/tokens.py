import hashlib
import secrets

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

RESET_TTL_SECONDS = 60 * 60
RESET_PREFIX = "password-reset"
VERIFY_TTL_SECONDS = 60 * 60 * 24 * 3
VERIFY_PREFIX = "email-verify"


def _digest(raw_token):
    return hashlib.sha256(raw_token.encode()).hexdigest()


def _key(prefix, raw_token):
    return f"{prefix}:{_digest(raw_token)}"


def issue_reset_token(user):
    raw = secrets.token_urlsafe(32)
    cache.set(
        _key(RESET_PREFIX, raw),
        {"user_id": user.pk, "issued_at": timezone.now().isoformat()},
        RESET_TTL_SECONDS,
    )
    return raw


def consume_reset_token(raw_token):
    if not raw_token:
        return None
    key = _key(RESET_PREFIX, raw_token)
    payload = cache.get(key)
    if payload is None:
        return None
    cache.delete(key)
    return payload.get("user_id")


def issue_verification_token(user):
    raw = secrets.token_urlsafe(32)
    cache.set(
        _key(VERIFY_PREFIX, raw),
        {"user_id": user.pk},
        VERIFY_TTL_SECONDS,
    )
    return raw


def consume_verification_token(raw_token):
    if not raw_token:
        return None
    key = _key(VERIFY_PREFIX, raw_token)
    payload = cache.get(key)
    if payload is None:
        return None
    cache.delete(key)
    return payload.get("user_id")


def frontend_link(path, token):
    base = getattr(settings, "FRONTEND_URL", "").rstrip("/")
    return f"{base}/{path.lstrip('/')}/{token}"
