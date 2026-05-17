from django.test import TestCase
from django.urls import reverse

from core_app.cutting_forms import CutDemandFormSet, ProfileCutOptimizationForm
from core_app.services.cutting_optimization import CutRequest, build_multi_cut_plan, build_single_cut_plan


class ProfileCutOptimizationServiceTests(TestCase):
    def test_build_single_cut_plan_for_standard_case(self):
        result = build_single_cut_plan(
            standard_length=600,
            cut_length=145,
            requested_quantity=135,
        )

        self.assertEqual(result.pieces_per_stock, 4)
        self.assertEqual(result.waste_per_full_stock, 20)
        self.assertEqual(result.required_stock_count, 34)
        self.assertEqual(result.full_stock_count, 33)
        self.assertEqual(result.partial_stock_used_pieces, 3)
        self.assertEqual(result.partial_stock_waste, 165)
        self.assertEqual(result.total_waste, 825)

    def test_build_multi_cut_plan_for_mixed_lengths(self):
        result = build_multi_cut_plan(
            standard_length=600,
            requests=[
                CutRequest(cut_length=145, requested_quantity=10),
                CutRequest(cut_length=92, requested_quantity=5),
            ],
        )

        self.assertGreaterEqual(result.total_stock_count, 1)
        self.assertEqual(result.total_cut_pieces, 15)
        self.assertGreaterEqual(len(result.pattern_usages), 1)
        self.assertTrue(any(pattern.waste >= 0 for pattern in result.pattern_usages))
        produced = {
            cut_length: 0
            for cut_length in [145, 92]
        }
        for pattern in result.pattern_usages:
            for cut_length, piece_count in pattern.counts_by_length:
                produced[cut_length] += piece_count * pattern.stock_count

        self.assertEqual(produced[145], 10)
        self.assertEqual(produced[92], 5)

    def test_build_multi_cut_plan_merges_duplicate_lengths(self):
        result = build_multi_cut_plan(
            standard_length=600,
            requests=[
                CutRequest(cut_length=145, requested_quantity=10),
                CutRequest(cut_length=145, requested_quantity=4),
            ],
        )

        self.assertEqual(len(result.requests), 1)
        self.assertEqual(result.requests[0].cut_length, 145)
        self.assertEqual(result.requests[0].requested_quantity, 14)


class ProfileCutOptimizationFormTests(TestCase):
    def test_main_form_rejects_zero_or_negative_standard_length(self):
        form = ProfileCutOptimizationForm(data={"standard_length": 0})

        self.assertFalse(form.is_valid())
        self.assertIn("standard_length", form.errors)

    def test_line_formset_rejects_cut_length_greater_than_standard_length(self):
        formset = CutDemandFormSet(data={
            "lines-TOTAL_FORMS": "1",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-cut_length": "700",
            "lines-0-requested_quantity": "10",
            "lines-0-DELETE": "",
        }, prefix="lines", standard_length=600)

        self.assertFalse(formset.is_valid())
        self.assertIn("Kesim boyu, standart profil boyundan buyuk olamaz.", formset.forms[0].errors["cut_length"])

    def test_line_formset_rejects_zero_or_negative_values(self):
        formset = CutDemandFormSet(data={
            "lines-TOTAL_FORMS": "1",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-cut_length": "-5",
            "lines-0-requested_quantity": "0",
            "lines-0-DELETE": "",
        }, prefix="lines", standard_length=600)

        self.assertFalse(formset.is_valid())
        self.assertIn("cut_length", formset.forms[0].errors)
        self.assertIn("requested_quantity", formset.forms[0].errors)

    def test_line_formset_merges_duplicate_lengths_in_output_requests(self):
        formset = CutDemandFormSet(data={
            "lines-TOTAL_FORMS": "2",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-cut_length": "142",
            "lines-0-requested_quantity": "90",
            "lines-0-DELETE": "",
            "lines-1-cut_length": "142",
            "lines-1-requested_quantity": "95",
            "lines-1-DELETE": "",
        }, prefix="lines", standard_length=600)

        self.assertTrue(formset.is_valid())
        requests = formset.to_cut_requests()
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].cut_length, 142)
        self.assertEqual(requests[0].requested_quantity, 185)


class ProfileCutOptimizationViewTests(TestCase):
    def test_optimizer_page_renders_with_multi_line_form(self):
        response = self.client.get(reverse("reports:profile_cut_optimizer"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Profil Kesim Planlama")
        self.assertContains(response, "Kesim Talepleri")
        self.assertContains(response, "Satir Ekle")
        self.assertContains(response, "Kesim Sonucu")

    def test_optimizer_page_shows_single_request_compatibility_summary(self):
        response = self.client.post(reverse("reports:profile_cut_optimizer"), {
            "standard_length": 600,
            "lines-TOTAL_FORMS": "1",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-cut_length": "145",
            "lines-0-requested_quantity": "135",
            "lines-0-DELETE": "",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tek Olculu Ozet")
        self.assertContains(response, "34 adet")
        self.assertContains(response, "33 profil tam dolu kullanilir")

    def test_optimizer_page_shows_patterns_for_multi_cut_plan(self):
        response = self.client.post(reverse("reports:profile_cut_optimizer"), {
            "standard_length": 600,
            "lines-TOTAL_FORMS": "2",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-cut_length": "145",
            "lines-0-requested_quantity": "10",
            "lines-0-DELETE": "",
            "lines-1-cut_length": "92",
            "lines-1-requested_quantity": "5",
            "lines-1-DELETE": "",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Kesim Desenleri")
        self.assertContains(response, "Fire orani")
        self.assertContains(response, "profil")
        self.assertContains(response, "145 cm x")
        self.assertContains(response, "92 cm x")

    def test_optimizer_page_accepts_duplicate_lengths_and_calculates_them_together(self):
        response = self.client.post(reverse("reports:profile_cut_optimizer"), {
            "standard_length": 600,
            "lines-TOTAL_FORMS": "3",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-cut_length": "142",
            "lines-0-requested_quantity": "90",
            "lines-0-DELETE": "",
            "lines-1-cut_length": "156",
            "lines-1-requested_quantity": "30",
            "lines-1-DELETE": "",
            "lines-2-cut_length": "142",
            "lines-2-requested_quantity": "95",
            "lines-2-DELETE": "",
        })

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Ayni kesim boyu birden fazla satirda girilemez")
        self.assertContains(response, "Kesim Desenleri")
        self.assertContains(response, "142 cm x")
        self.assertContains(response, "156 cm x")
