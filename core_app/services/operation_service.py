from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from core_app.models import PriceItem, PriceList, Stock, StockMovement, StockTransaction, StockTransactionDraft, StockTransactionLine
from core_app.services.price_match_helpers import build_price_item_lookup, resolve_price_item_for_stock
from core_app.services.stock_movement import create_stock_movement

CRITICAL_STOCK_THRESHOLD = 3


@dataclass
class OperationSubmitResult:
    transaction: StockTransaction
    movement_count: int


@dataclass
class OperationDeleteResult:
    transaction_number: str
    reversed_movement_count: int


@dataclass
class OperationDraftSaveResult:
    draft: StockTransactionDraft
    created: bool


def get_transaction_return_status(transaction: StockTransaction):
    line_ids = list(transaction.lines.values_list("id", flat=True))
    returned_quantities = {
        row["source_line"]: row["total_quantity"] or 0
        for row in (
            StockTransactionLine.objects.filter(
                source_line_id__in=line_ids,
                transaction__operation_type=StockTransaction.RETURN,
            )
            .values("source_line")
            .annotate(total_quantity=Sum("quantity"))
        )
    }

    remaining_by_line = {}
    fully_returned = True
    has_partial_return = False

    for line in transaction.lines.all():
        returned = int(returned_quantities.get(line.id, 0))
        remaining = max(int(line.quantity) - returned, 0)
        remaining_by_line[line.id] = remaining
        if remaining > 0:
            fully_returned = False
        if 0 < remaining < int(line.quantity):
            has_partial_return = True

    return {
        "can_return": transaction.operation_type == StockTransaction.SALE,
        "remaining_by_line": remaining_by_line,
        "fully_returned": bool(remaining_by_line) and fully_returned,
        "has_partial_return": has_partial_return,
    }


def build_operation_draft_from_transaction(transaction: StockTransaction, *, mode: str, line_ids=None, line_quantities=None):
    status = get_transaction_return_status(transaction)
    lines = list(transaction.lines.all())
    if line_ids is not None:
        selected_ids = {int(line_id) for line_id in line_ids}
        lines = [line for line in lines if line.id in selected_ids]

    if mode in {"return_all", "return_selected"}:
        if transaction.operation_type != StockTransaction.SALE:
            raise ValueError("İade yalnızca satış fişinden oluşturulabilir.")
        if status["fully_returned"]:
            raise ValueError("Bu satış fişinin iadesi zaten tamamen oluşturulmuş.")

    line_quantities = line_quantities or {}
    rows = []
    for line in lines:
        remaining_quantity = status["remaining_by_line"].get(line.id, int(line.quantity))
        if mode in {"return_all", "return_selected"} and remaining_quantity <= 0:
            continue

        quantity_for_row = remaining_quantity if mode in {"return_all", "return_selected"} else int(line.quantity)
        if mode == "return_selected":
            requested_quantity = line_quantities.get(line.id)
            if requested_quantity is not None:
                if requested_quantity <= 0:
                    continue
                if requested_quantity > remaining_quantity:
                    raise ValueError(f"'{line.stock_name}' satırı için en fazla {remaining_quantity} adet iade edebilirsin.")
                quantity_for_row = requested_quantity

        label_parts = [line.stock_name]
        if line.stock_sku:
            label_parts.append(line.stock_sku)
        elif line.stock_subgroup:
            label_parts.append(line.stock_subgroup)
        if line.stock_category:
            label_parts.append(line.stock_category)

        rows.append({
            "stock_id": str(line.stock_id or ""),
            "source_line_id": str(line.id) if mode in {"return_all", "return_selected"} else "",
            "product_label": " | ".join(label_parts),
            "description": line.description or "",
            "quantity": str(quantity_for_row),
            "unit": line.unit,
            "unit_price": f"{line.unit_price:.2f}",
        })

    if mode == "return_all":
        operation_type = StockTransaction.RETURN
        note = f"{transaction.display_number} fişinden tam iade"
    elif mode == "return_selected":
        operation_type = StockTransaction.RETURN
        note = f"{transaction.display_number} fişinden kısmi iade"
    elif mode == "copy_selected":
        operation_type = StockTransaction.SALE
        note = f"{transaction.display_number} fişinden seçili ürünler aktarıldı"
    else:
        operation_type = StockTransaction.SALE
        note = f"{transaction.display_number} fişi yeni satışa kopyalandı"

    source_transaction_id = transaction.id if operation_type == StockTransaction.RETURN else None

    return {
        "operation_type": operation_type,
        "customer_name": transaction.customer_name,
        "phone": transaction.phone,
        "note": note,
        "payment_type": "",
        "recipient_name": transaction.recipient_name,
        "vehicle_plate": transaction.vehicle_plate,
        "rows": rows,
        "source_transaction_id": source_transaction_id,
        "mode": mode,
    }


def validate_return_rows(source_transaction_id: int | None, rows: list[dict]):
    if not source_transaction_id:
        return None, rows

    source_transaction = StockTransaction.objects.prefetch_related("lines").filter(id=source_transaction_id).first()
    if source_transaction is None:
        raise ValueError("Kaynak satış fişi bulunamadı.")
    if source_transaction.operation_type != StockTransaction.SALE:
        raise ValueError("İade yalnızca satış fişinden başlatılabilir.")

    status = get_transaction_return_status(source_transaction)
    if status["fully_returned"]:
        raise ValueError("Bu satış fişinin iadesi zaten tamamen oluşturulmuş.")

    source_lines = {line.id: line for line in source_transaction.lines.all()}
    validated_rows = []
    for row in rows:
        source_line_id = row.get("source_line_id")
        if not source_line_id:
            raise ValueError("İade satırında kaynak fiş kalemi eksik.")
        source_line = source_lines.get(int(source_line_id))
        if source_line is None:
            raise ValueError("İade satırındaki kaynak kalem bulunamadı.")

        remaining_quantity = status["remaining_by_line"].get(source_line.id, 0)
        if remaining_quantity <= 0:
            raise ValueError(f"'{source_line.stock_name}' satırı için iade hakkı kalmadı.")
        if int(row["quantity"]) > remaining_quantity:
            raise ValueError(f"'{source_line.stock_name}' satırı için en fazla {remaining_quantity} adet iade edebilirsin.")

        validated_rows.append({**row, "source_line": source_line})

    if not validated_rows:
        raise ValueError("İade için kullanılabilir kalem bulunamadı.")

    return source_transaction, validated_rows


def _resolve_active_price_list(active_price_list_id):
    if not active_price_list_id:
        return None
    return PriceList.objects.filter(id=active_price_list_id).first()


def _build_price_maps(active_list):
    if not active_list:
        return {}, {}
    items = PriceItem.objects.filter(price_list=active_list).order_by("-id").values("name", "group", "price")
    return build_price_item_lookup(items)[:2]


def _format_catalog_label(stock: Stock):
    parts = [stock.name]
    if stock.sku:
        parts.append(stock.sku)
    elif stock.subgroup:
        parts.append(stock.subgroup)
    if stock.category:
        parts.append(stock.category)
    return " | ".join(parts)


def build_operation_line_warnings(stock_data: dict | None, *, quantity: int, unit: str, operation_type: str):
    if not stock_data:
        return []

    warnings = []
    selected_unit = (unit or "").strip() or "adet"
    stock_unit = (stock_data.get("unit") or "").strip() or "adet"
    stock_quantity = int(stock_data.get("quantity") or 0)

    if not stock_data.get("is_active", True):
        warnings.append({"level": "danger", "code": "inactive", "message": "Seçilen ürün pasif durumda."})

    if not stock_data.get("has_price", False):
        warnings.append({"level": "warning", "code": "missing_price", "message": "Aktif fiyat listesinde fiyat bulunamadı."})

    if stock_unit and selected_unit and selected_unit != stock_unit:
        warnings.append({
            "level": "warning",
            "code": "unit_mismatch",
            "message": f"Ürün birimi {stock_unit}, satır birimi {selected_unit}.",
        })

    if operation_type == StockTransaction.SALE:
        if quantity > stock_quantity:
            warnings.append({
                "level": "danger",
                "code": "insufficient_stock",
                "message": f"Mevcut stok yetersiz. Stok: {stock_quantity}, istenen: {quantity}.",
            })
        else:
            remaining = stock_quantity - quantity
            if remaining <= CRITICAL_STOCK_THRESHOLD:
                warnings.append({
                    "level": "warning",
                    "code": "critical_stock",
                    "message": f"Bu satış sonrası kalan stok kritik seviyeye düşecek: {remaining}.",
                })

    return warnings


def get_operation_home_data(active_price_list_id=None):
    active_list = _resolve_active_price_list(active_price_list_id)
    exact_price, name_only_price = _build_price_maps(active_list)

    stocks = list(Stock.objects.order_by("-is_active", "name", "sku", "id"))
    catalog = []
    for stock in stocks:
        price_item, _match_type = resolve_price_item_for_stock(stock, exact_price, name_only_price)
        unit_price = price_item.get("price") if price_item else Decimal("0.00")
        catalog.append({
            "id": stock.id,
            "label": _format_catalog_label(stock),
            "name": stock.name,
            "sku": stock.sku,
            "category": stock.category,
            "subgroup": stock.subgroup,
            "unit": stock.unit,
            "unit_label": stock.get_unit_display(),
            "quantity": stock.quantity,
            "is_active": stock.is_active,
            "has_price": price_item is not None,
            "unit_price": f"{Decimal(unit_price):.2f}",
        })

    recent_transactions = list(StockTransaction.objects.prefetch_related("lines").all()[:5])
    for transaction in recent_transactions:
        transaction.home_return_status = get_transaction_return_status(transaction)
    pending_drafts = list(StockTransactionDraft.objects.all()[:8])

    return {
        "active_price_list": active_list,
        "stock_catalog": catalog,
        "operation_warning_config": {
            "critical_stock_threshold": CRITICAL_STOCK_THRESHOLD,
        },
        "daily_operation_panel": get_daily_operation_panel(),
        "recent_transactions": recent_transactions,
        "pending_drafts": pending_drafts,
    }


def get_daily_operation_panel(today=None):
    today = today or timezone.localdate()
    today_transactions = StockTransaction.objects.filter(created_at__date=today)
    totals = today_transactions.aggregate(
        sale_total=Sum("total_amount", filter=Q(operation_type=StockTransaction.SALE)),
        return_total=Sum("total_amount", filter=Q(operation_type=StockTransaction.RETURN)),
    )
    sale_total = (totals["sale_total"] or Decimal("0.00")).quantize(Decimal("0.01"))
    return_total = (totals["return_total"] or Decimal("0.00")).quantize(Decimal("0.01"))

    recent_items = list(
        today_transactions.order_by("-created_at", "-id")[:5]
    )

    return {
        "today": today,
        "sale_total": sale_total,
        "return_total": return_total,
        "net_total": (sale_total - return_total).quantize(Decimal("0.01")),
        "transaction_count": today_transactions.count(),
        "recent_transactions": recent_items,
    }


def _serialize_draft_rows(rows: list[dict]) -> list[dict]:
    serialized = []
    for row in rows:
        stock = row["stock"]
        serialized.append({
            "stock_id": str(stock.id),
            "source_line_id": str(row.get("source_line_id") or (getattr(row.get("source_line"), "id", "") or "")),
            "product_label": _format_catalog_label(stock),
            "description": row.get("description", ""),
            "quantity": str(int(row["quantity"])),
            "unit": row["unit"],
            "unit_price": f"{row['unit_price'].quantize(Decimal('0.01')):.2f}",
        })
    return serialized


def save_operation_draft(
    *,
    operation_type: str,
    customer_name: str,
    phone: str,
    note: str,
    payment_type: str,
    recipient_name: str,
    vehicle_plate: str,
    rows: list[dict],
    source_transaction_id: int | None = None,
    draft_id: int | None = None,
) -> OperationDraftSaveResult:
    payload_rows = _serialize_draft_rows(rows)
    if draft_id:
        draft = StockTransactionDraft.objects.filter(id=draft_id).first()
    else:
        draft = None

    created = draft is None
    if draft is None:
        draft = StockTransactionDraft()

    draft.operation_type = operation_type
    draft.customer_name = (customer_name or "").strip()[:120]
    draft.phone = (phone or "").strip()[:40]
    draft.note = (note or "").strip()[:200]
    draft.payment_type = (payment_type or "").strip()[:20]
    draft.recipient_name = (recipient_name or "").strip()[:120]
    draft.vehicle_plate = (vehicle_plate or "").strip()[:40]
    draft.source_transaction_id = source_transaction_id
    draft.rows = payload_rows
    draft.save()
    return OperationDraftSaveResult(draft=draft, created=created)


def build_session_draft_from_saved_draft(draft: StockTransactionDraft) -> dict:
    return {
        "operation_type": draft.operation_type,
        "customer_name": draft.customer_name,
        "phone": draft.phone,
        "note": draft.note,
        "payment_type": draft.payment_type,
        "recipient_name": draft.recipient_name,
        "vehicle_plate": draft.vehicle_plate,
        "rows": draft.rows,
        "source_transaction_id": draft.source_transaction_id or "",
        "saved_draft_id": draft.id,
    }


@transaction.atomic
def delete_stock_transaction(transaction_id: int) -> OperationDeleteResult:
    operation = (
        StockTransaction.objects.select_for_update()
        .prefetch_related("lines__stock", "derived_transactions")
        .filter(id=transaction_id)
        .first()
    )
    if operation is None:
        raise ValueError("Silinecek fiş bulunamadı.")

    if operation.operation_type == StockTransaction.SALE and operation.derived_transactions.filter(
        operation_type=StockTransaction.RETURN
    ).exists():
        raise ValueError("Bu satış fişine bağlı iade kayıtları var. Önce iadeleri silmelisin.")

    reverse_movement_type = StockMovement.IN if operation.operation_type == StockTransaction.SALE else StockMovement.OUT
    reverse_label = "Fiş silme geri alma"
    reversed_movement_count = 0

    for line in operation.lines.all():
        if not line.stock_id:
            continue
        note = f"{reverse_label} {operation.display_number}"
        if line.description:
            note = f"{note} | {line.description}"
        create_stock_movement(
            stock_id=line.stock_id,
            movement_type=reverse_movement_type,
            quantity=int(line.quantity),
            note=note,
        )
        reversed_movement_count += 1

    transaction_number = operation.display_number
    operation.delete()
    return OperationDeleteResult(
        transaction_number=transaction_number,
        reversed_movement_count=reversed_movement_count,
    )


@transaction.atomic
def submit_stock_operation(
    *,
    operation_type: str,
    customer_name: str,
    phone: str,
    note: str,
    payment_type: str,
    recipient_name: str,
    vehicle_plate: str,
    rows: list[dict],
    source_transaction: StockTransaction | None = None,
) -> OperationSubmitResult:
    total_quantity = sum(int(row["quantity"]) for row in rows)
    total_amount = sum((row["unit_price"] * row["quantity"] for row in rows), Decimal("0.00"))

    operation = StockTransaction.objects.create(
        operation_type=operation_type,
        source_transaction=source_transaction if operation_type == StockTransaction.RETURN else None,
        customer_name=(customer_name or "").strip()[:120],
        phone=(phone or "").strip()[:40],
        note=(note or "").strip()[:200],
        payment_type=(payment_type or "").strip()[:20],
        recipient_name=(recipient_name or "").strip()[:120],
        vehicle_plate=(vehicle_plate or "").strip()[:40],
        total_quantity=total_quantity,
        total_amount=total_amount.quantize(Decimal("0.01")),
    )

    movement_type = StockMovement.OUT if operation_type == StockTransaction.SALE else StockMovement.IN
    movement_label = operation.get_operation_type_display()
    movement_count = 0

    for row in rows:
        stock = row["stock"]
        quantity = int(row["quantity"])
        unit_price = row["unit_price"].quantize(Decimal("0.01"))
        description = (row.get("description") or "").strip()
        line_total = (unit_price * quantity).quantize(Decimal("0.01"))

        movement_note = f"{movement_label} fişi {operation.display_number}"
        if description:
            movement_note = f"{movement_note} | {description}"

        create_stock_movement(
            stock_id=stock.id,
            movement_type=movement_type,
            quantity=quantity,
            note=movement_note,
        )

        StockTransactionLine.objects.create(
            transaction=operation,
            source_line=row.get("source_line") if operation_type == StockTransaction.RETURN else None,
            stock=stock,
            stock_name=stock.name,
            stock_sku=stock.sku,
            stock_category=stock.category,
            stock_subgroup=stock.subgroup,
            description=description,
            quantity=quantity,
            unit=row["unit"],
            unit_price=unit_price,
            line_total=line_total,
        )
        movement_count += 1

    return OperationSubmitResult(transaction=operation, movement_count=movement_count)
