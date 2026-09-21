from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    ChangePasswordView,
    LoginView,
    LogoutView,
    MeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RegisterView,
    SendVerificationEmailView,
    VerifyEmailView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("refresh/", TokenRefreshView.as_view(), name="auth-refresh"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("password/change/", ChangePasswordView.as_view(), name="auth-password-change"),
    path(
        "password/reset/",
        PasswordResetRequestView.as_view(),
        name="auth-password-reset",
    ),
    path(
        "password/reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="auth-password-reset-confirm",
    ),
    path(
        "email/verify/send/",
        SendVerificationEmailView.as_view(),
        name="auth-email-verify-send",
    ),
    path(
        "email/verify/",
        VerifyEmailView.as_view(),
        name="auth-email-verify",
    ),
]
