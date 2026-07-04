"""
Fintables Hisse Detay / Teknik Analiz DOM Keşif Aracı
-------------------------------------------------------
Bu bir üretim (production) modülü DEĞİLDİR; integrations/
explore_fintables_dom.py'nin Radar tablosu için yaptığının aynısını,
tek bir hissenin Teknik Analiz sayfası için yapan tek seferlik bir
keşif aracıdır.

integrations/fintables_browser.py içindeki fetch_technical_detail() ve
run_full_update(), RSI/MACD/EMA20/EMA50/EMA200/ADX/ATR değerlerini
config/watchlist.yaml -> fintables.detay.selectors altındaki CSS
seçicilerle okumaya çalışır. Bu seçiciler ŞU AN BOŞ/YER TUTUCU çünkü
gerçek sayfa yapısı henüz görülmedi. Bu script, o yapıyı ortaya
çıkarmak için:

    1. RSI, MACD, EMA20/50/200, ADX, ATR gibi bilinen gösterge
       ETİKETLERİNİ metin içinde arar (Radar'daki gibi bir tabloda
       olabilir ya da her biri ayrı bir "kart"/etiket-değer çifti
       olarak sayfada duruyor olabilir - ikisi de olası).
    2. Her eşleşme için: elementin kendisi VE bir üst (parent)
       elementin sadeleştirilmiş HTML'ini yazdırır, böylece değerin
       (örn. "62.5") hangi kardeş/çocuk elementte durduğu görülebilir.
    3. Ek olarak, Radar keşfinde kullanılan genel tablo/grid taramasını
       da (varsa) çalıştırır - göstergeler bir tabloda geliyorsa bu
       daha hızlı sonuç verebilir.

Hiçbir veriyi kaydetmez/parse etmeye çalışmaz; sadece terminale
yazdırır. Şifreye hiçbir şekilde dokunmaz.

Kullanım:
    cd johnny-terminal
    python3 integrations/explore_fintables_detail_dom.py

Akış:
    1. Görünür (headless=False) bir Chromium penceresi açılır (kayıtlı
       oturum varsa yüklenir).
    2. SİZ o pencerede incelemek istediğiniz hissenin (örn. SASA)
       Teknik Analiz / Teknik göstergeler bölümünü/sekmesini açarsınız.
    3. Sayfa tamamen yüklendiğinde terminale dönüp ENTER'a basarsınız.
    4. Script, gösterge etiketlerini arar ve bulduğu her yerin DOM
       bağlamını yazdırır.
    5. İsterseniz başka bir hisseyi/sayfayı da tarayabilir, bitirince
       oturumu (isteğe bağlı) kaydedip çıkabilirsiniz.

Çıktıyı buraya (Johnny Terminal geliştiricisine) yapıştırırsanız,
config/watchlist.yaml -> fintables.detay.selectors ve
integrations/fintables_browser.py -> DETAY_URL_TEMPLATE_VARSAYILAN
gerçek, doğrulanmış değerlerle güncellenir.
"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from integrations.fintables_browser import (  # noqa: E402
    FINTABLES_LOGIN_URL_VARSAYILAN,
    SESSION_DIR,
    SESSION_PATH,
    has_saved_session,
)
from integrations.explore_fintables_dom import (  # noqa: E402
    CANDIDATE_SELECTORS,
    sayfa_yapisini_tara,
)

# Aranacak gösterge etiketleri. Fintables'ın gerçek etiket metinleri
# (örn. "RSI (14)" mi, "Rölatif Güç Endeksi" mi) tam olarak bilinmiyor;
# bu yüzden hem kısaltma hem de olası uzun adlar denenir. Bulunamayan
# bir anahtar sessizce atlanır - hata fırlatmaz.
GOSTERGE_ANAHTAR_KELIMELERI = [
    "RSI",
    "MACD",
    "EMA 20", "EMA20", "EMA(20)",
    "EMA 50", "EMA50", "EMA(50)",
    "EMA 200", "EMA200", "EMA(200)",
    "ADX",
    "ATR",
]

DETAY_LIMIT = 5   # her anahtar kelime icin ayrintili incelenecek eslesme sayisi
HTML_KISALTMA = 300  # yazdirilan outerHTML'in azami karakter sayisi


def _kisalt(metin, limit=HTML_KISALTMA):
    if metin is None:
        return None
    metin = " ".join(metin.split())  # fazla bosluk/satir sonlarini sadelestir
    return metin if len(metin) <= limit else metin[:limit] + "…"


def canvas_ve_iframe_raporu(page):
    """Sayfadaki <canvas> ve <iframe> elementlerini raporlar. Bu, sağ tık
    menüsünde 'İncele' seçeneğinin çıkmaması gibi durumlarda (bazı grafik/
    chart kütüphaneleri contextmenu olayını engeller) göstergelerin DOM
    metni olarak mı yoksa çizim (canvas) / gömülü sayfa (iframe) olarak mı
    sunulduğunu ANLAMAK için kullanılır. Bir sayfa canvas tabanlıysa
    göstergeler DOM'da hiç metin olarak bulunmaz - bu durumda otomatik
    okuma mümkün değildir (OCR/canvas-parse denenmez, bkz. proje kuralı:
    agresif/engel-aşan scraping yapılmaz)."""
    print("\n--- <canvas> elementleri ---")
    try:
        canvaslar = page.locator("canvas")
        n = canvaslar.count()
    except Exception as e:
        print(f"  [HATA] canvas taranırken sorun: {e}")
        n = 0
    if n == 0:
        print("  (Sayfada hiç <canvas> elementi yok)")
    for i in range(min(n, 10)):
        el = canvaslar.nth(i)
        try:
            cls = el.get_attribute("class")
        except Exception:
            cls = None
        try:
            el_id = el.get_attribute("id")
        except Exception:
            el_id = None
        try:
            box = el.bounding_box()
        except Exception:
            box = None
        print(f"  [{i}] id={el_id!r} class={cls!r} boyut={box}")

    print("\n--- <iframe> elementleri (page.frames) ---")
    try:
        frames = page.frames
    except Exception as e:
        print(f"  [HATA] frame listesi alınırken sorun: {e}")
        frames = []
    if len(frames) <= 1:
        print("  (Sayfada ek iframe yok - sadece ana sayfa çerçevesi var)")
    else:
        for f in frames[1:]:  # frames[0] her zaman ana sayfanın kendisi
            print(f"  - iframe url={f.url!r} name={f.name!r}")
            try:
                iframe_canvas_sayisi = f.locator("canvas").count()
            except Exception:
                iframe_canvas_sayisi = "?"
            print(f"      iframe İÇİNDEKİ <canvas> sayısı: {iframe_canvas_sayisi}")

            # Fiyat ekseni üzerindeki renkli "değer" rozetleri (örn.
            # "46,65") genelde başlık metniyle (RSI/MACD) AYNI elementte
            # durmaz - bunlar TradingView'de ayrı, class adında "value"
            # geçen elementler olarak render edilir (crisp metin için
            # canvas değil DOM kullanılır). Bunları class/data-name'e göre
            # ARA (kelime içeriğine göre değil).
            deger_secicileri = [
                "[class*='value' i]",
                "[class*='Value']",
                "[data-name*='value']",
                "[data-name*='legend-source-item']",
            ]
            for sec in deger_secicileri:
                try:
                    loc = f.locator(sec)
                    n = loc.count()
                except Exception:
                    continue
                if n == 0:
                    continue
                goster = min(n, 40)  # tüm göstergeleri (RSI/MACD/ADX/ATR dahil) kaçırmamak için üst sınır yüksek tutulur
                print(f"      -> '{sec}' seçicisiyle {n} eşleşme bulundu, ilk {goster} tanesi:")
                for i in range(goster):
                    try:
                        metin = loc.nth(i).inner_text(timeout=2000).strip()
                    except Exception:
                        metin = None
                    try:
                        cls = loc.nth(i).get_attribute("class")
                    except Exception:
                        cls = None
                    if metin:
                        print(f"         [{i}] metin={metin!r}  class={cls!r}")
            # Bu iframe'in İÇİNDE de gösterge etiketlerini aramayı dene.
            # NOT: Bu bir "engel aşma" değildir - Playwright otomasyon
            # API'si zaten yüklenmiş DOM içeriğini okur; tarayıcının sağ
            # tık/İncele menüsünü engellemesiyle ilgisi yoktur.
            for anahtar in GOSTERGE_ANAHTAR_KELIMELERI:
                try:
                    loc = f.get_by_text(anahtar, exact=False)
                    count = loc.count()
                except Exception:
                    continue
                if count > 0:
                    print(f"      -> iframe içinde '{anahtar}' bulundu ({count} eşleşme)")
                    for i in range(min(count, 3)):
                        eleman = loc.nth(i)
                        try:
                            kendi = eleman.evaluate("el => el.outerHTML")
                        except Exception:
                            kendi = None
                        # Sadece başlık (örn. "RSI") bulunmuş olabilir;
                        # yanındaki SAYISAL DEĞER genelde bir üst/dede
                        # elementin İÇİNDE, kardeş bir span/div'de durur.
                        # Bu yüzden 1 ve 2 üst seviyeyi de (daha büyük bir
                        # karakter limitiyle) yazdırıyoruz - amaç, başlık +
                        # değerin birlikte göründüğü "satır"ı görmek.
                        try:
                            ebeveyn = eleman.evaluate(
                                "el => el.parentElement ? el.parentElement.outerHTML : null"
                            )
                        except Exception:
                            ebeveyn = None
                        try:
                            dede = eleman.evaluate(
                                "el => (el.parentElement && el.parentElement.parentElement) "
                                "? el.parentElement.parentElement.outerHTML : null"
                            )
                        except Exception:
                            dede = None
                        print(f"         [{i}] kendi : {_kisalt(kendi, 200)}")
                        print(f"             ebeveyn (1 üst) : {_kisalt(ebeveyn, 500)}")
                        print(f"             dede (2 üst)    : {_kisalt(dede, 800)}")


def gostergeleri_ara(page):
    """GOSTERGE_ANAHTAR_KELIMELERI listesindeki her etiketi sayfada metin
    olarak arar; her eşleşme için elementin ve bir üst elementin
    sadeleştirilmiş HTML'ini yazdırır."""
    print()
    print("=" * 70)
    print(f"GÖSTERGE ETİKETİ ARAMASI - Sayfa: {page.url}")
    print("=" * 70)

    herhangi_bulundu = False

    for anahtar in GOSTERGE_ANAHTAR_KELIMELERI:
        try:
            # Playwright'ın metin eşleştirme seçicisi: case-insensitive,
            # kısmi eşleşme. Çok fazla alakasız eşleşme gelebilir (örn.
            # sayfanın herhangi bir yerinde "RSI" geçen açıklama metni);
            # bu yüzden sadece ilk birkaçı ayrıntılı gösterilir.
            loc = page.get_by_text(anahtar, exact=False)
            count = loc.count()
        except Exception as e:
            print(f"\n[HATA] '{anahtar}' aranırken sorun oluştu: {e}")
            continue

        if count == 0:
            continue

        herhangi_bulundu = True
        print(f"\n--- Etiket: {anahtar!r}  (eşleşme sayısı: {count}) ---")

        for i in range(min(count, DETAY_LIMIT)):
            eleman = loc.nth(i)
            try:
                kendi_html = eleman.evaluate("el => el.outerHTML")
            except Exception:
                kendi_html = None
            try:
                ust_html = eleman.evaluate(
                    "el => el.parentElement ? el.parentElement.outerHTML : null"
                )
            except Exception:
                ust_html = None
            try:
                tag = eleman.evaluate("el => el.tagName")
            except Exception:
                tag = "?"
            try:
                cls = eleman.get_attribute("class")
            except Exception:
                cls = None

            print(f"  [{i}] tag={tag}  class={cls!r}")
            print(f"      kendi HTML : {_kisalt(kendi_html)}")
            print(f"      üst HTML   : {_kisalt(ust_html)}")

    if not herhangi_bulundu:
        print(
            "\n(Hiçbir gösterge etiketi metin olarak bulunamadı. Sayfa "
            "henüz tam yüklenmemiş olabilir, ya da göstergeler farklı "
            "bir sekme/bölümde/isimle gösteriliyor olabilir - doğru "
            "sekmeyi/bölümü açtığınızdan emin olun. Aşağıdaki canvas/"
            "iframe raporuna bakın: göstergeler bir grafik/çizim üzerinde "
            "render ediliyor olabilir, bu durumda DOM'dan metin olarak "
            "okunamaz.)"
        )

    canvas_ve_iframe_raporu(page)

    print("\n" + "-" * 70)
    print(
        "Ayrıca genel tablo/grid taraması da çalıştırılıyor (göstergeler "
        "bir tabloda geliyorsa daha hızlı sonuç verebilir)..."
    )
    print("-" * 70)
    sayfa_yapisini_tara(page)


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright kurulu değil. Şunu çalıştırın:")
        print("  pip install playwright")
        print("  playwright install chromium")
        sys.exit(1)

    SESSION_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)

        if has_saved_session():
            print(f"Kayıtlı oturum bulundu ({SESSION_PATH}), yükleniyor...")
            context = browser.new_context(storage_state=str(SESSION_PATH))
            baslangic_url = "https://fintables.com"
        else:
            print("Kayıtlı oturum yok, giriş sayfası açılıyor.")
            context = browser.new_context()
            baslangic_url = FINTABLES_LOGIN_URL_VARSAYILAN

        page = context.new_page()
        page.goto(baslangic_url, timeout=60_000)

        devam = True
        while devam:
            print()
            print("=" * 70)
            print("1) Açılan tarayıcı penceresinde Fintables'a giriş yapın")
            print("   (henüz giriş yapmadıysanız).")
            print("2) İncelemek istediğiniz bir hissenin (örn. SASA) detay")
            print("   sayfasını açın ve Teknik Analiz / teknik göstergeler")
            print("   bölümünü/sekmesini görünür hale getirin.")
            print("3) Sayfa tamamen yüklendiğinde buraya dönüp ENTER'a basın.")
            print("=" * 70)
            input(">>> Hazır olduğunuzda ENTER'a basın... ")

            # Kullanıcı yeni bir sekme açmış olabilir; en son açılan
            # sekmeyi (muhtemelen üzerinde çalıştığı) hedef alalım.
            aktif_sayfa = context.pages[-1] if context.pages else page
            try:
                aktif_sayfa.wait_for_load_state("networkidle", timeout=10_000)
            except Exception:
                pass  # sayfa zaten yuklenmis olabilir, sorun degil

            gostergeleri_ara(aktif_sayfa)

            cevap = input(
                "\nBaşka bir hisse/sayfa daha taramak ister misiniz? (e/h): "
            ).strip().lower()
            devam = cevap in ("e", "evet", "y", "yes")

        cevap = input(
            "\nOturumu (çerezler) ileride yeniden giriş yapmadan kullanmak "
            "için kaydedeyim mi? (e/h): "
        ).strip().lower()
        if cevap in ("e", "evet", "y", "yes"):
            context.storage_state(path=str(SESSION_PATH))
            print(f"Oturum kaydedildi: {SESSION_PATH}")
        else:
            print("Oturum kaydedilmedi.")

        browser.close()


if __name__ == "__main__":
    main()
