"""Root URL configuration."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)

from apps.core.views import health_check

API = "api/v1/"

urlpatterns = [
    path("admin/", admin.site.urls),

    # health probe for Render
    path("healthz/", health_check, name="health-check"),

    # api
    path(f"{API}auth/", include("apps.accounts.urls")),
    path(f"{API}stores/", include("apps.stores.urls")),

    # docs
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
