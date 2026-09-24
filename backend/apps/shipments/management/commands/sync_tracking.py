from django.core.management.base import BaseCommand

from apps.shipments.services import sync_due_shipments


class Command(BaseCommand):
    help = (
        "Poll couriers for tracking updates on in-transit shipments. "
        "The scheduled jobs endpoint runs the same sync."
    )

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=200)

    def handle(self, *args, **options):
        synced = sync_due_shipments(limit=options["limit"])
        self.stdout.write(
            self.style.SUCCESS(f"Synced {synced} shipment(s).")
        )
