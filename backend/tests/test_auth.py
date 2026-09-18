"""Registration, login, token lifecycle and profile (PRD FR-1.1, FR-1.2)."""
import pytest

from apps.accounts.models import User, normalise_bd_phone

pytestmark = pytest.mark.django_db

REGISTER = "/api/v1/auth/register/"
LOGIN = "/api/v1/auth/login/"
REFRESH = "/api/v1/auth/refresh/"
LOGOUT = "/api/v1/auth/logout/"
ME = "/api/v1/auth/me/"

GOOD_PASSWORD = "Str0ngPass!23"


def _payload(**overrides):
    data = {
        "email": "new@example.com",
        "full_name": "New Seller",
        "phone": "01712345678",
        "password": GOOD_PASSWORD,
        "password_confirm": GOOD_PASSWORD,
    }
    data.update(overrides)
    return data


class TestPhoneNormalisation:
    """
    Every local phone format must collapse to one canonical value, or
    customer lookup-by-phone silently creates duplicates (PRD FR-4.1).
    """

    @pytest.mark.parametrize(
        "raw",
        [
            "01712345678",
            "+8801712345678",
            "8801712345678",
            "+880 1712-345678",
            "01712 345 678",
        ],
    )
    def test_formats_collapse_to_canonical(self, raw):
        assert normalise_bd_phone(raw) == "+8801712345678"

    @pytest.mark.parametrize(
        "raw", ["0171234567", "01212345678", "12345", "abcdefghijk", "+11234567890"]
    )
    def test_invalid_numbers_rejected(self, raw):
        from django.core.exceptions import ValidationError

        with pytest.raises(ValidationError):
            normalise_bd_phone(raw)

    def test_blank_is_allowed(self):
        assert normalise_bd_phone("") == ""


class TestRegistration:
    def test_creates_account_and_returns_tokens(self, api):
        response = api.post(REGISTER, _payload(), format="json")

        assert response.status_code == 201
        assert "access" in response.data
        assert "refresh" in response.data
        assert response.data["user"]["email"] == "new@example.com"
        # A brand-new account has no store yet; the wizard comes next.
        assert response.data["stores"] == []

    def test_phone_is_stored_normalised(self, api):
        api.post(REGISTER, _payload(phone="01712345678"), format="json")
        assert User.objects.get(email="new@example.com").phone == "+8801712345678"

    def test_email_is_lowercased(self, api):
        api.post(REGISTER, _payload(email="MiXeD@Example.COM"), format="json")
        assert User.objects.filter(email="mixed@example.com").exists()

    def test_duplicate_email_rejected(self, api, make_user):
        make_user(email="taken@example.com")
        response = api.post(REGISTER, _payload(email="taken@example.com"), format="json")

        assert response.status_code == 400
        assert response.data["error"]["code"] == "VALIDATION_ERROR"

    def test_mismatched_passwords_rejected(self, api):
        response = api.post(
            REGISTER, _payload(password_confirm="Different!23"), format="json"
        )

        assert response.status_code == 400
        assert "password_confirm" in response.data["error"]["details"]

    def test_weak_password_rejected(self, api):
        response = api.post(
            REGISTER, _payload(password="12345678", password_confirm="12345678"),
            format="json",
        )

        assert response.status_code == 400
        assert "password" in response.data["error"]["details"]

    def test_password_is_hashed_not_stored_plain(self, api):
        api.post(REGISTER, _payload(), format="json")
        user = User.objects.get(email="new@example.com")

        assert user.password != GOOD_PASSWORD
        assert user.check_password(GOOD_PASSWORD)


class TestLogin:
    def test_valid_credentials_return_tokens(self, api, make_user):
        make_user(email="seller@example.com", password=GOOD_PASSWORD)
        response = api.post(
            LOGIN, {"email": "seller@example.com", "password": GOOD_PASSWORD},
            format="json",
        )

        assert response.status_code == 200
        assert "access" in response.data
        assert "refresh" in response.data

    def test_login_includes_store_memberships(
        self, api, make_user, make_store
    ):
        user = make_user(email="seller@example.com", password=GOOD_PASSWORD)
        make_store(user, name="My Shop")

        response = api.post(
            LOGIN, {"email": "seller@example.com", "password": GOOD_PASSWORD},
            format="json",
        )

        assert response.status_code == 200
        assert len(response.data["stores"]) == 1
        store_row = response.data["stores"][0]
        assert store_row["store_name"] == "My Shop"
        assert store_row["role"] == "owner"
        # Capabilities travel with the membership so the UI can gate itself.
        assert "manage_staff" in store_row["capabilities"]

    def test_wrong_password_rejected(self, api, make_user):
        make_user(email="seller@example.com", password=GOOD_PASSWORD)
        response = api.post(
            LOGIN, {"email": "seller@example.com", "password": "WrongPass!23"},
            format="json",
        )

        assert response.status_code == 401

    def test_unknown_email_rejected(self, api):
        response = api.post(
            LOGIN, {"email": "ghost@example.com", "password": GOOD_PASSWORD},
            format="json",
        )

        assert response.status_code == 401

    def test_inactive_account_cannot_log_in(self, api, make_user):
        user = make_user(email="seller@example.com", password=GOOD_PASSWORD)
        user.is_active = False
        user.save(update_fields=["is_active"])

        response = api.post(
            LOGIN, {"email": "seller@example.com", "password": GOOD_PASSWORD},
            format="json",
        )

        assert response.status_code == 401


class TestTokenLifecycle:
    def test_refresh_returns_new_access_token(self, api, make_user):
        make_user(email="seller@example.com", password=GOOD_PASSWORD)
        login = api.post(
            LOGIN, {"email": "seller@example.com", "password": GOOD_PASSWORD},
            format="json",
        )
        response = api.post(
            REFRESH, {"refresh": login.data["refresh"]}, format="json"
        )

        assert response.status_code == 200
        assert "access" in response.data

    def test_logout_blacklists_refresh_token(self, api, make_user, auth):
        user = make_user(email="seller@example.com", password=GOOD_PASSWORD)
        login = api.post(
            LOGIN, {"email": "seller@example.com", "password": GOOD_PASSWORD},
            format="json",
        )
        refresh = login.data["refresh"]

        client = auth(user)
        assert client.post(LOGOUT, {"refresh": refresh}, format="json").status_code == 205

        # The blacklisted token must no longer be exchangeable.
        api.credentials()
        assert api.post(REFRESH, {"refresh": refresh}, format="json").status_code == 401

    def test_logout_requires_a_refresh_token(self, make_user, auth):
        user = make_user()
        response = auth(user).post(LOGOUT, {}, format="json")

        assert response.status_code == 400


class TestMeEndpoint:
    def test_requires_authentication(self, api):
        assert api.get(ME).status_code == 401

    def test_returns_user_and_stores(self, make_user, make_store, auth):
        user = make_user(email="seller@example.com")
        make_store(user, name="My Shop")

        response = auth(user).get(ME)

        assert response.status_code == 200
        assert response.data["user"]["email"] == "seller@example.com"
        assert len(response.data["stores"]) == 1

    def test_never_exposes_password(self, make_user, auth):
        user = make_user()
        response = auth(user).get(ME)

        assert "password" not in response.data["user"]
