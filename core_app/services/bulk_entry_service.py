from __future__ import annotations

from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher

from core_app.services.text import normalize_text


UNIT_ALIASES = {
    "adet": "adet",
    "ad": "adet",
    "kg": "kg",
    "kilo": "kg",
    "mt": "mt",
    "m": "mt",
    "metre": "mt",
}


def _is_number_token(value: str) -> bool:
    try:
        Decimal(value.replace(",", "."))
    except (InvalidOperation, AttributeError):
        return False
    return True


def _parse_decimal(value: str) -> Decimal:
    return Decimal(value.replace(",", "."))


def _normalize_unit(value: str) -> str | None:
    return UNIT_ALIASES.get(normalize_text(value))


def _parse_line(raw_line: str) -> dict:
    line = " ".join((raw_line or "").strip().split())
    if not line:
        return {"raw_line": raw_line, "status": "empty"}

    tokens = line.split()
    quantity = None
    unit = None
    unit_price = None
    name_tokens = tokens[:]

    if len(tokens) >= 4 and _is_number_token(tokens[-1]) and _normalize_unit(tokens[-2]) and _is_number_token(tokens[-3]):
        unit_price = _parse_decimal(tokens[-1])
        unit = _normalize_unit(tokens[-2])
        quantity = int(_parse_decimal(tokens[-3]))
        name_tokens = tokens[:-3]
    elif len(tokens) >= 3 and _normalize_unit(tokens[-1]) and _is_number_token(tokens[-2]):
        unit = _normalize_unit(tokens[-1])
        quantity = int(_parse_decimal(tokens[-2]))
        name_tokens = tokens[:-2]
    elif len(tokens) >= 3 and _is_number_token(tokens[-1]) and _normalize_unit(tokens[-2]):
        unit = _normalize_unit(tokens[-2])
        quantity = int(_parse_decimal(tokens[-1]))
        name_tokens = tokens[:-2]
    elif len(tokens) >= 3 and _is_number_token(tokens[-1]) and _is_number_token(tokens[-2]):
        unit_price = _parse_decimal(tokens[-1])
        quantity = int(_parse_decimal(tokens[-2]))
        name_tokens = tokens[:-2]
    elif len(tokens) >= 2 and _is_number_token(tokens[-1]):
        quantity = int(_parse_decimal(tokens[-1]))
        name_tokens = tokens[:-1]

    parsed_name = " ".join(name_tokens).strip()
    if not parsed_name:
        parsed_name = line.strip()

    return {
        "raw_line": raw_line,
        "parsed_name": parsed_name,
        "quantity": quantity if quantity and quantity > 0 else 1,
        "unit": unit or "",
        "unit_price": unit_price,
        "normalized_name": normalize_text(parsed_name),
        "status": "parsed",
    }


def _score_catalog_item(parsed_name: str, catalog_item: dict) -> float:
    query = normalize_text(parsed_name)
    if not query:
        return 0

    name = normalize_text(catalog_item.get("name"))
    sku = normalize_text(catalog_item.get("sku"))
    subgroup = normalize_text(catalog_item.get("subgroup"))

    if query == name or (sku and query == sku) or (subgroup and query == subgroup):
        return 100
    if query and name and (query in name or name in query):
        return 96
    if query and subgroup and (query in subgroup or subgroup in query):
        return 94
    if query and sku and (query in sku or sku in query):
        return 93

    score = 0.0
    for candidate in [name, subgroup, sku]:
        if not candidate:
            continue
        ratio = SequenceMatcher(None, query, candidate).ratio()
        score = max(score, ratio * 100)
    return score


def _build_suggestions(parsed_name: str, catalog: list[dict]) -> list[dict]:
    ranked = []
    for item in catalog:
        score = _score_catalog_item(parsed_name, item)
        if score >= 45:
            ranked.append((score, item))
    ranked.sort(key=lambda row: (-row[0], row[1]["label"]))
    suggestions = []
    for score, item in ranked[:3]:
        suggestions.append({
            "stock_id": item["id"],
            "label": item["label"],
            "unit": item["unit"],
            "unit_price": item["unit_price"],
            "score": round(score, 1),
        })
    return suggestions


def build_bulk_entry_preview(bulk_text: str, catalog: list[dict]) -> dict:
    lines = [line for line in (bulk_text or "").splitlines() if line.strip()]
    results = []

    for raw_line in lines:
        parsed = _parse_line(raw_line)
        suggestions = _build_suggestions(parsed["parsed_name"], catalog)

        matched = suggestions[0] if suggestions and suggestions[0]["score"] >= 95 else None
        if matched:
            status = "matched"
            message = "Eşleşti"
        elif suggestions:
            status = "suggested"
            message = "Benzer ürün önerildi"
        else:
            status = "unmatched"
            message = "Eşleşen ürün bulunamadı"

        results.append({
            "raw_line": raw_line,
            "parsed_name": parsed["parsed_name"],
            "quantity": parsed["quantity"],
            "unit": parsed["unit"] or (matched["unit"] if matched else "adet"),
            "unit_price": f"{(parsed['unit_price'] if parsed['unit_price'] is not None else Decimal(matched['unit_price']) if matched else Decimal('0.00')):.2f}",
            "status": status,
            "message": message,
            "matched_stock_id": matched["stock_id"] if matched else "",
            "matched_label": matched["label"] if matched else "",
            "suggestions": suggestions,
        })

    return {
        "rows": results,
        "summary": {
            "total": len(results),
            "matched": sum(1 for row in results if row["status"] == "matched"),
            "suggested": sum(1 for row in results if row["status"] == "suggested"),
            "unmatched": sum(1 for row in results if row["status"] == "unmatched"),
        },
    }
