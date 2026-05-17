from django.urls import path

from core_app.views.import_export import export_stocks_xlsx, import_stocks_xlsx
from core_app.views.reporting import movement_report, report_home
from . import views

app_name = "reports"

urlpatterns = [
    path("", report_home, name="report_home"),
    path("hareket-grafik/", movement_report, name="movement_report"),
    path("stok-excel/", export_stocks_xlsx, name="export_stocks_xlsx"),
    path("stok-excel-yukle/", import_stocks_xlsx, name="import_stocks_xlsx"),
    path("sku-cakismalari/", views.duplicate_sku_report, name="duplicate_sku_report"),
    path("stok-merge/", views.stock_merge_assistant, name="stock_merge_assistant"),
    path("isim-cakismalari/detay/", views.same_name_conflict_detail, name="same_name_conflict_detail"),
    path("sku-cakismalari/temizle/", views.cleanup_duplicate_sku_report, name="cleanup_duplicate_sku_report"),
    path("fiyat-eslesme/", views.price_match_report, name="price_match_report"),
    path("fiyat-eslesme/olustur/<int:item_id>/", views.create_stock_from_price_match, name="create_stock_from_price_match"),
    path("fiyat-eslesme/bulk-sku/", views.price_match_bulk_sku, name="price_match_bulk_sku"),
    path("fiyat-eslesme/export/", views.price_match_export, name="price_match_export"),
    path("fiyat-karsilastir/", views.price_list_compare, name="price_list_compare"),
    path("fiyat-karsilastir/detay/", views.price_list_compare_detail, name="price_list_compare_detail"),
    path("profil-kesim-planlama/", views.profile_cut_optimizer, name="profile_cut_optimizer"),
]
