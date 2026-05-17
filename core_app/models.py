from django.db import models

from decimal import Decimal

from .services.text import build_stock_identity_key, normalize_text


class Stock(models.Model):
    UNIT_CHOICES = [
        ("adet", "Adet"),
        ("kg", "Kg"),
        ("mt", "Metre"),
    ]

    name = models.CharField(max_length=120)
    normalized_name = models.CharField(max_length=160, blank=True, default="", db_index=True)

    category = models.CharField(max_length=80, blank=True, default="")
    subgroup = models.CharField(max_length=80, blank=True, default="")
    sku = models.CharField("Barkod / SKU", max_length=50, blank=True, default="")
    identity_key = models.CharField(max_length=255, blank=True, default="", db_index=True)

    quantity = models.IntegerField(default=0)
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES, default="adet")

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        self.name = (self.name or "").strip()
        self.category = (self.category or "").strip()
        self.subgroup = (self.subgroup or "").strip()
        self.sku = (self.sku or "").strip()
        self.normalized_name = normalize_text(self.name)
        self.identity_key = build_stock_identity_key(self.name, sku=self.sku, subgroup=self.subgroup)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class StockMovement(models.Model):
    IN = "IN"
    OUT = "OUT"
    TYPE_CHOICES = [
        (IN, "Giriş"),
        (OUT, "Çıkış"),
    ]

    stock = models.ForeignKey("core_app.Stock", on_delete=models.CASCADE, related_name="movements")
    movement_type = models.CharField(max_length=3, choices=TYPE_CHOICES)
    quantity = models.IntegerField()
    note = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.stock.name} - {self.get_movement_type_display()} - {self.quantity}"


class PriceList(models.Model):
    title = models.CharField(max_length=120)
    sheet_name = models.CharField(max_length=80, blank=True, default="")
    list_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=10, default="TRY")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} ({self.list_date or 'tarihsiz'})"


class PriceItem(models.Model):
    price_list = models.ForeignKey(PriceList, on_delete=models.CASCADE, related_name="items")
    group = models.CharField(max_length=80, blank=True, default="")
    name = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.name} - {self.price}"


class StockMergeAudit(models.Model):
    surviving_stock = models.ForeignKey("core_app.Stock", on_delete=models.CASCADE, related_name="merge_audits")
    removed_stock_id = models.IntegerField()
    merged_at = models.DateTimeField(auto_now_add=True)
    left_snapshot = models.JSONField(default=dict)
    right_snapshot = models.JSONField(default=dict)
    field_sources = models.JSONField(default=dict)
    merged_quantity = models.IntegerField(default=0)

    class Meta:
        ordering = ["-merged_at", "-id"]

    def __str__(self):
        return f"Merge audit #{self.id} -> stock #{self.surviving_stock_id}"


class StockTransaction(models.Model):
    SALE = "sale"
    RETURN = "return"
    TYPE_CHOICES = [
        (SALE, "Satış"),
        (RETURN, "İade"),
    ]
    PAYMENT_TYPE_CHOICES = [
        ("", "Belirtilmedi"),
        ("cash", "Nakit"),
        ("card", "Kart"),
        ("transfer", "Havale"),
        ("account", "Açık Hesap"),
    ]

    operation_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    source_transaction = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="derived_transactions",
    )
    customer_name = models.CharField(max_length=120, blank=True, default="")
    phone = models.CharField(max_length=40, blank=True, default="")
    note = models.CharField(max_length=200, blank=True, default="")
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPE_CHOICES, blank=True, default="")
    recipient_name = models.CharField(max_length=120, blank=True, default="")
    vehicle_plate = models.CharField(max_length=40, blank=True, default="")
    total_quantity = models.IntegerField(default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    @property
    def display_number(self):
        return f"ISL-{self.id:05d}"

    @property
    def detail_text(self):
        if self.note:
            return self.note

        line_names = [line.stock_name for line in self.lines.all()[:3] if line.stock_name]
        if not line_names:
            return ""

        remaining = max(self.lines.count() - len(line_names), 0)
        summary = ", ".join(line_names)
        if remaining:
            summary = f"{summary} +{remaining} kalem"
        return summary

    def __str__(self):
        return f"{self.get_operation_type_display()} #{self.id}"


class StockTransactionLine(models.Model):
    transaction = models.ForeignKey(
        "core_app.StockTransaction",
        on_delete=models.CASCADE,
        related_name="lines",
    )
    source_line = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="derived_lines",
    )
    stock = models.ForeignKey(
        "core_app.Stock",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transaction_lines",
    )
    stock_name = models.CharField(max_length=120)
    stock_sku = models.CharField(max_length=50, blank=True, default="")
    stock_category = models.CharField(max_length=80, blank=True, default="")
    stock_subgroup = models.CharField(max_length=80, blank=True, default="")
    description = models.CharField(max_length=200, blank=True, default="")
    quantity = models.IntegerField()
    unit = models.CharField(max_length=10, choices=Stock.UNIT_CHOICES, default="adet")
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.stock_name} x {self.quantity}"


class StockTransactionDraft(models.Model):
    operation_type = models.CharField(max_length=10, choices=StockTransaction.TYPE_CHOICES, default=StockTransaction.SALE)
    customer_name = models.CharField(max_length=120, blank=True, default="")
    phone = models.CharField(max_length=40, blank=True, default="")
    note = models.CharField(max_length=200, blank=True, default="")
    payment_type = models.CharField(max_length=20, choices=StockTransaction.PAYMENT_TYPE_CHOICES, blank=True, default="")
    recipient_name = models.CharField(max_length=120, blank=True, default="")
    vehicle_plate = models.CharField(max_length=40, blank=True, default="")
    source_transaction_id = models.IntegerField(null=True, blank=True)
    rows = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]

    @property
    def title(self):
        if self.note:
            return self.note
        line_names = [row.get("product_label") or "" for row in self.rows[:2] if row.get("product_label")]
        if not line_names:
            return "Bekleyen fiş"
        summary = ", ".join(line_names)
        remaining = max(len(self.rows) - len(line_names), 0)
        if remaining:
            summary = f"{summary} +{remaining} kalem"
        return summary[:120]

    @property
    def total_quantity(self):
        total = 0
        for row in self.rows:
            try:
                total += int(row.get("quantity") or 0)
            except (TypeError, ValueError):
                continue
        return total

    @property
    def total_amount(self):
        total = Decimal("0.00")
        for row in self.rows:
            try:
                quantity = Decimal(str(row.get("quantity") or 0))
                unit_price = Decimal(str(row.get("unit_price") or 0))
            except Exception:
                continue
            total += quantity * unit_price
        return total.quantize(Decimal("0.01"))

    def __str__(self):
        return f"Taslak #{self.id}"

