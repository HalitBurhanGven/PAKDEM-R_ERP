from django import forms

from core_app.models import Stock


class PriceImportForm(forms.Form):
    file = forms.FileField(label="Excel (.xlsx)")
    sheet = forms.CharField(label="Sheet adı", help_text="Örn: HIRDAVAT", max_length=80)
    title = forms.CharField(label="Liste adı", max_length=120)


class CreateStockFromPriceItemForm(forms.Form):
    name = forms.CharField(label="Ürün Adı", max_length=120)
    sku = forms.CharField(label="SKU", max_length=50, required=False)
    category = forms.CharField(label="Kategori", max_length=80, required=False)
    unit = forms.ChoiceField(label="Birim", choices=Stock.UNIT_CHOICES, initial="adet")
    quantity = forms.IntegerField(label="Miktar", min_value=0, initial=0)

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if len(name) < 2:
            raise forms.ValidationError("Ürün adı en az 2 karakter olmalı.")
        return name

    def clean_sku(self):
        return (self.cleaned_data.get("sku") or "").strip()[:50]

    def clean_category(self):
        return (self.cleaned_data.get("category") or "").strip()[:80]
