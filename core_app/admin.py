from django.contrib import admin

from .models import PriceItem, PriceList, Stock, StockMovement


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "subgroup", "unit", "sku", "quantity", "created_at")
    list_filter = ("category", "subgroup", "unit")
    search_fields = ("name", "category", "subgroup", "sku")
    list_editable = ("subgroup", "sku")
    list_display_links = ("name",)


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("stock", "movement_type", "quantity", "note", "created_at")
    list_filter = ("movement_type", "created_at")
    search_fields = ("stock__name", "stock__sku", "note")
    raw_id_fields = ("stock",)


@admin.register(PriceList)
class PriceListAdmin(admin.ModelAdmin):
    list_display = ("title", "sheet_name", "list_date", "currency", "created_at")
    list_filter = ("list_date", "currency")
    search_fields = ("title", "sheet_name")


@admin.register(PriceItem)
class PriceItemAdmin(admin.ModelAdmin):
    list_display = ("price_list", "group", "name", "price")
    list_filter = ("price_list", "group")
    search_fields = ("name", "group", "price_list__title")
    raw_id_fields = ("price_list",)
