from __future__ import annotations

from dataclasses import dataclass

from core_app.models import PriceItem, PriceList
from core_app.services.text import normalize_text


@dataclass
class CompareContextResult:
    context: dict
    warning: str | None = None


@dataclass
class CompareDetailResult:
    context: dict | None
    error: str | None = None


def build_price_list_compare_context(base_id=None, new_id=None):
    lists = list(PriceList.objects.all().order_by("-id").values("id", "title"))
    empty_context = {
        "lists": lists,
        "base_id": None,
        "new_id": None,
        "summary": None,
        "changed": [],
        "moved": [],
        "added": [],
        "removed": [],
        "ambiguous": [],
    }

    if len(lists) < 2:
        return CompareContextResult(
            context=empty_context,
            warning="Karşılaştırma için en az 2 fiyat listesi gerekli.",
        )

    base_id_value = base_id or str(lists[1]["id"])
    new_id_value = new_id or str(lists[0]["id"])

    try:
        base_id_int = int(base_id_value)
        new_id_int = int(new_id_value)
    except ValueError:
        base_id_int = int(lists[1]["id"])
        new_id_int = int(lists[0]["id"])

    warning = None
    if base_id_int == new_id_int:
        warning = "Aynı listeyi seçtin. Lütfen farklı iki liste seç."
        base_id_int = int(lists[1]["id"])
        new_id_int = int(lists[0]["id"])

    base_exact, base_by_name = build_price_index(base_id_int)
    new_exact, new_by_name = build_price_index(new_id_int)

    base_count_by_name = {name: len(rows) for name, rows in base_by_name.items()}
    new_count_by_name = {name: len(rows) for name, rows in new_by_name.items()}
    base_groups_by_name = {
        name: {((row.get("group") or "").strip()) for row in rows if (row.get("group") or "").strip()}
        for name, rows in base_by_name.items()
    }
    new_groups_by_name = {
        name: {((row.get("group") or "").strip()) for row in rows if (row.get("group") or "").strip()}
        for name, rows in new_by_name.items()
    }

    base_keys = set(base_exact.keys())
    new_keys = set(new_exact.keys())
    common = base_keys & new_keys
    added_keys = new_keys - base_keys
    removed_keys = base_keys - new_keys

    changed = build_changed_rows(
        common,
        base_exact,
        new_exact,
        base_groups_by_name,
        new_groups_by_name,
        base_count_by_name,
        new_count_by_name,
    )
    moved, ambiguous, added_keys, removed_keys = build_moved_and_ambiguous_rows(
        common,
        added_keys,
        removed_keys,
        base_by_name,
        new_by_name,
        base_groups_by_name,
        new_groups_by_name,
        base_count_by_name,
        new_count_by_name,
    )
    added = build_added_rows(added_keys, new_exact, base_groups_by_name, new_groups_by_name, base_count_by_name, new_count_by_name)
    removed = build_removed_rows(removed_keys, base_exact, base_groups_by_name, new_groups_by_name, base_count_by_name, new_count_by_name)

    changed.sort(key=lambda row: ((row.get("group") or ""), (row.get("name") or "")))
    moved.sort(key=lambda row: ((row.get("new_group") or ""), (row.get("name") or "")))
    added.sort(key=lambda row: ((row.get("group") or ""), (row.get("name") or "")))
    removed.sort(key=lambda row: ((row.get("group") or ""), (row.get("name") or "")))
    ambiguous.sort(key=lambda row: (row.get("name") or ""))

    summary = {
        "base_id": base_id_int,
        "new_id": new_id_int,
        "changed": len(changed),
        "moved": len(moved),
        "added": len(added),
        "removed": len(removed),
        "ambiguous": len(ambiguous),
        "base_total": len(base_exact),
        "new_total": len(new_exact),
    }

    return CompareContextResult(
        context={
            "lists": lists,
            "base_id": base_id_int,
            "new_id": new_id_int,
            "summary": summary,
            "changed": changed,
            "moved": moved,
            "added": added,
            "removed": removed,
            "ambiguous": ambiguous,
        },
        warning=warning,
    )


def build_price_list_compare_detail_context(base_id, new_id, name):
    try:
        base_id_int = int(base_id or 0)
        new_id_int = int(new_id or 0)
    except ValueError:
        return CompareDetailResult(context=None, error="Detay için base, new ve name parametreleri gerekli.")

    clean_name = (name or "").strip()
    if not base_id_int or not new_id_int or not clean_name:
        return CompareDetailResult(context=None, error="Detay için base, new ve name parametreleri gerekli.")

    try:
        base_list = PriceList.objects.get(id=base_id_int)
        new_list = PriceList.objects.get(id=new_id_int)
    except PriceList.DoesNotExist:
        return CompareDetailResult(context=None, error="Fiyat listesi bulunamadı.")

    target = normalize_text(clean_name)
    base_items_all = list(PriceItem.objects.filter(price_list_id=base_id_int).values("id", "name", "group", "price"))
    new_items_all = list(PriceItem.objects.filter(price_list_id=new_id_int).values("id", "name", "group", "price"))

    base_items = [row for row in base_items_all if normalize_text(row.get("name")) == target]
    new_items = [row for row in new_items_all if normalize_text(row.get("name")) == target]

    base_items.sort(key=lambda row: ((row.get("group") or ""), (row.get("id") or 0)))
    new_items.sort(key=lambda row: ((row.get("group") or ""), (row.get("id") or 0)))

    base_groups_set = {(row.get("group") or "").strip() for row in base_items if (row.get("group") or "").strip()}
    new_groups_set = {(row.get("group") or "").strip() for row in new_items if (row.get("group") or "").strip()}

    note = "-"
    if len(base_items) > 1 or len(new_items) > 1:
        note = "İsim birden fazla satırda geçtiği için otomatik eşleştirme yapılmadı."

    return CompareDetailResult(
        context={
            "base_id": base_id_int,
            "new_id": new_id_int,
            "name": clean_name,
            "base_list": base_list,
            "new_list": new_list,
            "base_items": base_items,
            "new_items": new_items,
            "base_groups": ", ".join(sorted(base_groups_set)) if base_groups_set else "-",
            "new_groups": ", ".join(sorted(new_groups_set)) if new_groups_set else "-",
            "base_count": len(base_items),
            "new_count": len(new_items),
            "note": note,
        }
    )


def build_price_index(price_list_id: int):
    rows = list(PriceItem.objects.filter(price_list_id=price_list_id).values("id", "name", "group", "price"))
    exact_multi = {}
    by_name = {}

    for row in rows:
        normalized_name = normalize_text(row.get("name"))
        if not normalized_name:
            continue
        normalized_group = normalize_text(row.get("group"))
        key = (normalized_name, normalized_group)
        exact_multi.setdefault(key, []).append(row)
        by_name.setdefault(normalized_name, []).append(row)

    exact_best = {key: pick_best_row(value) for key, value in exact_multi.items()}
    return exact_best, by_name


def pick_best_row(rows):
    if not rows:
        return None

    def score(row):
        price = row.get("price")
        nonzero = 1 if (price not in (None, 0)) else 0
        return (nonzero, row.get("id") or 0)

    return sorted(rows, key=score, reverse=True)[0]


def join_groups(groups) -> str:
    if not groups:
        return "-"
    text = ", ".join(sorted(groups))
    return text[:300]


def build_changed_rows(common, base_exact, new_exact, base_groups_by_name, new_groups_by_name, base_count_by_name, new_count_by_name):
    changed = []
    for key in common:
        base_item = base_exact[key]
        new_item = new_exact[key]
        if not base_item or not new_item:
            continue

        base_price = base_item.get("price")
        new_price = new_item.get("price")
        if base_price == new_price:
            continue

        delta = (new_price or 0) - (base_price or 0)
        pct = None
        if base_price not in (None, 0):
            pct = (delta / base_price) * 100

        name = (new_item.get("name") or base_item.get("name") or "").strip()
        name_key = normalize_text(name)
        changed.append({
            "name": name,
            "old_groups": join_groups(base_groups_by_name.get(name_key)),
            "new_groups": join_groups(new_groups_by_name.get(name_key)),
            "old_count": base_count_by_name.get(name_key, 0),
            "new_count": new_count_by_name.get(name_key, 0),
            "base_groups": join_groups(base_groups_by_name.get(name_key)),
            "base_count": base_count_by_name.get(name_key, 0),
            "note": "Fiyat değişti",
            "old_price": base_price,
            "new_price": new_price,
            "delta": delta,
            "pct": pct,
            "group": (new_item.get("group") or base_item.get("group") or ""),
        })
    return changed


def build_moved_and_ambiguous_rows(common, added_keys, removed_keys, base_by_name, new_by_name, base_groups_by_name, new_groups_by_name, base_count_by_name, new_count_by_name):
    moved = []
    ambiguous = []

    intersect_names = set(base_by_name.keys()) & set(new_by_name.keys())
    for normalized_name in intersect_names:
        base_list = base_by_name.get(normalized_name, [])
        new_list = new_by_name.get(normalized_name, [])

        if len(base_list) == 1 and len(new_list) == 1:
            base_item = base_list[0]
            new_item = new_list[0]

            base_key = (normalize_text(base_item.get("name")), normalize_text(base_item.get("group")))
            new_key = (normalize_text(new_item.get("name")), normalize_text(new_item.get("group")))

            if (base_key not in common) and (new_key not in common) and (base_key in removed_keys) and (new_key in added_keys):
                base_price = base_item.get("price")
                new_price = new_item.get("price")
                delta = (new_price or 0) - (base_price or 0)
                pct = None
                if base_price not in (None, 0):
                    pct = (delta / base_price) * 100

                moved.append({
                    "name": (new_item.get("name") or base_item.get("name") or "").strip(),
                    "old_group": base_item.get("group"),
                    "new_group": new_item.get("group"),
                    "old_groups": join_groups(base_groups_by_name.get(normalized_name)),
                    "new_groups": join_groups(new_groups_by_name.get(normalized_name)),
                    "old_count": base_count_by_name.get(normalized_name, 0),
                    "new_count": new_count_by_name.get(normalized_name, 0),
                    "base_groups": join_groups(base_groups_by_name.get(normalized_name)),
                    "base_count": base_count_by_name.get(normalized_name, 0),
                    "note": "Grup değişti",
                    "old_price": base_price,
                    "new_price": new_price,
                    "delta": delta,
                    "pct": pct,
                })
                removed_keys.discard(base_key)
                added_keys.discard(new_key)
        else:
            base_candidates = [row for row in base_list if (normalize_text(row.get("name")), normalize_text(row.get("group"))) in removed_keys]
            new_candidates = [row for row in new_list if (normalize_text(row.get("name")), normalize_text(row.get("group"))) in added_keys]

            if base_candidates or new_candidates:
                ambiguous.append({
                    "name": (base_candidates[0].get("name") if base_candidates else (new_candidates[0].get("name") if new_candidates else "")).strip(),
                    "base_groups": join_groups(base_groups_by_name.get(normalized_name)),
                    "new_groups": join_groups(new_groups_by_name.get(normalized_name)),
                    "base_count": base_count_by_name.get(normalized_name, 0),
                    "new_count": new_count_by_name.get(normalized_name, 0),
                    "old_groups": join_groups(base_groups_by_name.get(normalized_name)),
                    "old_count": base_count_by_name.get(normalized_name, 0),
                    "note": "İsim iki listede de var ama birden fazla geçtiği için otomatik eşleştirme yapılmadı.",
                })

    return moved, ambiguous, added_keys, removed_keys


def build_added_rows(added_keys, new_exact, base_groups_by_name, new_groups_by_name, base_count_by_name, new_count_by_name):
    added = []
    for key in added_keys:
        new_item = new_exact.get(key)
        if not new_item:
            continue
        normalized_name = normalize_text(new_item.get("name"))
        added.append({
            "name": new_item.get("name"),
            "group": new_item.get("group"),
            "price": new_item.get("price"),
            "old_groups": join_groups(base_groups_by_name.get(normalized_name)),
            "new_groups": join_groups(new_groups_by_name.get(normalized_name)),
            "old_count": base_count_by_name.get(normalized_name, 0),
            "new_count": new_count_by_name.get(normalized_name, 0),
            "base_groups": join_groups(base_groups_by_name.get(normalized_name)),
            "base_count": base_count_by_name.get(normalized_name, 0),
            "note": "Yeni satır",
        })
    return added


def build_removed_rows(removed_keys, base_exact, base_groups_by_name, new_groups_by_name, base_count_by_name, new_count_by_name):
    removed = []
    for key in removed_keys:
        base_item = base_exact.get(key)
        if not base_item:
            continue
        normalized_name = normalize_text(base_item.get("name"))
        removed.append({
            "name": base_item.get("name"),
            "group": base_item.get("group"),
            "price": base_item.get("price"),
            "old_groups": join_groups(base_groups_by_name.get(normalized_name)),
            "new_groups": join_groups(new_groups_by_name.get(normalized_name)),
            "old_count": base_count_by_name.get(normalized_name, 0),
            "new_count": new_count_by_name.get(normalized_name, 0),
            "base_groups": join_groups(base_groups_by_name.get(normalized_name)),
            "base_count": base_count_by_name.get(normalized_name, 0),
            "note": "Listeden çıktı",
        })
    return removed

