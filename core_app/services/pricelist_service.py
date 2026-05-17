from dataclasses import dataclass
from urllib.parse import urlencode

from django.db import transaction
from django.db.models import Count, Q

from core_app.models import PriceItem, PriceList, Stock
from core_app.services.price_match_helpers import build_stock_price_key
from core_app.services.text import normalize_text


def get_price_list_list_data(q="", active_id=None):
    qs = PriceList.objects.annotate(item_count=Count("items"))
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(sheet_name__icontains=q))
    return {
        "lists": qs.order_by("-list_date", "-id"),
        "q": q,
        "active_id": active_id,
    }


def get_price_list_detail_data(pk):
    price_list = PriceList.objects.get(pk=pk)
    return {
        "pl": price_list,
        "items": price_list.items.order_by("group", "name"),
    }


@dataclass
class StockDraftFromPriceItem:
    price_item: PriceItem
    name: str
    sku: str
    category: str
    unit: str
    quantity: int
    existing_stock: Stock | None


def build_duplicate_stock_explanation(draft: StockDraftFromPriceItem) -> dict:
    existing_stock = draft.existing_stock
    if existing_stock is None:
        raise ValueError("Çakışma açıklaması için mevcut stok kaydı bulunamadı.")

    rows = [
        {
            "label": "Ürün Adı",
            "draft_value": draft.name or "-",
            "existing_value": existing_stock.name or "-",
            "is_duplicate_key": True,
        },
        {
            "label": "SKU",
            "draft_value": draft.sku or "-",
            "existing_value": existing_stock.sku or "-",
            "is_duplicate_key": True,
        },
        {
            "label": "Kategori",
            "draft_value": draft.category or "-",
            "existing_value": existing_stock.category or "-",
            "is_duplicate_key": False,
        },
        {
            "label": "Birim",
            "draft_value": draft.unit or "-",
            "existing_value": existing_stock.unit or "-",
            "is_duplicate_key": False,
        },
        {
            "label": "Miktar",
            "draft_value": draft.quantity,
            "existing_value": existing_stock.quantity,
            "is_duplicate_key": False,
        },
    ]

    duplicate_reason = (
        "Yeni stok kartı açılamadı çünkü girilen ürün adı ve SKU birlikte "
        "mevcut bir stok kimliğiyle eşleşti."
    )
    return {
        "existing_stock": existing_stock,
        "rows": rows,
        "duplicate_reason": duplicate_reason,
        "duplicate_keys": ["name", "sku"],
    }


def build_stock_create_edit_query(draft: StockDraftFromPriceItem) -> str:
    return urlencode({
        "edit": "1",
        "name": draft.name,
        "sku": draft.sku,
        "category": draft.category,
        "unit": draft.unit,
        "quantity": draft.quantity,
    })


def _iter_stock_lookup_keys(stock: Stock):
    yield build_stock_price_key(stock.name, stock.sku)

    # Legacy data may have price-item group stored in subgroup while SKU stayed blank.
    if not (stock.sku or "").strip() and (stock.subgroup or "").strip():
        yield build_stock_price_key(stock.name, stock.subgroup)


def find_existing_stock_for_identity(name: str, sku: str) -> Stock | None:
    clean_name = (name or "").strip()
    clean_sku = (sku or "").strip()
    if not clean_name:
        return None

    target_key = build_stock_price_key(clean_name, clean_sku)
    normalized_name = normalize_text(clean_name)

    candidates = Stock.objects.only("id", "name", "sku", "subgroup", "category").all()
    for stock in candidates:
        if normalize_text(stock.name) != normalized_name:
            continue
        if target_key in set(_iter_stock_lookup_keys(stock)):
            return stock
    return None


def get_default_stock_unit_for_price_list(price_list: PriceList) -> str:
    normalized_sheet = normalize_text(getattr(price_list, "sheet_name", ""))
    if "profil" in normalized_sheet:
        return "mt"
    return "adet"


def build_stock_draft_from_price_item(price_item: PriceItem, price_list: PriceList) -> StockDraftFromPriceItem:
    name = (price_item.name or "").strip()
    sku = ((price_item.group or "").strip())[:50]
    category = (price_list.sheet_name or "").strip()
    unit = get_default_stock_unit_for_price_list(price_list)
    quantity = 0

    return StockDraftFromPriceItem(
        price_item=price_item,
        name=name,
        sku=sku,
        category=category,
        unit=unit,
        quantity=quantity,
        existing_stock=find_existing_stock_for_identity(name, sku),
    )


def build_stock_draft_from_form_data(price_item: PriceItem, form_data) -> StockDraftFromPriceItem:
    name = (form_data.get("name") or "").strip()
    sku = ((form_data.get("sku") or "").strip())[:50]
    category = (form_data.get("category") or "").strip()
    unit = (form_data.get("unit") or "adet").strip() or "adet"
    quantity = int(form_data.get("quantity") or 0)

    return StockDraftFromPriceItem(
        price_item=price_item,
        name=name,
        sku=sku,
        category=category,
        unit=unit,
        quantity=quantity,
        existing_stock=find_existing_stock_for_identity(name, sku),
    )


@transaction.atomic
def create_stock_from_price_item_draft(draft: StockDraftFromPriceItem) -> Stock:
    if not draft.name:
        raise ValueError("Fiyat kaleminde ürün adı boş olduğu için stok kartı oluşturulamaz.")
    if draft.existing_stock is not None:
        raise ValueError("Bu fiyat kalemi için aynı kimlikte stok kartı zaten var.")

    return Stock.objects.create(
        name=draft.name,
        category=draft.category,
        unit=draft.unit,
        sku=draft.sku,
        quantity=draft.quantity,
    )


@transaction.atomic
def sync_price_list_items_to_stock(price_list):
    created = 0
    skipped = 0
    default_unit = get_default_stock_unit_for_price_list(price_list)

    for item in PriceItem.objects.filter(price_list=price_list).only("name", "group"):
        name = (item.name or "").strip()
        group = (item.group or "").strip()
        if not name:
            continue

        sku_val = group[:50]
        existing = find_existing_stock_for_identity(name, sku_val)
        if existing is not None:
            skipped += 1
            continue

        Stock.objects.create(
            name=name,
            category=(price_list.sheet_name or "").strip(),
            unit=default_unit,
            sku=sku_val,
            quantity=0,
        )
        created += 1

    return {"created": created, "skipped": skipped}
