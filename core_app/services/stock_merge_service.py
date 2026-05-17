from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction

from core_app.models import PriceItem, Stock, StockMergeAudit, StockMovement
from core_app.services.price_match_helpers import build_price_item_lookup, calculate_stock_value, resolve_price_item_for_stock
from core_app.services.text import build_stock_identity_key


class StockMergeError(ValueError):
    pass


@dataclass
class StockMergePreview:
    left: Stock
    right: Stock
    merged_quantity: int


@dataclass
class StockMergeResult:
    surviving_stock: Stock
    removed_stock_id: int
    moved_movement_count: int


def _build_stock_snapshot(stock: Stock) -> dict:
    return {
        "id": stock.id,
        "name": stock.name,
        "sku": stock.sku,
        "category": stock.category,
        "subgroup": stock.subgroup,
        "unit": stock.unit,
        "quantity": stock.quantity,
        "is_active": stock.is_active,
        "last_price": str(stock.last_price) if getattr(stock, "last_price", None) is not None else None,
        "stock_value": str(stock.stock_value) if getattr(stock, "stock_value", None) is not None else None,
    }


def _build_price_maps(active_price_list_id=None):
    if not active_price_list_id:
        return {}, {}

    items = PriceItem.objects.filter(price_list_id=active_price_list_id).order_by("-id").values("name", "group", "price")
    return build_price_item_lookup(items)[:2]


def _annotate_stock_price(stock: Stock, exact_price, name_only_price) -> None:
    price_item, _match_type = resolve_price_item_for_stock(stock, exact_price, name_only_price)
    price = price_item.get("price") if price_item else None
    stock.last_price = price
    stock.stock_value = calculate_stock_value(stock.quantity, price) if price is not None else None


def _load_pair(left_id, right_id):
    try:
        left_id = int(left_id)
        right_id = int(right_id)
    except (TypeError, ValueError):
        raise StockMergeError("Geçerli iki stok kaydı seçilmedi.")

    if left_id == right_id:
        raise StockMergeError("Aynı kayıt kendiyle birleştirilemez.")

    stocks = {
        stock.id: stock
        for stock in Stock.objects.filter(id__in=[left_id, right_id])
    }
    if len(stocks) != 2:
        raise StockMergeError("Seçilen stok kayıtlarından biri bulunamadı.")

    return stocks[left_id], stocks[right_id]


def build_stock_merge_preview(left_id, right_id, active_price_list_id=None) -> StockMergePreview:
    left, right = _load_pair(left_id, right_id)
    exact_price, name_only_price = _build_price_maps(active_price_list_id)
    _annotate_stock_price(left, exact_price, name_only_price)
    _annotate_stock_price(right, exact_price, name_only_price)
    return StockMergePreview(
        left=left,
        right=right,
        merged_quantity=(left.quantity or 0) + (right.quantity or 0),
    )


def _validate_merge_target(surviving_stock_id: int, name: str, sku: str, subgroup: str) -> None:
    identity_key = build_stock_identity_key(name, sku=sku, subgroup=subgroup)
    conflict = (
        Stock.objects.exclude(id=surviving_stock_id)
        .filter(identity_key=identity_key)
        .first()
    )
    if conflict is not None:
        raise StockMergeError("Birleştirme sonucu başka bir stok kaydıyla aynı kimliğe düşüyor.")


@transaction.atomic
def apply_stock_merge(
    *,
    left_id,
    right_id,
    survivor_side: str,
    field_sources: dict,
) -> StockMergeResult:
    left_id = int(left_id)
    right_id = int(right_id)
    if left_id == right_id:
        raise StockMergeError("Aynı kayıt kendiyle birleştirilemez.")

    locked = list(Stock.objects.select_for_update().filter(id__in=[left_id, right_id]).order_by("id"))
    if len(locked) != 2:
        raise StockMergeError("Birleştirme için gerekli stok kayıtları bulunamadı.")

    stock_map = {stock.id: stock for stock in locked}
    left = stock_map.get(left_id)
    right = stock_map.get(right_id)
    if left is None or right is None:
        raise StockMergeError("Birleştirme için gerekli stok kayıtları bulunamadı.")

    if survivor_side not in {"left", "right"}:
        raise StockMergeError("Ana kayıt seçimi geçersiz.")

    source_map = {"left": left, "right": right}
    surviving_stock = source_map[survivor_side]
    removed_stock = right if surviving_stock.id == left.id else left
    left_snapshot = _build_stock_snapshot(left)
    right_snapshot = _build_stock_snapshot(right)

    selected_name = getattr(source_map[field_sources["name_source"]], "name", "").strip()
    selected_sku = getattr(source_map[field_sources["sku_source"]], "sku", "").strip()
    selected_category = getattr(source_map[field_sources["category_source"]], "category", "").strip()
    selected_subgroup = getattr(source_map[field_sources["subgroup_source"]], "subgroup", "").strip()
    selected_unit = getattr(source_map[field_sources["unit_source"]], "unit", "").strip() or "adet"
    merged_quantity = (left.quantity or 0) + (right.quantity or 0)

    if len(selected_name) < 2:
        raise StockMergeError("Birleştirme için seçilen ürün adı en az 2 karakter olmalı.")

    valid_units = {choice[0] for choice in Stock.UNIT_CHOICES}
    if selected_unit not in valid_units:
        raise StockMergeError("Birleştirme için seçilen birim geçersiz.")

    _validate_merge_target(surviving_stock.id, selected_name, selected_sku, selected_subgroup)

    surviving_stock.name = selected_name
    surviving_stock.sku = selected_sku[:50]
    surviving_stock.category = selected_category[:80]
    surviving_stock.subgroup = selected_subgroup[:80]
    surviving_stock.unit = selected_unit
    surviving_stock.quantity = merged_quantity
    surviving_stock.is_active = True
    surviving_stock.save()

    moved_movement_count = StockMovement.objects.filter(stock=removed_stock).update(stock=surviving_stock)
    removed_stock_id = removed_stock.id
    StockMergeAudit.objects.create(
        surviving_stock=surviving_stock,
        removed_stock_id=removed_stock_id,
        left_snapshot=left_snapshot,
        right_snapshot=right_snapshot,
        field_sources={
            "survivor_side": survivor_side,
            **field_sources,
        },
        merged_quantity=merged_quantity,
    )
    removed_stock.delete()

    return StockMergeResult(
        surviving_stock=surviving_stock,
        removed_stock_id=removed_stock_id,
        moved_movement_count=moved_movement_count,
    )
