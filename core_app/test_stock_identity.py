from django.test import TestCase

from core_app.models import Stock
from core_app.services.stock_identity import build_stock_identity
from core_app.services.text import normalize_text


class StockIdentityTests(TestCase):
    def test_normalize_text_handles_turkish_characters(self):
        self.assertEqual(normalize_text("Çivi İNCE  "), "civi ince")

    def test_normalize_text_handles_whitespace_and_case(self):
        self.assertEqual(normalize_text("  MATKAP    UCU "), "matkap ucu")

    def test_normalize_text_handles_dash_and_parentheses(self):
        self.assertEqual(normalize_text("M8-Civata (DIN 933)"), "m8 civata din 933")

    def test_normalize_text_handles_dots_and_commas(self):
        self.assertEqual(normalize_text("3.5, MM Vida"), "3 5 mm vida")

    def test_normalize_text_handles_mixed_symbols_consistently(self):
        self.assertEqual(normalize_text("A++ Kalite / Ozel_Urun"), "a kalite ozel urun")

    def test_normalize_text_handles_non_string_values(self):
        self.assertEqual(normalize_text(35), "35")
        self.assertEqual(normalize_text(0), "0")

    def test_build_identity_uses_sku_when_present(self):
        identity = build_stock_identity(
            name="Matkap Ucu",
            sku=" ABC-123 ",
            subgroup="Elektrik",
        )
        self.assertEqual(identity.identity_key, "sku:abc 123|name:matkap ucu|sub:elektrik")

    def test_build_identity_falls_back_to_name_and_subgroup_when_sku_missing(self):
        identity = build_stock_identity(
            name="Matkap Ucu",
            sku="",
            subgroup="İnce Uç",
        )
        self.assertEqual(identity.identity_key, "name:matkap ucu|sub:ince uc")

    def test_model_and_identity_builder_share_name_normalization(self):
        stock = Stock.objects.create(name=" Çelik Dübel ", subgroup="Montaj")
        identity = build_stock_identity(name=" Çelik Dübel ", subgroup="Montaj")

        self.assertEqual(stock.normalized_name, identity.normalized_name)
        self.assertEqual(stock.normalized_name, "celik dubel")

