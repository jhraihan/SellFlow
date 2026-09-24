import hmac

from django.conf import settings
from django.db import connection
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.response import Response


@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
def health_check(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False

    payload = {"status": "ok" if db_ok else "degraded", "database": db_ok}
    code = status.HTTP_200_OK if db_ok else status.HTTP_503_SERVICE_UNAVAILABLE
    return Response(payload, status=code)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([])
@throttle_classes([])
def run_scheduled_jobs(request):
    expected = getattr(settings, "CRON_SECRET", "")
    provided = request.headers.get("X-Cron-Secret", "")
    if not expected or not hmac.compare_digest(expected, provided):
        return Response(status=status.HTTP_404_NOT_FOUND)

    from apps.notifications.services import run_all_scans
    from apps.shipments.services import sync_due_shipments

    try:
        limit = int(request.query_params.get("limit", 25))
    except ValueError:
        limit = 25
    limit = max(1, min(limit, 100))

    synced = sync_due_shipments(limit=limit)
    alerts = run_all_scans()
    return Response({"shipments_synced": synced, "alerts": alerts})
