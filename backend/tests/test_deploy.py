import base64
import hashlib
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from django.test import override_settings

from apps.core import encryption

pytestmark = pytest.mark.django_db

JOBS = "/api/v1/internal/jobs/run/"


class TestEncryptionKeyFormats:
    def test_valid_fernet_key_is_used_unchanged(self):
        key = Fernet.generate_key().decode()
        with override_settings(FIELD_ENCRYPTION_KEY=key):
            token = encryption.encrypt_text("secret")

        assert Fernet(key.encode()).decrypt(token.encode()).decode() == "secret"

    def test_arbitrary_secret_string_is_accepted(self):
        with override_settings(FIELD_ENCRYPTION_KEY="any+render/generated=value"):
            token = encryption.encrypt_text("secret")
            assert encryption.decrypt_text(token) == "secret"

    def test_arbitrary_secret_derives_a_stable_key(self):
        raw = "any+render/generated=value"
        derived = base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())
        with override_settings(FIELD_ENCRYPTION_KEY=raw):
            token = encryption.encrypt_text("secret")

        assert Fernet(derived).decrypt(token.encode()).decode() == "secret"

    def test_missing_key_still_fails_loudly(self):
        from django.core.exceptions import ImproperlyConfigured

        with override_settings(FIELD_ENCRYPTION_KEY=""):
            with pytest.raises(ImproperlyConfigured):
                encryption.encrypt_text("secret")


class TestScheduledJobsEndpoint:
    def test_hidden_when_no_secret_is_configured(self, api):
        with override_settings(CRON_SECRET=""):
            response = api.post(JOBS, HTTP_X_CRON_SECRET="")
        assert response.status_code == 404

    def test_hidden_from_a_wrong_secret(self, api):
        with override_settings(CRON_SECRET="right"):
            response = api.post(JOBS, HTTP_X_CRON_SECRET="wrong")
        assert response.status_code == 404

    def test_hidden_when_header_is_missing(self, api):
        with override_settings(CRON_SECRET="right"):
            response = api.post(JOBS)
        assert response.status_code == 404

    def test_runs_both_jobs_with_the_right_secret(self, api):
        with override_settings(CRON_SECRET="right"), \
             patch("apps.shipments.services.sync_due_shipments", return_value=3) as sync, \
             patch("apps.notifications.services.run_all_scans",
                   return_value={"stores": 1, "low_stock": 0, "cod_overdue": 0}) as scans:
            response = api.post(JOBS, HTTP_X_CRON_SECRET="right")

        assert response.status_code == 200
        assert response.data["shipments_synced"] == 3
        sync.assert_called_once_with(limit=25)
        scans.assert_called_once()

    def test_limit_is_clamped(self, api):
        with override_settings(CRON_SECRET="right"), \
             patch("apps.shipments.services.sync_due_shipments", return_value=0) as sync, \
             patch("apps.notifications.services.run_all_scans", return_value={}):
            api.post(f"{JOBS}?limit=5000", HTTP_X_CRON_SECRET="right")

        sync.assert_called_once_with(limit=100)

    def test_get_is_not_allowed(self, api):
        with override_settings(CRON_SECRET="right"):
            response = api.get(JOBS, HTTP_X_CRON_SECRET="right")
        assert response.status_code == 405

    def test_runs_for_real_against_an_empty_database(self, api):
        with override_settings(CRON_SECRET="right"):
            response = api.post(JOBS, HTTP_X_CRON_SECRET="right")

        assert response.status_code == 200
        assert response.data["shipments_synced"] == 0


class TestEnsureSuperuser:
    def _run(self):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("ensure_superuser", stdout=out)
        return out.getvalue()

    def test_skips_without_variables(self, monkeypatch):
        monkeypatch.delenv("DJANGO_SUPERUSER_EMAIL", raising=False)
        monkeypatch.delenv("DJANGO_SUPERUSER_PASSWORD", raising=False)
        from apps.accounts.models import User

        assert "skipping" in self._run()
        assert not User.objects.filter(is_superuser=True).exists()

    def test_creates_the_superuser_with_a_default_name(self, monkeypatch):
        monkeypatch.setenv("DJANGO_SUPERUSER_EMAIL", "Admin@Example.com")
        monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "Deploy-check-123")
        monkeypatch.delenv("DJANGO_SUPERUSER_FULL_NAME", raising=False)
        from apps.accounts.models import User

        assert "Created" in self._run()
        user = User.objects.get(email="admin@example.com")
        assert user.is_superuser and user.is_staff
        assert user.full_name == "Platform Admin"
        assert user.check_password("Deploy-check-123")

    def test_second_run_leaves_the_existing_user_alone(self, monkeypatch):
        monkeypatch.setenv("DJANGO_SUPERUSER_EMAIL", "admin@example.com")
        monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "Deploy-check-123")
        from apps.accounts.models import User

        self._run()
        monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "Changed-456")
        assert "already exists" in self._run()
        assert User.objects.filter(email="admin@example.com").count() == 1
        assert User.objects.get(email="admin@example.com").check_password(
            "Deploy-check-123"
        )


class TestCrossOriginFrontend:
    ORIGIN = "https://shopflow-web.onrender.com"

    def test_preflight_allows_the_store_header(self, api):
        with override_settings(CORS_ALLOWED_ORIGINS=[self.ORIGIN]):
            response = api.options(
                "/api/v1/orders/",
                HTTP_ORIGIN=self.ORIGIN,
                HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
                HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization,x-store-id",
            )

        allowed = response["access-control-allow-headers"].lower()
        assert response["access-control-allow-origin"] == self.ORIGIN
        assert "x-store-id" in allowed
        assert "authorization" in allowed

    def test_download_filename_is_exposed(self, api):
        with override_settings(CORS_ALLOWED_ORIGINS=[self.ORIGIN]):
            response = api.get("/healthz/", HTTP_ORIGIN=self.ORIGIN)

        exposed = response["access-control-expose-headers"].lower()
        assert "content-disposition" in exposed
