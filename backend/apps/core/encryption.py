import json

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models


def _get_cipher():
    key = getattr(settings, "FIELD_ENCRYPTION_KEY", "")
    if not key:
        raise ImproperlyConfigured(
            "FIELD_ENCRYPTION_KEY is not set. Generate one with "
            "python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


def encrypt_text(value):
    if value in (None, ""):
        return ""
    return _get_cipher().encrypt(str(value).encode()).decode()


def decrypt_text(token):
    if token in (None, ""):
        return ""
    try:
        return _get_cipher().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return ""


class EncryptedJSONField(models.TextField):
    def from_db_value(self, value, expression, connection):
        if value in (None, ""):
            return {}
        plain = decrypt_text(value)
        if not plain:
            return {}
        try:
            return json.loads(plain)
        except json.JSONDecodeError:
            return {}

    def to_python(self, value):
        if isinstance(value, dict):
            return value
        if value in (None, ""):
            return {}
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {}

    def get_prep_value(self, value):
        if value in (None, "", {}):
            return ""
        if not isinstance(value, dict):
            raise ValueError("EncryptedJSONField only stores dictionaries.")
        return encrypt_text(json.dumps(value, sort_keys=True))
