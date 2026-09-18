import pytest

from apps.stores.models import StoreMembership, StoreRole

pytestmark = pytest.mark.django_db


class TestStoreListScoping:
    def test_user_sees_only_their_own_stores(self, two_stores, auth):
        client = auth(two_stores["alice"])
        response = client.get("/api/v1/stores/")

        assert response.status_code == 200
        names = {row["name"] for row in response.data["results"]}
        assert names == {"Alice Fashion"}
        assert "Bob Electronics" not in names

    def test_user_with_no_store_sees_empty_list(self, make_user, auth):
        loner = make_user(email="nobody@example.com")
        response = auth(loner).get("/api/v1/stores/")

        assert response.status_code == 200
        assert response.data["results"] == []

    def test_cannot_retrieve_another_users_store_by_id(self, two_stores, auth):
        client = auth(two_stores["alice"])
        response = client.get(f"/api/v1/stores/{two_stores['store_b'].id}/")

        assert response.status_code == 404

    def test_cannot_update_another_users_store(self, two_stores, auth):
        client = auth(two_stores["alice"])
        response = client.patch(
            f"/api/v1/stores/{two_stores['store_b'].id}/",
            {"name": "Hijacked"},
            format="json",
        )

        assert response.status_code == 404
        two_stores["store_b"].refresh_from_db()
        assert two_stores["store_b"].name == "Bob Electronics"

    def test_cannot_delete_another_users_store(self, two_stores, auth):
        client = auth(two_stores["alice"])
        response = client.delete(f"/api/v1/stores/{two_stores['store_b'].id}/")

        assert response.status_code == 404
        two_stores["store_b"].refresh_from_db()
        assert two_stores["store_b"].deleted_at is None


class TestStoreHeaderResolution:
    def test_forged_store_header_is_rejected(self, two_stores, auth):
        client = auth(two_stores["alice"], store=two_stores["store_b"])
        response = client.get("/api/v1/stores/my-capabilities/")

        assert response.status_code == 403
        assert response.data["error"]["code"] == "STORE_ACCESS_DENIED"

    def test_nonexistent_store_header_is_rejected(self, two_stores, auth):
        client = auth(two_stores["alice"])
        client.credentials(
            HTTP_AUTHORIZATION=client._credentials["HTTP_AUTHORIZATION"],
            HTTP_X_STORE_ID="999999",
        )
        response = client.get("/api/v1/stores/my-capabilities/")

        assert response.status_code == 403

    def test_malformed_store_header_is_rejected(self, two_stores, auth):
        client = auth(two_stores["alice"])
        client.credentials(
            HTTP_AUTHORIZATION=client._credentials["HTTP_AUTHORIZATION"],
            HTTP_X_STORE_ID="not-a-number",
        )
        response = client.get("/api/v1/stores/my-capabilities/")

        assert response.status_code == 403

    def test_single_membership_resolves_without_header(self, two_stores, auth):
        client = auth(two_stores["alice"])
        response = client.get("/api/v1/stores/my-capabilities/")

        assert response.status_code == 200
        assert response.data["store_id"] == two_stores["store_a"].id
        assert response.data["role"] == StoreRole.OWNER

    def test_multiple_memberships_require_explicit_header(
        self, two_stores, make_member, auth
    ):
        make_member(
            two_stores["store_b"], two_stores["alice"], StoreRole.ORDER_STAFF
        )
        client = auth(two_stores["alice"])
        response = client.get("/api/v1/stores/my-capabilities/")

        assert response.status_code == 403
        assert "X-Store-Id" in str(response.data["error"])

    def test_header_disambiguates_multiple_memberships(
        self, two_stores, make_member, auth
    ):
        make_member(
            two_stores["store_b"], two_stores["alice"], StoreRole.ORDER_STAFF
        )
        client = auth(two_stores["alice"], store=two_stores["store_b"])
        response = client.get("/api/v1/stores/my-capabilities/")

        assert response.status_code == 200
        assert response.data["store_id"] == two_stores["store_b"].id
        assert response.data["role"] == StoreRole.ORDER_STAFF

    def test_deactivated_membership_loses_access(self, two_stores, auth):
        StoreMembership.objects.filter(
            store=two_stores["store_a"], user=two_stores["alice"]
        ).update(is_active=False)

        client = auth(two_stores["alice"], store=two_stores["store_a"])
        response = client.get("/api/v1/stores/my-capabilities/")

        assert response.status_code == 403

    def test_soft_deleted_store_is_not_resolvable(self, two_stores, auth):
        two_stores["store_a"].delete()

        client = auth(two_stores["alice"], store=two_stores["store_a"])
        response = client.get("/api/v1/stores/my-capabilities/")

        assert response.status_code == 403


class TestStaffScoping:
    def test_staff_list_shows_only_own_store_members(
        self, two_stores, make_user, make_member, auth
    ):
        outsider = make_user(email="carol@example.com", full_name="Carol")
        make_member(two_stores["store_b"], outsider, StoreRole.ORDER_STAFF)

        client = auth(two_stores["alice"], store=two_stores["store_a"])
        response = client.get("/api/v1/stores/staff/")

        assert response.status_code == 200
        emails = {row["email"] for row in response.data["results"]}
        assert emails == {"alice@example.com"}
        assert "carol@example.com" not in emails

    def test_cannot_modify_membership_in_another_store(
        self, two_stores, make_user, make_member, auth
    ):
        outsider = make_user(email="carol@example.com")
        foreign = make_member(
            two_stores["store_b"], outsider, StoreRole.ORDER_STAFF
        )

        client = auth(two_stores["alice"], store=two_stores["store_a"])
        response = client.patch(
            f"/api/v1/stores/staff/{foreign.id}/",
            {"role": StoreRole.MANAGER},
            format="json",
        )

        assert response.status_code == 404
        foreign.refresh_from_db()
        assert foreign.role == StoreRole.ORDER_STAFF


class TestQuerysetLevelScoping:

    def test_memberships_are_partitioned_by_store(self, two_stores):
        a_members = StoreMembership.objects.filter(store=two_stores["store_a"])
        b_members = StoreMembership.objects.filter(store=two_stores["store_b"])

        assert a_members.count() == 1
        assert b_members.count() == 1
        assert a_members.first().user == two_stores["alice"]
        assert b_members.first().user == two_stores["bob"]

    def test_scoped_mixin_fails_closed_without_a_store(self, rf, two_stores):
        from apps.core.mixins import StoreScopedMixin

        class UnscopedParent:

            def get_queryset(self):
                return StoreMembership.objects.all()

        view_cls = type("ScopedView", (StoreScopedMixin, UnscopedParent), {})
        view = view_cls()
        view.request = rf.get("/")

        view.request.store = None
        assert view.get_queryset().count() == 0

        view.request.store = two_stores["store_a"]
        rows = view.get_queryset()
        assert rows.count() == 1
        assert rows.first().store_id == two_stores["store_a"].id
