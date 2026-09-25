from decouple import Csv, config

from .base import *  # noqa: F403
from .base import BASE_DIR

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0", "testserver"]

_database_url = config("DATABASE_URL", default="")

if _database_url:
    import dj_database_url

    DATABASES = {"default": dj_database_url.parse(_database_url)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:5173,http://127.0.0.1:5173",
    cast=Csv(),
)
CORS_ALLOW_CREDENTIALS = True

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = "SellFlow BD <noreply@sellflow.local>"

FRONTEND_URL = config("FRONTEND_URL", default="http://localhost:5173")
