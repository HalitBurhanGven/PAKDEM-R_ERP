# PAKDEM-R ERP

PAKDEM-R ERP, Django tabanli bir stok, fiyat listesi, satis/iade ve operasyon yonetim uygulamasidir. Proje; stok kartlarini takip etmek, stok hareketlerini kaydetmek, Excel uzerinden veri aktarimi yapmak, fiyat listelerini eslestirmek ve veri kalitesini raporlamak icin hazirlanmistir.

## Proje Kapsami

Bu proje asagidaki temel ihtiyaclara odaklanir:

- Stok karti olusturma, duzenleme ve listeleme
- Stok giris/cikis hareketlerini kaydetme
- Satis ve iade fisleri olusturma
- Bekleyen fis ve taslak operasyon akisi
- Excel ile stok ice aktarma ve disa aktarma
- Excel tabanli fiyat listesi yukleme
- Fiyat listesi ile stok eslestirme
- Cakisan SKU ve ayni isimli urunleri analiz etme
- Stok birlestirme yardimcisi
- Profil kesim planlama ve raporlama ekranlari

## Baslica Moduller

### Stok Yonetimi

`Stock` modeli ile urun adi, kategori, alt grup, SKU, miktar ve birim bilgileri tutulur. Sistem, urun adini normalize eder ve kayitlar icin bir `identity_key` uretir. Bu sayede benzer veya cakisan stoklar daha saglikli yonetilir.

### Stok Hareketleri

`StockMovement` modeli ile giris ve cikis hareketleri takip edilir. Hareketler stok miktarini etkiler ve stok yetersizligi gibi durumlar servis katmaninda kontrol edilir.

### Satis / Iade Operasyonlari

`StockTransaction` ve `StockTransactionLine` yapilari sayesinde satis ve iade fisleri tutulur. Sistem:

- fis bazli kalemleri kaydeder,
- fis detay ekranlari sunar,
- yazdirilabilir ciktilar uretir,
- mevcut fislerden yeni islem baslatabilir,
- taslak fisleri askiya alip daha sonra devam ettirebilir.

### Fiyat Listeleri

`PriceList` ve `PriceItem` modelleri ile Excel dosyalarindan fiyat listesi ice aktarilir. Aktif fiyat listesi secilerek stoklarla iliskilendirme yapilabilir.

### Raporlama ve Veri Kalitesi

Rapor modulu; SKU cakismalari, ayni isimli urunler, fiyat eslesme sorunlari, fiyat liste karsilastirmalari ve stok birlestirme yardimcilari gibi veri kalitesi odakli araclar sunar.

### Excel Destegi

Projede `openpyxl` kullanilarak:

- stok listesi `.xlsx` olarak disa aktarilabilir,
- stok verisi Excel'den ice alinabilir,
- fiyat listeleri onizleme ile birlikte sisteme yuklenebilir.

## Teknolojiler

- Python
- Django 6
- SQLite
- openpyxl

## Klasor Yapisi

```text
django_erp_prep/
|-- core/                 # Django ayarlari, ana URL yonlendirmeleri
|-- core_app/             # Ana is kurallari, modeller, formlar, gorunumler
|   |-- reports/          # Rapor ekranlari ve rapor odakli akislari
|   |-- services/         # Is mantigi ve servis katmani
|   |-- templates/        # HTML sablonlari
|   |-- static/           # CSS, JS, gorseller
|-- manage.py
|-- db.sqlite3            # Gelistirme veritabani
```

## Kurulum

### 1. Repoyu klonlayin

```bash
git clone https://github.com/HalitBurhanGven/PAKDEM-R_ERP.git
cd PAKDEM-R_ERP
```

### 2. Sanal ortam olusturun

Windows:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

macOS / Linux:

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Bagimliliklari kurun

Bu projede en az su paketlere ihtiyac vardir:

```bash
pip install django openpyxl
```

Isterseniz daha sonra `requirements.txt` de eklenebilir.

### 4. Migration calistirin

```bash
python manage.py migrate
```

### 5. Gelistirme sunucusunu baslatin

```bash
python manage.py runserver
```

Uygulama varsayilan olarak `http://127.0.0.1:8000/` adresinde calisir.

## Uygulama Icindeki Ana Alanlar

- `/` : Ana sayfa ve operasyon giris ekrani
- `/admin/` : Django admin paneli
- stok listesi, stok hareketleri ve kategori ekranlari
- fiyat listesi yukleme ve listeleme ekranlari
- `/rapor/` : rapor ve analiz ekranlari

## One Cikan Ozellikler

- Stoklar icin kimliklendirme ve muhtemel birlestirme mantigi
- Toplu satis girisi onizleme destegi
- Iade fislerini mevcut satis fislerinden baslatabilme
- Fiyat listesinden stok olusturma akisi
- Veri kalitesi ve cakisma tespiti raporlari
- Yazdirilabilir fis ve teslim formu sayfalari
- Profil kesim optimizasyonu araci

## Gelistirme Notlari

- Varsayilan veritabani `SQLite` olarak ayarlanmistir.
- Ayarlar dosyasinda gelistirme modu aciktir (`DEBUG = True`).
- Uretim ortamina cikmadan once `SECRET_KEY`, `ALLOWED_HOSTS`, veritabani ve guvenlik ayarlari tekrar duzenlenmelidir.
- Repoda sanal ortam (`venv/`) ve yerel veritabani dosyasi Git takibine alinmamistir.

## Testler

Projede stok, fiyat eslestirme, operasyon akisi ve import servisleri icin test dosyalari bulunur. Testleri calistirmak icin:

```bash
python manage.py test
```

## Gelecekte Eklenebilecekler

- `requirements.txt`
- ortam degiskeni tabanli ayar yonetimi
- PostgreSQL destegi
- kullanici yetkilendirme ve rol yonetimi
- CI/CD ve otomatik test akisi

## Lisans

Bu repo icin henuz acik bir lisans tanimi eklenmemistir. Gerekirse uygun bir lisans dosyasi eklenebilir.
