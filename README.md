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

**v1.0 REVİZYON 2 akışı ("🔄 Fintables'tan Güncelle" butonuna her bastığınızda) — "kalite havuzu" pipeline'ı:**

Eskiden ilk top_n aday DOĞRUDAN Radar momentum sıralamasından seçilip TradingView/fundamental verisi SONRADAN, sadece bilgi amaçlı ekleniyordu — bu, veri akışı eksik/zayıf/yeni hisselerin de ilk 20'ye girmesine yol açabiliyordu. Johnny'nin amacı **"en yüksek uçuk getirili hisseler" değil, "verisi güvenilir, teknik + temel olarak kaliteli günlük trade adayları"** bulmaktır. Artık top_n'den DAHA BÜYÜK bir "kalite havuzu" oluşturulur ve final top_n, bu havuzun İÇİNDEN fundamental kalite + TradingView teknik veri mevcudiyeti süzgeçlerini geçen adaylardan seçilir:

1. Kayıtlı oturumla Hisse Radar ana tablosu (`https://fintables.com/radar/hisse-senetleri`) açılıp okunur (~640 hisse). Tarayıcı SADECE bu adım için kullanılır.
2. **Kaba filtre** (`scoring/pre_screen.kaba_filtrele`): çok düşük hacimli ya da fiyat/hacim verisi eksik/anlamsız olan hisseler AÇIKÇA ve KESİN olarak elenir (`fintables.pre_screen.min_hacim_percentile`, varsayılan en düşük hacimli %20).
3. **Kalite havuzu**: kalan hisselerden, momentum sinyaline göre `top_n * havuz_carpani` büyüklüğünde bir aday havuzu seçilir (`fintables.pre_screen.top_n`, `havuz_carpani`; varsayılan 20 x 2 = 40). Radar okuma bitince tarayıcı hemen kapatılır.
4. Havuzdaki HER aday için F/K, PD/DD, ROE (varsa Net Borç/FAVÖK) Fintables'ın **"Piyasa Çarpanları" ve "Rasyo Analiz Tablosu"** sayfalarından okunmaya çalışılır (bkz. aşağıda "Fundamental veri kaynağı"). Bot koruması çıkarsa ya da veri okunamazsa bu alanlar **None** bırakılır.
5. **Fundamental kalite süzgeci** (`scoring/fundamental_engine.fundamental_yeterlilik_kontrolu`): verisi çok eksik (`fundamental_min_dolu_alan`, varsayılan 4 alandan en az 2'si dolu) ya da skoru zayıf (`fundamental_min_skor_orani`, varsayılan skorun en az %25'i) olan adaylar havuzdan ELENİR. Eşikler bu turda çok katı kalıp HİÇBİR aday geçemezse, sistem çökmez — tüm havuzla best-effort devam edilir.
6. Fundamental süzgecinden geçen adaylar için RSI, MACD (histogram), EMA20/50/200, ADX, ATR% **doğrudan TradingView'in herkese açık teknik analiz uç noktasından** (`integrations/tradingview_indicators.py`, `tradingview-ta` kütüphanesi) alınır — önce tek bir toplu istekle, o başarısız/0% olursa hisse başına tek tek denenerek.
7. **Teknik veri süzgeci** (`teknik_veri_mevcut_mu`, `fintables.pre_screen.teknik_veri_zorunlu`, varsayılan açık): TradingView'de HİÇ bulunamayan (tüm göstergeleri boş dönen) adaylar "güçlü havuz"tan çıkarılır.
8. **Final top_n seçimi**: önce güçlü havuzdan (fundamental + teknik süzgeçleri geçen) top_n aday seçilir. Yeterli aday kalmazsa, teknik verisi olmayan ama fundamental'i yeterli adaylarla **"düşük güven" (`_dusuk_guven`)** işaretiyle doldurulur — sistem asla çökmez ya da boş dönmez. Birleşen ham veri, mevcut Kolon Eşleştirme adımına gönderilir; oradan Johnny Score hesaplanır ve sadece işlem yapılabilir fırsatlar gösterilir (bkz. "Johnny bir trade asistanıdır" bölümü).

   **v1.0 revizyonu (kullanıcı isteği - "Top 20 aday oluştururken amaç maksimum puan değil, gerçekten kaliteli adaylar olmalı"):** final top_n sıralaması eskiden HAM Radar momentumuna (`_on_eleme_skoru`: hacim + gün % + kısa vadeli getiri rank toplamı — bu skor sadece 40'lık kalite havuzunu seçmek için, teknik/temel veri çekilmeden ÖNCE hesaplanan kaba bir ön-sinyaldi) göre yapılıyordu. Bu, momentumu yüksek ama teknik+temel olarak zayıf bir adayın, momentumu düşük ama gerçekten kaliteli bir adayın ÖNÜNE geçmesine yol açabiliyordu. Artık final sıralama, o ana kadar toplanan GERÇEK teknik+fundamental veriyle hesaplanan bir Johnny Score ön-hesabına göre yapılır (`fintables_browser._gercek_kaliteye_gore_skorla`, `scoring/johnny_score.compute_total_score` ile aynı formülü kullanır). Sadece 40'lık kalite havuzunu seçmek için kullanılan ilk momentum ön-eleme (adım 3) değişmedi — bu adımın henüz teknik/temel veri toplanmadan önce olması kaçınılmaz (aksi halde 640 hissenin tamamı için TradingView/fundamental isteği atmak gerekirdi).

Bir hissenin TradingView/fundamental verisi ağ hatası, bot koruması vb. yüzünden alınamazsa bu ayrı bir durumdur (alanlar None kalır, scoring nötr varsayımla devam eder) — (5) ve (7)'deki kalite süzgeçleri ise KASITLI olarak adayı tamamen havuzdan çıkarır, bu proje genelindeki "eksik veri = nötr puan" ilkesinin bilinçli bir istisnasıdır (sadece aday SEÇİMİ aşamasında).

Her adım (Fintables Radar okundu, kaba filtre sonucu, kalite havuzu seçildi, {SEMBOL} temel/teknik veri okundu/okunamadı, fundamental/teknik süzgeç sonuçları, düşük güven doldurma uyarıları, Johnny Score hesaplandı, fırsat taraması tamamlandı) buton altında canlı bir günlük olarak gösterilir.

**PASİF olan eski yöntem:** v1.0 FINAL'de RSI/MACD/EMA/ADX/ATR, Fintables'ın hisse detay/işlem ekranı sayfasındaki TradingView grafik widget'ının "legend" metin kutularından okunuyordu (`integrations/fintables_browser.py` içindeki `read_technical_indicators`, `fetch_technical_detail` vb.). Bu yöntem güvenilir bulunmadı: EMA20/EMA50/EMA200 gibi göstergeler kullanıcı grafiğe elle eklemediyse hiç görünmüyordu, ayrıca canvas/iframe tabanlı kırılgan bir DOM bağımlılığıydı. Bu fonksiyonlar geriye dönük referans/tekil test için dosyada duruyor ama `run_full_update()` artık bunları ÇAĞIRMIYOR.

**Doğrulanmış sayfa yapısı (Radar):** Hisse Radar sayfasının DOM yapısı
`integrations/explore_fintables_dom.py` ile gerçek bir oturumda
tarandı: sayfa gerçek bir HTML `table.grid` kullanıyor
(`thead > tr > th` başlıklar, `tbody.grid.relative > tr > td` veri
satırları). `fetch_radar_table()` bu yapıya göre yazıldı; başlık ile
hücre sayısı uyuşmayan satırlar sessizce atlanmaz, terminale uyarı
olarak loglanıp güvenli şekilde atlanır. Şimdilik sadece sayfa ilk
açıldığında görünen "Getiri" sekmesindeki tablo okunur; filtre/sekme
değiştirme henüz yapılmıyor (bilinçli kapsam sınırlaması).

**BUG FIX: Radar'ın TAMAMI (~640 hisse) okunuyor.** Canlı testte,
Radar tablosunun virtual scrolling (sanal kaydırma) kullandığı ve
sayfa ilk açıldığında ~640 hisseden sadece bir kısmının (~23 satır)
DOM'da göründüğü tespit edildi — eski "tek seferlik oku" yaklaşımı bu
yüzden eksik veri üretiyordu. `_radar_sayfasindan_df_olustur`
(`integrations/fintables_browser.py`) artık şu döngüyü çalıştırır: DOM'da
o an görünen satırları hisse koduna göre bir sözlükte biriktir (aynı
hisse tekrar görülürse SADECE güncellenir, asla ikinci kez eklenmez —
duplicate yok), "Scroll N: Toplam hisse: X" olarak logla, tabloyu aşağı
kaydır, tekrar oku. Art arda `sabit_kalma_esigi` (varsayılan 5,
`config/watchlist.yaml` -> `fintables.radar_scroll`) turda yeni hisse
gelmezse tablonun sonuna ulaşıldığı kabul edilip durur; `max_deneme`
(varsayılan 150) sonsuz döngüye karşı bir güvenlik sınırıdır. Kaydırma
container'ının tam olarak ne olduğu (sayfa mı, grid'in kendi iç scroll
div'i mi) canlı DOM taramasıyla kesin doğrulanmadığı için
`_radar_scroll_tetikle` birden fazla yöntemi (JS ile en yakın
kaydırılabilir atayı bulup `scrollTop` ayarlama, fare tekerleği, "End"
tuşu) sırayla dener; hiçbiri işe yaramasa bile akış çökmez, o ana kadar
toplanan satırlarla devam eder. Ön eleme (ilk N aday seçimi) artık bu
TAM (~640 hisse) listeden yapılıyor.

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

**Fundamental veri kaynağı ve bot koruması bulgusu:** Fintables'ın ayrı
şirket/temel analiz ana sayfası (`https://fintables.com/sirketler/
{TICKER}`) genel olarak **Cloudflare bot koruması** arkasında olabilir
— headless otomasyonla açıldığında "Just a moment... Performing
security verification" (Cloudflare Managed Challenge) çıkabiliyor
(bkz. `integrations/explore_fintables_fundamental_dom.py` ile yapılan
ilk doğrulama). **Projenin kuralı gereği bu koruma aşılmaya
ÇALIŞILMIYOR** (CAPTCHA/bot-koruması aşma girişimi yasak); her sayfa
açılışında önce bu kontrol edilir, çıkarsa o sayfanın verisi için
hemen vazgeçilir.

İlk denemede bu verilerin hisse detay sayfasındaki "Karne" sekmesinde
olduğu varsayılmıştı; **bu varsayım canlı bir tarayıcı oturumuyla
(Claude in Chrome üzerinden) test edilirken YANLIŞ çıktı** — "Karne"
sekmesi F/K/PD/DD/ROE/Net Borç/FAVÖK değil, "Karlılık/Büyüme/Borçluluk"
başlıklı ayrı bir kalite skor kartı (bps değişimleri, evet/hayır
kontrolleri) gösteriyor. Aynı canlı oturumda **doğru sayfalar** tespit
edildi (düz HTML tablo, canvas değil):

- **F/K, PD/DD** → `https://fintables.com/sirketler/{TICKER}/oran-analizi/piyasa-carpanlari` ("Güncel" satırında F/K, PD/DD, FD/FAVÖK sırasıyla)
- **ROE** → `https://fintables.com/sirketler/{TICKER}/oran-analizi/rasyo-analiz-tablosu` ("Özkaynak Karlılığı" satırı, en güncel çeyrek)
- **Net Borç/FAVÖK** bu iki sayfada da ayrı bir kalem olarak bulunamadı; esnek bir metin araması denenir, bulunamazsa `None` kalır

`integrations/fintables_browser.py` -> `fetch_fundamental_for_symbol`
her aday için bu iki sayfayı sırayla açar; her açılışta önce bot
koruması kontrol edilir (çıkarsa o sayfa/hisse için None bırakılır),
sonra sayfanın görünür metninden esnek bir arama ile değerler
ayıklanır. Herhangi bir adımda başarısız olunursa (bot koruması, sayfa
açılamadı, etiket bulunamadı) o hissenin ilgili alanları `None` kalır —
**sistem çökmez, hisse listeden atılmaz**; `scoring/
fundamental_engine.py` bu durumda nötr (2.5/5 = yarı puan) bir
varsayımla çalışır ve "Johnny neden bu puanı verdi?" bölümünde
"Fundamental veri eksik, nötr varsayım kullanıldı" notuyla açıkça
belirtilir. Eski "Karne" tabanlı kod (`_karne_fetch_fundamental_for_symbol_PASIF`
ve ilgili yardımcılar) referans için dosyada duruyor ama artık
ÇAĞRILMIYOR.

**Not:** Bu yeni sayfa yapısı canlı bir tarayıcı ile görsel olarak
doğrulandı, ama Playwright'ın (headless) otomasyonuyla bu spesifik iki
sayfaya erişimin Cloudflare'e takılıp takılmayacağı henüz canlı test
edilmedi (bkz. sınırlamalar). Metin ayıklama esnek/genel bir yöntemle
yazıldı ve mock testlerle doğrulandı. Kendi makinenizde canlı
denedikten sonra günlükteki "... temel veriler okundu/okunamadı"
satırlarını kontrol etmeniz ve gerekirse `_etiket_sonrasi_ilk_degerler`
fonksiyonundaki etiket eşleşmelerini gerçek sayfa metnine göre ince
ayar yapmanız gerekebilir.

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
| `gun_yuzde` | Opsiyonel | Günlük fiyat değişim yüzdesi. Fintables Radar'dan her zaman gelir; Rule Engine R2'de kullanılır. |
| `getiri_1h` | Opsiyonel | Son 1 haftalık getiri yüzdesi. Fintables Radar'dan her zaman gelir; Rule Engine R2'de kullanılır. |
| `getiri_1a` | Opsiyonel | Son 1 aylık getiri yüzdesi. Fintables Radar'dan her zaman gelir; Rule Engine R4'te kullanılır. |
| `getiri_3a` | Opsiyonel | Son 3 aylık getiri yüzdesi. Fintables Radar'dan her zaman gelir; Rule Engine R4'te kullanılır. |
| `rsi` | Opsiyonel | RSI (14) değeri. Fintables otomasyonunda TradingView'den alınır (bkz. yukarıda); alınamazsa nötr varsayımla hesaplanır (bkz. aşağıda). |
| `macd_signal` | Opsiyonel | MACD histogramı (MACD-Sinyal farkı); pozitif/negatif. Aynı şekilde opsiyonel. |
| `ema20` | Opsiyonel | 20 günlük EMA. TradingView'den alınır. |
| `ema50` | Opsiyonel | 50 günlük EMA. |
| `ema200` | Opsiyonel | 200 günlük EMA. |
| `adx` | Opsiyonel | ADX (trend gücü). |
| `atr_pct` | Opsiyonel | Günlük ATR'nin fiyata oranı (%). TradingView'den gelen ATR (mutlak) değeri fiyata bölünerek yüzdeye çevirilir. |
| `volume_ratio` | Opsiyonel | Güncel hacim / ortalama hacim oranı. Fintables Radar bunu hiçbir zaman sağlamaz; yoksa nötr (1.0) varsayımla hesaplanır. |
| `fk` | Opsiyonel | Fiyat/Kazanç oranı. Fintables otomasyonunda "Piyasa Çarpanları" sayfasından alınmaya çalışılır; bot koruması çıkarsa ya da okunamazsa nötr varsayımla hesaplanır (bkz. aşağıda). |
| `pddd` | Opsiyonel | Piyasa Değeri/Defter Değeri oranı. Aynı şekilde "Piyasa Çarpanları" sayfasından, opsiyonel. |
| `roe` | Opsiyonel | Özkaynak karlılığı (%). "Rasyo Analiz Tablosu" sayfasından, opsiyonel. |
| `net_borc_favok` | Opsiyonel | Net Borç/FAVÖK (kaldıraç çarpanı). Fintables'ta ayrı bir kalem olarak bulunamadı; genelde None kalır, opsiyonel. |
| `haber_puani` | Opsiyonel | Haber/KAP/katalizör puanı (0-10). Fintables bunu sağlamaz; yoksa **varsayılan 5/10**. İleride KAP entegrasyonuyla otomatikleşecek. |
| `kurumsal_puani` | Opsiyonel | Kurumsal beklenti puanı (0-10). Fintables bunu sağlamaz; yoksa **varsayılan 5/10**. İleride analist hedef fiyatlarından otomatikleşecek. |
| `piyasa_rejimi` | Opsiyonel | Piyasa rejimi puanı (0-10). Fintables bunu sağlamaz; yoksa **varsayılan 5/10**. İleride BIST100/XBANK/XUSIN/hacim/VIX/USD-TRY verilerinden Johnny tarafından otomatik hesaplanacak. |
| `yeni_is_iliskisi` | Opsiyonel | Yeni bir iş ilişkisi/ortaklık var mı (1/0). v0.4 ile Rule Engine R4 artık bunu KULLANMIYOR (Fintables hiçbir zaman sağlamaz); alan geriye dönük uyumluluk için duruyor. |

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

`fk`, `pddd`, `roe`, `net_borc_favok` de v1.0 FINAL REVİZYONU ile
opsiyonel hale getirildi: F/K, PD/DD "Piyasa Çarpanları" sayfasından,
ROE "Rasyo Analiz Tablosu" sayfasından okunmaya çalışılır (bkz.
"Fintables Kurulumu" -> "Fundamental veri kaynağı"); bu sayfalar bot
koruması arkasında olabilir ya da veri bulunamayabilir, bu durumda bu
dört alan eksik kalır (Net Borç/FAVÖK genelde eksik kalır - Fintables'ta
ayrı bir kalem olarak bulunamadı). Eksik olduklarında
`scoring/fundamental_engine.py` her bileşen için nötr (2.5/5) bir
varsayımla çalışır (asla çökmez) ve "Johnny neden bu puanı verdi?"
bölümünde "Fundamental veri eksik, nötr varsayım kullanıldı" notuyla
açıkça belirtilir.

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

**v0.4 revizyonu (kullanıcı geri bildirimi - "Top 3 sürekli UZAK DUR
çıkıyor"):** eski R2/R3/R4, Fintables + TradingView otomasyonunun
HİÇBİR ZAMAN sağlamadığı kolonlara (`volume_ratio`, `net_borc_favok`,
`yeni_is_iliskisi`) bağlıydı — bu yüzden otomatik "Fintables'tan
Güncelle" akışında bu üç kural pratikte hiç tetiklenemiyor, sadece R1
(+10) ulaşılabilir kalıyor ve toplam skor 70 (İZLE) eşiğinin altında
sıkışıyordu. Kurallar artık SADECE otomasyonda gerçekten gelen alanlara
(Gün %, 1 hafta/1 ay/3 aylık getiri — Fintables Radar'ın "Getiri"
sekmesi bunları HER ZAMAN sağlar; ROE/F-K/PD-DD; RSI/MACD/EMA) dayanıyor
— eşikler/puanlar şişirilmedi, Johnny hâlâ seçici.

| Kural | Koşul | Bonus |
|---|---|---|
| R1 | EMA20 > EMA50 > EMA200 + MACD pozitif + ADX > 25 | +10 |
| R2 | RSI 50-68 (geniş ideal bant) + Gün % pozitif + Son 1 haftalık getiri pozitif | +8 |
| R3 | ROE > %15 (yoksa F/K ≤15 ve PD/DD ≤2.5 makul aralıkta) | +8 |
| R4 | 1 aylık getiri pozitif + 3 aylık getiri > -%10 + TradingView teknik özeti olumlu (RSI>50, MACD histogram pozitif, EMA20>EMA50) | +7 |

Yeni bir kural eklemek için `scoring/rule_engine.py` içindeki `RULES`
listesine bir madde eklemek yeterlidir.

**Not (Radar'ın sabit kolon sırası - kullanıcı ekran görüntüsüyle
doğrulandı):** Fintables Radar'ın "Getiri" sekmesi her zaman şu 13
kolonu sağlar: `#, Hisse, Fiyat, Gün %, Hacim, Getiri % (Son 1 hafta),
Getiri % (Son 1 ay), Getiri % (Son 3 ay), Getiri % (Son 6 ay), Getiri %
(Yılbaşından bugüne), Getiri % (Son 1 yıl), Getiri % (Son 3 yıl),
Getiri % (Son 5 yıl)`. thead genelde bunları `<th>` olarak sağlamadığı
için (`_radar_sayfasindan_df_olustur`), Fiyat/Gün %/Hacim/Getiri_1H/1A/
3A artık bu bilinen SABİT pozisyona göre yeniden adlandırılıyor VE
(Fiyat/Gün %/Getiri_1H/1A/3A için) Türkçe formatlı metinden temiz
float'a çevriliyor — Hacim kasıtlı olarak ham metin ("168,48 mn")
kalıyor (bkz. kod içi not).

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
bir açıklama üretilir; arayüzde fırsat kartlarının altında ve tam tablonun
altındaki genişletilebilir bölümde görüntülenir.

### Johnny bir "trade asistanı"dır, bir puanlama tablosu değil

**v1.0 revizyonu (kullanıcı isteği):** Johnny'nin görevi hisseleri
sıralamak değil, GERÇEKTEN işlem yapılabilir fırsatları bulmaktır.
Kullanıcıya asla "en iyi UZAK DUR" ya da "en yüksek puanlı ama yine de
alma" gibi bir sonuç gösterilmez:

- `scoring/johnny_score.filter_tradeable(sonuc)` — `score_dataframe()`
  çıktısından SADECE Durum'u **AL** ya da **İZLE** olan satırları döner
  (zaten Johnny Score'a göre azalan sırada).
- Hiçbir aday bu seviyeye ulaşmıyorsa (`filter_tradeable` boş dönerse),
  arayüzde/`test_full_flow.py` çıktısında `NO_OPPORTUNITY_MESSAGE`
  ("Bugün işlem yapmaya değer güçlü bir fırsat bulamadım.") gösterilir —
  boş bir liste ya da en iyi UZAK DUR'lar ASLA gösterilmez.
- `app.py`'daki **"📋 Tüm Adaylar"** tablosu bunun istisnasıdır: bu,
  taranan TÜM adayların şeffaflık/araştırma amaçlı tam dökümüdür (UZAK
  DUR içerebilir) — bir öneri listesi değildir, ayrıca etiketlenmiştir.

Bu davranış `scoring/johnny_score.py` içinde merkezi olarak
uygulanır; hem `app.py` hem `test_full_flow.py` aynı fonksiyonu kullanır.

## Market Journal (v1.2) - Johnny kendi performansını ölçer

**Kullanıcı isteği:** Johnny sadece hisse seçen bir yazılım değil, kendi
geçmiş kararlarının GERÇEK sonucunu ölçen, zaman içinde daha kaliteli
öneriler sunmayı hedefleyen bir trade asistanı olmalı. Bu, MEVCUT
tarama/puanlama/öneri mekanizmasını DEĞİŞTİRMEDEN, üstüne eklenen ayrı
bir katmandır (`scoring/market_journal.py`, `scoring/performance_tracker.py`).

**Yapılandırılmış metrikler** (`score_dataframe` çıktısına eklendi):
her hisse için Teknik/Momentum/Temel puan, Rule Bonusları (hangi
kurallar tetiklendi), **Güven Skoru (%)** (veri ne kadar eksikse o kadar
düşer - eksik teknik gösterge/fundamental alan/hacim oranı başına ceza
uygulanır) ve **Risk/Getiri Oranı** (Hedef 1 mesafesi / Stop mesafesi)
artık ayrı kolonlar olarak mevcut.

**Snapshot + Piyasa Günlüğü:** her çalıştırma (`test_full_flow.py` ya da
`app.py` → "Fintables'tan Güncelle"), tam sonucu `history/snapshots/
YYYY-MM-DD_HHMM.csv` olarak kaydeder ve bir önceki snapshot'la otomatik
karşılaştırıp `history/journal/YYYY-MM-DD_HHMM.md` altına bir "Piyasa
Günlüğü" yazar: yeni giren/listeden çıkan hisseler, en fazla puan
kazanan/kaybedenler, Top 3 değişimi (sıralama değişti mi, kim çıktı, kim
yeni girdi), en istikrarlı hisse (son birkaç taramada en düşük skor
sapması) ve en hızlı yükselen/zayıflayan aday (skor eğimi). `app.py`'da
bu bölüm "📓 Piyasa Günlüğü" başlığı altında, `test_full_flow.py`'da
"PİYASA GÜNLÜĞÜ" bölümünde gösterilir. Geçmiş herhangi bir snapshot,
`app.py`'daki "🗂️ Geçmiş Analizler" bölümünden tekrar açılabilir.

**Performans takibi (ledger):** her AL/İZLE önerisi `history/ledger/
ledger.csv` altına bir kayıt olarak eklenir (giriş fiyatı, stop, hedef1/
2, hangi kurallar tetiklendi). Her çalıştırmada vadesi gelmiş (+1/+3/+5/
+10 **iş günü** - resmi tatiller hesaba katılmaz) öneriler otomatik
değerlendirilir: kapanış fiyatı, en yüksek/en düşük görülen fiyat, stop
çalıştı mı, Hedef 1/2'ye ulaşıldı mı, maksimum getiri/geri çekilme ve
elde tutma süresi hesaplanır - kronolojik sırayla ilk ÖNCE hangisi
tetiklendiyse (stop mu hedef1 mi) ona göre "başarılı/başarısız" kararı
verilir.

> **Önemli veri kaynağı sınırlaması:** Johnny'nin sürekli bir fiyat akışı
> (tick verisi) yoktur - sadece kendi taramalarını çalıştırdığında (günde
> birkaç kez, hafta içi) bir fiyat örneği alır. "En yüksek/en düşük
> görülen fiyat" bu yüzden GERÇEK intraday en yüksek/en düşük değil,
> Johnny'nin kendi örneklerinin en yüksek/en düşüğüdür - bir
> yaklaşıklıktır, tarama sıklığı arttıkça gerçeğe yaklaşır.

**Aylık/yıllık performans raporu** (`app.py` → "📊 Performans Raporu" ya
da `scoring.performance_tracker.generate_performance_report`): toplam
öneri sayısı, AL/İZLE başarı oranı, ortalama kazanç/kayıp, Hedef 1/2
başarı oranı, ortalama elde tutma süresi ve **kural (R1-R4) bazlı
başarı oranı** (bir kural tetiklendiğinde genelde ne oluyor?) - hangi
checkpoint'in (+1/+3/+5/+10 gün) referans alınacağı seçilebilir
(varsayılan +5 gün). Henüz hiçbir öneri o checkpoint'e ulaşmadıysa rapor
bunu açıkça belirtir, asla uydurma bir sayı göstermez.

`history/` klasörü (snapshot/journal/ledger) `.gitignore`'dadır - bu
kullanıcının çalışma zamanı verisidir, kaynak kod değildir.

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
│   ├── explore_fintables_fundamental_dom.py  # Tek seferlik DOM keşif aracı - şirket/temel analiz sayfası (Cloudflare bot koruması tespiti burada doğrulandı)
│   └── .sessions/                # Kayıtlı oturum (git'e girmez, .gitignore'da)
├── data/
│   └── sample_data.csv           # Örnek veri (ham göstergeler, standart kolon adlarıyla)
├── scoring/
│   ├── johnny_score.py           # Johnny Score v3 - taban puan + kural bonusu, durum, risk seviyeleri
│   ├── technical_engine.py       # Teknik skor motoru (30 puan)
│   ├── momentum_engine.py        # Momentum skor motoru (20 puan)
│   ├── fundamental_engine.py     # Bilanço/temel skor motoru (20 puan)
│   ├── rule_engine.py            # IF/THEN kural motoru (confluence bonusları)
│   ├── pre_screen.py             # v1.0: Radar verisiyle ilk N adayı seçen ön eleme mantığı
│   ├── market_journal.py         # v1.2: snapshot kaydı + önceki analizle karşılaştırma + Piyasa Günlüğü
│   └── performance_tracker.py    # v1.2: öneri takip defteri (ledger) + checkpoint değerlendirme + performans raporu
├── config/
│   └── watchlist.yaml            # Watchlist, eşikler, risk, skorlama ve Fintables parametreleri
├── history/                       # v1.2: snapshot/journal/ledger (git'e girmez, .gitignore'da)
│   ├── snapshots/                # Her analizin tam çıktısı (YYYY-MM-DD_HHMM.csv)
│   ├── journal/                  # Her analize ait Piyasa Günlüğü (YYYY-MM-DD_HHMM.md)
│   └── ledger/                   # Öneri takip defteri (ledger.csv)
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
`integrations/tradingview_indicators.py`). Fundamental veriler (F/K,
PD/DD, ROE, varsa Net Borç/FAVÖK) için önce "Karne" sekmesi denendi,
canlı bir tarayıcı oturumuyla (Claude in Chrome) bunun yanlış hedef
olduğu görüldü ve doğru sayfalara ("Piyasa Çarpanları", "Rasyo Analiz
Tablosu") geçildi (bkz. "Fundamental veri kaynağı"). Akış artık: Radar
→ ilk 20 aday → TradingView teknik veri + Fintables oran analizi
sayfalarından fundamental veri → Johnny Score → Top 3. Fintables'ın
Cloudflare korumalı sayfaları **hiçbir şekilde aşılmaya çalışılmaz**;
böyle bir koruma tespit edilirse o hisse için ilgili alanlar sadece
boş bırakılır.

Bilinen sınırlamalar:

- Bu ortamdaki ağ kısıtlamaları nedeniyle `tradingview-ta` kütüphanesi
  gerçek TradingView API'sine karşı canlı test edilemedi; entegrasyon
  kod incelemesi + sahte (mock) modüllerle uçtan uca test edildi.
  Kendi makinenizde bir kez canlı deneyip günlükteki "TradingView ...
  teknik veri alındı/alınamadı" satırlarını kontrol etmeniz önerilir.
- "Piyasa Çarpanları"/"Rasyo Analiz Tablosu" sayfalarının yapısı canlı
  bir tarayıcıyla görsel olarak doğrulandı, ama Playwright'ın
  (headless) otomasyonuyla bu sayfalara erişimin Cloudflare'e takılıp
  takılmayacağı henüz canlı test edilmedi; metin ayıklama esnek/genel
  bir yöntemle yazıldı ve mock testlerle doğrulandı. Kendi makinenizde
  canlı test edip gerekirse ince ayar yapmanız gerekebilir.

Sıradaki olası adımlar:

- TradingView entegrasyonunun gerçek API ile canlı doğrulanması
  (yukarıdaki sınırlama nedeniyle henüz yapılamadı).
- "Piyasa Çarpanları"/"Rasyo Analiz Tablosu" sayfalarından F/K/PD/DD/ROE
  okumanın Playwright otomasyonuyla gerçek Fintables hesabında canlı
  doğrulanması ve gerekirse etiket eşleşmelerinin
  (`_etiket_sonrasi_ilk_degerler`) ince ayarı.
- Net Borç/FAVÖK için Fintables'ta ayrı, güvenilir bir kaynak bulunması
  (şu an genelde None kalıyor).
- Radar tablosunun tamamının okunması (virtual scrolling döngüsü,
  "Scroll N: Toplam hisse: X" logu) DÜZELTİLDİ ve mock testlerle
  doğrulandı (bkz. yukarıdaki "BUG FIX" notu); gerçek Fintables
  hesabında canlı doğrulanması hâlâ gerekiyor - kaydırma yöntemlerinden
  (JS scrollTop / mouse wheel / End tuşu) hangisinin gerçek grid'i
  tetiklediği kesin olarak teyit edilmedi.
- `haber_puani`/`kurumsal_puani`/`piyasa_rejimi` için planlanan otomatik
  hesaplama (KAP entegrasyonu, analist hedef fiyatları, piyasa
  endeksleri/hacim verisi).

Sistem otomatik emir göndermez; sadece karar destek sağlar.
