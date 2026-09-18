"""Authentication endpoints (PRD §10.2 'Authentication')."""
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import User
from .serializers import (
    ChangePasswordSerializer,
    LoginSerializer,
    RegisterSerializer,
    UserSerializer,
)


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


@extend_schema(tags=["auth"])
class RegisterView(generics.CreateAPIView):
    """POST /api/v1/auth/register/ — create an account."""

    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Issue tokens immediately so the client can continue into the
        # store-creation wizard without a second login round trip.
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "user": UserSerializer(user).data,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "stores": [],
            },
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["auth"])
class LoginView(TokenObtainPairView):
    """POST /api/v1/auth/login/ — obtain access + refresh tokens."""

    serializer_class = LoginSerializer
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            email = request.data.get("email", "").lower().strip()
            User.objects.filter(email=email).update(
                last_login_ip=_client_ip(request), last_login=timezone.now()
            )
        return response


@extend_schema(tags=["auth"])
class LogoutView(APIView):
    """
    POST /api/v1/auth/logout/ — blacklist the refresh token.

    The access token stays valid until it expires (15 min); blacklisting
    the refresh token is what stops the session being renewed.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        token = request.data.get("refresh")
        if not token:
            return Response(
                {"error": {
                    "code": "VALIDATION_ERROR",
                    "message": "A refresh token is required.",
                    "details": {"refresh": ["This field is required."]},
                }},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            RefreshToken(token).blacklist()
        except TokenError:
            # Already blacklisted or malformed — the desired end state
            # (this token is unusable) holds either way.
            pass
        return Response(status=status.HTTP_205_RESET_CONTENT)


@extend_schema(tags=["auth"])
class MeView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/v1/auth/me/ — current user and their memberships."""

    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

    def retrieve(self, request, *args, **kwargs):
        from apps.stores.serializers import MembershipBriefSerializer

        memberships = (
            request.user.store_memberships
            .select_related("store")
            .filter(is_active=True, store__deleted_at__isnull=True)
        )
        return Response({
            "user": UserSerializer(request.user).data,
            "stores": MembershipBriefSerializer(memberships, many=True).data,
        })


@extend_schema(tags=["auth"])
class ChangePasswordView(APIView):
    """POST /api/v1/auth/password/change/"""

    permission_classes = [IsAuthenticated]
    throttle_scope = "auth"

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Password updated."}, status=status.HTTP_200_OK)
