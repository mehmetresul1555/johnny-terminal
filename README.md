# Johnny Terminal

BIST günlük trade karar destek sistemi (v1.0).

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
   Teknik göstergeler (RSI/MACD/EMA/ADX/ATR) artık TradingView'in
   herkese açık uç noktasından `tradingview-ta` kütüphanesiyle alınıyor
   (bkz. aşağıda); bu kütüphane `requirements.txt` ile birlikte kurulur,
   ayrı bir kurulum adımı veya giriş/hesap gerekmez.

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

Johnny Terminal'in ana veri kaynağı **Fintables Pro tarayıcı
otomasyonu**dur (`integrations/fintables_browser.py`). Fintables'ın
resmi bir API'si olmadığı için Playwright ile kullanıcının KENDİ
oturumu üzerinden ilgili sayfalar açılıp okunur.

**Nasıl çalışır (giriş):**

1. Sol menüden "Fintables (Tarayıcı Otomasyonu)" seçili (varsayılan).
2. **"🌐 Tarayıcıyı Aç ve Giriş Yap"** butonuna basın — gerçek bir
   tarayıcı penceresi açılır, Fintables giriş sayfasına gider.
3. Bu pencerede **kendi kullanıcı adı/şifrenizle ELLE** giriş yapın.
   Johnny bu forma hiçbir şekilde dokunmaz, şifrenizi görmez.
4. Giriş yaptıktan sonra pencereyi kapatın. Oturumunuz (çerezler +
   localStorage) lokalde `integrations/.sessions/fintables_session.json`
   dosyasına kaydedilir — bu dosya asla git'e commit'lenmez
   (`.gitignore`'da), asla bir yere gönderilmez.

**v1.0 FINAL REVİZYONU akış ("🔄 Fintables'tan Güncelle" butonuna her bastığınızda):**

1. Kayıtlı oturumla Hisse Radar ana tablosu (`https://fintables.com/radar/hisse-senetleri`) açılıp okunur (~640 hisse). Tarayıcı SADECE bu adım için kullanılır.
2. Radar verisiyle basit, şeffaf bir **ön eleme** yapılır (`scoring/pre_screen.py`) — hacim, günlük değişim ve kısa vadeli getiri kolonlarının percentile rank ortalamasına göre.
3. Ön elemeden geçen **ilk 20 aday** (`config/watchlist.yaml` -> `fintables.pre_screen.top_n`) seçilir. Radar okuma bitince tarayıcı hemen kapatılır.
4. Bu 20 aday için RSI, MACD (histogram), EMA20/50/200, ADX, ATR% **Fintables'tan değil doğrudan TradingView'in herkese açık teknik analiz uç noktasından** (`integrations/tradingview_indicators.py`, `tradingview-ta` kütüphanesi) alınır — önce tek bir toplu istekle, o başarısız olursa hisse başına tek tek denenerek. Giriş/hesap/tarayıcı gerekmez, basit bir HTTP isteğidir.
5. TradingView'den veri alınamayan bir hisse için (sembol bulunamadı, zaman aşımı vb.) o hissenin teknik alanları **None** bırakılır ve loglanır; hisse yine de listede kalır, ATLANMAZ.
6. Birleşen ham veri, mevcut Kolon Eşleştirme adımına gönderilir; oradan Johnny Score hesaplanır ve Top 3 gösterilir.

Her adım (Fintables Radar okundu, ilk 20 aday seçildi, TradingView {SEMBOL} teknik veri alındı/alınamadı, teknik veriler birleştirildi, Johnny Score hesaplandı, Top 3 hazır) buton altında canlı bir günlük olarak gösterilir.

**PASİF olan eski yöntem:** v1.0 FINAL'de RSI/MACD/EMA/ADX/ATR, Fintables'ın hisse detay/işlem ekranı sayfasındaki TradingView grafik widget'ının "legend" metin kutularından okunuyordu (`integrations/fintables_browser.py` içindeki `read_technical_indicators`, `fetch_technical_detail` vb.). Bu yöntem güvenilir bulunmadı: EMA20/EMA50/EMA200 gibi göstergeler kullanıcı grafiğe elle eklemediyse hiç görünmüyordu, ayrıca canvas/iframe tabanlı kırılgan bir DOM bağımlılığıydı. Bu fonksiyonlar geriye dönük referans/tekil test için dosyada duruyor ama `run_full_update()` artık bunları ÇAĞIRMIYOR.

**Doğrulanmış sayfa yapısı (Radar):** Hisse Radar sayfasının DOM yapısı
`integrations/explore_fintables_dom.py` ile gerçek bir oturumda
tarandı: sayfa gerçek bir HTML `table.grid` kullanıyor
(`thead > tr > th` başlıklar, `tbody.grid.relative > tr > td` veri
satırları). `fetch_radar_table()` bu yapıya göre yazıldı; başlık ile
hücre sayısı uyuşmayan satırlar sessizce atlanmaz, terminale uyarı
olarak loglanıp güvenli şekilde atlanır. Sayfa ilk açıldığında ~640
satırın tamamı DOM'da görünmeyebileceğinden, tablo okunmadan önce
mümkün olduğunca çok satırın yüklenmesi için EN İYİ ÇABA (best-effort,
doğrulanmamış) bir aşağı kaydırma denemesi yapılır. Şimdilik sadece
sayfa ilk açıldığında görünen "Getiri" sekmesindeki tablo okunur;
filtre/sekme değiştirme henüz yapılmıyor (bilinçli kapsam sınırlaması).

**TradingView teknik veri kaynağı (güncel yöntem):** Teknik göstergeler
`https://scanner.tradingview.com/{screener}/scan` uç noktasından
(TradingView'in kendi "Teknik Analiz" widget'ının kullandığı, kimlik
doğrulama GEREKTİRMEYEN herkese açık bir uç nokta) alınır. Kullanılan
kütüphane `tradingview-ta` (PyPI, MIT lisanslı,
github.com/AnalyzerREST/python-tradingview-ta) — basit bir HTTP POST
isteği atar, tarayıcı otomasyonu ya da giriş yoktur. BIST hisseleri
`"BIST:{KOD}"` formatında (örn. `"BIST:AKBNK"`) sorgulanır;
`config/watchlist.yaml` -> `tradingview` bloğunda `screener: "turkey"`,
`exchange: "BIST"`, `interval: "1d"` ayarlıdır. `ATR`, kütüphanenin
varsayılan gösterge listesinde olmadığı için ayrıca istenir
(`additional_indicators=["ATR"]`); `atr_pct` bu ATR değeri fiyata
bölünerek hesaplanır, `macd_signal` ise MACD çizgisi ile sinyal
çizgisi farkı (histogram) olarak hesaplanır. **Not:** Bu entegrasyon
kod incelemesi ve mock (sahte modül) testleriyle doğrulandı; sandbox
ağ kısıtlamaları nedeniyle gerçek TradingView API'sine karşı canlı
test yapılamadı — `pip install tradingview-ta` sonrası kendi
makinenizde bir kez "🔄 Fintables'tan Güncelle" ile deneyip günlükteki
"TradingView ... teknik veri alındı/alınamadı" satırlarını kontrol
etmeniz önerilir.

**PASİF: Eski Fintables Detay/Teknik göstergeler DOM yöntemi (referans
için):** `integrations/explore_fintables_detail_dom.py` ile AKBNK
üzerinde yapılan DOM taramasında, hisse detay/işlem ekranı sayfasında
(`https://fintables.com/islem-ekrani?code={TICKER}`) bir TradingView
grafik widget'ının `blob:` URL'li bir `<iframe>` içinde, göstergelerin
ise bir `<canvas>` üzerinde (DOM'dan okunamaz) render edildiği, ama her
göstergenin ayrıca `[data-name='legend-source-item']` seçicili bir
"legend" metin kutusunda da göründüğü tespit edilmişti. Bu yöntem artık
kullanılmıyor (yukarıdaki TradingView uç noktası yöntemine geçildi);
ilgili kod (`read_technical_indicators`, `ensure_indicators_visible`
vb.) `integrations/fintables_browser.py` içinde sadece referans/tekil
test amacıyla duruyor.

Farklı bir Radar görünümü/filtresi kullanmak isterseniz
`config/watchlist.yaml` -> `fintables.screener_url` değerini kendi
kaydettiğiniz sayfa URL'iyle değiştirebilirsiniz.

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
| `rsi` | Opsiyonel | RSI (14) değeri. Fintables otomasyonunda TradingView'den alınır (bkz. yukarıda); alınamazsa nötr varsayımla hesaplanır (bkz. aşağıda). |
| `macd_signal` | Opsiyonel | MACD histogramı (MACD-Sinyal farkı); pozitif/negatif. Aynı şekilde opsiyonel. |
| `ema20` | Opsiyonel | 20 günlük EMA. TradingView'den alınır. |
| `ema50` | Opsiyonel | 50 günlük EMA. |
| `ema200` | Opsiyonel | 200 günlük EMA. |
| `adx` | Opsiyonel | ADX (trend gücü). |
| `atr_pct` | Opsiyonel | Günlük ATR'nin fiyata oranı (%). TradingView'den gelen ATR (mutlak) değeri fiyata bölünerek yüzdeye çevirilir. |
| `volume_ratio` | Evet | Güncel hacim / ortalama hacim oranı |
| `fk` | Evet | Fiyat/Kazanç oranı |
| `pddd` | Evet | Piyasa Değeri/Defter Değeri oranı |
| `roe` | Evet | Özkaynak karlılığı (%) |
| `net_borc_favok` | Evet | Net Borç/FAVÖK (kaldıraç çarpanı) |
| `haber_puani` | Opsiyonel | Haber/KAP/katalizör puanı (0-10). Fintables bunu sağlamaz; yoksa **varsayılan 5/10**. İleride KAP entegrasyonuyla otomatikleşecek. |
| `kurumsal_puani` | Opsiyonel | Kurumsal beklenti puanı (0-10). Fintables bunu sağlamaz; yoksa **varsayılan 5/10**. İleride analist hedef fiyatlarından otomatikleşecek. |
| `piyasa_rejimi` | Opsiyonel | Piyasa rejimi puanı (0-10). Fintables bunu sağlamaz; yoksa **varsayılan 5/10**. İleride BIST100/XBANK/XUSIN/hacim/VIX/USD-TRY verilerinden Johnny tarafından otomatik hesaplanacak. |
| `yeni_is_iliskisi` | Opsiyonel | Yeni bir iş ilişkisi/ortaklık var mı (1/0). Rule Engine'in R4 kuralı için kullanılır; yoksa 0 kabul edilir |

`haber_puani`, `kurumsal_puani` ve `piyasa_rejimi` Johnny'nin kendi
öznel değerlendirmeleridir — Fintables (veya başka bir piyasa verisi
sağlayıcısı) bunları asla kolon olarak sunmaz. Bu yüzden kullanıcının
bunları hiçbir zaman elle doldurması beklenmez; eksik olduklarında
nötr bir varsayılan (5/10, ne olumlu ne olumsuz) kullanılır ve "Johnny
neden bu puanı verdi?" bölümünde "veri yok, nötr varsayılan kullanıldı"
notuyla açıkça belirtilir.

`rsi`, `macd_signal`, `ema20`, `ema50`, `ema200`, `adx`, `atr_pct` de
v1.0 FINAL ile opsiyonel hale getirildi: Fintables otomasyonu bu
göstergeleri artık TradingView'den almaya çalışır (bkz. "Fintables
Kurulumu"), ama bir hisse TradingView'de bulunamazsa ya da istek
başarısız olursa eksik kalabilir. Eksik olduklarında
`scoring/technical_engine.py` ve `scoring/momentum_engine.py`
nötr/makul varsayımlarla çalışır (asla çökmez) ve "Johnny neden bu
puanı verdi?" bölümünde hangi göstergelerin eksik olduğu açıkça
listelenir.

Diğer tüm alt skorlar kendi maksimum değerlerinin üzerine çıkarsa
otomatik olarak sınırlanır (clip edilir); eksik/bozuk veri güvenli
varsayılanlarla işlenir, uygulama çökmez.

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
│   ├── fintables_browser.py      # Playwright ile Fintables Radar okuma + run_full_update orkestratörü (eski detay/legend-DOM fonksiyonları PASİF, referans için duruyor)
│   ├── tradingview_indicators.py # TradingView'in herkese açık uç noktasından RSI/MACD/EMA/ADX/ATR çekme (tradingview-ta kütüphanesi, giriş gerektirmez)
│   ├── explore_fintables_dom.py  # Tek seferlik DOM keşif aracı - Radar tablosu (terminalden çalıştırılır)
│   ├── explore_fintables_detail_dom.py  # Tek seferlik DOM keşif aracı - hisse detay/Teknik Analiz sayfası (PASİF akış için referans)
│   └── .sessions/                # Kayıtlı oturum (git'e girmez, .gitignore'da)
├── data/
│   └── sample_data.csv           # Örnek veri (ham göstergeler, standart kolon adlarıyla)
├── scoring/
│   ├── johnny_score.py           # Johnny Score v3 - taban puan + kural bonusu, durum, risk seviyeleri
│   ├── technical_engine.py       # Teknik skor motoru (30 puan)
│   ├── momentum_engine.py        # Momentum skor motoru (20 puan)
│   ├── fundamental_engine.py     # Bilanço/temel skor motoru (20 puan)
│   ├── rule_engine.py            # IF/THEN kural motoru (confluence bonusları)
│   └── pre_screen.py             # v1.0: Radar verisiyle ilk N adayı seçen ön eleme mantığı
├── config/
│   └── watchlist.yaml            # Watchlist, eşikler, risk, skorlama ve Fintables parametreleri
├── outputs/                      # Dışa aktarılan sonuç CSV'leri (git'e girmez)
└── requirements.txt
```

## Yol haritası

Johnny Terminal'in ana veri kaynağı Fintables Radar tarayıcı
otomasyonudur (ön eleme için); manuel CSV/Excel yükleme ve örnek veri
seçenekleri yedek olarak duruyor. v1.0 FINAL REVİZYONU ile teknik
gösterge kaynağı Fintables'ın kırılgan legend-DOM okumasından
TradingView'in herkese açık, giriş gerektirmeyen teknik analiz uç
noktasına taşındı (bkz. "Fintables Kurulumu" ve
`integrations/tradingview_indicators.py`). Akış artık: Radar → ilk 20
aday → TradingView teknik veri → Johnny Score → Top 3.

Bilinen sınırlama: Bu ortamdaki ağ kısıtlamaları nedeniyle
`tradingview-ta` kütüphanesi gerçek TradingView API'sine karşı canlı
test edilemedi; entegrasyon kod incelemesi + sahte (mock) modüllerle
uçtan uca test edildi. Kendi makinenizde bir kez canlı deneyip
günlükteki "TradingView ... teknik veri alındı/alınamadı" satırlarını
kontrol etmeniz önerilir.

Sıradaki olası adımlar:

- TradingView entegrasyonunun gerçek API ile canlı doğrulanması
  (yukarıdaki sınırlama nedeniyle henüz yapılamadı).
- Radar tablosunun ~640 satırının tamamının güvenilir şekilde
  yüklenmesi (şu an best-effort bir kaydırma denemesi var; Fintables'ın
  grid bileşeni tamamen sanallaştırılmışsa yetersiz kalabilir).
- `haber_puani`/`kurumsal_puani`/`piyasa_rejimi` için planlanan otomatik
  hesaplama (KAP entegrasyonu, analist hedef fiyatları, piyasa
  endeksleri/hacim verisi).

Sistem otomatik emir göndermez; sadece karar destek sağlar.
