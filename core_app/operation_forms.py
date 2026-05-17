from decimal import Decimal, InvalidOperation

from django import forms

from core_app.models import Stock, StockTransaction


class StockOperationForm(forms.Form):
    operation_type = forms.ChoiceField(
        label="Islem Tipi",
        choices=StockTransaction.TYPE_CHOICES,
        initial=StockTransaction.SALE,
        widget=forms.RadioSelect,
    )
    customer_name = forms.CharField(label="Musteri Adi", required=False, max_length=120)
    phone = forms.CharField(label="Telefon", required=False, max_length=40)
    note = forms.CharField(
        label="Genel Not",
        required=False,
        max_length=200,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    payment_type = forms.ChoiceField(
        label="Odeme Tipi",
        required=False,
        choices=StockTransaction.PAYMENT_TYPE_CHOICES,
    )
    recipient_name = forms.CharField(label="Teslim Alan", required=False, max_length=120)
    vehicle_plate = forms.CharField(label="Arac / Plaka", required=False, max_length=40)

    def __init__(self, *args, stock_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = stock_queryset or Stock.objects.none()
        self.stock_map = {stock.id: stock for stock in queryset}
        self.cleaned_rows = []

    def clean(self):
        cleaned_data = super().clean()
        cleaned_data["customer_name"] = (cleaned_data.get("customer_name") or "").strip()[:120]
        cleaned_data["phone"] = " ".join((cleaned_data.get("phone") or "").split())[:40]
        cleaned_data["note"] = (cleaned_data.get("note") or "").strip()
        cleaned_data["payment_type"] = (cleaned_data.get("payment_type") or "").strip()
        cleaned_data["recipient_name"] = (cleaned_data.get("recipient_name") or "").strip()[:120]
        cleaned_data["vehicle_plate"] = " ".join((cleaned_data.get("vehicle_plate") or "").split())[:40]
        cleaned_data["rows"] = self._clean_rows()
        return cleaned_data

    def _clean_rows(self):
        stock_ids = self.data.getlist("stock_id")
        source_line_ids = self.data.getlist("source_line_id")
        product_labels = self.data.getlist("product_label")
        descriptions = self.data.getlist("line_description")
        quantities = self.data.getlist("line_quantity")
        units = self.data.getlist("line_unit")
        unit_prices = self.data.getlist("line_unit_price")

        row_count = max(
            len(stock_ids),
            len(product_labels),
            len(descriptions),
            len(quantities),
            len(units),
            len(unit_prices),
        )

        rows = []
        valid_units = {choice[0] for choice in Stock.UNIT_CHOICES}

        for index in range(row_count):
            stock_id_raw = (stock_ids[index] if index < len(stock_ids) else "").strip()
            source_line_id_raw = (source_line_ids[index] if index < len(source_line_ids) else "").strip()
            product_label = (product_labels[index] if index < len(product_labels) else "").strip()
            description = (descriptions[index] if index < len(descriptions) else "").strip()
            quantity_raw = (quantities[index] if index < len(quantities) else "").strip()
            unit = (units[index] if index < len(units) else "").strip() or "adet"
            unit_price_raw = (unit_prices[index] if index < len(unit_prices) else "").strip()

            if not any([stock_id_raw, product_label, description, quantity_raw, unit_price_raw]):
                continue

            if not stock_id_raw:
                self.add_error(None, f"{index + 1}. satirda gecerli bir urun sec.")
                continue

            try:
                stock_id = int(stock_id_raw)
            except ValueError:
                self.add_error(None, f"{index + 1}. satirdaki urun bilgisi gecersiz.")
                continue

            stock = self.stock_map.get(stock_id)
            if stock is None:
                self.add_error(None, f"{index + 1}. satirdaki urun bulunamadi.")
                continue

            try:
                quantity = int(quantity_raw)
            except ValueError:
                self.add_error(None, f"{index + 1}. satirdaki miktar sayi olmali.")
                continue

            if quantity <= 0:
                self.add_error(None, f"{index + 1}. satirdaki miktar 0'dan buyuk olmali.")
                continue

            if unit not in valid_units:
                self.add_error(None, f"{index + 1}. satirdaki birim gecersiz.")
                continue

            try:
                unit_price = Decimal(unit_price_raw or "0")
            except InvalidOperation:
                self.add_error(None, f"{index + 1}. satirdaki birim fiyat gecersiz.")
                continue

            if unit_price < 0:
                self.add_error(None, f"{index + 1}. satirdaki birim fiyat negatif olamaz.")
                continue

            rows.append({
                "stock": stock,
                "source_line_id": source_line_id_raw,
                "description": description[:200],
                "quantity": quantity,
                "unit": unit,
                "unit_price": unit_price.quantize(Decimal("0.01")),
            })

        if not rows:
            self.add_error(None, "En az bir urun satiri eklemelisin.")

        self.cleaned_rows = rows
        return rows

    def get_rows_for_display(self):
        rows = []
        stock_ids = self.data.getlist("stock_id")
        source_line_ids = self.data.getlist("source_line_id")
        product_labels = self.data.getlist("product_label")
        descriptions = self.data.getlist("line_description")
        quantities = self.data.getlist("line_quantity")
        units = self.data.getlist("line_unit")
        unit_prices = self.data.getlist("line_unit_price")
        row_count = max(
            len(stock_ids),
            len(product_labels),
            len(descriptions),
            len(quantities),
            len(units),
            len(unit_prices),
            1,
        )

        for index in range(row_count):
            rows.append({
                "stock_id": stock_ids[index] if index < len(stock_ids) else "",
                "source_line_id": source_line_ids[index] if index < len(source_line_ids) else "",
                "product_label": product_labels[index] if index < len(product_labels) else "",
                "description": descriptions[index] if index < len(descriptions) else "",
                "quantity": quantities[index] if index < len(quantities) else "1",
                "unit": units[index] if index < len(units) else "adet",
                "unit_price": unit_prices[index] if index < len(unit_prices) else "0.00",
            })
        return rows
