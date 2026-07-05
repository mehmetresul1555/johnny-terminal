"""
Fintables Şirket/Temel Analiz Sayfası - DOM Keşif Scripti
------------------------------------------------------------
AMAÇ: F/K, PD/DD, ROE, Net Borç/FAVÖK değerlerinin
https://fintables.com/sirketler/{TICKER} sayfasında DOM'dan
GÜVENİLİR ŞEKİLDE okunabilir (düz metin) mi, yoksa Teknik Analiz
grafiğinde olduğu gibi bir canvas/grafik üzerinde mi render
edildiğini tespit etmek. Bu bilgiye göre, bu sayfayı otomatik
okuyan bir fetch_fundamental_for_symbol() fonksiyonu yazılıp
yazılamayacağına karar verilecek.

SALT OKUNUR bir keşif scriptidir: sayfaya hiçbir veri göndermez,
hiçbir forma dokunmaz, sadece açıp okur. Kayıtlı Fintables
oturumunuzu kullanır (önce 'streamlit run app.py' -> "🌐 Tarayıcıyı
Aç ve Giriş Yap" ile bir kez giriş yapılmış olmalı).

Kullanım:
    cd ~/Desktop/johnny-terminal
    python3 integrations/explore_fintables_fundamental_dom.py AKBNK

(Parametre verilmezse varsayılan olarak AKBNK taranır.)

Çıktı (hepsi terminale yazdırılır):
    1. Sayfa başlığı
    2. Sayfadaki TÜM görünür metin (body.inner_text) - F/K, PD/DD,
       ROE, Net Borç/FAVÖK'ü bu dökümde gözle de arayabilirsiniz
    3. Anahtar kelime araması: F/K, PD/DD, ROE, FAVÖK vb. geçen
       elementlerin tag adı ve kısa HTML özeti
    4. Sayfada kaç <canvas> / <svg> elementi olduğu (çoksa, ilgili
       veri muhtemelen grafik olarak render ediliyordur - DOM'dan
       okunması güvenilir olmaz)
    5. Referans için tam sayfa ekran görüntüsü
       (integrations/.sessions/sirketler_{TICKER}_kesif.png)

Bu script tarayıcıyı headless (görünmez) açar ve işi bitince
KENDİLİĞİNDEN kapatır - bekleyen bir input() YOKTUR, bu yüzden
script bittikten sonra terminalde başka komut (örn. git) çalıştırmak
güvenlidir.
"""
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from integrations.fintables_browser import (  # noqa: E402
    SESSION_DIR,
    SESSION_PATH,
    has_saved_session,
)

ANAHTAR_KELIMELER = [
    "F/K", "PD/DD", "ROE", "FAVÖK", "Net Borç", "Fiyat/Kazanç",
    "Piyasa Değeri/Defter Değeri", "Özkaynak",
]


def main():
    ticker = sys.argv[1].strip().upper() if len(sys.argv) > 1 else "AKBNK"
    url = f"https://fintables.com/sirketler/{ticker}"

    if not has_saved_session():
        print(
            "HATA: Kayıtlı bir Fintables oturumu yok.\n"
            "Önce 'streamlit run app.py' ile açıp '🌐 Tarayıcıyı Aç ve "
            "Giriş Yap' butonuyla bir kez giriş yapmanız gerekiyor."
        )
        sys.exit(1)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("HATA: playwright kurulu değil. Terminal'de: pip3 install -r requirements.txt")
        sys.exit(1)

    print(f"Açılıyor: {url}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(SESSION_PATH))
        page = context.new_page()

        try:
            page.goto(url, timeout=30_000)
        except Exception as e:
            print(f"HATA: sayfa açılamadı - {e}")
            browser.close()
            sys.exit(1)

        # Sayfanın/verinin tam yüklenmesi için kısa bir bekleme.
        page.wait_for_timeout(4000)

        print("\n=== SAYFA BAŞLIĞI ===")
        try:
            print(page.title())
        except Exception as e:
            print(f"(okunamadı: {e})")

        print("\n=== GÜNCEL URL (yönlendirme oldu mu kontrol için) ===")
        print(page.url)

        print("\n=== SAYFADAKİ TÜM GÖRÜNÜR METİN (body.inner_text) ===")
        try:
            print(page.inner_text("body"))
        except Exception as e:
            print(f"(metin okunamadı: {e})")

        print("\n=== ANAHTAR KELİME ARAMASI ===")
        for kelime in ANAHTAR_KELIMELER:
            try:
                bulunanlar = page.get_by_text(kelime, exact=False)
                sayi = bulunanlar.count()
                print(f"\n'{kelime}': {sayi} eşleşme")
                for i in range(min(sayi, 3)):
                    try:
                        el = bulunanlar.nth(i)
                        tag = el.evaluate("e => e.tagName")
                        ozet = el.evaluate("e => e.outerHTML.slice(0, 200)")
                        print(f"  [{i}] <{tag}> {ozet}")
                    except Exception as e:
                        print(f"  [{i}] okunamadı: {e}")
            except Exception as e:
                print(f"'{kelime}' aranırken hata: {e}")

        try:
            canvas_sayisi = page.locator("canvas").count()
            svg_sayisi = page.locator("svg").count()
            print(f"\n=== Sayfada {canvas_sayisi} <canvas>, {svg_sayisi} <svg> elementi var. ===")
            if canvas_sayisi > 0:
                print(
                    "UYARI: canvas elementleri var - eğer F/K, PD/DD, ROE, "
                    "Net Borç/FAVÖK YUKARIDAKİ metin dökümünde GÖRÜNMÜYORSA, "
                    "muhtemelen bir grafik/canvas üzerinde render ediliyor "
                    "demektir ve DOM'dan güvenilir okunamaz (RSI/MACD/EMA "
                    "grafiğinde yaşadığımız sorunun aynısı)."
                )
        except Exception:
            pass

        ekran_goruntusu = SESSION_DIR / f"sirketler_{ticker}_kesif.png"
        try:
            page.screenshot(path=str(ekran_goruntusu), full_page=True)
            print(f"\nEkran görüntüsü kaydedildi: {ekran_goruntusu}")
        except Exception as e:
            print(f"\n(ekran görüntüsü alınamadı: {e})")

        browser.close()

    print("\nBitti. Tarayıcı kapatıldı, script sona erdi.")


if __name__ == "__main__":
    main()
