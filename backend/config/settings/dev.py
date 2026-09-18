"""Local development settings: SQLite, permissive CORS, console email."""
from decouple import Csv, config

from .base import *  # noqa: F403
from .base import BASE_DIR

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0", "testserver"]

# ---------------------------------------------------------------- database
# SQLite locally for zero setup. Postgres-specific behaviour (JSONB,
# select_for_update) is exercised against Postgres in CI before Phase 3.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# ---------------------------------------------------------------- cors
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:5173,http://127.0.0.1:5173",
    cast=Csv(),
)
CORS_ALLOW_CREDENTIALS = True

# ---------------------------------------------------------------- email
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = "ShopFlow BD <noreply@shopflow.local>"

# Frontend base URL, used to build invite and password-reset links.
FRONTEND_URL = config("FRONTEND_URL", default="http://localhost:5173")
