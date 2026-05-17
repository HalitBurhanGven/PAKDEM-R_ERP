from django.urls import path

from core_app.views.pricelist import (
    import_price_list,
    price_list_delete,
    price_list_detail,
    price_list_list,
    set_active_price_list,
    sync_price_list_to_stock,
)

urlpatterns = [
    path("fiyat/", price_list_list, name="price_list_list"),
    path("fiyat/yukle/", import_price_list, name="import_price_list"),
    path("fiyat/sync-stok/", sync_price_list_to_stock, name="sync_price_list_to_stock"),
    path("fiyat/aktif/<int:pk>/", set_active_price_list, name="set_active_price_list"),
    path("fiyat/sil/<int:pk>/", price_list_delete, name="price_list_delete"),
    path("fiyat/<int:pk>/", price_list_detail, name="price_list_detail"),
]
