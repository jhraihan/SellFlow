import re

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel

BD_PHONE_RE = re.compile(r"^(?:\+?880|0)?1[3-9]\d{8}$")


def normalise_bd_phone(raw):
    if not raw:
        return ""
    digits = re.sub(r"[\s\-()]", "", str(raw))
    if not BD_PHONE_RE.match(digits):
        raise ValidationError(
            "Enter a valid Bangladeshi mobile number, e.g. 01712345678."
        )
    digits = digits.lstrip("+")
    if digits.startswith("880"):
        digits = digits[3:]
    digits = digits.lstrip("0")
    return f"+880{digits}"


def validate_bd_phone(value):
    normalise_bd_phone(value)


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("Users must have an email address.")
        email = self.normalize_email(email).lower()
        if extra.get("phone"):
            extra["phone"] = normalise_bd_phone(extra["phone"])
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("is_active", True)
        extra.setdefault("email_verified_at", timezone.now())
        if extra.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel):

    email = models.EmailField(unique=True, db_index=True)
    full_name = models.CharField(max_length=150)
    phone = models.CharField(
        max_length=20,
        blank=True,
        validators=[validate_bd_phone],
        help_text="Bangladeshi mobile, stored as +8801XXXXXXXXX.",
    )

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    email_verified_at = models.DateTimeField(null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        db_table = "accounts_user"
        ordering = ["-created_at"]

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        self.email = self.email.lower().strip()
        if self.phone:
            self.phone = normalise_bd_phone(self.phone)
        super().save(*args, **kwargs)

    @property
    def is_email_verified(self):
        return self.email_verified_at is not None

    def get_short_name(self):
        return self.full_name.split(" ")[0] if self.full_name else self.email

    def get_full_name(self):
        return self.full_name or self.email
