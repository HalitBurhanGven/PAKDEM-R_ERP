from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core_app.urls")),
    path("", include("core_app.stock_urls")),
    path("", include("core_app.price_urls")),
    path("rapor/", include("core_app.reports.urls")),
]
