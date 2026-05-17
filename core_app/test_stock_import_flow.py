from django.test import TestCase

from core_app.models import Stock
from core_app.services.stock_identity import create_or_merge_stock


class StockImportFlowTests(TestCase):
    def test_import_like_flow_does_not_merge_same_name_different_sku(self):
        create_or_merge_stock(name="Rondela", sku="R-1", subgroup="A", quantity=2)
        create_or_merge_stock(name="Rondela", sku="R-2", subgroup="A", quantity=3)

        self.assertEqual(Stock.objects.count(), 2)

    def test_import_like_flow_merges_same_identity_rows(self):
        create_or_merge_stock(name="Rondela", sku="R-1", subgroup="A", quantity=2)
        create_or_merge_stock(name="Rondela", sku="R-1", subgroup="A", quantity=3)

        stock = Stock.objects.get(sku="R-1")
        self.assertEqual(stock.quantity, 5)
