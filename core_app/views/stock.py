from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.templatetags.static import static
from django.utils import timezone
from django.views.decorators.http import require_POST

from core_app.models import Stock, StockMergeAudit, StockTransaction, StockTransactionDraft
from core_app.operation_forms import StockOperationForm
from core_app.services.operation_service import (
    build_operation_draft_from_transaction,
    build_session_draft_from_saved_draft,
    delete_stock_transaction,
    get_operation_home_data,
    get_transaction_return_status,
    save_operation_draft,
    submit_stock_operation,
    validate_return_rows,
)
from core_app.services.bulk_entry_service import build_bulk_entry_preview
from core_app.services.stock_identity import create_or_merge_stock
from core_app.services.stock_movement import (
    InsufficientStockError,
    InvalidStockMovementError,
    create_stock_movement,
)
from core_app.services.stock_service import (
    get_category_detail_data,
    get_category_list_data,
    get_category_sku_data,
    get_home_stats,
    get_stock_list_data,
    get_stock_movement_data,
)
from core_app.stock_forms import StockForm, StockMovementForm

OPERATION_PRINT_LOGO_PATH = "core_app/img/company-logo.svg"
OPERATION_PRINT_BUSINESS_NAME = "ERP Panel"


def _build_operation_rows_for_display(form=None, draft=None):
    if form is not None and form.is_bound:
        return form.get_rows_for_display()
    if draft and draft.get("rows"):
        return draft["rows"]
    return [{
        "stock_id": "",
        "source_line_id": "",
        "product_label": "",
        "description": "",
        "quantity": "1",
        "unit": "adet",
        "unit_price": "0.00",
    }]


def _build_operation_print_context(transaction: StockTransaction, *, template_type: str):
    is_return = transaction.operation_type == StockTransaction.RETURN
    title = "İade Fişi" if is_return else "Satış Fişi"
    if template_type == "delivery":
        title = "A4 Teslim Formu"

    return {
        "transaction": transaction,
        "print_title": title,
        "print_template_type": template_type,
        "is_return": is_return,
        "business_name": OPERATION_PRINT_BUSINESS_NAME,
        "logo_url": static(OPERATION_PRINT_LOGO_PATH),
        "show_logo": True,
        "line_count": transaction.lines.count(),
    }


def home(request):
    operation_data = get_operation_home_data(request.session.get("active_price_list_id"))
    stock_queryset = Stock.objects.order_by("-is_active", "name", "sku", "id")
    draft = request.session.pop("operation_draft", None) if request.method == "GET" else None

    if request.method == "POST":
        form = StockOperationForm(request.POST, stock_queryset=stock_queryset)
        if form.is_valid():
            try:
                submit_action = (request.POST.get("submit_action") or "save_operation").strip()
                source_transaction = None
                rows = form.cleaned_data["rows"]
                source_transaction_id = request.POST.get("source_transaction_id")
                saved_draft_id = request.POST.get("saved_draft_id")
                if form.cleaned_data["operation_type"] == StockTransaction.RETURN:
                    source_transaction, rows = validate_return_rows(
                        int(source_transaction_id) if source_transaction_id else None,
                        rows,
                    )
                if submit_action in {"save_draft", "suspend_draft"}:
                    draft_result = save_operation_draft(
                        operation_type=form.cleaned_data["operation_type"],
                        customer_name=form.cleaned_data.get("customer_name", ""),
                        phone=form.cleaned_data.get("phone", ""),
                        note=form.cleaned_data.get("note", ""),
                        payment_type=form.cleaned_data.get("payment_type", ""),
                        recipient_name=form.cleaned_data.get("recipient_name", ""),
                        vehicle_plate=form.cleaned_data.get("vehicle_plate", ""),
                        rows=rows,
                        source_transaction_id=int(source_transaction_id) if source_transaction_id else None,
                        draft_id=int(saved_draft_id) if saved_draft_id else None,
                    )
                    action_label = "Taslak kaydedildi" if submit_action == "save_draft" else "Fiş askıya alındı"
                    messages.success(
                        request,
                        f"{action_label}. Bekleyen fiş: TASLAK-{draft_result.draft.id:04d}",
                    )
                    return redirect("home")
                result = submit_stock_operation(
                    operation_type=form.cleaned_data["operation_type"],
                    customer_name=form.cleaned_data.get("customer_name", ""),
                    phone=form.cleaned_data.get("phone", ""),
                    note=form.cleaned_data.get("note", ""),
                    payment_type=form.cleaned_data.get("payment_type", ""),
                    recipient_name=form.cleaned_data.get("recipient_name", ""),
                    vehicle_plate=form.cleaned_data.get("vehicle_plate", ""),
                    rows=rows,
                    source_transaction=source_transaction,
                )
            except (InsufficientStockError, InvalidStockMovementError, ValueError) as exc:
                form.add_error(None, str(exc))
            else:
                if saved_draft_id:
                    StockTransactionDraft.objects.filter(id=saved_draft_id).delete()
                messages.success(
                    request,
                    f"{result.transaction.get_operation_type_display()} işlemi kaydedildi. "
                    f"Fiş No: {result.transaction.display_number}, Kalem: {result.movement_count}",
                )
                return redirect("home")
    else:
        form = StockOperationForm(
            stock_queryset=stock_queryset,
            initial={
                "operation_type": (draft or {}).get("operation_type", "sale"),
                "customer_name": (draft or {}).get("customer_name", ""),
                "phone": (draft or {}).get("phone", ""),
                "note": (draft or {}).get("note", ""),
                "payment_type": (draft or {}).get("payment_type", ""),
                "recipient_name": (draft or {}).get("recipient_name", ""),
                "vehicle_plate": (draft or {}).get("vehicle_plate", ""),
            },
        )

    context = {
        **get_home_stats(),
        **operation_data,
        "operation_form": form,
        "operation_rows": _build_operation_rows_for_display(form, draft=draft),
        "source_transaction_id": (draft or {}).get("source_transaction_id") or "",
        "saved_draft_id": (draft or {}).get("saved_draft_id", ""),
        "operation_logo_url": static(OPERATION_PRINT_LOGO_PATH),
        "unit_choices": Stock.UNIT_CHOICES,
        "today": timezone.localdate(),
    }
    return render(request, "core_app/home.html", context)


def operation_detail(request, pk):
    transaction = get_object_or_404(
        StockTransaction.objects.prefetch_related("lines__stock"),
        pk=pk,
    )
    return_status = get_transaction_return_status(transaction)
    line_rows = [
        {
            "line": line,
            "remaining_return_quantity": return_status["remaining_by_line"].get(line.id, 0),
        }
        for line in transaction.lines.all()
    ]
    return render(request, "core_app/operation_detail.html", {
        "transaction": transaction,
        "return_status": return_status,
        "line_rows": line_rows,
    })


def operation_print_receipt(request, pk):
    transaction = get_object_or_404(
        StockTransaction.objects.select_related("source_transaction").prefetch_related("lines"),
        pk=pk,
    )
    template_name = (
        "core_app/print/operation_return_receipt.html"
        if transaction.operation_type == StockTransaction.RETURN
        else "core_app/print/operation_sale_receipt.html"
    )
    return render(
        request,
        template_name,
        _build_operation_print_context(transaction, template_type="receipt"),
    )


def operation_print_delivery_form(request, pk):
    transaction = get_object_or_404(
        StockTransaction.objects.select_related("source_transaction").prefetch_related("lines"),
        pk=pk,
    )
    return render(
        request,
        "core_app/print/operation_delivery_form.html",
        _build_operation_print_context(transaction, template_type="delivery"),
    )


@require_POST
def operation_bulk_preview(request):
    operation_type = (request.POST.get("operation_type") or StockTransaction.SALE).strip()
    if operation_type != StockTransaction.SALE:
        return JsonResponse({
            "rows": [],
            "summary": {
                "total": 0,
                "matched": 0,
                "suggested": 0,
                "unmatched": 0,
            },
            "message": "Toplu giriş ilk sürümde yalnızca satış modunda kullanılır.",
        })
    operation_data = get_operation_home_data(request.session.get("active_price_list_id"))
    preview = build_bulk_entry_preview(request.POST.get("bulk_text", ""), operation_data["stock_catalog"])
    return JsonResponse(preview)


@require_POST
def operation_delete(request, pk):
    try:
        result = delete_stock_transaction(pk)
    except (InsufficientStockError, InvalidStockMovementError, ValueError) as exc:
        messages.warning(request, str(exc))
    else:
        messages.success(
            request,
            f"{result.transaction_number} fişi silindi. {result.reversed_movement_count} stok hareketi güvenli şekilde geri alındı.",
        )
    return redirect(request.POST.get("next") or "home")


@require_POST
def operation_draft_open(request, pk):
    draft = get_object_or_404(StockTransactionDraft, pk=pk)
    request.session["operation_draft"] = build_session_draft_from_saved_draft(draft)
    messages.success(request, f"TASLAK-{draft.id:04d} açıldı. Kaldığın yerden devam edebilirsin.")
    return redirect("home")


@require_POST
def operation_draft_delete(request, pk):
    draft = get_object_or_404(StockTransactionDraft, pk=pk)
    draft_label = f"TASLAK-{draft.id:04d}"
    draft.delete()
    messages.success(request, f"{draft_label} silindi.")
    return redirect(request.POST.get("next") or "home")


@require_POST
def operation_start_from_receipt(request, pk):
    transaction = get_object_or_404(
        StockTransaction.objects.prefetch_related("lines"),
        pk=pk,
    )
    action = (request.POST.get("action") or "").strip()
    selected_line_ids = request.POST.getlist("line_ids")
    selected_line_quantities = {}

    if action == "return_selected":
        for line_id in selected_line_ids:
            quantity_raw = (request.POST.get(f"return_quantity_{line_id}") or "").strip()
            if not quantity_raw:
                continue
            try:
                selected_line_quantities[int(line_id)] = int(quantity_raw)
            except ValueError:
                messages.warning(request, "Kısmi iade miktarı sayı olmalıdır.")
                return redirect("operation_detail", pk=pk)

    if action in {"return_selected", "copy_selected"} and not selected_line_ids:
        messages.warning(request, "Seçili satırlardan işlem başlatmak için en az bir kalem seç.")
        return redirect("operation_detail", pk=pk)

    mode_map = {
        "copy_sale": "copy_sale",
        "return_all": "return_all",
        "return_selected": "return_selected",
        "copy_selected": "copy_selected",
    }
    mode = mode_map.get(action)
    if mode is None:
        messages.warning(request, "Geçersiz fiş işlemi seçildi.")
        return redirect("operation_detail", pk=pk)

    try:
        draft = build_operation_draft_from_transaction(
            transaction,
            mode=mode,
            line_ids=selected_line_ids if action in {"return_selected", "copy_selected"} else None,
            line_quantities=selected_line_quantities if action == "return_selected" else None,
        )
    except ValueError as exc:
        messages.warning(request, str(exc))
        return redirect("operation_detail", pk=pk)

    if not draft["rows"]:
        messages.warning(request, "Aktarılacak uygun fiş kalemi bulunamadı.")
        return redirect("operation_detail", pk=pk)

    request.session["operation_draft"] = draft
    messages.success(request, "Fiş kalemleri ana ekrana aktarıldı. Düzenleyip kaydedebilirsin.")
    return redirect("home")


def stock_list(request):
    if request.method == "POST":
        form = StockForm(request.POST)
        if form.is_valid():
            create_or_merge_stock(
                name=(form.cleaned_data.get("name") or "").strip(),
                category=(form.cleaned_data.get("category") or "").strip(),
                subgroup=(form.cleaned_data.get("subgroup") or "").strip(),
                unit=form.cleaned_data.get("unit") or "adet",
                sku=(form.cleaned_data.get("sku") or "").strip(),
                quantity=int(form.cleaned_data.get("quantity") or 0),
            )
            return redirect("stock_list")
    else:
        form = StockForm()

    q = (request.GET.get("q") or "").strip()
    category = (request.GET.get("category") or "").strip()
    unit = (request.GET.get("unit") or "").strip()
    sku = (request.GET.get("sku") or "").strip()
    list_data = get_stock_list_data(
        q=q,
        category=category,
        unit=unit,
        sku=sku,
        sort=request.GET.get("sort") or "created_at",
        order=request.GET.get("order") or "desc",
        active_price_list_id=request.session.get("active_price_list_id"),
    )

    context = {
        "form": form,
        "q": q,
        "category": category,
        "unit": unit,
        "sku": sku,
        "current_url": request.get_full_path(),
    }
    context.update(list_data)
    return render(request, "core_app/stock_list.html", context)


def stock_bulk_delete(request):
    if request.method != "POST":
        return redirect("stock_list")

    stock_ids = request.POST.getlist("stock_ids")
    if not stock_ids:
        messages.warning(request, "Toplu silme için en az bir ürün seç.")
        return redirect(request.POST.get("next") or "stock_list")

    deleted_count, _detail = Stock.objects.filter(id__in=stock_ids).delete()
    messages.success(request, f"{deleted_count} ürün toplu olarak silindi.")
    return redirect(request.POST.get("next") or "stock_list")


def stock_delete(request, pk):
    stock = get_object_or_404(Stock, pk=pk)
    if request.method == "POST":
        stock.delete()
    return redirect("stock_list")


def stock_edit(request, pk):
    stock = get_object_or_404(Stock, pk=pk)
    if request.method == "POST":
        form = StockForm(request.POST, instance=stock)
        if form.is_valid():
            form.save()
            return redirect("stock_list")
    else:
        form = StockForm(instance=stock)

    merge_audits = StockMergeAudit.objects.filter(surviving_stock=stock)[:5]
    return render(request, "core_app/stock_edit.html", {"form": form, "stock": stock, "merge_audits": merge_audits})


def stock_movement(request, pk):
    stock = get_object_or_404(Stock, pk=pk)
    if request.method == "POST":
        form = StockMovementForm(request.POST)
        if form.is_valid():
            try:
                result = create_stock_movement(
                    stock_id=stock.id,
                    movement_type=form.cleaned_data["movement_type"],
                    quantity=form.cleaned_data["quantity"],
                    note=form.cleaned_data.get("note", "") or "",
                )
                stock = result.stock
                return redirect("stock_movement", pk=stock.id)
            except InsufficientStockError as exc:
                form.add_error("quantity", str(exc))
    else:
        form = StockMovementForm()

    context = get_stock_movement_data(stock)
    context["form"] = form
    return render(request, "core_app/stock_movement.html", context)


def category_list(request):
    return render(request, "core_app/category_list.html", get_category_list_data())


def category_detail(request, category):
    subgroup_filter = (request.GET.get("subgroup") or "").strip()
    context = get_category_detail_data(category, subgroup_filter=subgroup_filter)
    context["current_url"] = request.get_full_path()
    return render(request, "core_app/category_detail.html", context)


def category_bulk_subgroup(request, category):
    if request.method != "POST":
        return redirect("category_detail", category=category)

    stock_ids = request.POST.getlist("stock_ids")
    subgroup_new = (request.POST.get("subgroup_new") or "").strip()
    subgroup_sel = (request.POST.get("subgroup") or "").strip()
    subgroup = subgroup_new or subgroup_sel

    if not stock_ids:
        messages.warning(request, "Seçim yapmadın.")
        return redirect(request.POST.get("next") or reverse("category_detail", args=[category]))
    if not subgroup:
        messages.warning(request, "Alt grup seçmedin (veya yeni alt grup yazmadın).")
        return redirect(request.POST.get("next") or reverse("category_detail", args=[category]))

    subgroup_value = "" if subgroup == "__EMPTY__" else subgroup[:80]
    stocks = list(Stock.objects.filter(id__in=stock_ids, category__iexact=category))
    updated = 0

    for stock in stocks:
        if stock.subgroup == subgroup_value:
            continue
        stock.subgroup = subgroup_value
        stock.save(update_fields=["subgroup", "identity_key", "normalized_name", "updated_at"])
        updated += 1

    if subgroup_value:
        messages.success(request, f"{updated} ürün '{subgroup_value}' alt grubuna alındı.")
    else:
        messages.success(request, f"{updated} ürünün alt grubu temizlendi (Diğer/boş).")

    return redirect(request.POST.get("next") or reverse("category_detail", args=[category]))


def category_sku(request, category):
    context = get_category_sku_data(
        category,
        sku_filter=(request.GET.get("sku") or "").strip(),
        sku_empty=(request.GET.get("sku_empty") or "") == "1",
    )
    return render(request, "core_app/category_sku.html", context)
