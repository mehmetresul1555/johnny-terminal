"""
Fintables DOM Keşif Aracı
--------------------------
Bu bir üretim (production) modülü DEĞİLDİR; tek seferlik bir keşif
aracıdır. Amaç: Fintables'ın Hisse Radar/Tarama sayfasının gerçek DOM
yapısını (tablo mu, ag-Grid mi, özel bir div[role=grid] mi olduğunu)
ortaya çıkarmak. Hiçbir veriyi parse etmeye/kaydetmeye ÇALIŞMAZ; sadece
olası veri container'larını tarayıp selector/class/id/örnek metinlerini
terminale yazdırır.

Kullanım:
    cd johnny-terminal
    python3 integrations/explore_fintables_dom.py

Akış:
    1. Görünür (headless=False) bir Chromium penceresi açılır.
       - Daha önce kaydedilmiş bir Fintables oturumu varsa yüklenir
         (muhtemelen zaten giriş yapılmış olursunuz).
       - Yoksa doğrudan Fintables giriş sayfası açılır.
    2. SİZ o pencerede ELLE giriş yapıp incelemek istediğiniz Radar/
       Tarama sayfasını açarsınız. Bu script login formuna hiçbir
       şekilde dokunmaz, şifrenizi görmez.
    3. Sayfa tamamen yüklendiğinde terminale dönüp ENTER'a basarsınız.
    4. Script, o an açık olan sekmedeki sayfayı tarar: table, [role=grid],
       [role=table], ag-Grid sınıfları, class/id içinde "grid" ya da
       "table" geçen elementler gibi olası veri container'larını arar.
       Her biri için: CSS selector, count() sonucu, ilk birkaç eşleşmenin
       tag/class/id bilgisi ve içindeki ilk 5 "satır"ın metnini yazdırır.
    5. İsterseniz başka bir sayfayı/görünümü de tarayabilir, bitirince
       oturumu (isteğe bağlı) kaydedip çıkabilirsiniz.
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

# Olası veri container'ları için taranacak CSS seçiciler. Genel/geniş
# seçiciler (örn. [class*='grid']) modern sitelerde CSS-grid layout
# amaçlı yüzlerce elementle eşleşebilir; bu normaldir, sadece ilk
# birkaçının ayrıntısı gösterilir.
CANDIDATE_SELECTORS = [
    "table",
    "tbody",
    "div[role='grid']",
    "div[role='table']",
    "div[role='rowgroup']",
    "[class*='ag-root']",
    "[class*='ag-grid']",
    "[class*='ag-body']",
    "[class*='data-grid']",
    "[class*='datagrid']",
    "[class*='DataGrid']",
    "[class*='grid']",
    "[class*='table']",
    "[data-testid*='table']",
    "[data-testid*='grid']",
    "[data-testid*='radar']",
]

ROW_SELECTOR_ADAYLARI = ["tr", "[role='row']", ":scope > *"]

DETAY_LIMIT = 3   # her selector icin ayrintili incelenecek eslesme sayisi
SATIR_LIMIT = 5   # her elementten yazdirilacak ornek satir sayisi


def _satirlari_al(locator):
    """Bir container locator'ının içinden 'satır' benzeri alt elementleri
    bulmayı dener (önce <tr>, sonra role=row, sonra doğrudan çocuklar)."""
    for row_sel in ROW_SELECTOR_ADAYLARI:
        try:
            alt = locator.locator(row_sel)
            n = alt.count()
        except Exception:
            continue
        if n > 0:
            try:
                metinler = alt.all_inner_texts()
            except Exception:
                metinler = []
            metinler = [m.strip().replace("\n", " | ") for m in metinler if m.strip()]
            if metinler:
                return row_sel, metinler[:SATIR_LIMIT]
    return None, []


def sayfa_yapisini_tara(page):
    """Verilen Playwright page nesnesi üzerinde CANDIDATE_SELECTORS
    listesindeki her seçiciyi dener, sonuçları terminale yazdırır."""
    print()
    print("=" * 70)
    print(f"TARANAN SAYFA: {page.url}")
    print("=" * 70)

    ozet = []

    for selector in CANDIDATE_SELECTORS:
        try:
            loc = page.locator(selector)
            count = loc.count()
        except Exception as e:
            print(f"\n[HATA] Selector '{selector}' denenirken sorun oluştu: {e}")
            continue

        ozet.append((selector, count))

        if count == 0:
            continue

        print(f"\n--- Selector: {selector}  (page.locator(...).count() = {count}) ---")

        for i in range(min(count, DETAY_LIMIT)):
            eleman = loc.nth(i)
            try:
                tag = eleman.evaluate("el => el.tagName")
            except Exception:
                tag = "?"
            try:
                cls = eleman.get_attribute("class")
            except Exception:
                cls = None
            try:
                el_id = eleman.get_attribute("id")
            except Exception:
                el_id = None

            print(f"  [{i}] tag={tag}  id={el_id!r}  class={cls!r}")

            row_sel, satirlar = _satirlari_al(eleman)
            if satirlar:
                print(f"      satır seçici: {row_sel!r} -> ilk {len(satirlar)} satır:")
                for j, s in enumerate(satirlar, 1):
                    kisaltilmis = (s[:150] + "…") if len(s) > 150 else s
                    print(f"        {j}. {kisaltilmis}")
            else:
                print("      (içinde satır benzeri alt eleman bulunamadı)")

    print("\n" + "-" * 70)
    print("ÖZET (selector -> eşleşme sayısı):")
    for selector, count in ozet:
        isaret = "✅" if count > 0 else "  "
        print(f"  {isaret} {selector:35s} -> {count}")
    print("-" * 70)


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
            print("2) İncelemek istediğiniz Hisse Radar/Tarama sayfasını açın.")
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

            sayfa_yapisini_tara(aktif_sayfa)

            cevap = input("\nBaşka bir sayfa/görünüm daha taramak ister misiniz? (e/h): ").strip().lower()
            devam = cevap in ("e", "evet", "y", "yes")

        cevap = input("\nOturumu (çerezler) ileride yeniden giriş yapmadan kullanmak için kaydedeyim mi? (e/h): ").strip().lower()
        if cevap in ("e", "evet", "y", "yes"):
            context.storage_state(path=str(SESSION_PATH))
            print(f"Oturum kaydedildi: {SESSION_PATH}")
        else:
            print("Oturum kaydedilmedi.")

        browser.close()


if __name__ == "__main__":
    main()
