from django import forms

from core_app.models import Stock, StockMovement


class StockImportForm(forms.Form):
    file = forms.FileField(label="Excel Dosyası (.xlsx)")


class StockForm(forms.ModelForm):
    class Meta:
        model = Stock
        fields = ["name", "category", "subgroup", "unit", "sku", "quantity"]

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if len(name) < 2:
            raise forms.ValidationError("Ürün adı en az 2 karakter olmalı.")
        return name

    def clean_sku(self):
        return (self.cleaned_data.get("sku") or "").strip()

    def clean_quantity(self):
        quantity = self.cleaned_data.get("quantity")
        if quantity is None:
            raise forms.ValidationError("Miktar zorunludur.")
        if quantity < 0:
            raise forms.ValidationError("Miktar negatif olamaz.")
        return quantity


class StockMovementForm(forms.ModelForm):
    class Meta:
        model = StockMovement
        fields = ["movement_type", "quantity", "note"]

    def clean_quantity(self):
        quantity = self.cleaned_data.get("quantity")
        if quantity is None:
            raise forms.ValidationError("Miktar zorunludur.")
        if quantity <= 0:
            raise forms.ValidationError("Miktar 0 veya negatif olamaz.")
        return quantity
