from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.stores.models import (
    Store,
    StoreInvitation,
    StoreMembership,
    StoreRole,
    StoreSettings,
)

pytestmark = pytest.mark.django_db

STORES = "/api/v1/stores/"
INVITATIONS = "/api/v1/stores/invitations/"
ACCEPT = "/api/v1/stores/invitations/accept/"


class TestStoreCreation:
    def test_creates_store_membership_and_settings(self, make_user, auth):
        user = make_user()
        response = auth(user).post(
            STORES,
            {"name": "Rumana Fashion", "district": "Dhaka",
             "business_type": "fashion"},
            format="json",
        )

        assert response.status_code == 201
        store = Store.objects.get(id=response.data["id"])
        assert store.owner == user
        assert StoreMembership.objects.filter(
            store=store, user=user, role=StoreRole.OWNER
        ).exists()
        assert StoreSettings.objects.filter(store=store).exists()

    def test_slug_is_generated(self, make_user, auth):
        user = make_user()
        response = auth(user).post(
            STORES, {"name": "Rumana Fashion"}, format="json"
        )
        assert response.data["slug"] == "rumana-fashion"

    def test_duplicate_names_get_distinct_slugs(self, make_user, auth):
        first = make_user(email="a@example.com")
        second = make_user(email="b@example.com")

        auth(first).post(STORES, {"name": "Trendy"}, format="json")
        response = auth(second).post(STORES, {"name": "Trendy"}, format="json")

        assert response.data["slug"] == "trendy-2"

    def test_order_prefix_is_uppercased(self, make_user, auth):
        user = make_user()
        response = auth(user).post(
            STORES, {"name": "Shop", "order_prefix": "rb"}, format="json"
        )
        assert response.data["order_prefix"] == "RB"

    def test_invalid_order_prefix_rejected(self, make_user, auth):
        user = make_user()
        response = auth(user).post(
            STORES, {"name": "Shop", "order_prefix": "R-B!"}, format="json"
        )
        assert response.status_code == 400

    def test_short_name_rejected(self, make_user, auth):
        user = make_user()
        response = auth(user).post(STORES, {"name": "X"}, format="json")
        assert response.status_code == 400

    def test_requires_authentication(self, api):
        assert api.post(STORES, {"name": "Shop"}, format="json").status_code == 401


class TestStoreSettings:
    def test_defaults_match_bd_market(self, make_user, make_store):
        store = make_store(make_user())
        settings = store.settings

        assert settings.delivery_charge_inside_dhaka == Decimal("60.00")
        assert settings.delivery_charge_outside_dhaka == Decimal("120.00")
        assert settings.cod_overdue_days == 7

    def test_owner_can_update_settings(self, make_user, make_store, auth):
        owner = make_user()
        store = make_store(owner)

        response = auth(owner, store=store).patch(
            f"{STORES}{store.id}/settings/",
            {"delivery_charge_inside_dhaka": "80.00"},
            format="json",
        )

        assert response.status_code == 200
        store.settings.refresh_from_db()
        assert store.settings.delivery_charge_inside_dhaka == Decimal("80.00")

    def test_order_staff_cannot_update_settings(
        self, make_user, make_store, make_member, auth
    ):
        owner = make_user(email="owner@example.com")
        store = make_store(owner)
        staff = make_user(email="staff@example.com")
        make_member(store, staff, StoreRole.ORDER_STAFF)

        response = auth(staff, store=store).patch(
            f"{STORES}{store.id}/settings/",
            {"delivery_charge_inside_dhaka": "1.00"},
            format="json",
        )

        assert response.status_code == 403

    def test_negative_district_override_rejected(self, make_user, make_store, auth):
        owner = make_user()
        store = make_store(owner)

        response = auth(owner, store=store).patch(
            f"{STORES}{store.id}/settings/",
            {"district_charge_overrides": {"Khulna": "-10"}},
            format="json",
        )

        assert response.status_code == 400

    def test_non_numeric_district_override_rejected(self, make_user, make_store, auth):
        owner = make_user()
        store = make_store(owner)

        response = auth(owner, store=store).patch(
            f"{STORES}{store.id}/settings/",
            {"district_charge_overrides": {"Khulna": "free"}},
            format="json",
        )

        assert response.status_code == 400


class TestDeliveryChargeResolution:

    def test_dhaka_uses_inside_rate(self, make_user, make_store):
        store = make_store(make_user())
        assert store.settings.delivery_charge_for("Dhaka") == Decimal("60.00")

    def test_dhaka_is_case_insensitive(self, make_user, make_store):
        store = make_store(make_user())
        assert store.settings.delivery_charge_for("dhaka") == Decimal("60.00")

    def test_other_district_uses_outside_rate(self, make_user, make_store):
        store = make_store(make_user())
        assert store.settings.delivery_charge_for("Sylhet") == Decimal("120.00")

    def test_explicit_override_wins(self, make_user, make_store):
        store = make_store(make_user())
        store.settings.district_charge_overrides = {"Chattogram": "100.00"}
        store.settings.save()

        assert store.settings.delivery_charge_for("Chattogram") == Decimal("100.00")

    def test_override_beats_the_dhaka_rule(self, make_user, make_store):
        store = make_store(make_user())
        store.settings.district_charge_overrides = {"Dhaka": "50.00"}
        store.settings.save()

        assert store.settings.delivery_charge_for("Dhaka") == Decimal("50.00")

    def test_blank_district_falls_back_to_outside(self, make_user, make_store):
        store = make_store(make_user())
        assert store.settings.delivery_charge_for("") == Decimal("120.00")


class TestInvitations:
    def test_owner_can_invite_staff(self, make_user, make_store, auth):
        owner = make_user(email="owner@example.com")
        store = make_store(owner)

        response = auth(owner, store=store).post(
            INVITATIONS,
            {"email": "newstaff@example.com", "role": StoreRole.ORDER_STAFF},
            format="json",
        )

        assert response.status_code == 201
        invitation = StoreInvitation.objects.get(email="newstaff@example.com")
        assert invitation.store == store
        assert invitation.is_usable

    def test_invitation_expires_in_72_hours(self, make_user, make_store, auth):
        owner = make_user(email="owner@example.com")
        store = make_store(owner)

        auth(owner, store=store).post(
            INVITATIONS,
            {"email": "newstaff@example.com", "role": StoreRole.ORDER_STAFF},
            format="json",
        )

        invitation = StoreInvitation.objects.get(email="newstaff@example.com")
        expected = timezone.now() + timedelta(hours=72)
        assert abs((invitation.expires_at - expected).total_seconds()) < 60

    def test_cannot_invite_as_owner(self, make_user, make_store, auth):
        owner = make_user(email="owner@example.com")
        store = make_store(owner)

        response = auth(owner, store=store).post(
            INVITATIONS,
            {"email": "newstaff@example.com", "role": StoreRole.OWNER},
            format="json",
        )

        assert response.status_code == 400

    def test_cannot_invite_existing_member(
        self, make_user, make_store, make_member, auth
    ):
        owner = make_user(email="owner@example.com")
        store = make_store(owner)
        existing = make_user(email="staff@example.com")
        make_member(store, existing, StoreRole.ORDER_STAFF)

        response = auth(owner, store=store).post(
            INVITATIONS,
            {"email": "staff@example.com", "role": StoreRole.MANAGER},
            format="json",
        )

        assert response.status_code == 400

    def test_duplicate_pending_invite_rejected(self, make_user, make_store, auth):
        owner = make_user(email="owner@example.com")
        store = make_store(owner)
        client = auth(owner, store=store)
        body = {"email": "new@example.com", "role": StoreRole.ORDER_STAFF}

        assert client.post(INVITATIONS, body, format="json").status_code == 201
        assert client.post(INVITATIONS, body, format="json").status_code == 400

    def test_manager_cannot_invite(
        self, make_user, make_store, make_member, auth
    ):
        owner = make_user(email="owner@example.com")
        store = make_store(owner)
        manager = make_user(email="manager@example.com")
        make_member(store, manager, StoreRole.MANAGER)

        response = auth(manager, store=store).post(
            INVITATIONS,
            {"email": "new@example.com", "role": StoreRole.ORDER_STAFF},
            format="json",
        )

        assert response.status_code == 403


class TestAcceptInvitation:
    def _invite(self, store, owner, email="new@example.com",
                role=StoreRole.ORDER_STAFF):
        import secrets

        return StoreInvitation.objects.create(
            store=store, email=email, role=role,
            token=secrets.token_urlsafe(32), invited_by=owner,
            expires_at=timezone.now() + timedelta(hours=72),
        )

    def test_new_user_accepts_and_gets_account(self, api, make_user, make_store):
        owner = make_user(email="owner@example.com")
        store = make_store(owner)
        invitation = self._invite(store, owner)

        response = api.post(
            ACCEPT,
            {"token": invitation.token, "full_name": "New Staff",
             "password": "Str0ngPass!23"},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["account_created"] is True
        assert response.data["membership"]["role"] == StoreRole.ORDER_STAFF
        assert "access" in response.data

    def test_existing_user_accepts_without_password(
        self, api, make_user, make_store
    ):
        owner = make_user(email="owner@example.com")
        store = make_store(owner)
        existing = make_user(email="known@example.com", full_name="Known")
        invitation = self._invite(store, owner, email="known@example.com")

        response = api.post(ACCEPT, {"token": invitation.token}, format="json")

        assert response.status_code == 200
        assert response.data["account_created"] is False
        assert StoreMembership.objects.filter(
            store=store, user=existing, is_active=True
        ).exists()

    def test_new_user_must_supply_name_and_password(
        self, api, make_user, make_store
    ):
        owner = make_user(email="owner@example.com")
        store = make_store(owner)
        invitation = self._invite(store, owner)

        response = api.post(ACCEPT, {"token": invitation.token}, format="json")

        assert response.status_code == 400
        details = response.data["error"]["details"]
        assert "full_name" in details and "password" in details

    def test_token_cannot_be_reused(self, api, make_user, make_store):
        owner = make_user(email="owner@example.com")
        store = make_store(owner)
        invitation = self._invite(store, owner)
        body = {"token": invitation.token, "full_name": "New Staff",
                "password": "Str0ngPass!23"}

        assert api.post(ACCEPT, body, format="json").status_code == 200
        assert api.post(ACCEPT, body, format="json").status_code == 400

    def test_expired_token_rejected(self, api, make_user, make_store):
        owner = make_user(email="owner@example.com")
        store = make_store(owner)
        invitation = self._invite(store, owner)
        invitation.expires_at = timezone.now() - timedelta(minutes=1)
        invitation.save()

        response = api.post(
            ACCEPT,
            {"token": invitation.token, "full_name": "X",
             "password": "Str0ngPass!23"},
            format="json",
        )

        assert response.status_code == 400

    def test_unknown_token_rejected(self, api):
        response = api.post(ACCEPT, {"token": "not-a-real-token"}, format="json")
        assert response.status_code == 400


class TestStaffManagement:
    def test_owner_can_change_a_members_role(
        self, make_user, make_store, make_member, auth
    ):
        owner = make_user(email="owner@example.com")
        store = make_store(owner)
        staff = make_user(email="staff@example.com")
        membership = make_member(store, staff, StoreRole.ORDER_STAFF)

        response = auth(owner, store=store).patch(
            f"/api/v1/stores/staff/{membership.id}/",
            {"role": StoreRole.MANAGER},
            format="json",
        )

        assert response.status_code == 200
        membership.refresh_from_db()
        assert membership.role == StoreRole.MANAGER

    def test_owner_role_cannot_be_reassigned(self, make_user, make_store, auth):
        owner = make_user(email="owner@example.com")
        store = make_store(owner)
        membership = StoreMembership.objects.get(store=store, user=owner)

        response = auth(owner, store=store).patch(
            f"/api/v1/stores/staff/{membership.id}/",
            {"role": StoreRole.MANAGER},
            format="json",
        )

        assert response.status_code == 409
        assert response.data["error"]["code"] == "OWNER_ROLE_IMMUTABLE"

    def test_owner_cannot_be_removed(self, make_user, make_store, auth):
        owner = make_user(email="owner@example.com")
        store = make_store(owner)
        membership = StoreMembership.objects.get(store=store, user=owner)

        response = auth(owner, store=store).delete(
            f"/api/v1/stores/staff/{membership.id}/"
        )

        assert response.status_code == 409

    def test_removing_staff_deactivates_membership(
        self, make_user, make_store, make_member, auth
    ):
        owner = make_user(email="owner@example.com")
        store = make_store(owner)
        staff = make_user(email="staff@example.com")
        membership = make_member(store, staff, StoreRole.ORDER_STAFF)

        response = auth(owner, store=store).delete(
            f"/api/v1/stores/staff/{membership.id}/"
        )

        assert response.status_code == 204
        membership.refresh_from_db()
        assert membership.is_active is False
        assert StoreMembership.objects.filter(id=membership.id).exists()


class TestSoftDelete:
    def test_deleting_a_store_is_soft(self, make_user, make_store, auth):
        owner = make_user()
        store = make_store(owner)

        response = auth(owner, store=store).delete(f"{STORES}{store.id}/")

        assert response.status_code == 204
        reloaded = Store.all_objects.get(id=store.id)
        assert reloaded.deleted_at is not None

    def test_soft_deleted_store_is_hidden_from_default_manager(
        self, make_user, make_store
    ):
        store = make_store(make_user())
        store.delete()

        assert not Store.objects.filter(id=store.id).exists()
        assert Store.all_objects.filter(id=store.id).exists()

    def test_restore_brings_it_back(self, make_user, make_store):
        store = make_store(make_user())
        store.delete()
        store.restore()

        assert Store.objects.filter(id=store.id).exists()
