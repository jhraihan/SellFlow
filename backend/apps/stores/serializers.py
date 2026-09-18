"""Serializers for stores, memberships, settings and invitations."""
from django.db import transaction
from rest_framework import serializers

from apps.accounts.models import User

from .models import Store, StoreInvitation, StoreMembership, StoreRole, StoreSettings
from .permissions import capabilities_for


class StoreSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreSettings
        exclude = ["id", "store", "created_at", "updated_at"]

    def validate_district_charge_overrides(self, value):
        """Keys are district names, values must parse as money."""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Expected an object of district: charge.")
        from decimal import Decimal, InvalidOperation

        cleaned = {}
        for district, charge in value.items():
            try:
                amount = Decimal(str(charge))
            except (InvalidOperation, TypeError):
                raise serializers.ValidationError(
                    f"'{charge}' is not a valid charge for {district}."
                ) from None
            if amount < 0:
                raise serializers.ValidationError(
                    f"Charge for {district} cannot be negative."
                )
            cleaned[district.strip()] = str(amount.quantize(Decimal("0.01")))
        return cleaned


class StoreSerializer(serializers.ModelSerializer):
    settings = StoreSettingsSerializer(read_only=True)
    my_role = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = Store
        fields = [
            "id", "name", "slug", "logo", "contact_phone", "contact_email",
            "business_type", "address_line", "district",
            "facebook_page_url", "instagram_handle",
            "order_prefix", "is_active", "created_at",
            "settings", "my_role", "member_count",
        ]
        read_only_fields = ["id", "slug", "created_at"]

    def get_my_role(self, obj):
        membership = self.context.get("membership")
        if membership and membership.store_id == obj.id:
            return membership.role
        user = getattr(self.context.get("request"), "user", None)
        if user and user.is_authenticated:
            found = obj.memberships.filter(user=user, is_active=True).first()
            return found.role if found else None
        return None

    def get_member_count(self, obj):
        return obj.memberships.filter(is_active=True).count()


class StoreCreateSerializer(serializers.ModelSerializer):
    """
    Store-creation wizard (PRD FR-1.3).

    Creating a store also creates the owner membership and default
    settings, so a new store is immediately usable.
    """

    class Meta:
        model = Store
        fields = [
            "name", "contact_phone", "contact_email", "business_type",
            "address_line", "district", "facebook_page_url",
            "instagram_handle", "order_prefix",
        ]

    def validate_name(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("Store name is too short.")
        return value

    def validate_order_prefix(self, value):
        value = (value or "ORD").strip().upper()
        if not value.isalnum():
            raise serializers.ValidationError(
                "Order prefix must contain only letters and numbers."
            )
        return value

    @transaction.atomic
    def create(self, validated_data):
        user = self.context["request"].user
        store = Store.objects.create(owner=user, **validated_data)

        StoreMembership.objects.create(
            store=store,
            user=user,
            role=StoreRole.OWNER,
            joined_at=store.created_at,
        )
        StoreSettings.objects.create(store=store)
        return store


class MembershipBriefSerializer(serializers.ModelSerializer):
    """Compact membership shape, embedded in login and /me responses."""

    store_id = serializers.IntegerField(source="store.id", read_only=True)
    store_name = serializers.CharField(source="store.name", read_only=True)
    store_slug = serializers.CharField(source="store.slug", read_only=True)
    store_logo = serializers.ImageField(source="store.logo", read_only=True)
    capabilities = serializers.SerializerMethodField()

    class Meta:
        model = StoreMembership
        fields = [
            "store_id", "store_name", "store_slug", "store_logo",
            "role", "capabilities",
        ]

    def get_capabilities(self, obj):
        return capabilities_for(obj.role)


class StaffSerializer(serializers.ModelSerializer):
    """A staff member as shown on the settings screen."""

    user_id = serializers.IntegerField(source="user.id", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)

    class Meta:
        model = StoreMembership
        fields = [
            "id", "user_id", "email", "full_name", "phone",
            "role", "is_active", "joined_at", "created_at",
        ]
        read_only_fields = ["id", "joined_at", "created_at"]

    def validate_role(self, value):
        """
        The owner role is not assignable through staff management.

        Ownership transfer is a separate, deliberate action.
        """
        if value == StoreRole.OWNER:
            raise serializers.ValidationError(
                "Ownership cannot be assigned here. Use ownership transfer."
            )
        return value


class InvitationSerializer(serializers.ModelSerializer):
    invited_by_name = serializers.CharField(
        source="invited_by.full_name", read_only=True
    )
    is_usable = serializers.BooleanField(read_only=True)

    class Meta:
        model = StoreInvitation
        fields = [
            "id", "email", "role", "expires_at", "accepted_at",
            "invited_by_name", "is_usable", "created_at",
        ]
        read_only_fields = ["id", "expires_at", "accepted_at", "created_at"]


class InvitationCreateSerializer(serializers.Serializer):
    """Invite a new staff member by email (PRD FR-1.5)."""

    email = serializers.EmailField()
    role = serializers.ChoiceField(
        choices=[
            (r.value, r.label) for r in StoreRole if r != StoreRole.OWNER
        ]
    )

    def validate_email(self, value):
        value = value.lower().strip()
        store = self.context["store"]

        already = StoreMembership.objects.filter(
            store=store, user__email=value, is_active=True
        ).exists()
        if already:
            raise serializers.ValidationError(
                "This person is already a member of the store."
            )

        pending = StoreInvitation.objects.filter(
            store=store, email=value, accepted_at__isnull=True
        ).first()
        if pending and pending.is_usable:
            raise serializers.ValidationError(
                "An invitation is already pending for this email."
            )
        return value


class AcceptInvitationSerializer(serializers.Serializer):
    """
    Accept an invitation.

    An existing user just joins; a new one supplies name and password,
    since the invite is also their account creation (PRD FR-1.5).
    """

    token = serializers.CharField()
    full_name = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(
        required=False, write_only=True, min_length=8, trim_whitespace=False
    )

    def validate_token(self, value):
        invitation = StoreInvitation.objects.filter(token=value).first()
        if invitation is None:
            raise serializers.ValidationError("This invitation link is not valid.")
        if invitation.is_accepted:
            raise serializers.ValidationError(
                "This invitation has already been used."
            )
        if invitation.is_expired:
            raise serializers.ValidationError(
                "This invitation has expired. Ask for a new one."
            )
        self.context["invitation"] = invitation
        return value

    def validate(self, attrs):
        invitation = self.context.get("invitation")
        if invitation is None:
            return attrs

        existing = User.objects.filter(email=invitation.email).first()
        self.context["existing_user"] = existing

        if existing is None:
            missing = {}
            if not attrs.get("full_name"):
                missing["full_name"] = "Required to create your account."
            if not attrs.get("password"):
                missing["password"] = "Required to create your account."
            if missing:
                raise serializers.ValidationError(missing)
        return attrs
