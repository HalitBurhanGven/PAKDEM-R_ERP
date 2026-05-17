from dataclasses import dataclass

from django.db import transaction

from core_app.models import Stock, StockMovement


class InsufficientStockError(ValueError):
    pass


class InvalidStockMovementError(ValueError):
    pass


@dataclass
class StockMovementResult:
    stock: Stock
    movement: StockMovement


def _calculate_new_quantity(stock: Stock, movement_type: str, quantity: int) -> int:
    if quantity <= 0:
        raise InvalidStockMovementError("Hareket miktarı sıfırdan büyük olmalıdır.")

    if movement_type == StockMovement.IN:
        return stock.quantity + quantity

    if movement_type == StockMovement.OUT:
        new_quantity = stock.quantity - quantity
        if new_quantity < 0:
            raise InsufficientStockError("Cikis miktari mevcut stoktan buyuk olamaz.")
        return new_quantity

    raise InvalidStockMovementError("Gecersiz stok hareket tipi.")


@transaction.atomic
def create_stock_movement(stock_id: int, movement_type: str, quantity: int, note: str = "") -> StockMovementResult:
    stock = Stock.objects.select_for_update().get(pk=stock_id)
    note = (note or "").strip()
    stock.quantity = _calculate_new_quantity(stock, movement_type, quantity)

    stock.save(update_fields=["quantity", "updated_at"])
    movement = StockMovement.objects.create(
        stock=stock,
        movement_type=movement_type,
        quantity=quantity,
        note=note,
    )
    return StockMovementResult(stock=stock, movement=movement)
