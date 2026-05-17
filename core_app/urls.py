from django.urls import path

from core_app.views.stock import (
    home,
    operation_bulk_preview,
    operation_delete,
    operation_detail,
    operation_draft_delete,
    operation_draft_open,
    operation_print_delivery_form,
    operation_print_receipt,
    operation_start_from_receipt,
)

urlpatterns = [
    path("", home, name="home"),
    path("islem/liste-onizleme/", operation_bulk_preview, name="operation_bulk_preview"),
    path("islem/<int:pk>/", operation_detail, name="operation_detail"),
    path("islem/<int:pk>/yazdir/", operation_print_receipt, name="operation_print_receipt"),
    path("islem/<int:pk>/teslim-formu/", operation_print_delivery_form, name="operation_print_delivery_form"),
    path("islem/<int:pk>/sil/", operation_delete, name="operation_delete"),
    path("taslak/<int:pk>/ac/", operation_draft_open, name="operation_draft_open"),
    path("taslak/<int:pk>/sil/", operation_draft_delete, name="operation_draft_delete"),
    path("islem/<int:pk>/baslat/", operation_start_from_receipt, name="operation_start_from_receipt"),
]
