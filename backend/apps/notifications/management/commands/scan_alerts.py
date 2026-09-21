from django.core.management.base import BaseCommand

from apps.notifications.services import run_all_scans


class Command(BaseCommand):
    help = (
        "Raise low-stock and overdue-COD notifications for every active "
        "store. Intended to run as a Render Cron Job."
    )

    def handle(self, *args, **options):
        summary = run_all_scans()
        self.stdout.write(
            self.style.SUCCESS(
                f"Scanned {summary['stores']} store(s): "
                f"{summary['low_stock']} low-stock, "
                f"{summary['cod_overdue']} overdue-COD alert(s)."
            )
        )
