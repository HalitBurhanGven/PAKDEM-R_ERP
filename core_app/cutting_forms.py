from django import forms
from django.forms import BaseFormSet, formset_factory

from core_app.services.cutting_optimization import CutRequest


class ProfileCutOptimizationForm(forms.Form):
    standard_length = forms.IntegerField(
        label="Standart profil boyu (cm)",
        min_value=1,
        widget=forms.NumberInput(attrs={"placeholder": "Orn. 600"}),
    )


class CutDemandLineForm(forms.Form):
    cut_length = forms.IntegerField(
        label="Kesilecek boy (cm)",
        min_value=1,
        widget=forms.NumberInput(attrs={"placeholder": "Orn. 145"}),
    )
    requested_quantity = forms.IntegerField(
        label="Istenen adet",
        min_value=1,
        widget=forms.NumberInput(attrs={"placeholder": "Orn. 30"}),
    )


class BaseCutDemandFormSet(BaseFormSet):
    def __init__(self, *args, standard_length=None, **kwargs):
        self.standard_length = standard_length
        super().__init__(*args, **kwargs)

    def clean(self):
        super().clean()
        if any(self.errors):
            return

        active_line_count = 0

        for form in self.forms:
            cleaned_data = getattr(form, "cleaned_data", {})
            if not cleaned_data or cleaned_data.get("DELETE"):
                continue

            cut_length = cleaned_data.get("cut_length")
            requested_quantity = cleaned_data.get("requested_quantity")
            if cut_length in (None, "") and requested_quantity in (None, ""):
                continue

            active_line_count += 1

            if self.standard_length and cut_length and cut_length > self.standard_length:
                form.add_error("cut_length", "Kesim boyu, standart profil boyundan buyuk olamaz.")

        if active_line_count == 0:
            raise forms.ValidationError("En az bir kesim satiri girmelisin.")

    def to_cut_requests(self):
        aggregated_quantities = {}
        for form in self.forms:
            cleaned_data = getattr(form, "cleaned_data", {})
            if not cleaned_data or cleaned_data.get("DELETE"):
                continue
            if cleaned_data.get("cut_length") and cleaned_data.get("requested_quantity"):
                cut_length = cleaned_data["cut_length"]
                aggregated_quantities[cut_length] = (
                    aggregated_quantities.get(cut_length, 0) + cleaned_data["requested_quantity"]
                )

        return [
            CutRequest(cut_length=cut_length, requested_quantity=requested_quantity)
            for cut_length, requested_quantity in aggregated_quantities.items()
        ]


CutDemandFormSet = formset_factory(
    CutDemandLineForm,
    formset=BaseCutDemandFormSet,
    extra=1,
    can_delete=True,
)
