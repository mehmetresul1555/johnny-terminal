# Johnny Terminal

BIST günlük trade karar destek sistemi (v0.2).

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
menüden kendi CSV/Excel dosyanızı da yükleyebilirsiniz.

v0.2 ile birlikte hazır alt skorlar (`teknik_skor` vb.) yerine **ham
gösterge verileri** kullanılıyor; Johnny bu skorları kendi hesaplıyor.
Dosyanın aşağıdaki kolonları içermesi gerekir:

| Kolon | Zorunlu mu | Açıklama |
|---|---|---|
| `hisse` | Evet | Hisse kodu (örn. THYAO) |
| `fiyat` | Evet | Güncel fiyat |
| `rsi` | Evet | RSI (14) değeri |
| `macd_signal` | Evet | MACD - sinyal farkı (histogram); pozitif/negatif |
| `ema20` | Evet | 20 günlük EMA |
| `ema50` | Evet | 50 günlük EMA |
| `ema200` | Evet | 200 günlük EMA |
| `adx` | Evet | ADX (trend gücü) |
| `atr_pct` | Evet | Günlük ATR'nin fiyata oranı (%) |
| `volume_ratio` | Evet | Güncel hacim / ortalama hacim oranı |
| `fk` | Evet | Fiyat/Kazanç oranı |
| `pddd` | Evet | Piyasa Değeri/Defter Değeri oranı |
| `roe` | Evet | Özkaynak karlılığı (%) |
| `net_borc_favok` | Evet | Net Borç/FAVÖK (kaldıraç çarpanı) |
| `haber_puani` | Evet | Haber/KAP/katalizör puanı (0-10, elle veya Fintables'tan) |
| `kurumsal_puani` | Evet | Kurumsal beklenti puanı (0-10) |
| `piyasa_rejimi` | Evet | Piyasa rejimi puanı (0-10) |

Alt skorlar kendi maksimum değerlerinin üzerine çıkarsa otomatik olarak
sınırlanır (clip edilir); eksik/bozuk veri güvenli varsayılanlarla (0 veya
nötr bir değer) işlenir, uygulama çökmez.

## Johnny Score nedir?

Johnny Score, bir hissenin günlük trade adayı olarak ne kadar güçlü
olduğunu gösteren 0-100 arası bir puandır. Altı alt skorun toplamından
oluşur. İlk üçü ham göstergelerden ayrı birer "motor" tarafından
hesaplanır, son üçü CSV'de doğrudan puan olarak verilir:

- **Teknik** — 30 puan (`scoring/technical_engine.py`) — RSI, EMA20/50/200
  hizalanması, ADX, MACD
- **Momentum** — 20 puan (`scoring/momentum_engine.py`) — hacim oranı, ATR,
  fiyatın EMA20'ye göre momentumu
- **Bilanço/Temel** — 20 puan (`scoring/fundamental_engine.py`) — F/K,
  PD/DD, ROE, Net Borç/FAVÖK
- **Haber/KAP/Katalizör** — 10 puan (`haber_puani` kolonundan doğrudan)
- **Kurumsal beklenti** — 10 puan (`kurumsal_puani` kolonundan doğrudan)
- **Piyasa rejimi** — 10 puan (`piyasa_rejimi` kolonundan doğrudan)

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
kısa bir gerekçe cümlesi üretilir.

## Klasör yapısı

```
johnny-terminal/
├── app.py                        # Streamlit arayüzü
├── data/
│   └── sample_data.csv           # Örnek veri (ham göstergeler)
├── scoring/
│   ├── johnny_score.py           # Johnny Score v2 - toplam skor, durum, risk seviyeleri
│   ├── technical_engine.py       # Teknik skor motoru (30 puan)
│   ├── momentum_engine.py        # Momentum skor motoru (20 puan)
│   └── fundamental_engine.py     # Bilanço/temel skor motoru (20 puan)
├── config/
│   └── watchlist.yaml            # Watchlist, eşikler, risk parametreleri
├── outputs/                      # Dışa aktarılan sonuç CSV'leri (git'e girmez)
└── requirements.txt
```

## Yol haritası

Bu MVP; CSV/Excel dosyalarından manuel/yarı otomatik veri okur. İleride
Fintables Pro entegrasyonu (`config/watchlist.yaml` içindeki `fintables`
bloğu) ile veri akışı otomatikleştirilecek. Sistem otomatik emir göndermez;
sadece karar destek sağlar.
