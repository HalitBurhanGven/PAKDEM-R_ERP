from __future__ import annotations

from django.db.models import Count, Sum

from core_app.models import Stock
from core_app.services.data_quality_rules import get_issue_definition
from core_app.services.text import normalize_text


def classify_duplicate_sku(records):
    normalized_names = {
        normalize_text((record.get("name") or "").strip())
        for record in records
        if (record.get("name") or "").strip()
    }
    distinct_name_count = len(normalized_names)
    nonempty_subgroup_count = sum(1 for record in records if (record.get("subgroup") or "").strip())
    positive_quantity_count = sum(1 for record in records if (record.get("quantity") or 0) > 0)

    if distinct_name_count == 1:
        issue = get_issue_definition("merge_candidates")
        return {
            "code": "merge_candidates",
            "label": issue["label"],
            "severity": issue["severity"],
            "severity_label": issue["severity_label"],
            "reason": "Aynı SKU altında aynı ürün adı tekrar ediyor.",
            "recommendation": "Kayıtları tek üründe birleştir, miktarı ve notları koru.",
        }

    if distinct_name_count == len(records) and nonempty_subgroup_count == 0:
        issue = get_issue_definition("group_code_misuse")
        return {
            "code": "group_code_misuse",
            "label": issue["label"],
            "severity": issue["severity"],
            "severity_label": issue["severity_label"],
            "reason": "Aynı SKU altında farklı ürünler var ve alt grup boş.",
            "recommendation": "Bu değer muhtemelen ürün SKU'su değil grup etiketi. Alt gruba taşı, SKU alanını temizle.",
        }

    issue = get_issue_definition("manual_review")
    return {
        "code": "manual_review",
        "label": issue["label"],
        "severity": issue["severity"],
        "severity_label": issue["severity_label"],
        "reason": f"Farklı ürünler aynı SKU'yu paylaşıyor. Pozitif miktarlı kayıt sayısı: {positive_quantity_count}.",
        "recommendation": "Kayıtları tek tek incele. Gerekirse doğru SKU ata veya ayrı ürün kartları oluştur.",
    }


def build_duplicate_sku_data():
    duplicate_groups = list(
        Stock.objects.exclude(sku__isnull=True)
        .exclude(sku="")
        .values("sku")
        .annotate(record_count=Count("id"), total_quantity=Sum("quantity"))
        .filter(record_count__gt=1)
        .order_by("-record_count", "sku")
    )

    rows = []
    summary = {
        "merge_candidates": 0,
        "group_code_misuse": 0,
        "manual_review": 0,
    }
    for group in duplicate_groups:
        sku = (group.get("sku") or "").strip()
        records = list(
            Stock.objects.filter(sku=sku)
            .order_by("category", "subgroup", "name", "id")
            .values("id", "name", "category", "subgroup", "quantity", "unit", "created_at")
        )

        categories = sorted(
            {(record.get("category") or "").strip() for record in records if (record.get("category") or "").strip()}
        )
        subgroups = sorted(
            {(record.get("subgroup") or "").strip() for record in records if (record.get("subgroup") or "").strip()}
        )
        strategy = classify_duplicate_sku(records)
        summary[strategy["code"]] += 1

        rows.append({
            "sku": sku,
            "record_count": group["record_count"],
            "total_quantity": group["total_quantity"] or 0,
            "categories": categories,
            "subgroups": subgroups,
            "records": records,
            "strategy": strategy,
        })

    return {
        "duplicate_count": len(rows),
        "summary": summary,
        "rows": rows,
    }


def cleanup_group_code_misuse_sku(target_sku: str | None = None):
    cleaned_groups = 0
    cleaned_rows = 0
    skipped_groups = 0

    duplicate_rows = build_duplicate_sku_data()["rows"]
    if target_sku is not None:
        duplicate_rows = [row for row in duplicate_rows if row["sku"] == target_sku]

    for row in duplicate_rows:
        if row["strategy"]["code"] != "group_code_misuse":
            skipped_groups += 1
            continue

        subgroup_value = row["sku"][:80]
        updated = Stock.objects.filter(sku=row["sku"], subgroup="").update(subgroup=subgroup_value, sku="")
        if updated:
            cleaned_groups += 1
            cleaned_rows += updated

    return {
        "cleaned_groups": cleaned_groups,
        "cleaned_rows": cleaned_rows,
        "skipped_groups": skipped_groups,
    }
