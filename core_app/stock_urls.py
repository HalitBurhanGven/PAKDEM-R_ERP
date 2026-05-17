from django.urls import path

from core_app.views.stock import (
    category_bulk_subgroup,
    category_detail,
    category_list,
    category_sku,
    stock_bulk_delete,
    stock_delete,
    stock_edit,
    stock_list,
    stock_movement,
)

urlpatterns = [
    path("stok/", stock_list, name="stock_list"),
    path("stok/toplu-sil/", stock_bulk_delete, name="stock_bulk_delete"),
    path("stok/duzenle/<int:pk>/", stock_edit, name="stock_edit"),
    path("stok/sil/<int:pk>/", stock_delete, name="stock_delete"),
    path("stok/hareket/<int:pk>/", stock_movement, name="stock_movement"),
    path("kategoriler/", category_list, name="category_list"),
    path("kategoriler/<str:category>/", category_detail, name="category_detail"),
    path("kategoriler/<str:category>/sku/", category_sku, name="category_sku"),
    path("kategoriler/<str:category>/bulk-subgroup/", category_bulk_subgroup, name="category_bulk_subgroup"),
]
