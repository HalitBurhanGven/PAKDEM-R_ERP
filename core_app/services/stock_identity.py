from dataclasses import dataclass

from django.db import transaction

from core_app.models import Stock
from core_app.services.text import build_stock_identity_key, normalize_text


@dataclass
class StockIdentity:
    name: str
    normalized_name: str
    category: str
    subgroup: str
    normalized_subgroup: str
    sku: str
    normalized_sku: str
    unit: str
    quantity: int
    identity_key: str


@dataclass
class CreateOrMergeResult:
    stock: Stock
    created: bool
    merged: bool


def build_stock_identity(
    name: str,
    sku: str = "",
    subgroup: str = "",
    category: str = "",
    unit: str = "adet",
    quantity: int = 0,
) -> StockIdentity:
    clean_name = (name or "").strip()
    clean_sku = (sku or "").strip()
    clean_subgroup = (subgroup or "").strip()
    clean_category = (category or "").strip()
    clean_unit = (unit or "adet").strip() or "adet"

    return StockIdentity(
        name=clean_name,
        normalized_name=normalize_text(clean_name),
        category=clean_category,
        subgroup=clean_subgroup,
        normalized_subgroup=normalize_text(clean_subgroup),
        sku=clean_sku,
        normalized_sku=normalize_text(clean_sku),
        unit=clean_unit,
        quantity=int(quantity or 0),
        identity_key=build_stock_identity_key(clean_name, sku=clean_sku, subgroup=clean_subgroup),
    )


def _subgroup_is_compatible(stock: Stock, identity: StockIdentity) -> bool:
    current_subgroup = normalize_text(stock.subgroup)
    incoming_subgroup = identity.normalized_subgroup

    if not current_subgroup or not incoming_subgroup:
        return True
    return current_subgroup == incoming_subgroup


def _find_existing_stock_by_sku(identity: StockIdentity) -> Stock | None:
    candidates = list(Stock.objects.filter(sku__iexact=identity.sku).order_by("id"))
    if not candidates:
        return None

    same_name_candidates = [
        stock for stock in candidates
        if normalize_text(stock.name) == identity.normalized_name
    ]
    if not same_name_candidates:
        return None

    exact_subgroup_match = next(
        (stock for stock in same_name_candidates if normalize_text(stock.subgroup) == identity.normalized_subgroup),
        None,
    )
    if exact_subgroup_match:
        return exact_subgroup_match

    compatible_match = next((stock for stock in same_name_candidates if _subgroup_is_compatible(stock, identity)), None)
    return compatible_match


def find_existing_stock(identity: StockIdentity) -> Stock | None:
    if identity.normalized_sku:
        return _find_existing_stock_by_sku(identity)
    return Stock.objects.filter(identity_key=identity.identity_key).first()


def _apply_safe_updates(stock: Stock, identity: StockIdentity) -> None:
    stock.name = identity.name

    if identity.category and not stock.category:
        stock.category = identity.category

    if identity.subgroup and not stock.subgroup:
        stock.subgroup = identity.subgroup

    if identity.unit:
        stock.unit = identity.unit

    if identity.sku:
        current_sku = normalize_text(stock.sku)
        if current_sku and current_sku != identity.normalized_sku:
            raise ValueError("Existing stock SKU conflicts with incoming SKU.")
        stock.sku = identity.sku


@transaction.atomic
def create_or_merge_stock(
    name: str,
    category: str = "",
    subgroup: str = "",
    unit: str = "adet",
    sku: str = "",
    quantity: int = 0,
) -> CreateOrMergeResult:
    identity = build_stock_identity(
        name=name,
        sku=sku,
        subgroup=subgroup,
        category=category,
        unit=unit,
        quantity=quantity,
    )

    if not identity.name:
        raise ValueError("Stock name cannot be blank.")

    existing = find_existing_stock(identity)
    if existing:
        _apply_safe_updates(existing, identity)
        existing.quantity += identity.quantity
        existing.save()
        return CreateOrMergeResult(stock=existing, created=False, merged=True)

    stock = Stock.objects.create(
        name=identity.name,
        category=identity.category,
        subgroup=identity.subgroup,
        unit=identity.unit,
        sku=identity.sku,
        quantity=identity.quantity,
    )
    return CreateOrMergeResult(stock=stock, created=True, merged=False)
