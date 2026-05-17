from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core_app.models import PriceItem, PriceList, Stock, StockMovement, StockTransaction, StockTransactionDraft
from core_app.services.operation_service import build_operation_line_warnings, get_daily_operation_panel


class OperationHomeTests(TestCase):
    def setUp(self):
        self.stock_a = Stock.objects.create(name="Çelik Vida", sku="VDA-01", quantity=20, unit="adet", category="HIRDAVAT")
        self.stock_b = Stock.objects.create(name="22'lik Menteşe", sku="MNT-22", quantity=15, unit="adet", category="HIRDAVAT")
        self.price_list = PriceList.objects.create(title="Perakende", sheet_name="HIRDAVAT")
        PriceItem.objects.create(price_list=self.price_list, name="Çelik Vida", group="VDA-01", price="12.50")
        PriceItem.objects.create(price_list=self.price_list, name="22'lik Menteşe", group="MNT-22", price="6.00")

        session = self.client.session
        session["active_price_list_id"] = self.price_list.id
        session.save()

    def test_home_get_shows_active_price_catalog(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Satış ve İade İşlem Ekranı")
        self.assertEqual(response.context["active_price_list"].id, self.price_list.id)
        catalog = response.context["stock_catalog"]
        self.assertTrue(any(item["id"] == self.stock_a.id and item["unit_price"] == "12.50" for item in catalog))

    def test_multi_line_sale_updates_stock_and_creates_transaction(self):
        response = self.client.post(reverse("home"), {
            "operation_type": "sale",
            "note": "Kasadan satış",
            "stock_id": [str(self.stock_a.id), str(self.stock_b.id)],
            "product_label": ["Çelik Vida | VDA-01 | HIRDAVAT", "22'lik Menteşe | MNT-22 | HIRDAVAT"],
            "line_description": ["Kasa önü", ""],
            "line_quantity": ["2", "3"],
            "line_unit": ["adet", "adet"],
            "line_unit_price": ["12.50", "6.00"],
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))

        self.stock_a.refresh_from_db()
        self.stock_b.refresh_from_db()
        self.assertEqual(self.stock_a.quantity, 18)
        self.assertEqual(self.stock_b.quantity, 12)

        txn = StockTransaction.objects.get()
        self.assertEqual(txn.operation_type, StockTransaction.SALE)
        self.assertEqual(txn.total_quantity, 5)
        self.assertEqual(str(txn.total_amount), "43.00")
        self.assertEqual(txn.lines.count(), 2)
        self.assertEqual(StockMovement.objects.filter(movement_type=StockMovement.OUT).count(), 2)

    def test_return_increases_stock(self):
        response = self.client.post(reverse("home"), {
            "operation_type": "return",
            "note": "Müşteri iadesi",
            "stock_id": [str(self.stock_a.id)],
            "product_label": ["Çelik Vida | VDA-01 | HIRDAVAT"],
            "line_description": [""],
            "line_quantity": ["4"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })

        self.assertEqual(response.status_code, 302)
        self.stock_a.refresh_from_db()
        self.assertEqual(self.stock_a.quantity, 24)
        self.assertEqual(StockTransaction.objects.get().operation_type, StockTransaction.RETURN)
        self.assertEqual(StockMovement.objects.get().movement_type, StockMovement.IN)

    def test_recent_transactions_show_note_or_content(self):
        response = self.client.post(reverse("home"), {
            "operation_type": "sale",
            "note": "Kasaya gelen müşteri siparişi",
            "stock_id": [str(self.stock_a.id)],
            "product_label": ["Çelik Vida | VDA-01 | HIRDAVAT"],
            "line_description": [""],
            "line_quantity": ["2"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })

        self.assertEqual(response.status_code, 302)
        home_response = self.client.get(reverse("home"))
        self.assertContains(home_response, "Kasaya gelen müşteri siparişi")
        transaction = StockTransaction.objects.get()
        self.assertContains(home_response, reverse("operation_detail", args=[transaction.id]))

    def test_operation_detail_shows_full_receipt_information(self):
        response = self.client.post(reverse("home"), {
            "operation_type": "sale",
            "note": "Detaylı fiş notu",
            "stock_id": [str(self.stock_a.id), str(self.stock_b.id)],
            "product_label": ["Çelik Vida | VDA-01 | HIRDAVAT", "22'lik Menteşe | MNT-22 | HIRDAVAT"],
            "line_description": ["Kasa önü", "Sağ kapı"],
            "line_quantity": ["2", "3"],
            "line_unit": ["adet", "adet"],
            "line_unit_price": ["12.50", "6.00"],
        })

        self.assertEqual(response.status_code, 302)
        transaction = StockTransaction.objects.get()

        detail_response = self.client.get(reverse("operation_detail", args=[transaction.id]))

        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, transaction.display_number)
        self.assertContains(detail_response, "Detaylı fiş notu")
        self.assertContains(detail_response, "Çelik Vida")
        self.assertContains(detail_response, "22&#x27;lik Menteşe")
        self.assertContains(detail_response, "Kasa önü")
        self.assertContains(detail_response, "Sağ kapı")
        self.assertContains(detail_response, "Stok kartı mevcut")
        self.assertContains(detail_response, "Güncel stok:")
        self.assertNotContains(detail_response, reverse("stock_edit", args=[self.stock_a.id]))
        self.assertNotContains(detail_response, reverse("stock_movement", args=[self.stock_a.id]))
        self.assertContains(detail_response, "Seçilenlerden İade Oluştur")
        self.assertContains(detail_response, "İade Et")
        self.assertContains(detail_response, f"return_quantity_{transaction.lines.first().id}")

    def test_receipt_can_start_new_sale_with_prefilled_rows(self):
        self.client.post(reverse("home"), {
            "operation_type": "sale",
            "note": "Önceki satış",
            "stock_id": [str(self.stock_a.id), str(self.stock_b.id)],
            "product_label": ["Çelik Vida | VDA-01 | HIRDAVAT", "22'lik Menteşe | MNT-22 | HIRDAVAT"],
            "line_description": ["Kasa önü", ""],
            "line_quantity": ["2", "3"],
            "line_unit": ["adet", "adet"],
            "line_unit_price": ["12.50", "6.00"],
        })
        transaction = StockTransaction.objects.latest("id")

        response = self.client.post(
            reverse("operation_start_from_receipt", args=[transaction.id]),
            {"action": "copy_sale"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, transaction.display_number)
        self.assertContains(response, 'value="2"')
        self.assertContains(response, 'value="3"')
        self.assertContains(response, "Çelik Vida | VDA-01 | HIRDAVAT")
        self.assertEqual(response.context["source_transaction_id"], "")

    def test_receipt_copy_sale_creates_new_transaction_only_after_save(self):
        self.client.post(reverse("home"), {
            "operation_type": "sale",
            "note": "Referans satış",
            "stock_id": [str(self.stock_a.id), str(self.stock_b.id)],
            "product_label": ["Çelik Vida | VDA-01 | HIRDAVAT", "22'lik Menteşe | MNT-22 | HIRDAVAT"],
            "line_description": ["Kasa önü", ""],
            "line_quantity": ["2", "3"],
            "line_unit": ["adet", "adet"],
            "line_unit_price": ["12.50", "6.00"],
        })
        source_transaction = StockTransaction.objects.latest("id")
        source_line_ids = list(source_transaction.lines.values_list("id", flat=True))
        movement_count_before_copy = StockMovement.objects.count()
        stock_a_before_copy = Stock.objects.get(id=self.stock_a.id).quantity
        stock_b_before_copy = Stock.objects.get(id=self.stock_b.id).quantity

        draft_response = self.client.post(
            reverse("operation_start_from_receipt", args=[source_transaction.id]),
            {"action": "copy_sale"},
            follow=True,
        )

        self.assertEqual(draft_response.status_code, 200)
        self.assertEqual(StockTransaction.objects.count(), 1)
        self.assertEqual(StockMovement.objects.count(), movement_count_before_copy)
        self.assertEqual(Stock.objects.get(id=self.stock_a.id).quantity, stock_a_before_copy)
        self.assertEqual(Stock.objects.get(id=self.stock_b.id).quantity, stock_b_before_copy)
        self.assertEqual(draft_response.context["source_transaction_id"], "")

        save_response = self.client.post(reverse("home"), {
            "submit_action": "save_operation",
            "operation_type": "sale",
            "note": "Kopyadan yeni satış",
            "source_transaction_id": "",
            "stock_id": [str(self.stock_a.id), str(self.stock_b.id)],
            "source_line_id": ["", ""],
            "product_label": ["Çelik Vida | VDA-01 | HIRDAVAT", "22'lik Menteşe | MNT-22 | HIRDAVAT"],
            "line_description": ["Kasa önü", ""],
            "line_quantity": ["2", "3"],
            "line_unit": ["adet", "adet"],
            "line_unit_price": ["12.50", "6.00"],
        })

        self.assertEqual(save_response.status_code, 302)
        self.assertEqual(StockTransaction.objects.count(), 2)

        new_transaction = StockTransaction.objects.latest("id")
        self.assertNotEqual(new_transaction.id, source_transaction.id)
        self.assertEqual(new_transaction.operation_type, StockTransaction.SALE)
        self.assertIsNone(new_transaction.source_transaction)
        self.assertEqual(list(source_transaction.lines.values_list("id", flat=True)), source_line_ids)
        self.assertEqual(source_transaction.note, "Referans satış")

        self.stock_a.refresh_from_db()
        self.stock_b.refresh_from_db()
        self.assertEqual(self.stock_a.quantity, stock_a_before_copy - 2)
        self.assertEqual(self.stock_b.quantity, stock_b_before_copy - 3)
        self.assertEqual(StockMovement.objects.count(), movement_count_before_copy + 2)

    def test_receipt_can_start_partial_return_from_selected_lines(self):
        self.client.post(reverse("home"), {
            "operation_type": "sale",
            "note": "Kısmi iade denemesi",
            "stock_id": [str(self.stock_a.id), str(self.stock_b.id)],
            "product_label": ["Çelik Vida | VDA-01 | HIRDAVAT", "22'lik Menteşe | MNT-22 | HIRDAVAT"],
            "line_description": ["Kasa önü", "Sağ kapı"],
            "line_quantity": ["2", "3"],
            "line_unit": ["adet", "adet"],
            "line_unit_price": ["12.50", "6.00"],
        })
        transaction = StockTransaction.objects.latest("id")
        selected_line = transaction.lines.first()

        response = self.client.post(
            reverse("operation_start_from_receipt", args=[transaction.id]),
            {
                "action": "return_selected",
                "line_ids": [str(selected_line.id)],
                f"return_quantity_{selected_line.id}": "1",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["operation_rows"][0]["stock_id"], str(selected_line.stock_id))
        self.assertEqual(len(response.context["operation_rows"]), 1)
        self.assertContains(response, "kısmi iade")
        self.assertContains(response, selected_line.stock_name)
        self.assertEqual(response.context["operation_rows"][0]["quantity"], "1")

    def test_receipt_can_start_return_with_prefilled_rows_and_save(self):
        self.client.post(reverse("home"), {
            "operation_type": "sale",
            "note": "İadeye kaynak satış",
            "stock_id": [str(self.stock_a.id), str(self.stock_b.id)],
            "product_label": ["Çelik Vida | VDA-01 | HIRDAVAT", "22'lik Menteşe | MNT-22 | HIRDAVAT"],
            "line_description": ["Kasa önü", "Sağ kapı"],
            "line_quantity": ["2", "3"],
            "line_unit": ["adet", "adet"],
            "line_unit_price": ["12.50", "6.00"],
        })
        sale_transaction = StockTransaction.objects.filter(operation_type=StockTransaction.SALE).latest("id")
        sale_line_a, sale_line_b = list(sale_transaction.lines.all())
        movement_count_before_start = StockMovement.objects.count()
        stock_a_before_start = Stock.objects.get(id=self.stock_a.id).quantity
        stock_b_before_start = Stock.objects.get(id=self.stock_b.id).quantity

        start_response = self.client.post(
            reverse("operation_start_from_receipt", args=[sale_transaction.id]),
            {"action": "return_all"},
            follow=True,
        )

        self.assertEqual(start_response.status_code, 200)
        self.assertEqual(start_response.context["source_transaction_id"], sale_transaction.id)
        self.assertEqual(start_response.context["operation_form"].initial["operation_type"], "return")
        self.assertEqual(start_response.context["operation_rows"][0]["source_line_id"], str(sale_line_a.id))
        self.assertEqual(start_response.context["operation_rows"][1]["source_line_id"], str(sale_line_b.id))
        self.assertEqual(start_response.context["operation_rows"][0]["quantity"], "2")
        self.assertEqual(start_response.context["operation_rows"][1]["quantity"], "3")
        self.assertEqual(StockTransaction.objects.filter(operation_type=StockTransaction.RETURN).count(), 0)
        self.assertEqual(StockMovement.objects.count(), movement_count_before_start)
        self.assertEqual(Stock.objects.get(id=self.stock_a.id).quantity, stock_a_before_start)
        self.assertEqual(Stock.objects.get(id=self.stock_b.id).quantity, stock_b_before_start)

        save_response = self.client.post(reverse("home"), {
            "submit_action": "save_operation",
            "operation_type": "return",
            "note": f"{sale_transaction.display_number} fişinden tam iade",
            "source_transaction_id": str(sale_transaction.id),
            "stock_id": [str(self.stock_a.id), str(self.stock_b.id)],
            "source_line_id": [str(sale_line_a.id), str(sale_line_b.id)],
            "product_label": ["Çelik Vida | VDA-01 | HIRDAVAT", "22'lik Menteşe | MNT-22 | HIRDAVAT"],
            "line_description": ["Kasa önü", "Sağ kapı"],
            "line_quantity": ["2", "3"],
            "line_unit": ["adet", "adet"],
            "line_unit_price": ["12.50", "6.00"],
        })

        self.assertEqual(save_response.status_code, 302)
        self.assertEqual(StockTransaction.objects.filter(operation_type=StockTransaction.RETURN).count(), 1)

        return_transaction = StockTransaction.objects.filter(operation_type=StockTransaction.RETURN).latest("id")
        self.assertEqual(return_transaction.source_transaction_id, sale_transaction.id)
        self.assertEqual(return_transaction.lines.count(), 2)
        self.assertEqual(return_transaction.lines.first().source_line_id, sale_line_a.id)
        self.assertEqual(return_transaction.lines.last().source_line_id, sale_line_b.id)
        self.assertEqual(sale_transaction.note, "İadeye kaynak satış")

        self.stock_a.refresh_from_db()
        self.stock_b.refresh_from_db()
        self.assertEqual(self.stock_a.quantity, stock_a_before_start + 2)
        self.assertEqual(self.stock_b.quantity, stock_b_before_start + 3)
        self.assertEqual(StockMovement.objects.filter(movement_type=StockMovement.IN).count(), 2)

    def test_receipt_partial_return_rejects_quantity_over_remaining(self):
        self.client.post(reverse("home"), {
            "operation_type": "sale",
            "note": "Fazla iade denemesi",
            "stock_id": [str(self.stock_a.id)],
            "product_label": ["Çelik Vida | VDA-01 | HIRDAVAT"],
            "line_description": [""],
            "line_quantity": ["2"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })
        transaction = StockTransaction.objects.latest("id")
        selected_line = transaction.lines.first()

        response = self.client.post(
            reverse("operation_start_from_receipt", args=[transaction.id]),
            {
                "action": "return_selected",
                "line_ids": [str(selected_line.id)],
                f"return_quantity_{selected_line.id}": "5",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "en fazla 2 adet iade edebilirsin")

    def test_partial_return_start_only_includes_selected_lines(self):
        stock_c = Stock.objects.create(name="Kapı Kolu", sku="KPK-01", quantity=8, unit="adet", category="HIRDAVAT")

        self.client.post(reverse("home"), {
            "operation_type": "sale",
            "note": "Çok satırlı satış",
            "stock_id": [str(self.stock_a.id), str(self.stock_b.id), str(stock_c.id)],
            "product_label": [
                "Çelik Vida | VDA-01 | HIRDAVAT",
                "22'lik Menteşe | MNT-22 | HIRDAVAT",
                "Kapı Kolu | KPK-01 | HIRDAVAT",
            ],
            "line_description": ["Vida", "Menteşe", "Kol"],
            "line_quantity": ["10", "6", "2"],
            "line_unit": ["adet", "adet", "adet"],
            "line_unit_price": ["12.50", "6.00", "20.00"],
        })
        transaction = StockTransaction.objects.latest("id")
        line_a, line_b, line_c = list(transaction.lines.all())

        response = self.client.post(
            reverse("operation_start_from_receipt", args=[transaction.id]),
            {
                "action": "return_selected",
                "line_ids": [str(line_b.id), str(line_c.id)],
                f"return_quantity_{line_b.id}": "6",
                f"return_quantity_{line_c.id}": "2",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["operation_form"].initial["operation_type"], "return")
        self.assertEqual(response.context["source_transaction_id"], transaction.id)
        self.assertEqual(len(response.context["operation_rows"]), 2)
        returned_source_ids = {row["source_line_id"] for row in response.context["operation_rows"]}
        returned_labels = {row["product_label"] for row in response.context["operation_rows"]}
        self.assertEqual(returned_source_ids, {str(line_b.id), str(line_c.id)})
        self.assertNotIn(str(line_a.id), returned_source_ids)
        self.assertIn("22'lik Menteşe | MNT-22 | HIRDAVAT", returned_labels)
        self.assertIn("Kapı Kolu | KPK-01 | HIRDAVAT", returned_labels)
        self.assertNotContains(response, 'name="source_line_id" value="%s"' % line_a.id)

    def test_partial_return_selected_lines_create_return_only_after_save(self):
        stock_c = Stock.objects.create(name="Kapı Kolu", sku="KPK-01", quantity=8, unit="adet", category="HIRDAVAT")

        self.client.post(reverse("home"), {
            "operation_type": "sale",
            "note": "Kısmi iade kaynağı",
            "stock_id": [str(self.stock_a.id), str(self.stock_b.id), str(stock_c.id)],
            "product_label": [
                "Çelik Vida | VDA-01 | HIRDAVAT",
                "22'lik Menteşe | MNT-22 | HIRDAVAT",
                "Kapı Kolu | KPK-01 | HIRDAVAT",
            ],
            "line_description": ["Vida", "Menteşe", "Kol"],
            "line_quantity": ["10", "6", "2"],
            "line_unit": ["adet", "adet", "adet"],
            "line_unit_price": ["12.50", "6.00", "20.00"],
        })
        sale_transaction = StockTransaction.objects.filter(operation_type=StockTransaction.SALE).latest("id")
        line_a, line_b, line_c = list(sale_transaction.lines.all())
        movement_count_before_start = StockMovement.objects.count()
        stock_a_before_start = Stock.objects.get(id=self.stock_a.id).quantity
        stock_b_before_start = Stock.objects.get(id=self.stock_b.id).quantity
        stock_c_before_start = Stock.objects.get(id=stock_c.id).quantity

        start_response = self.client.post(
            reverse("operation_start_from_receipt", args=[sale_transaction.id]),
            {
                "action": "return_selected",
                "line_ids": [str(line_b.id), str(line_c.id)],
                f"return_quantity_{line_b.id}": "4",
                f"return_quantity_{line_c.id}": "1",
            },
            follow=True,
        )

        self.assertEqual(start_response.status_code, 200)
        self.assertEqual(StockTransaction.objects.filter(operation_type=StockTransaction.RETURN).count(), 0)
        self.assertEqual(StockMovement.objects.count(), movement_count_before_start)
        self.assertEqual(Stock.objects.get(id=self.stock_a.id).quantity, stock_a_before_start)
        self.assertEqual(Stock.objects.get(id=self.stock_b.id).quantity, stock_b_before_start)
        self.assertEqual(Stock.objects.get(id=stock_c.id).quantity, stock_c_before_start)
        self.assertEqual(len(start_response.context["operation_rows"]), 2)

        save_response = self.client.post(reverse("home"), {
            "submit_action": "save_operation",
            "operation_type": "return",
            "note": f"{sale_transaction.display_number} fişinden kısmi iade",
            "source_transaction_id": str(sale_transaction.id),
            "stock_id": [str(self.stock_b.id), str(stock_c.id)],
            "source_line_id": [str(line_b.id), str(line_c.id)],
            "product_label": [
                "22'lik Menteşe | MNT-22 | HIRDAVAT",
                "Kapı Kolu | KPK-01 | HIRDAVAT",
            ],
            "line_description": ["Menteşe", "Kol"],
            "line_quantity": ["4", "1"],
            "line_unit": ["adet", "adet"],
            "line_unit_price": ["6.00", "20.00"],
        })

        self.assertEqual(save_response.status_code, 302)
        self.assertEqual(StockTransaction.objects.filter(operation_type=StockTransaction.RETURN).count(), 1)

        return_transaction = StockTransaction.objects.filter(operation_type=StockTransaction.RETURN).latest("id")
        self.assertEqual(return_transaction.source_transaction_id, sale_transaction.id)
        self.assertEqual(return_transaction.lines.count(), 2)
        self.assertEqual(
            {line.source_line_id for line in return_transaction.lines.all()},
            {line_b.id, line_c.id},
        )
        self.assertNotIn(line_a.id, {line.source_line_id for line in return_transaction.lines.all()})
        self.assertEqual(sale_transaction.lines.count(), 3)

        self.stock_a.refresh_from_db()
        self.stock_b.refresh_from_db()
        stock_c.refresh_from_db()
        self.assertEqual(self.stock_a.quantity, stock_a_before_start)
        self.assertEqual(self.stock_b.quantity, stock_b_before_start + 4)
        self.assertEqual(stock_c.quantity, stock_c_before_start + 1)
        self.assertEqual(StockMovement.objects.filter(movement_type=StockMovement.IN).count(), 2)

    def test_return_submit_rejects_quantity_over_sold_amount(self):
        self.client.post(reverse("home"), {
            "operation_type": "sale",
            "note": "5 adet satıldı",
            "stock_id": [str(self.stock_a.id)],
            "product_label": ["Çelik Vida | VDA-01 | HIRDAVAT"],
            "line_description": [""],
            "line_quantity": ["5"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })
        sale_transaction = StockTransaction.objects.filter(operation_type=StockTransaction.SALE).latest("id")
        sale_line = sale_transaction.lines.first()
        stock_before_return = Stock.objects.get(id=self.stock_a.id).quantity
        movement_count_before_return = StockMovement.objects.count()

        response = self.client.post(reverse("home"), {
            "submit_action": "save_operation",
            "operation_type": "return",
            "note": f"{sale_transaction.display_number} fişinden fazla iade",
            "source_transaction_id": str(sale_transaction.id),
            "stock_id": [str(self.stock_a.id)],
            "source_line_id": [str(sale_line.id)],
            "product_label": ["Çelik Vida | VDA-01 | HIRDAVAT"],
            "line_description": [""],
            "line_quantity": ["6"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "en fazla 5 adet iade edebilirsin")
        self.assertEqual(StockTransaction.objects.filter(operation_type=StockTransaction.RETURN).count(), 0)
        self.assertEqual(StockMovement.objects.count(), movement_count_before_return)
        self.stock_a.refresh_from_db()
        self.assertEqual(self.stock_a.quantity, stock_before_return)

    def test_second_return_submit_rejects_quantity_over_remaining(self):
        self.client.post(reverse("home"), {
            "operation_type": "sale",
            "note": "10 adet satış",
            "stock_id": [str(self.stock_a.id)],
            "product_label": ["Çelik Vida | VDA-01 | HIRDAVAT"],
            "line_description": [""],
            "line_quantity": ["10"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })
        sale_transaction = StockTransaction.objects.filter(operation_type=StockTransaction.SALE).latest("id")
        sale_line = sale_transaction.lines.first()

        first_return = self.client.post(reverse("home"), {
            "submit_action": "save_operation",
            "operation_type": "return",
            "note": f"{sale_transaction.display_number} fişinden ilk iade",
            "source_transaction_id": str(sale_transaction.id),
            "stock_id": [str(self.stock_a.id)],
            "source_line_id": [str(sale_line.id)],
            "product_label": ["Çelik Vida | VDA-01 | HIRDAVAT"],
            "line_description": [""],
            "line_quantity": ["4"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })

        self.assertEqual(first_return.status_code, 302)

        stock_before_second_attempt = Stock.objects.get(id=self.stock_a.id).quantity
        movement_count_before_second_attempt = StockMovement.objects.count()

        second_attempt = self.client.post(reverse("home"), {
            "submit_action": "save_operation",
            "operation_type": "return",
            "note": f"{sale_transaction.display_number} fişinden ikinci iade",
            "source_transaction_id": str(sale_transaction.id),
            "stock_id": [str(self.stock_a.id)],
            "source_line_id": [str(sale_line.id)],
            "product_label": ["Çelik Vida | VDA-01 | HIRDAVAT"],
            "line_description": [""],
            "line_quantity": ["7"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })

        self.assertEqual(second_attempt.status_code, 200)
        self.assertContains(second_attempt, "en fazla 6 adet iade edebilirsin")
        self.assertEqual(StockTransaction.objects.filter(operation_type=StockTransaction.RETURN).count(), 1)
        self.assertEqual(StockMovement.objects.count(), movement_count_before_second_attempt)
        self.stock_a.refresh_from_db()
        self.assertEqual(self.stock_a.quantity, stock_before_second_attempt)

    def test_receipt_selected_actions_require_line_selection(self):
        self.client.post(reverse("home"), {
            "operation_type": "sale",
            "note": "Seçimsiz deneme",
            "stock_id": [str(self.stock_a.id)],
            "product_label": ["Çelik Vida | VDA-01 | HIRDAVAT"],
            "line_description": [""],
            "line_quantity": ["2"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })
        transaction = StockTransaction.objects.latest("id")

        response = self.client.post(
            reverse("operation_start_from_receipt", args=[transaction.id]),
            {"action": "return_selected"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "en az bir kalem seç")

    def test_sale_prevents_negative_stock(self):
        response = self.client.post(reverse("home"), {
            "operation_type": "sale",
            "note": "",
            "stock_id": [str(self.stock_a.id)],
            "product_label": ["Çelik Vida | VDA-01 | HIRDAVAT"],
            "line_description": [""],
            "line_quantity": ["999"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cikis miktari mevcut stoktan buyuk olamaz.")
        self.stock_a.refresh_from_db()
        self.assertEqual(self.stock_a.quantity, 20)
        self.assertEqual(StockTransaction.objects.count(), 0)

    def test_full_return_cannot_be_started_twice_from_same_receipt(self):
        self.client.post(reverse("home"), {
            "operation_type": "sale",
            "note": "Tam iade testi",
            "stock_id": [str(self.stock_a.id)],
            "product_label": ["Ã‡elik Vida | VDA-01 | HIRDAVAT"],
            "line_description": [""],
            "line_quantity": ["2"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })
        sale_transaction = StockTransaction.objects.filter(operation_type=StockTransaction.SALE).latest("id")
        source_line = sale_transaction.lines.first()

        first_draft = self.client.post(
            reverse("operation_start_from_receipt", args=[sale_transaction.id]),
            {"action": "return_all"},
            follow=True,
        )

        self.assertEqual(first_draft.status_code, 200)

        save_response = self.client.post(reverse("home"), {
            "operation_type": "return",
            "note": f"{sale_transaction.display_number} fiÅŸinden tam iade",
            "source_transaction_id": str(sale_transaction.id),
            "stock_id": [str(self.stock_a.id)],
            "source_line_id": [str(source_line.id)],
            "product_label": ["Ã‡elik Vida | VDA-01 | HIRDAVAT"],
            "line_description": [""],
            "line_quantity": ["2"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })

        self.assertEqual(save_response.status_code, 302)
        self.assertEqual(StockTransaction.objects.filter(operation_type=StockTransaction.RETURN).count(), 1)

        second_attempt = self.client.post(
            reverse("operation_start_from_receipt", args=[sale_transaction.id]),
            {"action": "return_all"},
            follow=True,
        )

        self.assertEqual(second_attempt.status_code, 200)
        self.assertEqual(StockTransaction.objects.filter(operation_type=StockTransaction.RETURN).count(), 1)
        self.assertContains(second_attempt, "Bu fişin tam iadesi zaten oluşturulmuş")

    def test_operation_detail_shows_return_state_after_full_return(self):
        self.client.post(reverse("home"), {
            "operation_type": "sale",
            "note": "Detay iade durumu",
            "stock_id": [str(self.stock_a.id)],
            "product_label": ["Ã‡elik Vida | VDA-01 | HIRDAVAT"],
            "line_description": [""],
            "line_quantity": ["2"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })
        sale_transaction = StockTransaction.objects.filter(operation_type=StockTransaction.SALE).latest("id")
        source_line = sale_transaction.lines.first()

        self.client.post(reverse("home"), {
            "operation_type": "return",
            "note": f"{sale_transaction.display_number} fiÅŸinden tam iade",
            "source_transaction_id": str(sale_transaction.id),
            "stock_id": [str(self.stock_a.id)],
            "source_line_id": [str(source_line.id)],
            "product_label": ["Ã‡elik Vida | VDA-01 | HIRDAVAT"],
            "line_description": [""],
            "line_quantity": ["2"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })

        response = self.client.get(reverse("operation_detail", args=[sale_transaction.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bu satış fişinin iadesi tamamen oluşturulmuş")
        self.assertContains(response, "Kalan iade: 0")
        self.assertContains(response, "Bu fişin tam iadesi zaten oluşturulmuş")

    def test_recent_receipt_can_be_deleted_and_stock_is_reverted(self):
        self.client.post(reverse("home"), {
            "operation_type": "sale",
            "note": "Silinecek satış",
            "stock_id": [str(self.stock_a.id)],
            "product_label": ["Ã‡elik Vida | VDA-01 | HIRDAVAT"],
            "line_description": [""],
            "line_quantity": ["3"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })
        sale_transaction = StockTransaction.objects.filter(operation_type=StockTransaction.SALE).latest("id")

        self.stock_a.refresh_from_db()
        self.assertEqual(self.stock_a.quantity, 17)

        response = self.client.post(
            reverse("operation_delete", args=[sale_transaction.id]),
            {"next": reverse("home")},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "fişi silindi")
        self.assertFalse(StockTransaction.objects.filter(id=sale_transaction.id).exists())
        self.stock_a.refresh_from_db()
        self.assertEqual(self.stock_a.quantity, 20)

    def test_sale_with_related_return_cannot_be_deleted(self):
        self.client.post(reverse("home"), {
            "operation_type": "sale",
            "note": "İadeli satış",
            "stock_id": [str(self.stock_a.id)],
            "product_label": ["Ã‡elik Vida | VDA-01 | HIRDAVAT"],
            "line_description": [""],
            "line_quantity": ["2"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })
        sale_transaction = StockTransaction.objects.filter(operation_type=StockTransaction.SALE).latest("id")
        source_line = sale_transaction.lines.first()

        self.client.post(reverse("home"), {
            "operation_type": "return",
            "note": f"{sale_transaction.display_number} fiÅŸinden tam iade",
            "source_transaction_id": str(sale_transaction.id),
            "stock_id": [str(self.stock_a.id)],
            "source_line_id": [str(source_line.id)],
            "product_label": ["Ã‡elik Vida | VDA-01 | HIRDAVAT"],
            "line_description": [""],
            "line_quantity": ["2"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })

        response = self.client.post(
            reverse("operation_delete", args=[sale_transaction.id]),
            {"next": reverse("home")},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Önce iadeleri silmelisin")
        self.assertTrue(StockTransaction.objects.filter(id=sale_transaction.id).exists())

    def test_operation_can_be_saved_as_draft_without_stock_change(self):
        response = self.client.post(reverse("home"), {
            "submit_action": "save_draft",
            "operation_type": "sale",
            "note": "Bekleyen müşteri fişi",
            "stock_id": [str(self.stock_a.id), str(self.stock_b.id)],
            "source_line_id": ["", ""],
            "product_label": ["Çelik Vida | VDA-01 | HIRDAVAT", "22'lik Menteşe | MNT-22 | HIRDAVAT"],
            "line_description": ["", ""],
            "line_quantity": ["2", "1"],
            "line_unit": ["adet", "adet"],
            "line_unit_price": ["12.50", "6.00"],
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(StockTransaction.objects.count(), 0)
        self.assertEqual(StockTransactionDraft.objects.count(), 1)
        self.stock_a.refresh_from_db()
        self.assertEqual(self.stock_a.quantity, 20)
        self.assertContains(response, "Taslak kaydedildi")
        self.assertContains(response, "3 adet | 31.00")

    def test_return_operation_can_be_saved_as_draft_without_stock_change(self):
        response = self.client.post(reverse("home"), {
            "submit_action": "save_draft",
            "operation_type": "return",
            "note": "Müşteri sonra dönecek",
            "stock_id": [str(self.stock_a.id)],
            "source_line_id": [""],
            "product_label": ["Çelik Vida | VDA-01 | HIRDAVAT"],
            "line_description": [""],
            "line_quantity": ["4"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(StockTransaction.objects.count(), 0)
        self.assertEqual(StockTransactionDraft.objects.count(), 1)
        self.assertEqual(StockTransactionDraft.objects.get().operation_type, StockTransaction.RETURN)
        self.assertEqual(StockMovement.objects.count(), 0)
        self.stock_a.refresh_from_db()
        self.assertEqual(self.stock_a.quantity, 20)
        self.assertContains(response, "Müşteri sonra dönecek")

    def test_opened_draft_can_be_updated_without_creating_new_draft(self):
        draft = StockTransactionDraft.objects.create(
            operation_type=StockTransaction.SALE,
            note="Kasada bekliyor",
            rows=[
                {
                    "stock_id": str(self.stock_a.id),
                    "source_line_id": "",
                    "product_label": "Çelik Vida | VDA-01 | HIRDAVAT",
                    "description": "",
                    "quantity": "2",
                    "unit": "adet",
                    "unit_price": "12.50",
                }
            ],
        )

        self.client.post(reverse("operation_draft_open", args=[draft.id]), follow=True)
        response = self.client.post(reverse("home"), {
            "submit_action": "save_draft",
            "operation_type": "sale",
            "note": "Kasada güncellendi",
            "saved_draft_id": str(draft.id),
            "source_transaction_id": "",
            "stock_id": [str(self.stock_a.id), str(self.stock_b.id)],
            "source_line_id": ["", ""],
            "product_label": ["Çelik Vida | VDA-01 | HIRDAVAT", "22'lik Menteşe | MNT-22 | HIRDAVAT"],
            "line_description": ["", ""],
            "line_quantity": ["2", "1"],
            "line_unit": ["adet", "adet"],
            "line_unit_price": ["12.50", "6.00"],
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(StockTransactionDraft.objects.count(), 1)
        draft.refresh_from_db()
        self.assertEqual(draft.note, "Kasada güncellendi")
        self.assertEqual(len(draft.rows), 2)
        self.assertEqual(StockTransaction.objects.count(), 0)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_drafts_do_not_appear_in_recent_completed_transactions(self):
        StockTransactionDraft.objects.create(
            operation_type=StockTransaction.SALE,
            note="Bekleyen müşteri fişi",
            rows=[
                {
                    "stock_id": str(self.stock_a.id),
                    "source_line_id": "",
                    "product_label": "Çelik Vida | VDA-01 | HIRDAVAT",
                    "description": "",
                    "quantity": "2",
                    "unit": "adet",
                    "unit_price": "12.50",
                }
            ],
        )

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bekleyen müşteri fişi")
        self.assertContains(response, "Henüz işlem yok.")

    def test_saved_draft_can_be_opened_on_home(self):
        draft = StockTransactionDraft.objects.create(
            operation_type=StockTransaction.RETURN,
            note="Sonra devam et",
            rows=[
                {
                    "stock_id": str(self.stock_a.id),
                    "source_line_id": "",
                    "product_label": "Çelik Vida | VDA-01 | HIRDAVAT",
                    "description": "",
                    "quantity": "2",
                    "unit": "adet",
                    "unit_price": "12.50",
                }
            ],
        )

        response = self.client.post(
            reverse("operation_draft_open", args=[draft.id]),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sonra devam et")
        self.assertEqual(response.context["saved_draft_id"], draft.id)
        self.assertEqual(response.context["operation_rows"][0]["stock_id"], str(self.stock_a.id))

    def test_completed_sale_card_shows_operational_actions(self):
        self.client.post(reverse("home"), {
            "operation_type": "sale",
            "note": "Operasyon kartı satışı",
            "stock_id": [str(self.stock_a.id)],
            "product_label": ["Çelik Vida | VDA-01 | HIRDAVAT"],
            "line_description": [""],
            "line_quantity": ["2"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })
        transaction = StockTransaction.objects.get()

        response = self.client.get(reverse("home"))

        self.assertContains(response, "Detayı Aç")
        self.assertContains(response, "Yeni Satış Olarak Kopyala")
        self.assertContains(response, "Bu Fişten İade Oluştur")
        self.assertContains(response, reverse("operation_start_from_receipt", args=[transaction.id]))

    def test_completed_return_card_hides_sale_only_actions(self):
        self.client.post(reverse("home"), {
            "operation_type": "return",
            "note": "İade kartı",
            "stock_id": [str(self.stock_a.id)],
            "product_label": ["Çelik Vida | VDA-01 | HIRDAVAT"],
            "line_description": [""],
            "line_quantity": ["2"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })

        response = self.client.get(reverse("home"))

        self.assertContains(response, "Detayı Aç")
        self.assertNotContains(response, "Yeni Satış Olarak Kopyala")
        self.assertNotContains(response, "Bu Fişten İade Oluştur")

    def test_draft_card_shows_continue_actions_only(self):
        draft = StockTransactionDraft.objects.create(
            operation_type=StockTransaction.SALE,
            note="Kasada devam edecek",
            rows=[
                {
                    "stock_id": str(self.stock_a.id),
                    "source_line_id": "",
                    "product_label": "Ã‡elik Vida | VDA-01 | HIRDAVAT",
                    "description": "",
                    "quantity": "2",
                    "unit": "adet",
                    "unit_price": "12.50",
                }
            ],
        )

        response = self.client.get(reverse("home"))

        self.assertContains(response, "Kasada devam edecek")
        self.assertContains(response, reverse("operation_draft_open", args=[draft.id]))
        self.assertContains(response, reverse("operation_draft_delete", args=[draft.id]))
        self.assertNotContains(response, "Bu Fişten İade Oluştur")

    def test_home_shows_keyboard_shortcut_help_and_targets(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Klavye Kısayolları")
        self.assertContains(response, "F2")
        self.assertContains(response, "F3")
        self.assertContains(response, "F4")
        self.assertContains(response, "F5")
        self.assertContains(response, "Ctrl+Z")
        self.assertContains(response, 'id="operation-type-sale"')
        self.assertContains(response, 'id="operation-type-return"')
        self.assertContains(response, 'id="submit-operation-btn"')
        self.assertContains(response, 'id="operation-form"')
        self.assertContains(response, 'class="product-label-input"')

    def test_home_shows_row_copy_and_duplicate_actions(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Kopyala")
        self.assertContains(response, "Altına")
        self.assertContains(response, 'class="row-copy-btn"')
        self.assertContains(response, 'class="row-duplicate-btn"')

    def test_sale_submit_with_duplicated_rows_parses_successfully(self):
        response = self.client.post(reverse("home"), {
            "operation_type": "sale",
            "note": "Çoğaltılmış satırlar",
            "stock_id": [str(self.stock_a.id), str(self.stock_a.id)],
            "source_line_id": ["", ""],
            "product_label": ["Çelik Vida | VDA-01 | HIRDAVAT", "Çelik Vida | VDA-01 | HIRDAVAT"],
            "line_description": ["İlk satır", "İlk satır"],
            "line_quantity": ["10", "6"],
            "line_unit": ["adet", "adet"],
            "line_unit_price": ["12.50", "12.50"],
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(StockTransaction.objects.count(), 1)
        transaction = StockTransaction.objects.get()
        self.assertEqual(transaction.lines.count(), 2)
        self.assertEqual(transaction.total_quantity, 16)
        self.assertEqual(str(transaction.total_amount), "200.00")
        self.stock_a.refresh_from_db()
        self.assertEqual(self.stock_a.quantity, 4)

    def test_draft_save_with_repeated_rows_remains_reopenable(self):
        response = self.client.post(reverse("home"), {
            "submit_action": "save_draft",
            "operation_type": "sale",
            "note": "Tekrarlı taslak",
            "stock_id": [str(self.stock_a.id), str(self.stock_a.id)],
            "source_line_id": ["", ""],
            "product_label": ["Çelik Vida | VDA-01 | HIRDAVAT", "Çelik Vida | VDA-01 | HIRDAVAT"],
            "line_description": ["İlk satır", "İkinci satır"],
            "line_quantity": ["3", "5"],
            "line_unit": ["adet", "adet"],
            "line_unit_price": ["12.50", "12.50"],
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        draft = StockTransactionDraft.objects.get()
        reopen_response = self.client.post(reverse("operation_draft_open", args=[draft.id]), follow=True)

        self.assertEqual(reopen_response.status_code, 200)
        self.assertEqual(len(reopen_response.context["operation_rows"]), 2)
        self.assertEqual(reopen_response.context["operation_rows"][0]["quantity"], "3")
        self.assertEqual(reopen_response.context["operation_rows"][1]["quantity"], "5")

    def test_completed_operation_removes_loaded_draft(self):
        draft = StockTransactionDraft.objects.create(
            operation_type=StockTransaction.SALE,
            note="Kasada bekliyor",
            rows=[
                {
                    "stock_id": str(self.stock_a.id),
                    "source_line_id": "",
                    "product_label": "Çelik Vida | VDA-01 | HIRDAVAT",
                    "description": "",
                    "quantity": "2",
                    "unit": "adet",
                    "unit_price": "12.50",
                }
            ],
        )

        self.client.post(reverse("operation_draft_open", args=[draft.id]), follow=True)
        response = self.client.post(reverse("home"), {
            "submit_action": "save_operation",
            "operation_type": "sale",
            "note": "Kasada bekliyor",
            "saved_draft_id": str(draft.id),
            "source_transaction_id": "",
            "stock_id": [str(self.stock_a.id)],
            "source_line_id": [""],
            "product_label": ["Çelik Vida | VDA-01 | HIRDAVAT"],
            "line_description": [""],
            "line_quantity": ["2"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })

        self.assertEqual(response.status_code, 302)
        self.assertFalse(StockTransactionDraft.objects.filter(id=draft.id).exists())

    def test_home_shows_bulk_entry_parser_panel(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="bulk-entry-box"')
        self.assertContains(response, 'id="bulk-entry-text"')
        self.assertContains(response, 'id="bulk-preview-btn"')
        self.assertContains(response, 'id="bulk-apply-btn"')
        self.assertContains(response, 'id="bulk-preview-list"')
        self.assertContains(response, 'id="bulk-entry-mode-hint"')
        self.assertContains(response, "İlk sürümde toplu giriş satış modunda çalışır")

    def test_build_operation_line_warnings_marks_insufficient_stock(self):
        warnings = build_operation_line_warnings(
            {"quantity": 5, "unit": "adet", "is_active": True, "has_price": True},
            quantity=6,
            unit="adet",
            operation_type=StockTransaction.SALE,
        )

        self.assertTrue(any(item["code"] == "insufficient_stock" for item in warnings))

    def test_build_operation_line_warnings_marks_critical_stock(self):
        warnings = build_operation_line_warnings(
            {"quantity": 5, "unit": "adet", "is_active": True, "has_price": True},
            quantity=3,
            unit="adet",
            operation_type=StockTransaction.SALE,
        )

        self.assertTrue(any(item["code"] == "critical_stock" for item in warnings))

    def test_build_operation_line_warnings_marks_missing_price_passive_and_unit_mismatch(self):
        warnings = build_operation_line_warnings(
            {"quantity": 20, "unit": "adet", "is_active": False, "has_price": False},
            quantity=2,
            unit="kg",
            operation_type=StockTransaction.SALE,
        )

        codes = {item["code"] for item in warnings}
        self.assertIn("inactive", codes)
        self.assertIn("missing_price", codes)
        self.assertIn("unit_mismatch", codes)

    def test_home_catalog_includes_warning_metadata_for_rows(self):
        passive_stock = Stock.objects.create(
            name="Pasif Urun",
            sku="PSF-01",
            quantity=2,
            unit="kg",
            category="BOYA",
            is_active=False,
        )

        response = self.client.get(reverse("home"))

        catalog = response.context["stock_catalog"]
        passive_row = next(item for item in catalog if item["id"] == passive_stock.id)
        self.assertEqual(passive_row["quantity"], 2)
        self.assertEqual(passive_row["unit"], "kg")
        self.assertFalse(passive_row["is_active"])
        self.assertFalse(passive_row["has_price"])
        self.assertContains(response, 'class="line-warning-list"')

    def test_sale_can_be_saved_with_optional_header_fields(self):
        response = self.client.post(reverse("home"), {
            "operation_type": "sale",
            "customer_name": "Pakdemir Insaat",
            "phone": "0532 111 22 33",
            "note": "Santiye teslimi",
            "payment_type": "card",
            "recipient_name": "Halit",
            "vehicle_plate": "34 ABC 123",
            "stock_id": [str(self.stock_a.id)],
            "product_label": ["Ã‡elik Vida | VDA-01 | HIRDAVAT"],
            "line_description": [""],
            "line_quantity": ["2"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })

        self.assertEqual(response.status_code, 302)
        transaction = StockTransaction.objects.get()
        self.assertEqual(transaction.customer_name, "Pakdemir Insaat")
        self.assertEqual(transaction.phone, "0532 111 22 33")
        self.assertEqual(transaction.note, "Santiye teslimi")
        self.assertEqual(transaction.payment_type, "card")
        self.assertEqual(transaction.recipient_name, "Halit")
        self.assertEqual(transaction.vehicle_plate, "34 ABC 123")

    def test_draft_preserves_header_fields_when_reopened(self):
        response = self.client.post(reverse("home"), {
            "submit_action": "save_draft",
            "operation_type": "sale",
            "customer_name": "Pakdemir Insaat",
            "phone": "0532 111 22 33",
            "note": "Bekleyen sevkiyat",
            "payment_type": "account",
            "recipient_name": "Depo",
            "vehicle_plate": "34 XYZ 987",
            "stock_id": [str(self.stock_a.id)],
            "product_label": ["Ã‡elik Vida | VDA-01 | HIRDAVAT"],
            "line_description": [""],
            "line_quantity": ["2"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        draft = StockTransactionDraft.objects.get()
        self.assertEqual(draft.customer_name, "Pakdemir Insaat")
        reopen_response = self.client.post(reverse("operation_draft_open", args=[draft.id]), follow=True)

        self.assertEqual(reopen_response.status_code, 200)
        self.assertEqual(reopen_response.context["operation_form"]["customer_name"].value(), "Pakdemir Insaat")
        self.assertEqual(reopen_response.context["operation_form"]["phone"].value(), "0532 111 22 33")
        self.assertEqual(reopen_response.context["operation_form"]["payment_type"].value(), "account")
        self.assertEqual(reopen_response.context["operation_form"]["recipient_name"].value(), "Depo")
        self.assertEqual(reopen_response.context["operation_form"]["vehicle_plate"].value(), "34 XYZ 987")

    def test_operation_detail_shows_saved_header_fields(self):
        self.client.post(reverse("home"), {
            "operation_type": "sale",
            "customer_name": "Pakdemir Insaat",
            "phone": "0532 111 22 33",
            "note": "Santiye teslimi",
            "payment_type": "transfer",
            "recipient_name": "Halit",
            "vehicle_plate": "34 ABC 123",
            "stock_id": [str(self.stock_a.id)],
            "product_label": ["Ã‡elik Vida | VDA-01 | HIRDAVAT"],
            "line_description": [""],
            "line_quantity": ["2"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })
        transaction = StockTransaction.objects.get()

        response = self.client.get(reverse("operation_detail", args=[transaction.id]))

        self.assertContains(response, "Pakdemir Insaat")
        self.assertContains(response, "0532 111 22 33")
        self.assertContains(response, "Havale")
        self.assertContains(response, "Halit")
        self.assertContains(response, "34 ABC 123")

    def test_sale_receipt_print_view_renders_completed_transaction(self):
        self.client.post(reverse("home"), {
            "operation_type": "sale",
            "customer_name": "Pakdemir Insaat",
            "phone": "0532 111 22 33",
            "note": "Santiye teslimi",
            "payment_type": "card",
            "recipient_name": "Halit",
            "vehicle_plate": "34 ABC 123",
            "stock_id": [str(self.stock_a.id)],
            "product_label": [f"{self.stock_a.name} | {self.stock_a.sku} | {self.stock_a.category}"],
            "line_description": ["Kasa onü"],
            "line_quantity": ["2"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })
        transaction = StockTransaction.objects.get()

        response = self.client.get(reverse("operation_print_receipt", args=[transaction.id]))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core_app/print/operation_sale_receipt.html")
        self.assertContains(response, "Satış Fişi")
        self.assertContains(response, transaction.display_number)
        self.assertContains(response, "Pakdemir Insaat")
        self.assertContains(response, "0532 111 22 33")
        self.assertContains(response, "Kart")
        self.assertContains(response, "Halit")
        self.assertContains(response, "34 ABC 123")
        self.assertContains(response, "company-logo.svg")

    def test_return_receipt_print_view_renders_completed_return(self):
        self.client.post(reverse("home"), {
            "operation_type": "sale",
            "note": "Kaynak satış",
            "stock_id": [str(self.stock_a.id)],
            "product_label": [f"{self.stock_a.name} | {self.stock_a.sku} | {self.stock_a.category}"],
            "line_description": [""],
            "line_quantity": ["2"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })
        sale_transaction = StockTransaction.objects.get()
        sale_line = sale_transaction.lines.get()

        self.client.post(reverse("home"), {
            "operation_type": "return",
            "customer_name": "Pakdemir Insaat",
            "phone": "0532 111 22 33",
            "note": f"{sale_transaction.display_number} fişinden iade",
            "payment_type": "transfer",
            "stock_id": [str(self.stock_a.id)],
            "source_line_id": [str(sale_line.id)],
            "product_label": [f"{self.stock_a.name} | {self.stock_a.sku} | {self.stock_a.category}"],
            "line_description": [""],
            "line_quantity": ["1"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
            "source_transaction_id": str(sale_transaction.id),
        })
        return_transaction = StockTransaction.objects.filter(operation_type=StockTransaction.RETURN).get()

        response = self.client.get(reverse("operation_print_receipt", args=[return_transaction.id]))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core_app/print/operation_return_receipt.html")
        self.assertContains(response, "İade Fişi")
        self.assertContains(response, return_transaction.display_number)
        self.assertContains(response, sale_transaction.display_number)
        self.assertContains(response, "Havale")
        self.assertContains(response, "company-logo.svg")

    def test_delivery_form_print_view_shows_header_fields(self):
        self.client.post(reverse("home"), {
            "operation_type": "sale",
            "customer_name": "Pakdemir Insaat",
            "phone": "0532 111 22 33",
            "note": "Santiye teslimi",
            "payment_type": "account",
            "recipient_name": "Depo",
            "vehicle_plate": "34 XYZ 987",
            "stock_id": [str(self.stock_a.id)],
            "product_label": [f"{self.stock_a.name} | {self.stock_a.sku} | {self.stock_a.category}"],
            "line_description": ["Ana depo"],
            "line_quantity": ["2"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })
        transaction = StockTransaction.objects.get()

        response = self.client.get(reverse("operation_print_delivery_form", args=[transaction.id]))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core_app/print/operation_delivery_form.html")
        self.assertContains(response, "A4 Teslim Formu")
        self.assertContains(response, "Teslim Alan")
        self.assertContains(response, "Depo")
        self.assertContains(response, "34 XYZ 987")
        self.assertContains(response, "company-logo.svg")

    def test_draft_id_does_not_render_completed_print_view(self):
        draft = StockTransactionDraft.objects.create(
            operation_type=StockTransaction.SALE,
            customer_name="Taslak Musteri",
            rows=[],
        )

        response = self.client.get(reverse("operation_print_receipt", args=[draft.id]))

        self.assertEqual(response.status_code, 404)

    def test_receipt_copy_carries_contact_headers_but_clears_payment_type(self):
        self.client.post(reverse("home"), {
            "operation_type": "sale",
            "customer_name": "Pakdemir Insaat",
            "phone": "0532 111 22 33",
            "note": "Eski fis notu",
            "payment_type": "cash",
            "recipient_name": "Halit",
            "vehicle_plate": "34 ABC 123",
            "stock_id": [str(self.stock_a.id)],
            "product_label": ["Ã‡elik Vida | VDA-01 | HIRDAVAT"],
            "line_description": [""],
            "line_quantity": ["2"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })
        transaction = StockTransaction.objects.get()

        response = self.client.post(
            reverse("operation_start_from_receipt", args=[transaction.id]),
            {"action": "copy_sale"},
            follow=True,
        )

        self.assertEqual(response.context["operation_form"]["customer_name"].value(), "Pakdemir Insaat")
        self.assertEqual(response.context["operation_form"]["phone"].value(), "0532 111 22 33")
        self.assertEqual(response.context["operation_form"]["recipient_name"].value(), "Halit")
        self.assertEqual(response.context["operation_form"]["vehicle_plate"].value(), "34 ABC 123")
        self.assertEqual(response.context["operation_form"]["payment_type"].value(), "")

    def test_passive_stock_draft_can_be_reopened_and_completed(self):
        self.stock_a.is_active = False
        self.stock_a.save(update_fields=["is_active"])
        product_label = f"{self.stock_a.name} | {self.stock_a.sku} | {self.stock_a.category}"

        draft = StockTransactionDraft.objects.create(
            operation_type=StockTransaction.SALE,
            customer_name="Pasif Musteri",
            note="Pasif stok taslagi",
            rows=[
                {
                    "stock_id": str(self.stock_a.id),
                    "source_line_id": "",
                    "product_label": product_label,
                    "description": "Mevcut stok satiri",
                    "quantity": "2",
                    "unit": "adet",
                    "unit_price": "12.50",
                }
            ],
        )

        reopen_response = self.client.post(reverse("operation_draft_open", args=[draft.id]), follow=True)

        self.assertEqual(reopen_response.status_code, 200)
        self.assertEqual(reopen_response.context["operation_rows"][0]["stock_id"], str(self.stock_a.id))
        self.assertEqual(reopen_response.context["operation_form"]["customer_name"].value(), "Pasif Musteri")

        save_response = self.client.post(reverse("home"), {
            "submit_action": "save_operation",
            "operation_type": "sale",
            "customer_name": "Pasif Musteri",
            "note": "Pasif stok tamamlandi",
            "saved_draft_id": str(draft.id),
            "source_transaction_id": "",
            "stock_id": [str(self.stock_a.id)],
            "source_line_id": [""],
            "product_label": [product_label],
            "line_description": ["Mevcut stok satiri"],
            "line_quantity": ["2"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })

        self.assertEqual(save_response.status_code, 302)
        self.assertEqual(StockTransaction.objects.count(), 1)
        self.assertFalse(StockTransactionDraft.objects.filter(id=draft.id).exists())
        self.stock_a.refresh_from_db()
        self.assertEqual(self.stock_a.quantity, 18)

    def test_receipt_copy_sale_with_passive_stock_can_still_be_completed(self):
        product_label = f"{self.stock_a.name} | {self.stock_a.sku} | {self.stock_a.category}"
        self.client.post(reverse("home"), {
            "operation_type": "sale",
            "note": "Kaynak satis",
            "stock_id": [str(self.stock_a.id)],
            "product_label": [product_label],
            "line_description": [""],
            "line_quantity": ["2"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })
        transaction = StockTransaction.objects.get()
        self.stock_a.is_active = False
        self.stock_a.save(update_fields=["is_active"])

        start_response = self.client.post(
            reverse("operation_start_from_receipt", args=[transaction.id]),
            {"action": "copy_sale"},
            follow=True,
        )

        self.assertEqual(start_response.status_code, 200)
        self.assertEqual(start_response.context["operation_rows"][0]["stock_id"], str(self.stock_a.id))

        save_response = self.client.post(reverse("home"), {
            "submit_action": "save_operation",
            "operation_type": "sale",
            "note": "Pasif urunden yeni satis",
            "source_transaction_id": "",
            "stock_id": [str(self.stock_a.id)],
            "source_line_id": [""],
            "product_label": [product_label],
            "line_description": [""],
            "line_quantity": ["1"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })

        self.assertEqual(save_response.status_code, 302)
        self.assertEqual(StockTransaction.objects.count(), 2)

    def test_bulk_preview_can_match_passive_stock_and_submit_it(self):
        self.stock_a.is_active = False
        self.stock_a.save(update_fields=["is_active"])
        product_label = f"{self.stock_a.name} | {self.stock_a.sku} | {self.stock_a.category}"

        preview_response = self.client.post(
            reverse("operation_bulk_preview"),
            {
                "bulk_text": f"{self.stock_a.name} 2",
                "operation_type": "sale",
            },
        )

        self.assertEqual(preview_response.status_code, 200)
        payload = preview_response.json()
        self.assertEqual(payload["rows"][0]["status"], "matched")
        self.assertEqual(str(payload["rows"][0]["matched_stock_id"]), str(self.stock_a.id))

        save_response = self.client.post(reverse("home"), {
            "submit_action": "save_operation",
            "operation_type": "sale",
            "note": "Parser pasif urun",
            "source_transaction_id": "",
            "stock_id": [str(self.stock_a.id)],
            "source_line_id": [""],
            "product_label": [product_label],
            "line_description": [""],
            "line_quantity": ["2"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })

        self.assertEqual(save_response.status_code, 302)
        self.assertEqual(StockTransaction.objects.count(), 1)

    def test_completed_draft_preserves_header_fields(self):
        product_label = f"{self.stock_a.name} | {self.stock_a.sku} | {self.stock_a.category}"
        self.client.post(reverse("home"), {
            "submit_action": "save_draft",
            "operation_type": "sale",
            "customer_name": "Pakdemir Insaat",
            "phone": "0532 111 22 33",
            "note": "Bekleyen sevkiyat",
            "payment_type": "account",
            "recipient_name": "Depo",
            "vehicle_plate": "34 XYZ 987",
            "stock_id": [str(self.stock_a.id)],
            "source_line_id": [""],
            "product_label": [product_label],
            "line_description": [""],
            "line_quantity": ["2"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        }, follow=True)
        draft = StockTransactionDraft.objects.get()

        self.client.post(reverse("operation_draft_open", args=[draft.id]), follow=True)
        save_response = self.client.post(reverse("home"), {
            "submit_action": "save_operation",
            "operation_type": "sale",
            "customer_name": "Pakdemir Insaat",
            "phone": "0532 111 22 33",
            "note": "Bekleyen sevkiyat",
            "payment_type": "account",
            "recipient_name": "Depo",
            "vehicle_plate": "34 XYZ 987",
            "saved_draft_id": str(draft.id),
            "source_transaction_id": "",
            "stock_id": [str(self.stock_a.id)],
            "source_line_id": [""],
            "product_label": [product_label],
            "line_description": [""],
            "line_quantity": ["2"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })

        self.assertEqual(save_response.status_code, 302)
        transaction = StockTransaction.objects.get()
        self.assertEqual(transaction.customer_name, "Pakdemir Insaat")
        self.assertEqual(transaction.phone, "0532 111 22 33")
        self.assertEqual(transaction.payment_type, "account")
        self.assertEqual(transaction.recipient_name, "Depo")
        self.assertEqual(transaction.vehicle_plate, "34 XYZ 987")
        self.assertFalse(StockTransactionDraft.objects.filter(id=draft.id).exists())

    def test_home_warning_config_matches_helper_threshold(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="operation-warning-config"')
        config = response.context["operation_warning_config"]
        self.assertEqual(config["critical_stock_threshold"], 3)

        warning_source = {
            "quantity": 5,
            "unit": "adet",
            "is_active": True,
            "has_price": True,
        }
        warnings = build_operation_line_warnings(
            warning_source,
            quantity=3,
            unit="adet",
            operation_type=StockTransaction.SALE,
        )
        self.assertTrue(any(item["code"] == "critical_stock" for item in warnings))

    def test_daily_operation_panel_totals_sales_for_today(self):
        self.client.post(reverse("home"), {
            "operation_type": "sale",
            "note": "Gunluk satis bir",
            "stock_id": [str(self.stock_a.id)],
            "product_label": [f"{self.stock_a.name} | {self.stock_a.sku} | {self.stock_a.category}"],
            "line_description": [""],
            "line_quantity": ["2"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })
        self.client.post(reverse("home"), {
            "operation_type": "sale",
            "note": "Gunluk satis iki",
            "stock_id": [str(self.stock_b.id)],
            "product_label": [f"{self.stock_b.name} | {self.stock_b.sku} | {self.stock_b.category}"],
            "line_description": [""],
            "line_quantity": ["3"],
            "line_unit": ["adet"],
            "line_unit_price": ["6.00"],
        })

        panel = get_daily_operation_panel()

        self.assertEqual(str(panel["sale_total"]), "43.00")
        self.assertEqual(str(panel["return_total"]), "0.00")
        self.assertEqual(str(panel["net_total"]), "43.00")
        self.assertEqual(panel["transaction_count"], 2)

    def test_daily_operation_panel_counts_returns_and_net_total(self):
        self.client.post(reverse("home"), {
            "operation_type": "sale",
            "note": "Gunluk satis",
            "stock_id": [str(self.stock_a.id)],
            "product_label": [f"{self.stock_a.name} | {self.stock_a.sku} | {self.stock_a.category}"],
            "line_description": [""],
            "line_quantity": ["4"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })
        self.client.post(reverse("home"), {
            "operation_type": "return",
            "note": "Gunluk iade",
            "stock_id": [str(self.stock_a.id)],
            "product_label": [f"{self.stock_a.name} | {self.stock_a.sku} | {self.stock_a.category}"],
            "line_description": [""],
            "line_quantity": ["1"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })

        panel = get_daily_operation_panel()

        self.assertEqual(str(panel["sale_total"]), "50.00")
        self.assertEqual(str(panel["return_total"]), "12.50")
        self.assertEqual(str(panel["net_total"]), "37.50")
        self.assertEqual(panel["transaction_count"], 2)

    def test_daily_operation_panel_excludes_drafts_and_old_transactions(self):
        self.client.post(reverse("home"), {
            "operation_type": "sale",
            "note": "Bugun tamamlanan",
            "stock_id": [str(self.stock_a.id)],
            "product_label": [f"{self.stock_a.name} | {self.stock_a.sku} | {self.stock_a.category}"],
            "line_description": [""],
            "line_quantity": ["1"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })
        old_txn = StockTransaction.objects.get()
        yesterday = timezone.now() - timedelta(days=1)
        StockTransaction.objects.filter(id=old_txn.id).update(created_at=yesterday)
        StockTransactionDraft.objects.create(
            operation_type=StockTransaction.SALE,
            note="Taslak panel disi",
            rows=[],
        )

        panel = get_daily_operation_panel()

        self.assertEqual(panel["transaction_count"], 0)
        self.assertEqual(str(panel["sale_total"]), "0.00")
        self.assertEqual(str(panel["return_total"]), "0.00")
        self.assertEqual(panel["recent_transactions"], [])

    def test_daily_operation_panel_recent_transactions_are_sorted(self):
        self.client.post(reverse("home"), {
            "operation_type": "sale",
            "note": "Ilk islem",
            "stock_id": [str(self.stock_a.id)],
            "product_label": [f"{self.stock_a.name} | {self.stock_a.sku} | {self.stock_a.category}"],
            "line_description": [""],
            "line_quantity": ["1"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })
        first_txn = StockTransaction.objects.latest("id")
        self.client.post(reverse("home"), {
            "operation_type": "return",
            "note": "Son islem",
            "stock_id": [str(self.stock_a.id)],
            "product_label": [f"{self.stock_a.name} | {self.stock_a.sku} | {self.stock_a.category}"],
            "line_description": [""],
            "line_quantity": ["1"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })
        last_txn = StockTransaction.objects.latest("id")

        panel = get_daily_operation_panel()

        self.assertEqual(panel["recent_transactions"][0].id, last_txn.id)
        self.assertEqual(panel["recent_transactions"][1].id, first_txn.id)

    def test_home_renders_daily_operation_panel(self):
        self.client.post(reverse("home"), {
            "operation_type": "sale",
            "note": "Panel satis",
            "stock_id": [str(self.stock_a.id)],
            "product_label": [f"{self.stock_a.name} | {self.stock_a.sku} | {self.stock_a.category}"],
            "line_description": [""],
            "line_quantity": ["2"],
            "line_unit": ["adet"],
            "line_unit_price": ["12.50"],
        })

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Gün Sonu Mini Panel")
        self.assertContains(response, "Bugün Satış")
        self.assertContains(response, "Bugün İade")
        self.assertContains(response, "Net Toplam")
        self.assertContains(response, "İşlem Sayısı")
        self.assertContains(response, "Bugünün Son İşlemleri")
