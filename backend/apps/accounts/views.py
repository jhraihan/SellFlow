from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import User
from .serializers import (
    ChangePasswordSerializer,
    EmailVerificationSerializer,
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    UserSerializer,
)
from .tokens import (
    consume_reset_token,
    consume_verification_token,
    frontend_link,
    issue_reset_token,
    issue_verification_token,
)


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


@extend_schema(tags=["auth"])
class RegisterView(generics.CreateAPIView):

    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

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
            pass
        return Response(status=status.HTTP_205_RESET_CONTENT)


@extend_schema(tags=["auth"])
class MeView(generics.RetrieveUpdateAPIView):

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

    permission_classes = [IsAuthenticated]
    throttle_scope = "auth"

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Password updated."}, status=status.HTTP_200_OK)


@extend_schema(tags=["auth"])
class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]

        user = User.objects.filter(email=email, is_active=True).first()
        if user is not None:
            token = issue_reset_token(user)
            link = frontend_link("reset-password", token)
            send_mail(
                subject="Reset your ShopFlow BD password",
                message=(
                    f"Hello {user.get_short_name()},\n\n"
                    f"Use this link to set a new password:\n{link}\n\n"
                    "The link expires in one hour. If you did not ask for a "
                    "reset, you can ignore this email."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True,
            )

        return Response(
            {
                "detail": (
                    "If an account exists for that email, a reset link has "
                    "been sent."
                )
            },
            status=status.HTTP_200_OK,
        )


@extend_schema(tags=["auth"])
class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_id = consume_reset_token(serializer.validated_data["token"])
        if user_id is None:
            return Response(
                {"error": {
                    "code": "INVALID_RESET_TOKEN",
                    "message": "That reset link is invalid or has expired.",
                    "details": {},
                }},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User.objects.filter(pk=user_id, is_active=True).first()
        if user is None:
            return Response(
                {"error": {
                    "code": "INVALID_RESET_TOKEN",
                    "message": "That reset link is no longer valid.",
                    "details": {},
                }},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password", "updated_at"])

        for token in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=token)

        return Response({"detail": "Your password has been reset."})


@extend_schema(tags=["auth"])
class SendVerificationEmailView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "auth"

    def post(self, request):
        user = request.user
        if user.is_email_verified:
            return Response({"detail": "This email is already verified."})

        token = issue_verification_token(user)
        link = frontend_link("verify-email", token)
        send_mail(
            subject="Verify your ShopFlow BD email",
            message=(
                f"Hello {user.get_short_name()},\n\n"
                f"Confirm your email address:\n{link}\n\n"
                "The link expires in three days."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        )
        return Response({"detail": "Verification email sent."})


@extend_schema(tags=["auth"])
class VerifyEmailView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        serializer = EmailVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_id = consume_verification_token(
            serializer.validated_data["token"]
        )
        if user_id is None:
            return Response(
                {"error": {
                    "code": "INVALID_VERIFICATION_TOKEN",
                    "message": "That link is invalid or has expired.",
                    "details": {},
                }},
                status=status.HTTP_400_BAD_REQUEST,
            )

        User.objects.filter(pk=user_id, email_verified_at__isnull=True).update(
            email_verified_at=timezone.now()
        )
        return Response({"detail": "Your email has been verified."})
