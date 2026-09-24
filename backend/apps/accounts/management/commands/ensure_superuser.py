import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Create the platform superuser from the DJANGO_SUPERUSER_* "
        "environment variables when it does not exist yet."
    )

    def handle(self, *args, **options):
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "").strip().lower()
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")
        full_name = os.environ.get(
            "DJANGO_SUPERUSER_FULL_NAME", ""
        ).strip() or "Platform Admin"

        if not email or not password:
            self.stdout.write("No superuser variables set, skipping.")
            return

        User = get_user_model()
        if User.objects.filter(email__iexact=email).exists():
            self.stdout.write(f"Superuser {email} already exists, skipping.")
            return

        User.objects.create_superuser(
            email=email, password=password, full_name=full_name
        )
        self.stdout.write(self.style.SUCCESS(f"Created superuser {email}."))
