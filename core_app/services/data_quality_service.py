from core_app.models import PriceItem, Stock
from core_app.services.data_quality_rules import get_issue_definition
from core_app.services.duplicate_sku_service import build_duplicate_sku_data
from core_app.services.matching_service import build_price_match_data
from core_app.services.price_match_helpers import build_price_item_lookup, resolve_price_item_for_stock


def _build_same_name_identity_rows():
    grouped = {}
    rows = (
        Stock.objects.exclude(normalized_name="")
        .values("id", "name", "normalized_name", "sku", "subgroup", "identity_key", "quantity", "category")
        .order_by("normalized_name", "id")
    )

    for row in rows:
        grouped.setdefault(row["normalized_name"], []).append(row)

    issue_meta = get_issue_definition("same_name_different_identity")
    result_rows = []
    for normalized_name, records in grouped.items():
        identity_keys = {record["identity_key"] for record in records if record["identity_key"]}
        if len(records) < 2 or len(identity_keys) < 2:
            continue

        result_rows.append({
            "normalized_name": normalized_name,
            "display_name": records[0]["name"],
            "record_count": len(records),
            "identity_count": len(identity_keys),
            "records": records,
            "issue": {"code": "same_name_different_identity", **issue_meta},
        })

    return result_rows


def build_same_name_identity_data():
    result_rows = _build_same_name_identity_rows()
    return {
        "count": len(result_rows),
        "rows": result_rows,
    }


def build_same_name_identity_detail(normalized_name, active_price_list_id=None):
    normalized_name = (normalized_name or "").strip()
    if not normalized_name:
        return None

    conflict = None
    for row in _build_same_name_identity_rows():
        if row["normalized_name"] == normalized_name:
            conflict = row
            break

    if conflict is None:
        return None

    exact_price = {}
    name_only_price = {}
    if active_price_list_id:
        price_items = list(
            PriceItem.objects.filter(price_list_id=active_price_list_id)
            .values("id", "name", "group", "price")
        )
        exact_price, name_only_price, _groups_by_name = build_price_item_lookup(price_items)

    records = []
    for record in conflict["records"]:
        enriched = dict(record)
        price_item, match_type = resolve_price_item_for_stock(record, exact_price, name_only_price)
        enriched["last_price"] = price_item.get("price") if price_item else None
        enriched["price_match_type"] = match_type
        records.append(enriched)

    return {
        **conflict,
        "records": records,
    }


def build_data_quality_overview(active_price_list_id=None):
    duplicate_data = build_duplicate_sku_data()
    same_name_data = build_same_name_identity_data()
    overview = {
        "duplicate_sku_groups": duplicate_data["duplicate_count"],
        "merge_candidates": duplicate_data["summary"]["merge_candidates"],
        "group_code_misuse": duplicate_data["summary"]["group_code_misuse"],
        "manual_review": duplicate_data["summary"]["manual_review"],
        "same_name_conflicts": same_name_data["count"],
    }

    if active_price_list_id:
        price_data = build_price_match_data(active_price_list_id)
        overview.update({
            "stocks_without_price": price_data["counts"]["stocks_without_price"],
            "priceitems_without_stock": price_data["counts"]["priceitems_without_stock"],
            "suspects": price_data["counts"]["suspects"],
        })

    return overview
