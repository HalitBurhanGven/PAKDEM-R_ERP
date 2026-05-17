from django import forms


SOURCE_CHOICES = (
    ("left", "Sol"),
    ("right", "Sağ"),
)


class StockMergeAssistantForm(forms.Form):
    left_id = forms.IntegerField(widget=forms.HiddenInput())
    right_id = forms.IntegerField(widget=forms.HiddenInput())
    survivor_side = forms.ChoiceField(label="Ana Kayıt", choices=SOURCE_CHOICES, widget=forms.RadioSelect)
    name_source = forms.ChoiceField(label="Ürün Adı", choices=SOURCE_CHOICES, widget=forms.RadioSelect)
    sku_source = forms.ChoiceField(label="SKU", choices=SOURCE_CHOICES, widget=forms.RadioSelect)
    category_source = forms.ChoiceField(label="Kategori", choices=SOURCE_CHOICES, widget=forms.RadioSelect)
    subgroup_source = forms.ChoiceField(label="Alt Grup", choices=SOURCE_CHOICES, widget=forms.RadioSelect)
    unit_source = forms.ChoiceField(label="Birim", choices=SOURCE_CHOICES, widget=forms.RadioSelect)
    confirm = forms.BooleanField(
        label="Bu işlemin geri alınamayacağını biliyorum ve birleştirme işlemini onaylıyorum.",
        required=True,
    )
