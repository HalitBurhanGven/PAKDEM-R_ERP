from unittest.mock import MagicMock, patch

from django.test import TestCase

from core_app.models import Stock, StockMovement
from core_app.services.stock_movement import InsufficientStockError, create_stock_movement


class StockMovementServiceTests(TestCase):
    def test_in_movement_increases_quantity_and_creates_row(self):
        stock = Stock.objects.create(name="Vida", quantity=5, unit="adet")

        result = create_stock_movement(
            stock_id=stock.id,
            movement_type=StockMovement.IN,
            quantity=3,
            note="giris",
        )

        stock.refresh_from_db()
        self.assertEqual(stock.quantity, 8)
        self.assertEqual(result.movement.stock_id, stock.id)
        self.assertEqual(result.movement.note, "giris")

    def test_out_movement_decreases_quantity_and_creates_row(self):
        stock = Stock.objects.create(name="Somun", quantity=9, unit="adet")

        create_stock_movement(
            stock_id=stock.id,
            movement_type=StockMovement.OUT,
            quantity=4,
            note="cikis",
        )

        stock.refresh_from_db()
        self.assertEqual(stock.quantity, 5)
        self.assertEqual(StockMovement.objects.filter(stock=stock).count(), 1)

    def test_out_movement_raises_when_stock_is_insufficient(self):
        stock = Stock.objects.create(name="Pul", quantity=2, unit="adet")

        with self.assertRaises(InsufficientStockError):
            create_stock_movement(
                stock_id=stock.id,
                movement_type=StockMovement.OUT,
                quantity=3,
                note="fazla cikis",
            )

        stock.refresh_from_db()
        self.assertEqual(stock.quantity, 2)
        self.assertEqual(StockMovement.objects.filter(stock=stock).count(), 0)

    def test_repeated_out_movements_do_not_allow_negative_balance(self):
        stock = Stock.objects.create(name="Pul", quantity=5, unit="adet")

        create_stock_movement(
            stock_id=stock.id,
            movement_type=StockMovement.OUT,
            quantity=3,
            note="ilk cikis",
        )

        with self.assertRaises(InsufficientStockError):
            create_stock_movement(
                stock_id=stock.id,
                movement_type=StockMovement.OUT,
                quantity=3,
                note="ikinci cikis",
            )

        stock.refresh_from_db()
        self.assertEqual(stock.quantity, 2)
        self.assertEqual(StockMovement.objects.filter(stock=stock).count(), 1)

    @patch("core_app.services.stock_movement.StockMovement.objects.create", side_effect=RuntimeError("db write failed"))
    def test_stock_quantity_rolls_back_when_movement_row_creation_fails(self, movement_create_mock):
        stock = Stock.objects.create(name="Rondela", quantity=10, unit="adet")

        with self.assertRaises(RuntimeError):
            create_stock_movement(
                stock_id=stock.id,
                movement_type=StockMovement.OUT,
                quantity=4,
                note="rollback",
            )

        stock.refresh_from_db()
        self.assertEqual(stock.quantity, 10)
        self.assertEqual(StockMovement.objects.filter(stock=stock).count(), 0)
        movement_create_mock.assert_called_once()

    @patch("core_app.services.stock_movement.StockMovement.objects.create")
    @patch("core_app.services.stock_movement.Stock.objects")
    def test_service_uses_select_for_update(self, stock_objects_mock, movement_create_mock):
        locked_stock = MagicMock()
        locked_stock.id = 99
        locked_stock.quantity = 10
        locked_stock.save = MagicMock()

        select_for_update_qs = MagicMock()
        select_for_update_qs.get.return_value = locked_stock
        stock_objects_mock.select_for_update.return_value = select_for_update_qs

        movement_create_mock.return_value = MagicMock(stock=locked_stock)

        create_stock_movement(
            stock_id=99,
            movement_type=StockMovement.OUT,
            quantity=4,
            note="locked update",
        )

        stock_objects_mock.select_for_update.assert_called_once()
        select_for_update_qs.get.assert_called_once_with(pk=99)
