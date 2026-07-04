# Johnny Terminal

BIST günlük trade karar destek sistemi (v0.5).

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
4. Fintables tarayıcı otomasyonunu kullanacaksanız (opsiyonel — manuel
   CSV/Excel yükleme veya örnek veri olmadan da uygulama çalışır),
   Playwright'ın tarayıcı motorunu da indirin:
   ```
   playwright install chromium
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

## Fintables Kurulumu (tarayıcı otomasyonu)

v0.5 ile Johnny Terminal'in ana veri kaynağı **Fintables Pro tarayıcı
otomasyonu**dur (`integrations/fintables_browser.py`). Fintables'ın
resmi bir API'si olmadığı için Playwright ile kullanıcının KENDİ
oturumu üzerinden ilgili sayfa açılıp okunur.

**Nasıl çalışır:**

1. Sol menüden "Fintables (Tarayıcı Otomasyonu)" seçili (varsayılan).
2. **"🌐 Tarayıcıyı Aç ve Giriş Yap"** butonuna basın — gerçek bir
   tarayıcı penceresi açılır, Fintables giriş sayfasına gider.
3. Bu pencerede **kendi kullanıcı adı/şifrenizle ELLE** giriş yapın.
   Johnny bu forma hiçbir şekilde dokunmaz, şifrenizi görmez.
4. Giriş yaptıktan sonra pencereyi kapatın. Oturumunuz (çerezler +
   localStorage) lokalde `integrations/.sessions/fintables_session.json`
   dosyasına kaydedilir — bu dosya asla git'e commit'lenmez
   (`.gitignore`'da), asla bir yere gönderilmez.
5. **"🔄 Fintables'tan Güncelle"** butonuna her bastığınızda, kayıtlı
   oturumla Hisse Radar/Tarama sayfası açılıp tablo okunur ve Kolon
   Eşleştirme adımına gönderilir. Bu tamamen manuel/tek seferlik bir
   tetiklemedir; arka planda otomatik veya periyodik bir tarama yapılmaz.

**Zorunlu ayar — `config/watchlist.yaml` -> `fintables.screener_url`:**
Fintables hesabınızda Hisse Radar/Tarama sayfasını açıp adres
çubuğundaki gerçek URL'i bu alana yapıştırmanız gerekir; Johnny bu
URL'i tahmin edemez, hesabınıza/kaydettiğiniz filtreye göre değişebilir.

**CSS seçiciler:** Fintables'ın tabloyu nasıl render ettiğini (gerçek
bir HTML `<table>` mi, yoksa özel bir grid bileşeni mi) doğrulamadan bu
modül yazıldı. Sayfa standart bir `<table>` değilse
`integrations/fintables_browser.py` içindeki `fetch_screener_table`
fonksiyonunun seçici tabanlı okuma kısmını gerçek sayfa yapısına göre
tamamlamanız gerekebilir; `config/watchlist.yaml` -> `fintables.selectors`
altından seçicileri güncelleyin.

**Kullanım şartları uyarısı:** Otomasyonu etkinleştirmeden önce
Fintables'ın güncel kullanım şartlarını kontrol edin. Johnny yalnızca
sizin kendi Pro hesabınızla zaten görebildiğiniz sayfaları, siz butona
bastığınızda tek seferlik okur; bot-koruması/CAPTCHA aşma girişimi ya da
arka planda agresif/periyodik bir tarama yapmaz. Bu araç sizin adınıza
kullanım şartlarına uygunluğu garanti etmez — sorumluluk kullanıcıya
aittir.

**Oturum sorunu yaşarsanız:** Sol menüdeki "Oturum yönetimi" altından
"🗑️ Oturumu Sil" ile kayıtlı oturumu silip 2. adımdan yeniden başlayın.

## Veri kaynağı ve CSV kolonları

Manuel CSV/Excel yükleme ve örnek veri seçenekleri de korunmuştur — sol
menüden "Dosya yükle (CSV / Excel)" veya "Örnek veri" seçebilirsiniz.
Varsayılan örnek veri `data/sample_data.csv` dosyasından okunur.

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
| `yeni_is_iliskisi` | Opsiyonel | Yeni bir iş ilişkisi/ortaklık var mı (1/0). Rule Engine'in R4 kuralı için kullanılır; yoksa 0 kabul edilir |

Alt skorlar kendi maksimum değerlerinin üzerine çıkarsa otomatik olarak
sınırlanır (clip edilir); eksik/bozuk veri güvenli varsayılanlarla (0 veya
nötr bir değer) işlenir, uygulama çökmez.

## Johnny Score nedir?

v0.3 ile birlikte Johnny Score artık alt skorların düz (lineer) toplamı
**değildir**. İki katmanlı çalışır:

1. **Taban puan** — altı alt skorun toplamı, ama son skora tam ağırlığıyla
   yansımaz; `config/watchlist.yaml` içindeki `scoring.base_damping`
   katsayısıyla (varsayılan **0.6**) sıkıştırılır.
2. **Kural motoru bonusu** (`scoring/rule_engine.py`) — göstergeler
   arasındaki IF/THEN kombinasyonları (confluence) tetiklendiğinde sabit
   bonus puan ekler. Asıl farklılaştırıcı puan artık buradan gelir: "her
   şeyde ortalama iyi" ama hiçbir güçlü kombinasyonu yakalamayan bir hisse
   ile birden fazla güçlü sinyali AYNI ANDA taşıyan bir hisse artık aynı
   şekilde puanlanmaz.

```
Toplam = clip(taban_puan × base_damping + kural_bonusu, 0, 100)
```

Taban puanın altı bileşeni:

- **Teknik** — 30 puan (`scoring/technical_engine.py`) — RSI, EMA20/50/200
  hizalanması, ADX, MACD
- **Momentum** — 20 puan (`scoring/momentum_engine.py`) — hacim oranı, ATR,
  fiyatın EMA20'ye göre momentumu
- **Bilanço/Temel** — 20 puan (`scoring/fundamental_engine.py`) — F/K,
  PD/DD, ROE, Net Borç/FAVÖK
- **Haber/KAP/Katalizör** — 10 puan (`haber_puani` kolonundan doğrudan)
- **Kurumsal beklenti** — 10 puan (`kurumsal_puani` kolonundan doğrudan)
- **Piyasa rejimi** — 10 puan (`piyasa_rejimi` kolonundan doğrudan)

### Rule Engine kuralları (`scoring/rule_engine.py`)

| Kural | Koşul | Bonus |
|---|---|---|
| R1 | EMA20 > EMA50 > EMA200 + MACD pozitif + ADX > 25 | +10 |
| R2 | RSI 55-65 + Hacim oranı > 1.5 | +8 |
| R3 | ROE > %25 + Net Borç/FAVÖK < 2 | +8 |
| R4 | Yeni iş ilişkisi + Kurumsal beklenti yüksek (≥8) | +7 |

Yeni bir kural eklemek için `scoring/rule_engine.py` içindeki `RULES`
listesine bir madde eklemek yeterlidir.

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

Her hisse için hem kısa bir gerekçe cümlesi hem de "Johnny neden bu puanı
verdi?" başlıklı, madde madde (taban analiz + tetiklenen kurallar) detaylı
bir açıklama üretilir; arayüzde Top 3 kartlarının altında ve tam tablonun
altındaki genişletilebilir bölümde görüntülenir.

## Kolon Eşleştirme (Fintables ve diğer kaynaklar için)

Fintables Pro'dan (veya başka bir kaynaktan) indirdiğiniz/kopyaladığınız
CSV/Excel dosyasının kolon adları Johnny'nin standart kolon adlarıyla
birebir aynı olmak zorunda değildir. "Dosya yükle" ile bir dosya
seçtiğinizde uygulama:

1. Dosyadaki kolon adlarını gösterir
2. `data_mapper.py` içindeki Türkçe/İngilizce takma ad (alias) sözlüğüyle
   her Johnny kolonu için otomatik bir eşleşme önerir (örn. "Son Fiyat" ->
   `fiyat`, "RSI(14)" -> `rsi`, "Net Borç/FAVÖK" -> `net_borc_favok`)
3. Eksik kalan veya yanlış eşleşen kolonlar için açılır menüden elle
   düzeltme yapabilirsiniz
4. Zorunlu kolonların tamamı eşleşmeden skorlama çalışmaz; eksik olanlar
   açıkça listelenir
5. Onaylanan eşleştirmeye göre temizlenmiş DataFrame `score_dataframe`'e
   gönderilir

Bu eşleştirme akışı hem manuel dosya yüklemede hem de Fintables tarayıcı
otomasyonundan gelen veride aynı şekilde çalışır (`app.py` ->
`render_kolon_eslestirme`). Yeni bir takma ad eklemek için
`data_mapper.py` içindeki `COLUMN_ALIASES` sözlüğüne bir satır eklemek
yeterlidir.

## Klasör yapısı

```
johnny-terminal/
├── app.py                        # Streamlit arayüzü
├── data_mapper.py                 # CSV/Excel kolon eşleştirme (Fintables vb. için)
├── integrations/
│   ├── fintables_browser.py      # Playwright ile Fintables tarayıcı otomasyonu
│   └── .sessions/                # Kayıtlı oturum (git'e girmez, .gitignore'da)
├── data/
│   └── sample_data.csv           # Örnek veri (ham göstergeler, standart kolon adlarıyla)
├── scoring/
│   ├── johnny_score.py           # Johnny Score v3 - taban puan + kural bonusu, durum, risk seviyeleri
│   ├── technical_engine.py       # Teknik skor motoru (30 puan)
│   ├── momentum_engine.py        # Momentum skor motoru (20 puan)
│   ├── fundamental_engine.py     # Bilanço/temel skor motoru (20 puan)
│   └── rule_engine.py            # IF/THEN kural motoru (confluence bonusları)
├── config/
│   └── watchlist.yaml            # Watchlist, eşikler, risk, skorlama ve Fintables parametreleri
├── outputs/                      # Dışa aktarılan sonuç CSV'leri (git'e girmez)
└── requirements.txt
```

## Yol haritası

v0.5 ile Johnny Terminal'in ana veri kaynağı Fintables tarayıcı
otomasyonu oldu; manuel CSV/Excel yükleme ve örnek veri seçenekleri
yedek olarak duruyor. Sıradaki olası adımlar: Fintables sayfa
yapısına göre `fetch_screener_table`'ın seçicilerinin gerçek sayfa
üzerinde doğrulanması/iyileştirilmesi ve çoklu sayfa/filtre desteği.
Sistem otomatik emir göndermez; sadece karar destek sağlar.
