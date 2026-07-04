# Johnny Terminal

BIST günlük trade karar destek sistemi (MVP v0.1).

Bu araç **otomatik emir göndermez**. Her sabah BIST hisseleri arasından en iyi
3 trade adayını bulup her biri için alım aralığı, stop, hedef 1, hedef 2 ve
bir güven skoru (Johnny Score) üretir. Karar, emri gönderme işlemi kullanıcıya
aittir.

## Kurulum

1. Python 3.9+ kurulu olmalı (kontrol: `python3 --version`).
2. Proje klasörüne girin:
   ```
   cd johnny-terminal
   ```
3. Bağımlılıkları kurun:
   ```
   pip3 install -r requirements.txt
   ```

## Çalıştırma

```
streamlit run app.py
```

Komut, yerel bir sunucu başlatır ve tarayıcınızda otomatik olarak Johnny
Terminal arayüzünü açar. Kapatmak için, açılan terminal penceresinde
`Ctrl+C` yapın veya pencereyi kapatın (tarayıcı sekmesini kapatmak sunucuyu
durdurmaz).

Masaüstünden çift tıklayarak açmak isterseniz, proje klasöründeki
`Johnny Terminal.command` dosyasını kullanabilirsiniz.

## Veri kaynağı ve CSV kolonları

Uygulama varsayılan olarak `data/sample_data.csv` dosyasını okur. Sol
menüden kendi CSV/Excel dosyanızı da yükleyebilirsiniz. Dosyanın aşağıdaki
kolonları içermesi gerekir:

| Kolon | Zorunlu mu | Açıklama |
|---|---|---|
| `hisse` | Evet | Hisse kodu (örn. THYAO) |
| `fiyat` | Evet | Güncel fiyat |
| `teknik_skor` | Evet | Teknik analiz alt skoru (0-30) |
| `momentum_skor` | Evet | Momentum alt skoru (0-20) |
| `bilanco_skor` | Evet | Bilanço/temel alt skor (0-20) |
| `haber_skor` | Evet | Haber/KAP/katalizör alt skoru (0-10) |
| `kurumsal_skor` | Evet | Kurumsal beklenti alt skoru (0-10) |
| `piyasa_rejimi_skor` | Evet | Piyasa rejimi alt skoru (0-10) |
| `atr_pct` | Opsiyonel | Günlük ATR'nin fiyata oranı (%). Verilmezse %1.5 varsayılır |
| `gerekce_notu` | Opsiyonel | Analistin serbest metin notu (otomatik gerekçeye eklenir) |

Alt skorlar kendi maksimum değerlerinin üzerine çıkarsa otomatik olarak
sınırlanır (clip edilir); eksik/bozuk veri 0 kabul edilir.

## Johnny Score nedir?

Johnny Score, bir hissenin günlük trade adayı olarak ne kadar güçlü
olduğunu gösteren 0-100 arası bir puandır. Altı alt skorun toplamından
oluşur:

- **Teknik** — 30 puan
- **Momentum** — 20 puan
- **Bilanço/Temel** — 20 puan
- **Haber/KAP/Katalizör** — 10 puan
- **Kurumsal beklenti** — 10 puan
- **Piyasa rejimi** — 10 puan

Toplam skora göre durum ataması:

- **85 ve üzeri** → **AL**
- **70-84** → **İZLE**
- **70 altı** → **UZAK DUR**

AL veya İZLE durumundaki hisseler için alım aralığı, stop ve hedef
seviyeleri fiyat ile ATR yüzdesine göre hesaplanır ve şu kurallara uyar:

- Stop mesafesi en fazla **%2**
- Hedef 1 en az **%1.5**
- Hedef 2 en az **%3**

UZAK DUR durumundaki hisseler için bu seviyeler hesaplanmaz (`-` gösterilir).

Her satır için ayrıca en güçlü ve en zayıf alt skorlara bakılarak otomatik
kısa bir gerekçe cümlesi üretilir; CSV'deki `gerekce_notu` doluysa bu not
gerekçenin başına eklenir.

## Klasör yapısı

```
johnny-terminal/
├── app.py                  # Streamlit arayüzü
├── data/
│   └── sample_data.csv     # Örnek veri
├── scoring/
│   └── johnny_score.py     # Johnny Score v1 hesaplama motoru
├── config/
│   └── watchlist.yaml      # Watchlist, eşikler, risk parametreleri
├── outputs/                # Dışa aktarılan sonuç CSV'leri (git'e girmez)
└── requirements.txt
```

## Yol haritası

Bu MVP; CSV/Excel dosyalarından manuel/yarı otomatik veri okur. İleride
Fintables Pro entegrasyonu (`config/watchlist.yaml` içindeki `fintables`
bloğu) ile veri akışı otomatikleştirilecek. Sistem otomatik emir göndermez;
sadece karar destek sağlar.
