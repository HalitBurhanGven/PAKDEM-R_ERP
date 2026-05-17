from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from urllib.parse import urlencode

from core_app.cutting_forms import CutDemandFormSet, ProfileCutOptimizationForm
from core_app.models import PriceItem, PriceList
from core_app.price_forms import CreateStockFromPriceItemForm
from core_app.services.data_quality_service import (
    build_data_quality_overview,
    build_same_name_identity_data,
    build_same_name_identity_detail,
)
from core_app.services.cutting_optimization import build_multi_cut_plan
from core_app.services.duplicate_sku_service import (
    build_duplicate_sku_data,
    cleanup_group_code_misuse_sku,
    classify_duplicate_sku,
)
from core_app.services.matching_service import (
    apply_price_match_bulk_sku,
    apply_price_match_filters,
    build_price_match_data,
    build_price_match_export_response,
    get_active_price_list,
    get_price_match_metadata,
)
from core_app.services.price_compare_service import (
    build_price_list_compare_context,
    build_price_list_compare_detail_context,
)
from core_app.services.pricelist_service import (
    build_duplicate_stock_explanation,
    build_stock_create_edit_query,
    build_stock_draft_from_form_data,
    build_stock_draft_from_price_item,
    create_stock_from_price_item_draft,
)
from core_app.services.stock_merge_service import (
    StockMergeError,
    apply_stock_merge,
    build_stock_merge_preview,
)
from core_app.stock_merge_forms import StockMergeAssistantForm


def _build_clean_query(params, exclude_keys=None):
    exclude_keys = set(exclude_keys or [])
    clean = {}
    for key, value in params.items():
        if key in exclude_keys:
            continue
        if value in (None, "", False):
            continue
        if value is True:
            clean[key] = "1"
        else:
            clean[key] = value
    return urlencode(clean)


def _contains_text(haystack, needle_cf):
    return needle_cf in (haystack or "").casefold()


def _filter_duplicate_report_rows(request, context):
    q = (request.GET.get("q") or "").strip()
    severity = (request.GET.get("severity") or "").strip()
    issue_code = (request.GET.get("issue_code") or "").strip()

    rows = list(context["rows"])
    same_name_rows = list(context["same_name_identity"]["rows"])
    q_cf = q.casefold()

    if q:
        rows = [
            row for row in rows
            if _contains_text(row.get("sku"), q_cf)
            or any(
                _contains_text(record.get("name"), q_cf)
                or _contains_text(record.get("category"), q_cf)
                or _contains_text(record.get("subgroup"), q_cf)
                for record in row.get("records", [])
            )
        ]
        same_name_rows = [
            row for row in same_name_rows
            if _contains_text(row.get("display_name"), q_cf)
            or any(
                _contains_text(record.get("name"), q_cf)
                or _contains_text(record.get("sku"), q_cf)
                or _contains_text(record.get("subgroup"), q_cf)
                for record in row.get("records", [])
            )
        ]

    if severity:
        rows = [row for row in rows if row["strategy"].get("severity") == severity]
        same_name_rows = [row for row in same_name_rows if row["issue"].get("severity") == severity]

    if issue_code:
        rows = [row for row in rows if row["strategy"].get("code") == issue_code]
        same_name_rows = [row for row in same_name_rows if row["issue"].get("code") == issue_code]

    rows_paginator = Paginator(rows, 5)
    same_name_paginator = Paginator(same_name_rows, 5)
    rows_page = rows_paginator.get_page(request.GET.get("dup_page"))
    same_name_page = same_name_paginator.get_page(request.GET.get("same_page"))

    context.update({
        "rows": rows_page.object_list,
        "same_name_identity": {
            **context["same_name_identity"],
            "rows": same_name_page.object_list,
            "filtered_count": len(same_name_rows),
            "page_obj": same_name_page,
        },
        "duplicate_filters": {
            "q": q,
            "severity": severity,
            "issue_code": issue_code,
        },
        "duplicate_filtered_count": len(rows),
        "duplicate_page_obj": rows_page,
        "duplicate_page_query": _build_clean_query(
            {"q": q, "severity": severity, "issue_code": issue_code},
            exclude_keys={"dup_page"},
        ),
        "same_name_page_query": _build_clean_query(
            {"q": q, "severity": severity, "issue_code": issue_code},
            exclude_keys={"same_page"},
        ),
    })
    return context


def _paginate_price_match_lists(request, filters):
    base_query = _build_clean_query({
        "tab": filters["tab"],
        "q": filters["q"],
        "category": filters["category"],
        "sku_empty": filters["sku_empty"],
        "suggested_only": filters["suggested_only"],
        "multi_only": filters["multi_only"],
        "severity": filters["severity"],
        "issue_code": filters["issue_code"],
        "match_type": filters["match_type"],
    }, exclude_keys={"page"})

    paginator = Paginator(filters["suspects"], 10)
    suspects_page = paginator.get_page(request.GET.get("page"))
    filters["suspects"] = suspects_page.object_list
    filters["page_obj"] = suspects_page
    filters["page_query"] = base_query

    active_tab = filters["tab"]
    if active_tab == "stocks_without_price":
        page_obj = Paginator(filters["stocks_without_price"], 10).get_page(request.GET.get("page"))
        filters["stocks_without_price"] = page_obj.object_list
        filters["page_obj"] = page_obj
    elif active_tab == "priceitems_without_stock":
        page_obj = Paginator(filters["priceitems_without_stock"], 10).get_page(request.GET.get("page"))
        filters["priceitems_without_stock"] = page_obj.object_list
        filters["page_obj"] = page_obj

    filters["tab_urls"] = {
        "suspects": "?" + _build_clean_query({
            "tab": "suspects",
            "q": filters["q"],
            "category": filters["category"],
            "sku_empty": filters["sku_empty"],
            "suggested_only": filters["suggested_only"],
            "multi_only": filters["multi_only"],
            "severity": filters["severity"],
            "issue_code": filters["issue_code"],
            "match_type": filters["match_type"],
        }),
        "stocks_without_price": "?" + _build_clean_query({
            "tab": "stocks_without_price",
            "q": filters["q"],
            "category": filters["category"],
            "sku_empty": filters["sku_empty"],
            "severity": filters["severity"],
            "issue_code": filters["issue_code"],
        }),
        "priceitems_without_stock": "?" + _build_clean_query({
            "tab": "priceitems_without_stock",
            "q": filters["q"],
            "category": filters["category"],
            "sku_empty": filters["sku_empty"],
            "severity": filters["severity"],
            "issue_code": filters["issue_code"],
        }),
    }

    return filters


def price_match_report(request):
    active_id, active_price_list = get_active_price_list(request)

    if not active_id or not active_price_list:
        return render(request, "reports/price_match_report.html", {
            "active_price_list": None,
            "counts_all": {
                "stocks_total": 0,
                "priceitems_total": 0,
                "stocks_without_price": 0,
                "priceitems_without_stock": 0,
                "suspects": 0,
            },
            "filtered_counts": {
                "stocks_without_price": 0,
                "priceitems_without_stock": 0,
                "suspects": 0,
            },
            "tab": (request.GET.get("tab") or "suspects"),
            "q": (request.GET.get("q") or ""),
            "category": (request.GET.get("category") or ""),
            "sku_empty": (request.GET.get("sku_empty") or "") == "1",
            "categories": [],
            "stocks_without_price": [],
            "priceitems_without_stock": [],
            "suspects": [],
            "all_groups": [],
            "current_url": request.path,
        })

    data = build_price_match_data(active_id)
    filters = apply_price_match_filters(request, data)
    filters = _paginate_price_match_lists(request, filters)
    metadata = get_price_match_metadata(active_id)
    quality_overview = build_data_quality_overview(active_id)

    return render(request, "reports/price_match_report.html", {
        "active_price_list": active_price_list,
        "counts_all": data["counts"],
        "filtered_counts": filters["filtered_counts"],
        "tab": filters["tab"],
        "q": filters["q"],
        "category": filters["category"],
        "sku_empty": filters["sku_empty"],
        "suggested_only": filters["suggested_only"],
        "multi_only": filters["multi_only"],
        "severity": filters["severity"],
        "issue_code": filters["issue_code"],
        "match_type": filters["match_type"],
        "current_url": filters["current_url"],
        "page_obj": filters["page_obj"],
        "page_query": filters["page_query"],
        "categories": metadata["categories"],
        "all_groups": metadata["all_groups"],
        "stocks_without_price": filters["stocks_without_price"],
        "priceitems_without_stock": filters["priceitems_without_stock"],
        "suspects": filters["suspects"],
        "quality_overview": quality_overview,
    })


def duplicate_sku_report(request):
    context = build_duplicate_sku_data()
    context["same_name_identity"] = build_same_name_identity_data()
    context["quality_overview"] = build_data_quality_overview()
    context = _filter_duplicate_report_rows(request, context)
    return render(request, "reports/duplicate_sku_report.html", context)


def stock_merge_assistant(request):
    left_id = request.GET.get("left") if request.method == "GET" else request.POST.get("left_id")
    right_id = request.GET.get("right") if request.method == "GET" else request.POST.get("right_id")
    active_id, active_price_list = get_active_price_list(request)

    try:
        preview = build_stock_merge_preview(left_id, right_id, active_price_list_id=active_id)
    except StockMergeError as exc:
        messages.warning(request, str(exc))
        return redirect("reports:duplicate_sku_report")

    if request.method == "POST":
        form = StockMergeAssistantForm(request.POST)
        if form.is_valid():
            try:
                result = apply_stock_merge(
                    left_id=form.cleaned_data["left_id"],
                    right_id=form.cleaned_data["right_id"],
                    survivor_side=form.cleaned_data["survivor_side"],
                    field_sources={
                        "name_source": form.cleaned_data["name_source"],
                        "sku_source": form.cleaned_data["sku_source"],
                        "category_source": form.cleaned_data["category_source"],
                        "subgroup_source": form.cleaned_data["subgroup_source"],
                        "unit_source": form.cleaned_data["unit_source"],
                    },
                )
            except StockMergeError as exc:
                form.add_error(None, str(exc))
            else:
                messages.success(
                    request,
                    f"Birleştirme tamamlandı. Kayıt #{result.removed_stock_id} kapatıldı ve hareketler #{result.surviving_stock.id} kaydına taşındı.",
                )
                return redirect("stock_edit", pk=result.surviving_stock.id)
    else:
        form = StockMergeAssistantForm(initial={
            "left_id": preview.left.id,
            "right_id": preview.right.id,
            "survivor_side": "left",
            "name_source": "left",
            "sku_source": "left",
            "category_source": "left",
            "subgroup_source": "left",
            "unit_source": "left",
        })

    return render(request, "reports/stock_merge_assistant.html", {
        "preview": preview,
        "form": form,
        "active_price_list": active_price_list,
    })


def same_name_conflict_detail(request):
    normalized_name = (request.GET.get("name") or "").strip()
    active_id, active_price_list = get_active_price_list(request)
    conflict = build_same_name_identity_detail(normalized_name, active_id)

    if conflict is None:
        messages.warning(request, "Geçerli bir aynı isim çatışması kaydı bulunamadı.")
        return redirect("reports:duplicate_sku_report")

    return render(request, "reports/same_name_conflict_detail.html", {
        "conflict": conflict,
        "active_price_list": active_price_list,
    })


@require_POST
def cleanup_duplicate_sku_report(request):
    target_sku = (request.POST.get("sku") or "").strip() or None
    result = cleanup_group_code_misuse_sku(target_sku=target_sku)

    if result["cleaned_groups"]:
        messages.success(
            request,
            f"Temizlik uygulandı. Grup={result['cleaned_groups']}, Kayıt={result['cleaned_rows']}, Atlanan={result['skipped_groups']}",
        )
    else:
        messages.warning(
            request,
            f"Temizlik uygulanmadı. Atlanan grup sayısı: {result['skipped_groups']}",
        )

    return redirect("reports:duplicate_sku_report")


def price_match_bulk_sku(request):
    if request.method != "POST":
        return redirect("/rapor/fiyat-eslesme/?tab=suspects")

    active_id, _active_price_list = get_active_price_list(request)
    if not active_id:
        messages.error(request, "Aktif fiyat listesi yok.")
        return redirect("/rapor/fiyat-eslesme/?tab=suspects")

    stock_ids = request.POST.getlist("stock_ids")
    overwrite = request.POST.get("overwrite") == "1"
    mode = (request.POST.get("mode") or "manual").strip()
    chosen_group = (request.POST.get("group") or "").strip()

    if not stock_ids:
        messages.warning(request, "Seçim yapmadın.")
        return redirect("/rapor/fiyat-eslesme/?tab=suspects")

    if mode == "manual" and not chosen_group:
        messages.warning(request, "Grup seçmedin.")
        return redirect("/rapor/fiyat-eslesme/?tab=suspects")

    result = apply_price_match_bulk_sku(
        active_price_list_id=active_id,
        stock_ids=stock_ids,
        overwrite=overwrite,
        mode=mode,
        chosen_group=chosen_group,
    )

    if mode == "manual":
        messages.success(
            request,
            f"{result['updated']} satır güncellendi. (Atlanan dolu SKU: {result['skipped_not_overwritten']})",
        )
    else:
        messages.success(
            request,
            f"{result['updated']} satırda önerilen SKU uygulandı. "
            f"(Çoklu öneri: {result['skipped_multi']}, öneri yok: {result['skipped_no_suggestion']}, atlanan dolu SKU: {result['skipped_not_overwritten']})",
        )

    next_url = request.POST.get("next") or "/rapor/fiyat-eslesme/?tab=suspects"
    if next_url.startswith("/"):
        return redirect(next_url)
    return redirect("/rapor/fiyat-eslesme/?tab=suspects")


def price_match_export(request):
    active_id, active_price_list = get_active_price_list(request)
    if not active_id or not active_price_list:
        messages.error(request, "Aktif fiyat listesi yok.")
        return redirect("/rapor/fiyat-eslesme/")

    data = build_price_match_data(active_id)
    filters = apply_price_match_filters(request, data)
    return build_price_match_export_response(active_price_list, data, filters)


def create_stock_from_price_match(request, item_id):
    active_id, active_price_list = get_active_price_list(request)
    if not active_id or not active_price_list:
        messages.error(request, "Aktif fiyat listesi yok.")
        return redirect("reports:price_match_report")

    price_item = get_object_or_404(PriceItem, id=item_id, price_list_id=active_id)
    price_list = get_object_or_404(PriceList, id=active_id)
    draft = build_stock_draft_from_price_item(price_item, price_list)
    edit_mode = (request.GET.get("edit") or "") == "1"

    if request.method == "POST":
        form = CreateStockFromPriceItemForm(request.POST)
        if form.is_valid():
            submitted_draft = build_stock_draft_from_form_data(price_item, form.cleaned_data)
            if submitted_draft.existing_stock is not None:
                explanation = build_duplicate_stock_explanation(submitted_draft)
                return render(request, "reports/create_stock_duplicate_explanation.html", {
                    "active_price_list": active_price_list,
                    "price_item": price_item,
                    "draft": submitted_draft,
                    "duplicate_explanation": explanation,
                    "edit_query": build_stock_create_edit_query(submitted_draft),
                })

            try:
                stock = create_stock_from_price_item_draft(submitted_draft)
            except ValueError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f"Stok kartı oluşturuldu: {stock.name}")
                return redirect("stock_edit", pk=stock.id)
    else:
        initial = {
            "name": request.GET.get("name", draft.name),
            "sku": request.GET.get("sku", draft.sku),
            "category": request.GET.get("category", draft.category),
            "unit": request.GET.get("unit", draft.unit),
            "quantity": request.GET.get("quantity", draft.quantity),
        }
        form = CreateStockFromPriceItemForm(initial=initial)

    duplicate_explanation = None
    edit_query = ""
    if draft.existing_stock is not None and not edit_mode:
        duplicate_explanation = build_duplicate_stock_explanation(draft)
        edit_query = build_stock_create_edit_query(draft)

    return render(request, "reports/create_stock_from_price_item.html", {
        "active_price_list": active_price_list,
        "price_item": price_item,
        "draft": draft,
        "form": form,
        "duplicate_explanation": duplicate_explanation,
        "edit_mode": edit_mode,
        "edit_query": edit_query,
    })


def price_list_compare(request):
    result = build_price_list_compare_context(
        base_id=request.GET.get("base"),
        new_id=request.GET.get("new"),
    )
    if result.warning:
        messages.warning(request, result.warning)
    return render(request, "reports/price_list_compare.html", result.context)


def price_list_compare_detail(request):
    result = build_price_list_compare_detail_context(
        base_id=request.GET.get("base"),
        new_id=request.GET.get("new"),
        name=request.GET.get("name"),
    )
    if result.error:
        messages.error(request, result.error)
        return redirect("reports:price_list_compare")
    return render(request, "reports/price_list_compare_detail.html", result.context)


def profile_cut_optimizer(request):
    result = None

    if request.method == "POST":
        form = ProfileCutOptimizationForm(request.POST)
        standard_length = None
        if form.is_valid():
            standard_length = form.cleaned_data["standard_length"]
        line_formset = CutDemandFormSet(
            request.POST,
            prefix="lines",
            standard_length=standard_length,
        )

        if form.is_valid() and line_formset.is_valid():
            result = build_multi_cut_plan(
                standard_length=form.cleaned_data["standard_length"],
                requests=line_formset.to_cut_requests(),
            )
    else:
        form = ProfileCutOptimizationForm(initial={
            "standard_length": 600,
        })
        line_formset = CutDemandFormSet(
            prefix="lines",
            initial=[{
                "cut_length": 142,
                "requested_quantity": 90,
            }],
        )

    return render(request, "reports/profile_cut_optimizer.html", {
        "form": form,
        "line_formset": line_formset,
        "result": result,
    })
