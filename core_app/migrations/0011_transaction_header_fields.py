from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core_app", "0010_stocktransactiondraft"),
    ]

    operations = [
        migrations.AddField(
            model_name="stocktransaction",
            name="customer_name",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="stocktransaction",
            name="payment_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "Belirtilmedi"),
                    ("cash", "Nakit"),
                    ("card", "Kart"),
                    ("transfer", "Havale"),
                    ("account", "Açık Hesap"),
                ],
                default="",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="stocktransaction",
            name="phone",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
        migrations.AddField(
            model_name="stocktransaction",
            name="recipient_name",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="stocktransaction",
            name="vehicle_plate",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
        migrations.AddField(
            model_name="stocktransactiondraft",
            name="customer_name",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="stocktransactiondraft",
            name="payment_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "Belirtilmedi"),
                    ("cash", "Nakit"),
                    ("card", "Kart"),
                    ("transfer", "Havale"),
                    ("account", "Açık Hesap"),
                ],
                default="",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="stocktransactiondraft",
            name="phone",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
        migrations.AddField(
            model_name="stocktransactiondraft",
            name="recipient_name",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="stocktransactiondraft",
            name="vehicle_plate",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
    ]
