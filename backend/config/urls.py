from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)

from apps.core.views import health_check
from apps.shipments.views import CourierWebhookView

API = "api/v1/"

urlpatterns = [
    path("admin/", admin.site.urls),

    path("healthz/", health_check, name="health-check"),

    path(f"{API}auth/", include("apps.accounts.urls")),
    path(f"{API}stores/", include("apps.stores.urls")),
    path(f"{API}", include("apps.catalog.urls")),
    path(f"{API}customers/", include("apps.customers.urls")),
    path(f"{API}orders/", include("apps.orders.urls")),
    path(f"{API}couriers/", include("apps.couriers.urls")),
    path(f"{API}shipments/", include("apps.shipments.urls")),
    path(
        f"{API}webhooks/courier/<slug:courier_code>/",
        CourierWebhookView.as_view(),
        name="courier-webhook",
    ),

    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
