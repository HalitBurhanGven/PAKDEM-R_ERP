from collections import defaultdict
from decimal import Decimal

from django.db.models import Count, Sum

from core_app.models import PriceItem, PriceList, Stock, StockMovement
from core_app.services.price_match_helpers import (
    build_price_item_lookup,
    calculate_stock_value,
    resolve_price_item_for_stock,
)
from core_app.services.text import normalize_text


def get_home_stats():
    return {
        "total_stock": Stock.objects.count(),
        "total_quantity": Stock.objects.aggregate(Sum("quantity"))["quantity__sum"] or 0,
    }


def _resolve_active_price_list(active_price_list_id):
    if not active_price_list_id:
        return None
    return PriceList.objects.filter(id=active_price_list_id).first()


def _build_price_maps(active_list):
    if not active_list:
        return {}, {}

    items = PriceItem.objects.filter(price_list=active_list).order_by("-id").values("name", "group", "price")
    return build_price_item_lookup(items)[:2]


def _annotate_stock_values(stocks, exact_price, name_only_price):
    total_stock_value = Decimal("0.00")
    for stock in stocks:
        if getattr(stock, "unit", "") == "mt":
            stock.last_price = None
            stock.stock_value = None
            continue

        price_item, _match_type = resolve_price_item_for_stock(stock, exact_price, name_only_price)
        price = price_item.get("price") if price_item else None

        stock.last_price = price
        if price is not None:
            stock.stock_value = calculate_stock_value(stock.quantity, price)
            total_stock_value += stock.stock_value
        else:
            stock.stock_value = None

    return total_stock_value


def _matches_stock_search(stock, query):
    normalized_query = normalize_text(query)
    if not normalized_query:
        return True

    haystacks = [
        getattr(stock, "name", ""),
        getattr(stock, "sku", ""),
        getattr(stock, "subgroup", ""),
    ]
    return any(normalized_query in normalize_text(value) for value in haystacks)


def _build_stock_groups(stocks):
    category_map = {}

    for stock in stocks:
        category_label = (getattr(stock, "category", "") or "").strip() or "Kategorisiz"
        subgroup_label = (getattr(stock, "subgroup", "") or "").strip() or "Diğer / Alt kategori yok"

        category_group = category_map.setdefault(category_label, {
            "label": category_label,
            "stock_count": 0,
            "total_quantity": 0,
            "subgroups": {},
        })
        subgroup_group = category_group["subgroups"].setdefault(subgroup_label, {
            "label": subgroup_label,
            "stock_count": 0,
            "total_quantity": 0,
            "stocks": [],
        })

        category_group["stock_count"] += 1
        category_group["total_quantity"] += stock.quantity or 0
        subgroup_group["stock_count"] += 1
        subgroup_group["total_quantity"] += stock.quantity or 0
        subgroup_group["stocks"].append(stock)

    category_groups = []
    for category_label in sorted(category_map.keys(), key=lambda value: value.casefold()):
        category_group = category_map[category_label]
        subgroup_groups = []
        for subgroup_label in sorted(category_group["subgroups"].keys(), key=lambda value: value.casefold()):
            subgroup_groups.append(category_group["subgroups"][subgroup_label])
        category_groups.append({
            "label": category_group["label"],
            "stock_count": category_group["stock_count"],
            "total_quantity": category_group["total_quantity"],
            "subgroups": subgroup_groups,
        })
    return category_groups


def get_stock_list_data(q="", category="", unit="", sku="", sort="created_at", order="desc", active_price_list_id=None):
    stocks_qs = Stock.objects.all()
    if category:
        stocks_qs = stocks_qs.filter(category__iexact=category)
    if unit:
        stocks_qs = stocks_qs.filter(unit=unit)
    if sku:
        stocks_qs = stocks_qs.filter(sku__iexact=sku)

    allowed_sorts = {"name", "quantity", "created_at"}
    if sort not in allowed_sorts:
        sort = "created_at"
    if order not in {"asc", "desc"}:
        order = "desc"

    stocks_qs = stocks_qs.order_by(sort if order == "asc" else f"-{sort}")
    active_list = _resolve_active_price_list(active_price_list_id)
    exact_price, name_only_price = _build_price_maps(active_list)

    stocks = list(stocks_qs)
    if q:
        stocks = [stock for stock in stocks if _matches_stock_search(stock, q)]
    total_stock_value = _annotate_stock_values(stocks, exact_price, name_only_price)
    stock_groups = _build_stock_groups(stocks)

    return {
        "stocks": stocks,
        "stock_groups": stock_groups,
        "sort": sort,
        "order": order,
        "active_price_list": active_list,
        "active_id": active_list.id if active_list else None,
        "total_stock_value": total_stock_value,
        "price_list": active_list,
        "total_value": total_stock_value,
    }


def get_stock_movement_data(stock, limit=50):
    return {
        "stock": stock,
        "movements": stock.movements.order_by("-created_at")[:limit],
    }


def get_category_list_data():
    categories = (
        Stock.objects.exclude(category="")
        .values("category")
        .annotate(item_count=Count("id"))
        .order_by("category")
    )
    return {"categories": categories}


def get_category_detail_data(category, subgroup_filter=""):
    stocks_cat = Stock.objects.filter(category__iexact=category)
    total_stock = stocks_cat.count()
    total_quantity = stocks_cat.aggregate(Sum("quantity"))["quantity__sum"] or 0
    total_in = (
        StockMovement.objects.filter(stock__category__iexact=category, movement_type=StockMovement.IN)
        .aggregate(Sum("quantity"))["quantity__sum"] or 0
    )
    total_out = (
        StockMovement.objects.filter(stock__category__iexact=category, movement_type=StockMovement.OUT)
        .aggregate(Sum("quantity"))["quantity__sum"] or 0
    )
    raw = stocks_cat.values("subgroup").annotate(count=Count("id"), qty=Sum("quantity"))

    subgroup_summary = []
    subgroup_choices_set = set()
    empty_count = 0
    empty_qty = 0
    for row in raw:
        subgroup = (row.get("subgroup") or "").strip()
        count = row.get("count") or 0
        qty = row.get("qty") or 0
        if not subgroup:
            empty_count += count
            empty_qty += qty
        else:
            subgroup_choices_set.add(subgroup)
            subgroup_summary.append({"key": subgroup, "label": subgroup, "count": count, "qty": qty})

    subgroup_summary.sort(key=lambda item: item["label"].casefold())
    if empty_count or empty_qty:
        subgroup_summary.insert(0, {
            "key": "__EMPTY__",
            "label": "Diğer / Boş",
            "count": empty_count,
            "qty": empty_qty,
        })

    qs = stocks_cat
    if subgroup_filter == "__EMPTY__":
        qs = qs.filter(subgroup="")
    elif subgroup_filter:
        qs = qs.filter(subgroup=subgroup_filter)

    return {
        "category": category,
        "stocks": qs.order_by("subgroup", "name"),
        "total_stock": total_stock,
        "total_quantity": total_quantity,
        "total_in": total_in,
        "total_out": total_out,
        "net": total_in - total_out,
        "subgroup_summary": subgroup_summary,
        "subgroup_filter": subgroup_filter,
        "subgroup_choices": sorted(subgroup_choices_set, key=lambda value: value.casefold()),
    }


def get_category_sku_data(category, sku_filter="", sku_empty=False):
    stocks_cat = Stock.objects.filter(category__iexact=category)
    total_stock = stocks_cat.count()
    total_quantity = stocks_cat.aggregate(Sum("quantity"))["quantity__sum"] or 0
    total_in = (
        StockMovement.objects.filter(stock__category__iexact=category, movement_type=StockMovement.IN)
        .aggregate(Sum("quantity"))["quantity__sum"] or 0
    )
    total_out = (
        StockMovement.objects.filter(stock__category__iexact=category, movement_type=StockMovement.OUT)
        .aggregate(Sum("quantity"))["quantity__sum"] or 0
    )

    qs = stocks_cat
    if sku_filter:
        qs = qs.filter(sku=sku_filter)
    elif sku_empty:
        qs = qs.filter(sku="")
    qs = qs.order_by("sku", "subgroup", "name")

    subgroup_map = defaultdict(list)
    for stock in qs:
        subgroup = (getattr(stock, "subgroup", "") or "").strip() or "Diğer"
        subgroup_map[subgroup].append(stock)
    subgroup_groups = sorted(subgroup_map.items(), key=lambda item: item[0].casefold())

    sku_stats = {}
    empty_count = 0
    for row in stocks_cat.values("sku", "subgroup"):
        sku_value = (row.get("sku") or "").strip()
        subgroup = (row.get("subgroup") or "").strip() or "Diğer"
        if not sku_value:
            empty_count += 1
            continue
        if sku_value not in sku_stats:
            sku_stats[sku_value] = {"count": 0, "subgroups": defaultdict(int)}
        sku_stats[sku_value]["count"] += 1
        sku_stats[sku_value]["subgroups"][subgroup] += 1

    sku_summary = []
    for sku_value, info in sku_stats.items():
        subparts = [f"{key}({value})" for key, value in sorted(info["subgroups"].items(), key=lambda item: item[0].casefold())]
        sku_summary.append({"sku": sku_value, "count": info["count"], "subgroups_text": ", ".join(subparts)})
    sku_summary.sort(key=lambda item: (-item["count"], item["sku"].casefold()))

    return {
        "category": category,
        "total_stock": total_stock,
        "total_quantity": total_quantity,
        "total_in": total_in,
        "total_out": total_out,
        "net": total_in - total_out,
        "subgroup_groups": subgroup_groups,
        "sku_summary": sku_summary,
        "sku_empty_count": empty_count,
        "sku_filter": sku_filter,
        "sku_empty": sku_empty,
    }
