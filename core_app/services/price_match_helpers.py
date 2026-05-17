from decimal import Decimal

from core_app.services.text import normalize_text


def normalize_match_text(value):
    return normalize_text(value)


def build_stock_price_key(name, sku=""):
    return (normalize_match_text(name), normalize_match_text(sku))


def build_price_item_key(name, group=""):
    return (normalize_match_text(name), normalize_match_text(group))


def build_price_item_lookup(priceitems):
    exact_price = {}
    name_only_price = {}
    groups_by_name = {}

    for price_item in priceitems:
        key = build_price_item_key(price_item.get("name"), price_item.get("group"))
        if key not in exact_price:
            exact_price[key] = price_item

        normalized_name = normalize_match_text(price_item.get("name"))
        raw_group = (price_item.get("group") or "").strip()
        if not normalized_name:
            continue

        if raw_group:
            groups_by_name.setdefault(normalized_name, set()).add(raw_group)
        elif normalized_name not in name_only_price:
            name_only_price[normalized_name] = price_item

    return exact_price, name_only_price, groups_by_name


def resolve_price_item_for_stock(stock, exact_price, name_only_price):
    name = stock.get("name") if isinstance(stock, dict) else getattr(stock, "name", "")
    sku = stock.get("sku") if isinstance(stock, dict) else getattr(stock, "sku", "")

    key = build_stock_price_key(name, sku)
    price_item = exact_price.get(key)
    if price_item is not None:
        return price_item, "exact"

    if not (sku or "").strip():
        normalized_name = normalize_match_text(name)
        price_item = name_only_price.get(normalized_name)
        if price_item is not None:
            return price_item, "name_only"

    return None, None


def calculate_stock_value(quantity, price):
    if price is None:
        return None

    price_decimal = price if isinstance(price, Decimal) else Decimal(str(price))
    return (price_decimal * Decimal(int(quantity or 0))).quantize(Decimal("0.01"))
