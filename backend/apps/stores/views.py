import secrets
from datetime import timedelta

from django.conf import settings as django_settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.core.exceptions import APIError, StoreAccessDenied
from apps.core.mixins import StoreContextMixin

from .models import Store, StoreInvitation, StoreMembership, StoreRole, StoreSettings
from .permissions import Cap, HasStoreCapability, IsStoreMember, IsStoreOwner
from .serializers import (
    AcceptInvitationSerializer,
    InvitationCreateSerializer,
    InvitationSerializer,
    StaffSerializer,
    StoreCreateSerializer,
    StoreSerializer,
    StoreSettingsSerializer,
)

INVITE_TTL_HOURS = 72


@extend_schema(tags=["stores"])
class StoreViewSet(viewsets.ModelViewSet):

    serializer_class = StoreSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "pk"

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Store.objects.none()
        return (
            Store.objects
            .filter(memberships__user=user, memberships__is_active=True)
            .select_related("settings")
            .distinct()
        )

    def get_serializer_class(self):
        if self.action == "create":
            return StoreCreateSerializer
        return StoreSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        store = serializer.save()
        return Response(
            StoreSerializer(store, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    def _require_role(self, store, *roles):
        membership = store.memberships.filter(
            user=self.request.user, is_active=True
        ).first()
        if membership is None or membership.role not in roles:
            raise StoreAccessDenied()
        return membership

    def update(self, request, *args, **kwargs):
        store = self.get_object()
        self._require_role(store, StoreRole.OWNER, StoreRole.MANAGER)
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        store = self.get_object()
        self._require_role(store, StoreRole.OWNER)
        store.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get", "patch"], url_path="settings")
    def store_settings(self, request, pk=None):
        store = self.get_object()
        settings_obj, _ = StoreSettings.objects.get_or_create(store=store)

        if request.method == "GET":
            return Response(StoreSettingsSerializer(settings_obj).data)

        self._require_role(store, StoreRole.OWNER, StoreRole.MANAGER)
        serializer = StoreSettingsSerializer(
            settings_obj, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


@extend_schema(tags=["staff"])
class StaffViewSet(StoreContextMixin, viewsets.ModelViewSet):

    serializer_class = StaffSerializer
    permission_classes = [IsAuthenticated, IsStoreMember, HasStoreCapability]
    required_capability = Cap.MANAGE_STAFF
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self):
        store = getattr(self.request, "store", None)
        if store is None:
            return StoreMembership.objects.none()
        return (
            StoreMembership.objects
            .filter(store=store)
            .select_related("user")
            .order_by("role", "created_at")
        )

    def perform_update(self, serializer):
        membership = self.get_object()
        if membership.role == StoreRole.OWNER:
            raise APIError(
                "The owner's role cannot be changed here.",
                code="OWNER_ROLE_IMMUTABLE",
                status_code=status.HTTP_409_CONFLICT,
            )
        serializer.save()

    def perform_destroy(self, instance):
        if instance.role == StoreRole.OWNER:
            raise APIError(
                "The store owner cannot be removed.",
                code="CANNOT_REMOVE_OWNER",
                status_code=status.HTTP_409_CONFLICT,
            )
        if instance.user_id == self.request.user.id:
            raise APIError(
                "You cannot remove your own access.",
                code="CANNOT_REMOVE_SELF",
                status_code=status.HTTP_409_CONFLICT,
            )
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])


@extend_schema(tags=["staff"])
class InvitationViewSet(StoreContextMixin, viewsets.ModelViewSet):

    serializer_class = InvitationSerializer
    permission_classes = [IsAuthenticated, IsStoreMember, IsStoreOwner]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        store = getattr(self.request, "store", None)
        if store is None:
            return StoreInvitation.objects.none()
        return (
            StoreInvitation.objects
            .filter(store=store)
            .select_related("invited_by")
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["store"] = getattr(self.request, "store", None)
        return context

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        store = request.store
        serializer = InvitationCreateSerializer(
            data=request.data, context={"store": store, "request": request}
        )
        serializer.is_valid(raise_exception=True)

        invitation = StoreInvitation.objects.create(
            store=store,
            email=serializer.validated_data["email"],
            role=serializer.validated_data["role"],
            token=secrets.token_urlsafe(32),
            invited_by=request.user,
            expires_at=timezone.now() + timedelta(hours=INVITE_TTL_HOURS),
        )
        self._send_invite_email(invitation)

        return Response(
            InvitationSerializer(invitation).data,
            status=status.HTTP_201_CREATED,
        )

    def perform_destroy(self, instance):
        if instance.is_accepted:
            raise APIError(
                "This invitation has already been accepted.",
                code="INVITATION_ALREADY_ACCEPTED",
                status_code=status.HTTP_409_CONFLICT,
            )
        instance.expires_at = timezone.now()
        instance.save(update_fields=["expires_at", "updated_at"])

    @staticmethod
    def _send_invite_email(invitation):
        base = getattr(django_settings, "FRONTEND_URL", "").rstrip("/")
        link = f"{base}/invite/{invitation.token}"
        send_mail(
            subject=f"You've been invited to {invitation.store.name} on SellFlow BD",
            message=(
                f"{invitation.invited_by.get_full_name()} invited you to join "
                f"{invitation.store.name} as {invitation.get_role_display()}.\n\n"
                f"Accept the invitation: {link}\n\n"
                f"This link expires in {INVITE_TTL_HOURS} hours."
            ),
            from_email=django_settings.DEFAULT_FROM_EMAIL,
            recipient_list=[invitation.email],
            fail_silently=True,
        )


@extend_schema(tags=["staff"])
class AcceptInvitationView(APIView):

    permission_classes = [AllowAny]
    throttle_scope = "auth"

    @transaction.atomic
    def post(self, request):
        serializer = AcceptInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        invitation = serializer.context["invitation"]
        user = serializer.context.get("existing_user")
        created = False

        if user is None:
            user = User.objects.create_user(
                email=invitation.email,
                password=serializer.validated_data["password"],
                full_name=serializer.validated_data["full_name"],
                email_verified_at=timezone.now(),
            )
            created = True

        membership, _ = StoreMembership.objects.update_or_create(
            store=invitation.store,
            user=user,
            defaults={
                "role": invitation.role,
                "is_active": True,
                "invited_by": invitation.invited_by,
                "joined_at": timezone.now(),
            },
        )

        invitation.accepted_at = timezone.now()
        invitation.save(update_fields=["accepted_at", "updated_at"])

        from rest_framework_simplejwt.tokens import RefreshToken

        from apps.accounts.serializers import UserSerializer

        from .serializers import MembershipBriefSerializer

        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "user": UserSerializer(user).data,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "membership": MembershipBriefSerializer(membership).data,
                "account_created": created,
            },
            status=status.HTTP_200_OK,
        )


@extend_schema(tags=["stores"])
class MyCapabilitiesView(StoreContextMixin, generics.GenericAPIView):

    permission_classes = [IsAuthenticated, IsStoreMember]

    def get(self, request):
        from .permissions import capabilities_for

        membership = request.membership
        return Response({
            "store_id": membership.store_id,
            "role": membership.role,
            "capabilities": capabilities_for(membership.role),
        })
