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

**v1.0 "final akış" ("🔄 Fintables'tan Güncelle" butonuna her bastığınızda):**

1. Kayıtlı oturumla Hisse Radar ana tablosu (`https://fintables.com/radar/hisse-senetleri`) açılıp okunur (~640 hisse).
2. Radar verisiyle basit, şeffaf bir **ön eleme** yapılır (`scoring/pre_screen.py`) — hacim, günlük değişim ve kısa vadeli getiri kolonlarının percentile rank ortalamasına göre.
3. Ön elemeden geçen **ilk 10 aday** (`config/watchlist.yaml` -> `fintables.pre_screen.top_n`) seçilir.
4. **Sadece bu 10 hissenin** detay/Teknik Analiz sayfasına girilir — kalan ~630 hissenin detayına HİÇ girilmez.
5. Her aday için RSI, MACD, EMA20/50/200, ADX, ATR okunur ve Radar verisiyle birleştirilir.
6. Birleşen ham veri, mevcut Kolon Eşleştirme adımına gönderilir; oradan Johnny Score hesaplanır ve Top 3 gösterilir.

Bu akış tek bir tarayıcı oturumunda, adaylar SIRAYLA (paralel değil) gezilerek çalışır; her hisse arasında kısa, rastgele bir bekleme bırakılır (`fintables.detay.bekleme_min_sn` / `bekleme_max_sn`, varsayılan 2-4 saniye) — "yavaş ve güvenli" çalışma prensibi. Bir hissenin detay sayfası açılamaz/okunamazsa o hisse ATLANIR ve arayüzde "⚠️ Atlanan hisseler" bölümünde nedeniyle birlikte listelenir; sistem durmaz, kalan adaylarla devam eder. İlerleme adımları buton altında canlı bir günlük olarak gösterilir.

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

**DOĞRULANMADI (Detay/Teknik Analiz sayfası):** `fetch_technical_detail`
ve `run_full_update`'in kullandığı hisse detay sayfası URL şablonu
(`config/watchlist.yaml` -> `fintables.detay.url_template`) ve CSS
seçicileri (`fintables.detay.selectors`) henüz gerçek bir Fintables
hisse detay sayfası üzerinde DOM taramasıyla doğrulanmadı — şu an yer
tutucudur (seçiciler varsayılan olarak boştur). Radar tablosunda
yapıldığı gibi (`explore_fintables_dom.py`), bir hissenin gerçek Teknik
Analiz sayfası açılıp DOM'u incelenmeli, ardından
`config/watchlist.yaml` -> `fintables.detay.selectors` gerçek CSS
seçicileriyle doldurulmalıdır. Seçiciler boş/yanlış olduğu sürece
teknik alanlar boş (`None`) gelir; bu sistemi çökertmez ama teknik
skorlar eksik veriyle (nötr varsayılanlarla) hesaplanır.

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
│   ├── fintables_browser.py      # Playwright ile Fintables tarayıcı otomasyonu (Radar okuma, ön eleme sonrası detay okuma, run_full_update orkestratörü)
│   ├── explore_fintables_dom.py  # Tek seferlik DOM keşif aracı (terminalden çalıştırılır)
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

Johnny Terminal'in ana veri kaynağı Fintables tarayıcı otomasyonudur;
manuel CSV/Excel yükleme ve örnek veri seçenekleri yedek olarak
duruyor. v1.0 ile Radar ön eleme + ilk 10 adayın detay/Teknik Analiz
sayfasından teknik veri okuma akışı eklendi (bkz. "Fintables Kurulumu").

Sıradaki olası adımlar:

- Hisse detay/Teknik Analiz sayfasının gerçek DOM yapısının
  `explore_fintables_dom.py` benzeri bir araçla taranıp
  `config/watchlist.yaml` -> `fintables.detay.selectors` ve
  `url_template` değerlerinin doğrulanması (şu an yer tutucu).
- Radar tablosunun ~640 satırının tamamının güvenilir şekilde
  yüklenmesi (şu an best-effort bir kaydırma denemesi var; Fintables'ın
  grid bileşeni tamamen sanallaştırılmışsa yetersiz kalabilir).
- `haber_puani`/`kurumsal_puani`/`piyasa_rejimi` için planlanan otomatik
  hesaplama (KAP entegrasyonu, analist hedef fiyatları, piyasa
  endeksleri/hacim verisi).

Sistem otomatik emir göndermez; sadece karar destek sağlar.
