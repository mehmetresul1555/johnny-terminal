"""
Fintables Browser Automation (v0.5)
------------------------------------
Fintables Pro genel bir API sunmuyor. Bu modül, kullanıcının KENDİ
Fintables Pro hesabıyla, kendi tarayıcı oturumunu kullanarak Hisse
Radar/Tarama sayfasını açıp gösterdiği tabloyu okur ve pandas
DataFrame'e çevirir.

Tasarım ilkeleri (kod bu ilkelere göre yazıldı):
    - Şifre HİÇBİR YERDE koda yazılmaz veya diskte saklanmaz.
    - İlk giriş her zaman kullanıcı tarafından, açılan gerçek bir
      tarayıcı penceresinde ELLE yapılır; bu modül login formunu
      doldurmaz, kullanıcı adı/şifre alanına hiçbir şekilde dokunmaz.
    - Giriş sonrası oturum (çerezler + localStorage) Playwright'ın
      `storage_state` mekanizmasıyla LOKAL bir JSON dosyasında saklanır
      (bkz. SESSION_PATH). Bu dosya .gitignore'dadır, asla commit'lenmez
      ve Johnny Terminal dışında hiçbir yere gönderilmez.
    - Veri çekme SADECE kullanıcı "Fintables'tan Güncelle" butonuna
      bastığında, tek seferlik olarak çalışır. Arka planda otomatik,
      periyodik ya da agresif bir tarama YAPILMAZ.
    - Sadece kullanıcının kendi Pro hesabıyla zaten görebildiği sayfalar
      açılır; bot-koruması/CAPTCHA aşma ya da yetkisiz erişim girişimi
      yoktur. Kullanım koşullarına uygunluk kullanıcının sorumluluğundadır
      — otomasyonu etkinleştirmeden önce Fintables'ın güncel kullanım
      şartlarını kontrol edin.

Kurulum:
    pip install playwright
    playwright install chromium

DURUM (Radar tablosu): Hisse Radar sayfasının
(https://fintables.com/radar/hisse-senetleri) DOM yapısı
`integrations/explore_fintables_dom.py` ile gerçek bir oturumda
taranarak DOĞRULANDI: gerçek bir HTML `<table class="grid">`,
`<thead><tr><th>` başlıkları ve `<tbody class="grid relative"><tr><td>`
veri satırları. `fetch_radar_table()` bu yapıya göre yazıldı ve
üretime hazırdır. Şimdilik yalnızca sayfa ilk açıldığında görünen
"Getiri" sekmesi okunur; filtre/sekme değiştirme henüz yapılmıyor
(bilinçli kapsam sınırlaması).

DURUM (Hisse Detay / Teknik Analiz sayfası) - PASİF (v1.0 FINAL
REVİZYONU itibarıyla `run_full_update()` tarafından KULLANILMIYOR):

`integrations/explore_fintables_detail_dom.py` ile gerçek bir hissenin
(AKBNK) sayfası tarandığında şu yapı bulunmuştu: hisse detay/işlem
sayfası (https://fintables.com/islem-ekrani?code={TICKER}) içinde bir
TradingView grafik widget'ı çalışıyor, göstergeler bir "legend" metin
kutusunda (`[data-name="legend-source-item"]`) gösteriliyor. Bu metni
okuyup ayrıştıran fonksiyonlar (`_teknik_grafik_frame_bul`,
`_legend_metnini_ayikla`, `read_technical_indicators`,
`ensure_indicators_visible`, `open_stock_detail`,
`open_technical_analysis_tab`, `fetch_technical_for_symbol`,
`fetch_technical_detail`) hâlâ modülde duruyor (geriye dönük uyumluluk/
tekil test için), AMA `run_full_update()` artık bunları ÇAĞIRMIYOR.

NEDEN PASİFLEŞTİRİLDİ: Bu yöntem güvenilir değildi - EMA20/EMA50/EMA200
gibi göstergeler kullanıcı grafiğe elle eklemediyse hiç görünmüyordu,
ve genel olarak Fintables'ın DOM yapısına (ve kullanıcının chart
kurulumuna) fazlasıyla bağımlı, kırılgan bir yaklaşımdı.

YENİ YAKLAŞIM: RSI/MACD/EMA20/EMA50/EMA200/ADX/ATR artık Fintables'tan
DEĞİL, doğrudan TradingView'in kendi herkese açık teknik analiz veri
uç noktasından alınıyor (bkz. integrations/tradingview_indicators.py,
`tradingview-ta` kütüphanesi). Bu yöntem giriş/hesap gerektirmez,
tarayıcı otomasyonu içermez - basit bir HTTP isteğidir. Fintables
tarayıcı otomasyonu Radar ana tablosunu okumak İÇİN ve aşağıda
açıklanan fundamental veri sayfaları İÇİN kullanılmaya devam ediyor.

DURUM (Fundamental veri: F/K, PD/DD, ROE, Net Borç/FAVÖK) - DÜZELTİLDİ:
İlk denemede bu verilerin hisse detay sayfasındaki "Karne" sekmesinde
olduğu varsayılmıştı. Claude in Chrome üzerinden GERÇEK bir tarayıcı
oturumuyla canlı bakıldığında bunun YANLIŞ olduğu görüldü - "Karne"
sekmesi bunun yerine "Karlılık/Büyüme/Borçluluk" başlıklı, bps değişimi
ve evet/hayır kontrolleri içeren AYRI bir kalite skor kartı gösteriyor.

DOĞRU sayfalar (aynı canlı oturumda tespit edildi, düz HTML tablo,
canvas DEĞİL):
    - F/K, PD/DD  -> https://fintables.com/sirketler/{TICKER}/oran-analizi/piyasa-carpanlari
                     ("Güncel" satırında F/K, PD/DD, FD/FAVÖK sırasıyla)
    - ROE         -> https://fintables.com/sirketler/{TICKER}/oran-analizi/rasyo-analiz-tablosu
                     ("Özkaynak Karlılığı" satırı, en güncel çeyrek)
    - Net Borç/FAVÖK bu iki sayfada da AYRI bir kalem olarak bulunamadı;
      esnek metin taramasıyla yakalanmaya çalışılır, yoksa None kalır.

Bu sayfalar da (Piyasa Çarpanları/Rasyo Analiz Tablosu gibi "/sirketler/"
altındaki diğer sayfalar) Cloudflare bot koruması arkasında olabilir -
`fetch_fundamental_for_symbol` her sayfa açılışında önce bunu kontrol
eder; çıkarsa o sayfanın verisi için HEMEN VAZGEÇİLİR (aşma girişimi
YOK), hisse ATLANMAZ, sadece ilgili alanlar None kalır. Eski Karne
tabanlı kod (`_karne_fetch_fundamental_for_symbol_PASIF`,
`_karne_sekmesini_ac_ve_oku`, `_karne_metninden_degerleri_ayikla`)
referans için modülde duruyor ama artık ÇAĞRILMIYOR.
"""

import re
from datetime import datetime
from pathlib import Path

import pandas as pd

SESSION_DIR = Path(__file__).resolve().parent / ".sessions"
SESSION_PATH = SESSION_DIR / "fintables_session.json"

FINTABLES_LOGIN_URL_VARSAYILAN = "https://fintables.com/auth/login"

# integrations/explore_fintables_dom.py ile yapılan DOM taramasında
# doğrulandı (bkz. proje geçmişi): Hisse Radar sayfası gerçek bir HTML
# <table class="grid"> kullanıyor; <thead><tr><th> kolon başlıkları,
# <tbody class="grid relative"><tr><td> veri satırları içeriyor.
RADAR_URL_VARSAYILAN = "https://fintables.com/radar/hisse-senetleri"
RADAR_TABLE_SELECTOR_VARSAYILAN = "table.grid"

# DOĞRULANDI (integrations/explore_fintables_detail_dom.py ile AKBNK
# üzerinde test edildi): hisse detay/işlem ekranı sayfası, TradingView
# grafiğini (RSI/MACD/EMA/ADX/ATR dahil) burada gösteriyor.
DETAY_URL_TEMPLATE_VARSAYILAN = "https://fintables.com/islem-ekrani?code={ticker}"

# DOĞRULANDI: TradingView grafiğindeki her gösterge (RSI/MACD/EMA/ADX/
# ATR/Hacim...) bu seçiciyle bulunan bir "legend" (üst bilgi) elementi
# olarak DOM'da durur. Grafiğin/gösterge çizgilerinin kendisi <canvas>
# üzerindedir ve okunamaz, ama bu legend metin kutuları gerçek DOM'dur.
LEGEND_ITEM_SECICI_VARSAYILAN = "[data-name='legend-source-item']"

# v1.0 FINAL REVİZYONU - FUNDAMENTAL VERİ:
# DOĞRULANDI (integrations/explore_fintables_fundamental_dom.py ile):
# Fintables'ın şirket/temel analiz sayfası (fintables.com/sirketler/
# {TICKER}) Cloudflare bot koruması arkasında - headless otomasyonla
# açıldığında "Just a moment... / Performing security verification"
# (Cloudflare Managed Challenge) gösteriyor. PROJE KURALI GEREĞİ bu
# korumayı aşmaya ÇALIŞMIYORUZ (CAPTCHA/bot-koruması aşma girişimi
# yasak). Her sayfa açılışında önce bu koruma kontrol edilir; çıkarsa o
# hissenin/sayfanın verisi None kalır - hata fırlatılmaz, akış durmaz.
BOT_KORUMASI_ANAHTAR_KELIMELERI = [
    "just a moment", "checking your browser", "cloudflare",
    "security verification", "captcha", "attention required",
    "enable javascript and cookies",
]

# DOĞRULANDI (canlı tarayıcı ile, Claude in Chrome üzerinden): F/K ve
# PD/DD, hisse detay sayfasındaki "Karne" sekmesinde DEĞİL, ayrı bir
# "Piyasa Çarpanları" sayfasında; ROE ise "Rasyo Analiz Tablosu"
# sayfasında düz HTML tablo olarak (canvas değil) gösteriliyor. Net
# Borç/FAVÖK bu iki sayfada da AYRI bir kalem olarak bulunamadı - varsa
# esnek metin taramasıyla yakalanmaya çalışılır, yoksa None kalır.
PIYASA_CARPANLARI_URL_TEMPLATE = "https://fintables.com/sirketler/{ticker}/oran-analizi/piyasa-carpanlari"
RASYO_ANALIZ_TABLOSU_URL_TEMPLATE = "https://fintables.com/sirketler/{ticker}/oran-analizi/rasyo-analiz-tablosu"

# Bu sayfalarda aranacak etiketler (olası varyasyonlar). "Güncel" satırı
# Piyasa Çarpanları tablosunda F/K, PD/DD, FD/FAVÖK sırasıyla 3 değer
# içerir (bkz. _piyasa_carpanlari_degerlerini_ayikla).
GUNCEL_SATIR_ETIKETI = ["Güncel"]
ROE_ETIKETLERI = ["Özkaynak Karlılığı", "ROE"]
NET_BORC_FAVOK_ETIKETLERI = ["Net Borç/FAVÖK", "Net Borç / FAVÖK", "Net Debt/EBITDA"]

_FUNDAMENTAL_KOLON_GORUNEN_ADI = {
    "fk": "F/K", "pddd": "PD/DD", "roe": "ROE", "net_borc_favok": "Net Borç/FAVÖK",
}

# --- PASİF (referans için tutuluyor, artık ÇAĞRILMIYOR) ---
# İlk denemede "Karne" sekmesinin F/K/PD/DD/ROE/Net Borç/FAVÖK
# içerdiği varsayılmıştı; canlı tarayıcı ile bakıldığında bunun YANLIŞ
# olduğu görüldü - "Karne" sekmesi bunun yerine "Karlılık/Büyüme/
# Borçluluk" başlıklı, bps değişimi ve evet/hayır kontrolleri içeren
# AYRI bir kalite skor kartı gösteriyor. Bu yüzden Karne tabanlı kod
# aşağıda referans için duruyor ama artık kullanılmıyor.
KARNE_SEKME_METNI_VARSAYILAN = "Karne"

KARNE_ETIKET_ESLESTIRME = {
    "fk": ["F/K", "Fiyat/Kazanç"],
    "pddd": ["PD/DD", "Piyasa Değeri/Defter Değeri"],
    "roe": ["ROE", "Özkaynak Karlılığı", "Özkaynak Getirisi"],
    "net_borc_favok": ["Net Borç/FAVÖK", "Net Borç / FAVÖK", "Net Debt/EBITDA"],
}

_KARNE_KOLON_GORUNEN_ADI = {
    "fk": "F/K", "pddd": "PD/DD", "roe": "ROE", "net_borc_favok": "Net Borç/FAVÖK",
}


class FintablesError(Exception):
    """Kullanıcıya doğrudan gösterilebilecek, anlaşılır hata mesajları
    üretmek için kullanılan özel hata sınıfı."""


def _ensure_playwright():
    """Playwright kurulu değilse anlaşılır bir hata fırlatır."""
    try:
        import playwright  # noqa: F401
    except ImportError as e:
        raise FintablesError(
            "Playwright kurulu değil. Terminal'de şunları çalıştırın:\n"
            "  pip install playwright\n"
            "  playwright install chromium"
        ) from e


def has_saved_session():
    """Daha önce kaydedilmiş bir Fintables oturumu var mı?"""
    return SESSION_PATH.exists()


def session_info():
    """Kayıtlı oturumun ne zaman oluşturulduğunu okunabilir bir metin
    olarak döner (oturum yoksa None)."""
    if not SESSION_PATH.exists():
        return None
    ts = datetime.fromtimestamp(SESSION_PATH.stat().st_mtime)
    return ts.strftime("%d.%m.%Y %H:%M")


def clear_session():
    """Kayıtlı oturumu siler; bir sonraki veri çekmede yeniden manuel
    giriş gerekir."""
    if SESSION_PATH.exists():
        SESSION_PATH.unlink()


def launch_login_session(login_url=None, timeout_ms=180_000):
    """Görünür (headless=False) bir tarayıcı penceresi açar. Kullanıcı bu
    pencerede KENDİSİ Fintables'a giriş yapar; bu fonksiyon login formuna
    hiçbir şekilde müdahale etmez, sadece pencereyi açar ve kullanıcı
    pencereyi kapatana kadar (ya da zaman aşımına kadar) bekler. Kapanış
    anında oturum (çerezler + localStorage) lokal olarak kaydedilir.

    Args:
        login_url: Fintables giriş sayfası URL'i (varsayılan: genel giriş
            sayfası). Kendi hesabınızın yönlendirdiği farklı bir URL
            varsa config/watchlist.yaml -> fintables.login_url ile
            değiştirebilirsiniz.
        timeout_ms: kullanıcının giriş yapıp pencereyi kapatması için
            beklenecek azami süre (varsayılan 3 dakika).

    Raises:
        FintablesError: playwright kurulu değilse veya tarayıcı
            açılırken/kapanırken bir sorun oluşursa, anlaşılır bir
            mesajla.
    """
    _ensure_playwright()
    from playwright.sync_api import sync_playwright

    login_url = login_url or FINTABLES_LOGIN_URL_VARSAYILAN
    SESSION_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.goto(login_url, timeout=60_000)

            # Kullanıcı bu pencerede ELLE giriş yapar. Giriş yaptıktan
            # sonra pencereyi kapatması, oturumun kaydedilmesi için
            # sinyaldir.
            try:
                page.wait_for_event("close", timeout=timeout_ms)
            except Exception:
                # Kullanıcı süre içinde pencereyi kapatmadıysa da mevcut
                # oturumu (girişi yapılmış olabilir) yine de kaydedelim.
                pass

            context.storage_state(path=str(SESSION_PATH))
            browser.close()
    except FintablesError:
        raise
    except Exception as e:
        raise FintablesError(f"Tarayıcı oturumu açılırken hata oluştu: {e}") from e


def fetch_screener_table(page_url, table_selector="table", row_selector="tr", headless=True, timeout_ms=30_000):
    """Kayıtlı oturumu kullanarak belirtilen Fintables sayfasını (Hisse
    Radar/Tarama) açar ve üzerindeki tabloyu okuyup ham (Fintables'ın
    kendi kolon adlarıyla) bir DataFrame döner.

    Args:
        page_url: Hisse Radar/Tarama sayfasının tam URL'i
        table_selector: tabloyu (veya tablo benzeri container'ı) bulan
            CSS seçici. Fintables gerçek bir HTML <table> kullanmıyorsa
            (örn. özel bir grid bileşeni) bu değeri ve okuma stratejisini
            gerçek sayfaya göre uyarlamanız gerekir.
        row_selector: her hisse satırını bulan CSS seçici (yalnızca
            özel grid durumunda, ileri seviye ayarlama için ayrılmıştır)
        headless: True ise tarayıcı görünmez çalışır (varsayılan, veri
            çekme sırasında pencere açılmasını istemiyorsanız)
        timeout_ms: sayfa/element bekleme zaman aşımı (ms)

    Returns:
        pd.DataFrame: Fintables'ın kendi kolon adlarıyla, ham veri.

    Raises:
        FintablesError: oturum yoksa, sayfa açılamazsa, zaman aşımına
            uğrarsa ya da okunabilir bir tablo bulunamazsa, kullanıcıya
            gösterilebilecek anlaşılır bir mesajla.
    """
    _ensure_playwright()
    from playwright.sync_api import sync_playwright

    if not has_saved_session():
        raise FintablesError(
            "Kayıtlı bir Fintables oturumu bulunamadı. Önce "
            "'Tarayıcıyı Aç ve Giriş Yap' butonuyla giriş yapın."
        )

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(storage_state=str(SESSION_PATH))
            page = context.new_page()
            page.goto(page_url, timeout=timeout_ms)
            page.wait_for_selector(table_selector, timeout=timeout_ms)
            html = page.content()
            browser.close()
    except FintablesError:
        raise
    except Exception as e:
        raise FintablesError(
            f"Fintables sayfası açılırken/okunurken hata oluştu: {e}\n"
            "Oturumunuzun süresi dolmuş olabilir; 'Tarayıcıyı Aç ve Giriş "
            "Yap' ile yeniden giriş yapmayı deneyin. Sorun devam ederse "
            "sayfa URL'sinin ve seçicilerin (config/watchlist.yaml -> "
            "fintables) güncel olduğunu kontrol edin."
        ) from e

    try:
        tablolar = pd.read_html(html)
    except ValueError as e:
        raise FintablesError(
            "Sayfada standart bir HTML <table> bulunamadı. Fintables bu "
            "sayfada özel bir grid bileşeni kullanıyor olabilir; "
            "integrations/fintables_browser.py içindeki "
            "fetch_screener_table fonksiyonunun seçici tabanlı okuma "
            "kısmının gerçek sayfa yapısına göre tamamlanması gerekiyor."
        ) from e

    if not tablolar:
        raise FintablesError("Sayfada okunabilir bir tablo bulunamadı.")

    # Sayfada birden fazla <table> olabilir (menü, footer vb.); en çok
    # satıra sahip olanı genelde asıl veri tablosudur.
    return max(tablolar, key=len)


def _radar_tablosunu_asagi_kaydir(page, max_deneme=40, bekleme_ms=350):
    """EN İYİ ÇABA (best-effort), DOĞRULANMAMIŞ: Radar tablosu ~640 hisse
    içeriyor ama sayfa ilk açıldığında genelde sadece bir kısmı (örn.
    23 satır) DOM'da görünüyor olabilir (muhtemelen sanal
    kaydırma/lazy-load bir grid bileşeni). Bu fonksiyon, tbody
    satır sayısı artmayı bırakana kadar (ya da max_deneme'ye ulaşana
    kadar) tablo alanını aşağı kaydırıp beklemeyi dener.

    Fintables'ın grid bileşeni tamamen sanallaştırılmışsa (yani
    ekran dışı satırları DOM'dan tamamen siliyorsa) bu yöntem TÜM
    satırları aynı anda biriktiremeyebilir; bu durumda sadece o anda
    DOM'da görünen satırlar okunur. Bu bilinen, kabul edilmiş bir
    sınırlamadır (kesin çözüm için gerçek sayfa üzerinde ayrı bir DOM
    incelemesi gerekir). Hata durumunda sessizce durur, sistemi
    ÇÖKERTMEZ.
    """
    try:
        onceki_satir_sayisi = -1
        sabit_kalma_sayaci = 0
        for _ in range(max_deneme):
            satir_sayisi = page.locator(
                f"{RADAR_TABLE_SELECTOR_VARSAYILAN} tbody:first-of-type tr"
            ).count()

            if satir_sayisi == onceki_satir_sayisi:
                sabit_kalma_sayaci += 1
                # Art arda 3 denemede satır sayısı artmadıysa muhtemelen
                # tüm veri yüklendi (ya da tablo sanallaştırılmış ve daha
                # fazlası gelmeyecek) - dur.
                if sabit_kalma_sayaci >= 3:
                    break
            else:
                sabit_kalma_sayaci = 0
            onceki_satir_sayisi = satir_sayisi

            page.mouse.wheel(0, 2000)
            page.wait_for_timeout(bekleme_ms)
    except Exception:
        # Kaydırma denemesi başarısız olsa bile mevcut satırlarla devam
        # edilebilir; bu adım opsiyonel bir iyileştirmedir.
        pass


def _radar_sayfasindan_df_olustur(page, timeout_ms=30_000):
    """Zaten açılmış (page.goto ile Radar URL'ine gidilmiş) bir Playwright
    `page` nesnesinden tabloyu okuyup DataFrame'e çevirir. Tarayıcı/context
    yaşam döngüsünü YÖNETMEZ (açmaz/kapatmaz) — bu, hem tek başına
    `fetch_radar_table()` tarafından hem de `run_full_update()` içindeki
    PAYLAŞILAN (tek) tarayıcı oturumu tarafından çağrılabilmesi içindir.

    integrations/explore_fintables_dom.py ile DOĞRULANMIŞ sayfa yapısı:
        table.grid
          thead > tr > th        (kolon başlıkları)
          tbody.grid.relative > tr > td   (veri satırları)

    NOT (EN İYİ ÇABA / DOĞRULANMAMIŞ): Sayfa ilk açıldığında ~640
    hissenin tamamı DOM'da görünmüyor olabilir. Bu fonksiyon önce
    `_radar_tablosunu_asagi_kaydir` ile mümkün olduğunca çok satırın
    yüklenmesini dener, sonra DOM'da o an bulunan satırları okur. Bu,
    kesin/doğrulanmış bir çözüm DEĞİLDİR; Fintables'ın grid bileşeni
    tamamen sanallaştırılmışsa yine de tüm 640 satır elde edilemeyebilir.

    Raises:
        FintablesError: tablo zaman aşımına uğrarsa, başlıklar
            okunamazsa ya da hiç geçerli veri satırı bulunamazsa.
    """
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    try:
        page.wait_for_selector(RADAR_TABLE_SELECTOR_VARSAYILAN, timeout=timeout_ms)
    except PlaywrightTimeoutError:
        # Tanı bilgisi topla: gerçekte hangi sayfadayız, neden tablo
        # görünmüyor? (örn. oturum geçersizse sayfa girişe
        # yönlendirilmiş olabilir, ya da headless modda site farklı
        # bir içerik gösteriyor olabilir.)
        guncel_url = page.url
        try:
            baslik = page.title()
        except Exception:
            baslik = None
        debug_path = SESSION_DIR / "son_hata_ekran_goruntusu.png"
        try:
            page.screenshot(path=str(debug_path), full_page=True)
        except Exception:
            debug_path = None

        mesaj = (
            f"Tablo ({RADAR_TABLE_SELECTOR_VARSAYILAN}) "
            f"{timeout_ms / 1000:.0f} saniye içinde görünmedi.\n"
            f"Şu an açık olan sayfa: {guncel_url}\n"
        )
        if baslik:
            mesaj += f"Sayfa başlığı: {baslik}\n"
        if debug_path:
            mesaj += f"Tanı için ekran görüntüsü kaydedildi: {debug_path}\n"
        mesaj += (
            "Olası nedenler:\n"
            "  1) Oturum geçersiz/süresi dolmuş olabilir — yukarıdaki "
            "URL bir giriş/login sayfasıysa bu kesin nedendir; "
            "'Tarayıcıyı Aç ve Giriş Yap' ile yeniden giriş yapın.\n"
            "  2) headless modda site otomasyonu farklı algılayıp "
            "farklı bir sayfa/uyarı gösteriyor olabilir — "
            "config/watchlist.yaml -> fintables.headless değerini "
            "geçici olarak false yapıp tekrar deneyin, tarayıcıda "
            "gerçekte ne göründüğünü gözlemleyin.\n"
            "  3) Radar sayfası normalden yavaş yükleniyor olabilir; "
            "timeout_ms değerini artırmayı deneyin."
        )
        raise FintablesError(mesaj)

    # EN İYİ ÇABA: mümkün olduğunca çok satırın yüklenmesi için tabloyu
    # aşağı kaydırmayı dene (bkz. _radar_tablosunu_asagi_kaydir docstring
    # - bu adım DOĞRULANMAMIŞ, başarısız olursa sessizce atlanır).
    _radar_tablosunu_asagi_kaydir(page)

    # NOT: Fintables Radar tablosu, "yapışkan" (sticky) kaydırma
    # başlığı için ikinci bir gizli/kopya <thead> içerebiliyor. Bu
    # yüzden sadece İLK <thead>'in İLK <tr>'sindeki <th>'ler alınır;
    # aksi halde başlık sayısı gerçek kolon sayısının iki katı çıkar ve
    # her satır "uyuşmuyor" görünür.
    basliklar = [
        b.strip()
        for b in page.locator(
            f"{RADAR_TABLE_SELECTOR_VARSAYILAN} thead:first-of-type tr"
        ).first.locator("th").all_inner_texts()
    ]

    # Aynı önlem tbody için de alınır (bilinen yapıda tek tbody var,
    # ama ileride değişirse diye ilk tbody'e sabitleniyor).
    satir_locator = page.locator(
        f"{RADAR_TABLE_SELECTOR_VARSAYILAN} tbody:first-of-type tr"
    )
    satir_sayisi = satir_locator.count()

    veri_satirlari = []
    uyumsuz_satir_sayisi = 0

    for i in range(satir_sayisi):
        hucreler = [h.strip() for h in satir_locator.nth(i).locator("td").all_inner_texts()]

        if len(hucreler) != len(basliklar):
            uyumsuz_satir_sayisi += 1
            print(
                f"[fintables_browser] UYARI: {i}. satır atlandı - "
                f"başlık sayısı ({len(basliklar)}) ile hücre sayısı "
                f"({len(hucreler)}) uyuşmuyor. Satır içeriği: {hucreler}"
            )
            continue

        veri_satirlari.append(hucreler)

    if not basliklar:
        raise FintablesError(
            "Tablo başlıkları (thead th) okunamadı. Fintables'ın sayfa "
            "yapısı değişmiş olabilir; integrations/explore_fintables_dom.py "
            "ile yeniden DOM taraması yapmanız gerekebilir."
        )

    if not veri_satirlari:
        raise FintablesError(
            f"Tablodan okunabilen veri satırı bulunamadı (toplam "
            f"{satir_sayisi} satırdan {uyumsuz_satir_sayisi} tanesi "
            "başlık/hücre uyuşmazlığı nedeniyle atlandı)."
        )

    if uyumsuz_satir_sayisi:
        print(
            f"[fintables_browser] Bilgi: {uyumsuz_satir_sayisi} satır "
            f"uyuşmazlık nedeniyle atlandı, {len(veri_satirlari)} satır "
            "başarıyla okundu."
        )

    return pd.DataFrame(veri_satirlari, columns=basliklar)


def _tr_sayi(metin):
    """Türkçe formatlı bir TradingView legend değerini ('46,65', '−0,36',
    '2,84', '∅') float'a çevirir. Çevrilemezse (boş/anlamsız/'∅' gibi
    "veri yok" işaretleri) None döner."""
    if metin is None:
        return None
    s = str(metin).strip()
    if not s or s in ("∅", "N/A", "NA", "-", "—"):
        return None
    s = s.replace("−", "-")  # unicode eksi işareti (−) -> ASCII -
    s = s.replace(" ", "").replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _legend_metnini_ayikla(metin):
    """Bir '[data-name="legend-source-item"]' elementinin inner_text'ini
    ayrıştırır. Format (satır satır): BAŞLIK, [parametreler,] değer(ler).
    Örnek: 'RSI\\n14\\n46,65' -> ('RSI', '14', ['46,65'])
           'MACD\\n12 26 close 9 EMA EMA\\n−0,36\\n1,60\\n1,96'
                -> ('MACD', '12 26 close 9 EMA EMA', ['−0,36', '1,60', '1,96'])

    Returns:
        (baslik: str|None, parametreler: str|None, degerler: list[str])
    """
    satirlar = [s.strip() for s in (metin or "").split("\n") if s.strip()]
    if not satirlar:
        return None, None, []
    baslik = satirlar[0].upper()
    parametre_satirlari = []
    deger_satirlari = []
    for s in satirlar[1:]:
        if _tr_sayi(s) is not None or s == "∅":
            deger_satirlari.append(s)
        else:
            parametre_satirlari.append(s)
    parametreler = " ".join(parametre_satirlari) if parametre_satirlari else None
    return baslik, parametreler, deger_satirlari


def _teknik_grafik_frame_bul(page, secici=None, timeout_ms=10_000):
    """Sayfadaki TradingView (veya benzeri) grafik widget'ının yüklendiği
    iframe'i bulur. Bu iframe'in adı/URL'i OTURUMDAN OTURUMA DEĞİŞİR
    (örn. 'tradingview_eb8fa', 'tradingview_56610') - bu yüzden isme göre
    değil, İÇERİĞİNE göre (`secici` eşleşmesi olan ilk iframe, varsayılan
    LEGEND_ITEM_SECICI_VARSAYILAN) tespit edilir.

    Args:
        secici: config/watchlist.yaml -> fintables.detay.legend_item_selector
            ile değiştirilebilir; verilmezse doğrulanmış varsayılan kullanılır.

    Returns:
        Playwright Frame nesnesi, ya da timeout_ms içinde bulunamazsa
        None (hata fırlatmaz - çağıran taraf bunu "gösterge sekmesi/
        grafiği açılamadı" olarak loglayıp devam eder).
    """
    import time as _time

    secici = secici or LEGEND_ITEM_SECICI_VARSAYILAN
    baslangic = _time.time()
    while (_time.time() - baslangic) * 1000 < timeout_ms:
        try:
            cerceveler = page.frames
        except Exception:
            cerceveler = []
        for f in cerceveler[1:]:  # frames[0] her zaman ana sayfa
            try:
                if f.locator(secici).count() > 0:
                    return f
            except Exception:
                continue
        page.wait_for_timeout(300)
    return None


def open_stock_detail(page, ticker, config=None, timeout_ms=30_000):
    """Bir hissenin detay/işlem ekranı sayfasını açar (DOĞRULANMIŞ URL:
    bkz. DETAY_URL_TEMPLATE_VARSAYILAN). `page` zaten kayıtlı oturumla
    açılmış bir Playwright page olmalı (paylaşılan tarayıcı oturumu -
    her hisse için yeni bir tarayıcı AÇILMAZ)."""
    fintables_cfg = (config or {}).get("fintables", {})
    detay_cfg = fintables_cfg.get("detay", {}) or {}
    url_template = detay_cfg.get("url_template") or DETAY_URL_TEMPLATE_VARSAYILAN
    page.goto(url_template.format(ticker=ticker), timeout=timeout_ms)


def open_technical_analysis_tab(page, config=None, timeout_ms=None):
    """Hisse detay/işlem ekranı sayfası açıldıktan sonra, Teknik Analiz
    grafiğinin (TradingView widget'ı) yüklenmesini bekler. Bu sayfada
    ayrı bir "Teknik Analiz" sekmesine TIKLAMAK gerekmiyor - grafik
    zaten sayfanın kendisinde gösteriliyor (bkz. modül docstring'i);
    bu fonksiyon sadece grafiğin (iframe + legend elementleri) hazır
    olup olmadığını doğrular.

    Returns:
        Playwright Frame (grafik iframe'i) bulunursa, yoksa None.
    """
    fintables_cfg = (config or {}).get("fintables", {})
    detay_cfg = fintables_cfg.get("detay", {}) or {}
    bekleme_ms = timeout_ms or detay_cfg.get("grafik_bekleme_ms", 10_000)
    secici = detay_cfg.get("legend_item_selector") or LEGEND_ITEM_SECICI_VARSAYILAN
    return _teknik_grafik_frame_bul(page, secici=secici, timeout_ms=bekleme_ms)


# Bu göstergelerin (başlık halleri) grafik legend'inde bulunması
# beklenir. EMA üç farklı periyotla (20/50/200) üç AYRI gösterge olarak
# eklenmiş olmalı - bkz. modül docstring'i.
GEREKLI_GOSTERGE_BASLIKLARI = ["RSI", "MACD", "EMA", "ADX", "ATR"]


def ensure_indicators_visible(page, config=None, timeout_ms=None):
    """Grafikte gerekli göstergelerin (RSI, MACD, EMA20/50/200, ADX, ATR)
    zaten görünür/eklenmiş olup olmadığını KONTROL EDER.

    ÖNEMLİ: Bu fonksiyon eksik göstergeleri OTOMATİK EKLEMEYİ DENEMEZ.
    Fintables/TradingView'in "gösterge ekle" arama/dialog akışı henüz
    bir DOM taramasıyla doğrulanmadı (Radar tablosu ve legend okuma için
    yaptığımız gibi); doğrulanmamış tıklama dizileri üretime konursa
    yanlış elementlere tıklayıp öngörülemeyen sonuçlara yol açabilir.

    Bunun yerine ÖNERİLEN YÖNTEM: kullanıcı bu göstergeleri (RSI, MACD,
    EMA(20), EMA(50), EMA(200), ADX, ATR) Fintables/TradingView
    hesabında BİR KEZ elle ekler ve mümkünse "varsayılan şablon" olarak
    kaydeder; TradingView bu düzeni genelde hesap/oturum boyunca
    korur, yani her hissede otomatik olarak görünür.

    Bu fonksiyon sadece hangi göstergelerin O AN eksik olduğunu tespit
    edip loglama/şeffaflık amacıyla döner - sistemi çökertmez.

    Returns:
        dict: {"RSI": bool, "MACD": bool, "EMA20": bool, "EMA50": bool,
        "EMA200": bool, "ADX": bool, "ATR": bool} - bulundu mu?
    """
    sonuc = {
        "RSI": False, "MACD": False, "EMA20": False, "EMA50": False,
        "EMA200": False, "ADX": False, "ATR": False,
    }
    fintables_cfg = (config or {}).get("fintables", {})
    detay_cfg = fintables_cfg.get("detay", {}) or {}
    secici = detay_cfg.get("legend_item_selector") or LEGEND_ITEM_SECICI_VARSAYILAN

    frame = _teknik_grafik_frame_bul(page, secici=secici, timeout_ms=timeout_ms or 5_000)
    if frame is None:
        return sonuc

    try:
        items = frame.locator(secici)
        n = items.count()
    except Exception:
        return sonuc

    for i in range(n):
        try:
            metin = items.nth(i).inner_text(timeout=2_000)
        except Exception:
            continue
        baslik, parametreler, _ = _legend_metnini_ayikla(metin)
        if baslik == "RSI":
            sonuc["RSI"] = True
        elif baslik == "MACD":
            sonuc["MACD"] = True
        elif baslik == "ADX":
            sonuc["ADX"] = True
        elif baslik == "ATR":
            sonuc["ATR"] = True
        elif baslik == "EMA" and parametreler:
            m = re.match(r"(\d+)", parametreler)
            if m:
                periyot = m.group(1)
                if periyot == "20":
                    sonuc["EMA20"] = True
                elif periyot == "50":
                    sonuc["EMA50"] = True
                elif periyot == "200":
                    sonuc["EMA200"] = True

    return sonuc


def read_technical_indicators(page, config=None, timeout_ms=10_000):
    """Grafiğin (TradingView iframe) legend elementlerinden RSI, MACD
    (histogram), EMA20/50/200, ADX, ATR (ham/mutlak) değerlerini okur.

    Bulunamayan/eksik olan her alan için None döner (hata fırlatmaz).
    ATR burada MUTLAK (TL cinsinden, örn. 2.84) değer olarak döner;
    yüzdeye (atr_pct) çevirme işlemi `fetch_technical_for_symbol`
    içinde fiyat kullanılarak yapılır (fiyat bu fonksiyonun kapsamında
    değil).

    Returns:
        dict: {"rsi": float|None, "macd_signal": float|None,
        "ema20": float|None, "ema50": float|None, "ema200": float|None,
        "adx": float|None, "atr_ham": float|None}
    """
    sonuc = {
        "rsi": None, "macd_signal": None, "ema20": None, "ema50": None,
        "ema200": None, "adx": None, "atr_ham": None,
    }

    fintables_cfg = (config or {}).get("fintables", {})
    detay_cfg = fintables_cfg.get("detay", {}) or {}
    secici = detay_cfg.get("legend_item_selector") or LEGEND_ITEM_SECICI_VARSAYILAN

    frame = _teknik_grafik_frame_bul(page, secici=secici, timeout_ms=timeout_ms)
    if frame is None:
        return sonuc

    try:
        items = frame.locator(secici)
        n = items.count()
    except Exception:
        return sonuc

    for i in range(n):
        try:
            metin = items.nth(i).inner_text(timeout=2_000)
        except Exception:
            continue

        baslik, parametreler, degerler = _legend_metnini_ayikla(metin)
        if not degerler:
            continue

        if baslik == "RSI":
            sonuc["rsi"] = _tr_sayi(degerler[-1])
        elif baslik == "MACD":
            # Sıra: histogram, MACD çizgisi, sinyal çizgisi. Johnny'nin
            # "macd_signal" kolonu histogramı (MACD-Sinyal farkı) temsil
            # eder (bkz. data_mapper.py alias yorumları).
            sonuc["macd_signal"] = _tr_sayi(degerler[0])
        elif baslik == "ADX":
            sonuc["adx"] = _tr_sayi(degerler[-1])
        elif baslik == "ATR":
            sonuc["atr_ham"] = _tr_sayi(degerler[-1])
        elif baslik == "EMA" and parametreler:
            m = re.match(r"(\d+)", parametreler)
            if not m:
                continue
            periyot = m.group(1)
            deger = _tr_sayi(degerler[-1])
            if periyot == "20":
                sonuc["ema20"] = deger
            elif periyot == "50":
                sonuc["ema50"] = deger
            elif periyot == "200":
                sonuc["ema200"] = deger

    return sonuc


def _kolon_bul_esnek(columns, anahtar_kelimeler):
    """Basit, bağımsız bir kolon-bulma yardımcısı (scoring/pre_screen.py
    içindeki özel _kolon_bul'un küçük bir kopyası) - Radar satırında
    'fiyat' gibi bir kolonu isim üzerinden (normalize edilmiş, substring
    eşleşmesiyle) bulmak için kullanılır."""
    for col in columns:
        norm = re.sub(r"[^a-z0-9]+", "", str(col).strip().lower())
        for anahtar in anahtar_kelimeler:
            norm_anahtar = re.sub(r"[^a-z0-9]+", "", anahtar.strip().lower())
            if norm_anahtar in norm:
                return col
    return None


def pre_screen_candidates(df_radar, top_n=None, hisse_kolonu=None):
    """scoring/pre_screen.select_top_candidates için ince bir sarmalayıcı
    (wrapper) - Radar verisiyle basit bir ön eleme yapıp ilk top_n adayı
    seçer. Asıl mantık scoring/pre_screen.py'de tutulur (tek bir yerden
    yönetilsin diye); bu fonksiyon sadece istenen isimle
    integrations/fintables_browser.py içinden de erişilebilir kılar."""
    from scoring import pre_screen

    if top_n is None:
        top_n = pre_screen.DEFAULT_TOP_N
    return pre_screen.select_top_candidates(df_radar, top_n=top_n, hisse_kolonu=hisse_kolonu)


def fetch_technical_for_symbol(page, ticker, config=None, on_progress=None):
    """Tek bir hisse için: detay sayfasını aç -> grafiğin yüklenmesini
    bekle -> gerekli göstergelerin görünürlüğünü kontrol et -> değerleri
    oku -> ATR'yi yüzdeye çevir (fiyat verilmişse). Her adım
    `on_progress` ile ayrıntılı loglanır.

    Args:
        page: paylaşılan Playwright page (zaten oturum yüklü context'e ait)
        ticker: hisse kodu
        config: watchlist.yaml içeriği
        on_progress: opsiyonel callable(str)

    Returns:
        dict: {"hisse": ticker, "rsi":..., "macd_signal":..., "ema20":...,
        "ema50":..., "ema200":..., "adx":..., "atr_pct":...}

    Raises:
        Exception: sayfa hiç açılamazsa (goto hatası) - çağıran taraf
            (run_full_update) bunu yakalayıp hisseyi atlar/loglar.
    """
    def _bildir(mesaj):
        print(f"[fintables_browser] {mesaj}")
        if on_progress:
            try:
                on_progress(mesaj)
            except Exception:
                pass

    fintables_cfg = (config or {}).get("fintables", {})
    detay_cfg = fintables_cfg.get("detay", {}) or {}
    timeout_ms = detay_cfg.get("timeout_ms", 30_000)
    grafik_bekleme_ms = detay_cfg.get("grafik_bekleme_ms", 10_000)

    open_stock_detail(page, ticker, config, timeout_ms=timeout_ms)
    _bildir(f"{ticker} detay sayfası açıldı.")

    frame = open_technical_analysis_tab(page, config, timeout_ms=grafik_bekleme_ms)
    if frame is None:
        _bildir(
            f"{ticker}: Teknik Analiz grafiği {grafik_bekleme_ms / 1000:.0f} "
            "saniye içinde yüklenmedi - göstergeler okunamayacak."
        )
    else:
        _bildir(f"{ticker}: Teknik Analiz grafiği açıldı.")

    gorunurluk = ensure_indicators_visible(page, config, timeout_ms=2_000)
    eksik_gostergeler = [g for g, var in gorunurluk.items() if not var]
    if eksik_gostergeler:
        _bildir(
            f"{ticker}: grafikte eksik/bulunamayan göstergeler: "
            f"{', '.join(eksik_gostergeler)} (nötr varsayımla hesaplanacak). "
            "Önerilen çözüm: bu göstergeleri Fintables/TradingView "
            "hesabınızda bir kez ekleyip varsayılan şablon olarak kaydedin."
        )

    teknik = read_technical_indicators(page, config, timeout_ms=2_000)

    for alan, etiket in [
        ("rsi", "RSI"), ("macd_signal", "MACD"), ("ema20", "EMA20"),
        ("ema50", "EMA50"), ("ema200", "EMA200"), ("adx", "ADX"),
    ]:
        if teknik.get(alan) is not None:
            _bildir(f"{ticker}: {etiket} okundu ({teknik[alan]}).")
        else:
            _bildir(f"{ticker}: {etiket} okunamadı.")

    if teknik.get("atr_ham") is not None:
        _bildir(f"{ticker}: ATR okundu ({teknik['atr_ham']}, mutlak değer - yüzdeye çevrilecek).")
    else:
        _bildir(f"{ticker}: ATR okunamadı.")

    # NOT: atr_ham (mutlak TL değeri) burada BİLEREK yüzdeye çevrilmiyor -
    # bunun için hissenin fiyatı gerekir, ki bu bilgi Radar satırında
    # (run_full_update içinde) mevcuttur. run_full_update, bu sözlüğü
    # Radar satırıyla birleştirdikten SONRA atr_ham/fiyat*100 hesaplayıp
    # "atr_pct" kolonunu üretir.
    teknik["hisse"] = ticker
    return teknik


def _bot_korumasi_var_mi(page):
    """Sayfada Cloudflare (veya benzeri) bir bot koruması/güvenlik
    doğrulaması ekranı olup olmadığını KABACA kontrol eder (sayfa
    başlığı ve görünür metnin ilk kısmına bakarak). Kesin bir tespit
    DEĞİLDİR, ama güvenli tarafta kalmak için yeterince hassastır -
    şüpheli durumda True döner ve çağıran taraf O HİSSE için otomasyonu
    durdurur (aşmaya ÇALIŞMAZ, sadece atlar)."""
    try:
        baslik = (page.title() or "").lower()
    except Exception:
        baslik = ""
    try:
        govde_ornegi = page.inner_text("body")[:500].lower()
    except Exception:
        govde_ornegi = ""
    metin = f"{baslik} {govde_ornegi}"
    return any(anahtar in metin for anahtar in BOT_KORUMASI_ANAHTAR_KELIMELERI)


def _karne_sekmesini_ac_ve_oku(page, sekme_metni=None, timeout_ms=8_000):
    """PASİF (artık ÇAĞRILMIYOR) - bkz. modül üstündeki not: "Karne"
    sekmesinin F/K/PD/DD/ROE/Net Borç/FAVÖK İÇERMEDİĞİ canlı tarayıcıyla
    doğrulandı. Bu fonksiyon sadece referans için duruyor.

    Hisse detay sayfasında 'Karne' sekmesini bulup TIKLAMAYI dener,
    sonra sayfanın görünür metnini okur. Sekme bulunamaz/tıklanamazsa ya
    da metin okunamazsa None döner (hata fırlatmaz)."""
    sekme_metni = sekme_metni or KARNE_SEKME_METNI_VARSAYILAN
    try:
        sekme = page.get_by_text(sekme_metni, exact=False).first
        sekme.click(timeout=timeout_ms)
    except Exception:
        return None

    try:
        page.wait_for_timeout(1_500)
        return page.inner_text("body")
    except Exception:
        return None


def _karne_metninden_degerleri_ayikla(tam_metin):
    """PASİF (artık ÇAĞRILMIYOR) - bkz. modül üstündeki not. Karne
    sekmesinin (ya da genel sayfanın) düz metninden F/K, PD/DD, ROE,
    Net Borç/FAVÖK değerlerini çıkarmayı dener.

    Sayfa yapısı canlı doğrulanmadığı için ESNEK bir yöntem kullanılır:
    her etiket için aynı satırda ya da sonraki 1-2 satırda ilk sayısal
    (Türkçe formatlı) değer aranır. Bulunamazsa o alan None kalır - hata
    fırlatmaz.

    Returns:
        dict: {"fk": float|None, "pddd": float|None, "roe": float|None,
        "net_borc_favok": float|None}
    """
    sonuc = {"fk": None, "pddd": None, "roe": None, "net_borc_favok": None}
    if not tam_metin:
        return sonuc

    satirlar = [s.strip() for s in tam_metin.split("\n") if s.strip()]

    for kolon, etiketler in KARNE_ETIKET_ESLESTIRME.items():
        for etiket in etiketler:
            etiket_kucuk = etiket.lower()
            bulundu = False
            for i, satir in enumerate(satirlar):
                satir_kucuk = satir.lower()
                if etiket_kucuk not in satir_kucuk:
                    continue
                sonrasi = satir_kucuk.split(etiket_kucuk, 1)[1]
                deger = _tr_sayi(sonrasi.strip(" :\t-"))
                if deger is None:
                    for j in range(i + 1, min(i + 3, len(satirlar))):
                        deger = _tr_sayi(satirlar[j])
                        if deger is not None:
                            break
                if deger is not None:
                    sonuc[kolon] = deger
                    bulundu = True
                    break
            if bulundu:
                break

    return sonuc


def _karne_fetch_fundamental_for_symbol_PASIF(page, ticker, config=None, on_progress=None):
    """PASİF (artık ÇAĞRILMIYOR) - bkz. modül üstündeki not: canlı
    tarayıcıyla bakıldığında "Karne" sekmesinin F/K/PD/DD/ROE/Net
    Borç/FAVÖK İÇERMEDİĞİ görüldü (bunun yerine ayrı bir kalite skor
    kartı gösteriyor). Yerine geçen güncel fonksiyon: aşağıdaki
    `fetch_fundamental_for_symbol` (Piyasa Çarpanları + Rasyo Analiz
    Tablosu sayfalarını kullanır). Bu fonksiyon sadece referans için
    duruyor, silinmedi.
    """
    def _bildir(mesaj):
        print(f"[fintables_browser] {mesaj}")
        if on_progress:
            try:
                on_progress(mesaj)
            except Exception:
                pass

    sonuc = {"hisse": ticker, "fk": None, "pddd": None, "roe": None, "net_borc_favok": None}

    fintables_cfg = (config or {}).get("fintables", {})
    detay_cfg = fintables_cfg.get("detay", {}) or {}
    timeout_ms = detay_cfg.get("timeout_ms", 30_000)

    try:
        open_stock_detail(page, ticker, config, timeout_ms=timeout_ms)
    except Exception as e:
        _bildir(f"{ticker}: detay sayfası açılamadı ({e}), Karne atlanıyor.")
        return sonuc

    if _bot_korumasi_var_mi(page):
        _bildir(
            f"{ticker}: bot koruması/güvenlik doğrulaması tespit edildi, "
            "Karne atlanıyor (aşma girişimi yapılmıyor)."
        )
        return sonuc

    tam_metin = _karne_sekmesini_ac_ve_oku(page)
    if tam_metin is None:
        _bildir(f"{ticker}: Karne sekmesi bulunamadı/açılamadı, fundamental alanlar boş bırakıldı.")
        return sonuc

    if _bot_korumasi_var_mi(page):
        _bildir(f"{ticker}: Karne sekmesi açılırken bot koruması çıktı, atlanıyor.")
        return sonuc

    degerler = _karne_metninden_degerleri_ayikla(tam_metin)
    sonuc.update(degerler)
    return sonuc


def _etiket_sonrasi_ilk_degerler(satirlar, etiketler, kac_deger=1):
    """`satirlar` içinde `etiketler`'den biriyle eşleşen İLK satırı bulur,
    o satırdan SONRAKİ satırlar arasında sırayla ilk `kac_deger` adet
    parse edilebilir (Türkçe formatlı, '%' içerebilir) sayıyı döner.

    Bulunamazsa `[None] * kac_deger` döner - hata fırlatmaz. Bu, sayfa
    yapısı canlı bir DOM taramasıyla (CSS seçici bazlı) değil, görünür
    metne bakılarak doğrulandığı için ESNEK/metin tabanlı bir yaklaşımdır.
    """
    for etiket in etiketler:
        etiket_kucuk = etiket.lower()
        for i, satir in enumerate(satirlar):
            if etiket_kucuk not in satir.lower():
                continue
            degerler = []
            j = i + 1
            while len(degerler) < kac_deger and j < len(satirlar) and j < i + 20:
                deger = _tr_sayi(satirlar[j].replace("%", "").strip())
                if deger is not None:
                    degerler.append(deger)
                j += 1
            if len(degerler) == kac_deger:
                return degerler
    return [None] * kac_deger


def _piyasa_carpanlari_degerlerini_ayikla(tam_metin):
    """"Piyasa Çarpanları" sayfasının düz metninden F/K ve PD/DD'yi
    çıkarır. DOĞRULANDI (canlı tarayıcı ile): sayfada "Güncel" satırından
    sonra sırasıyla F/K, PD/DD, FD/FAVÖK değerleri geliyor (düz HTML
    tablo, canvas değil). FD/FAVÖK Johnny'nin standart kolonlarından biri
    olmadığı için okunur ama kullanılmaz.

    Returns:
        dict: {"fk": float|None, "pddd": float|None}
    """
    if not tam_metin:
        return {"fk": None, "pddd": None}
    satirlar = [s.strip() for s in tam_metin.split("\n") if s.strip()]
    fk, pddd, _fd_favok = _etiket_sonrasi_ilk_degerler(satirlar, GUNCEL_SATIR_ETIKETI, kac_deger=3)
    return {"fk": fk, "pddd": pddd}


def _rasyo_tablosu_degerlerini_ayikla(tam_metin):
    """"Rasyo Analiz Tablosu" sayfasının düz metninden ROE'yi (Özkaynak
    Karlılığı) çıkarır; varsa Net Borç/FAVÖK'ü de esnek bir aramayla
    yakalamayı dener (bu sayfada AYRI bir kalem olarak bulunamadı, bu
    yüzden büyük olasılıkla None kalacaktır - bu beklenen bir durumdur).

    Returns:
        dict: {"roe": float|None, "net_borc_favok": float|None}
    """
    if not tam_metin:
        return {"roe": None, "net_borc_favok": None}
    satirlar = [s.strip() for s in tam_metin.split("\n") if s.strip()]
    roe = _etiket_sonrasi_ilk_degerler(satirlar, ROE_ETIKETLERI, kac_deger=1)[0]
    net_borc_favok = _etiket_sonrasi_ilk_degerler(satirlar, NET_BORC_FAVOK_ETIKETLERI, kac_deger=1)[0]
    return {"roe": roe, "net_borc_favok": net_borc_favok}


def fetch_fundamental_for_symbol(page, ticker, config=None, on_progress=None):
    """Tek bir hisse için fundamental verileri (F/K, PD/DD, ROE, varsa
    Net Borç/FAVÖK) Fintables'ın DOĞRU sayfalarından okumayı dener:

        - F/K, PD/DD  -> .../oran-analizi/piyasa-carpanlari
        - ROE         -> .../oran-analizi/rasyo-analiz-tablosu

    (Bkz. modül üstündeki not: "Karne" sekmesi bu verileri İÇERMEZ, bu
    yüzden artık kullanılmıyor.)

    Her sayfa açılışında önce bot koruması (Cloudflare vb.) kontrol
    edilir; çıkarsa o sayfanın verisi için HEMEN VAZGEÇİLİR (aşma
    girişimi YOK), diğer sayfa/hisselerle devam edilir. Herhangi bir
    adım başarısız olursa ilgili alanlar None kalır - hata fırlatmaz,
    hisse ATLANMAZ (scoring/fundamental_engine.py nötr puanlarla devam
    eder).

    Args:
        page: paylaşılan Playwright page (zaten oturum yüklü context'e ait)
        ticker: hisse kodu
        config: watchlist.yaml içeriği
        on_progress: opsiyonel callable(str)

    Returns:
        dict: {"hisse": ticker, "fk": ..., "pddd": ..., "roe": ...,
        "net_borc_favok": ...}
    """
    def _bildir(mesaj):
        print(f"[fintables_browser] {mesaj}")
        if on_progress:
            try:
                on_progress(mesaj)
            except Exception:
                pass

    sonuc = {"hisse": ticker, "fk": None, "pddd": None, "roe": None, "net_borc_favok": None}

    fintables_cfg = (config or {}).get("fintables", {})
    detay_cfg = fintables_cfg.get("detay", {}) or {}
    timeout_ms = detay_cfg.get("timeout_ms", 30_000)

    # 1) Piyasa Çarpanları (F/K, PD/DD)
    try:
        page.goto(PIYASA_CARPANLARI_URL_TEMPLATE.format(ticker=ticker), timeout=timeout_ms)
    except Exception as e:
        _bildir(f"{ticker}: Piyasa Çarpanları sayfası açılamadı ({e}).")
    else:
        if _bot_korumasi_var_mi(page):
            _bildir(f"{ticker}: Piyasa Çarpanları sayfasında bot koruması tespit edildi, atlanıyor.")
        else:
            try:
                metin = page.inner_text("body")
                sonuc.update(_piyasa_carpanlari_degerlerini_ayikla(metin))
            except Exception as e:
                _bildir(f"{ticker}: Piyasa Çarpanları verisi okunamadı ({e}).")

    try:
        page.wait_for_timeout(500)
    except Exception:
        pass

    # 2) Rasyo Analiz Tablosu (ROE, varsa Net Borç/FAVÖK)
    try:
        page.goto(RASYO_ANALIZ_TABLOSU_URL_TEMPLATE.format(ticker=ticker), timeout=timeout_ms)
    except Exception as e:
        _bildir(f"{ticker}: Rasyo Analiz Tablosu sayfası açılamadı ({e}).")
    else:
        if _bot_korumasi_var_mi(page):
            _bildir(f"{ticker}: Rasyo Analiz Tablosu sayfasında bot koruması tespit edildi, atlanıyor.")
        else:
            try:
                metin = page.inner_text("body")
                sonuc.update(_rasyo_tablosu_degerlerini_ayikla(metin))
            except Exception as e:
                _bildir(f"{ticker}: Rasyo Analiz Tablosu verisi okunamadı ({e}).")

    bulunanlar = [
        _FUNDAMENTAL_KOLON_GORUNEN_ADI[k]
        for k in ("fk", "pddd", "roe", "net_borc_favok")
        if sonuc.get(k) is not None
    ]
    if bulunanlar:
        _bildir(f"{ticker}: temel veriler okundu: {', '.join(bulunanlar)}.")
    else:
        _bildir(f"{ticker}: temel veriler (F/K, PD/DD, ROE, Net Borç/FAVÖK) okunamadı.")

    return sonuc


def fetch_radar_table(page_url=None, headless=True, timeout_ms=30_000):
    """Fintables Hisse Radar sayfasındaki tabloyu okuyup pandas
    DataFrame'e çevirir. Bu, integrations/explore_fintables_dom.py ile
    yapılan gerçek DOM taramasıyla DOĞRULANMIŞ bir sayfa yapısına göre
    yazılmıştır (bkz. `_radar_sayfasindan_df_olustur`).

    Şimdilik sadece sayfa ilk açıldığında görünen (varsayılan "Getiri"
    sekmesindeki) tablo okunur; herhangi bir filtre/kolon/sekme
    değişikliği YAPILMAZ. Bu bilinçli bir kapsam sınırlamasıdır — önce
    uçtan uca çalışan bir veri çekme hattı kurmak hedeflendi.

    Args:
        page_url: Radar sayfasının URL'i (varsayılan: doğrulanmış
            RADAR_URL_VARSAYILAN). config/watchlist.yaml ->
            fintables.screener_url ile değiştirilebilir.
        headless: True ise tarayıcı görünmez çalışır (varsayılan)
        timeout_ms: sayfa/element bekleme zaman aşımı (ms)

    Returns:
        pd.DataFrame: Fintables'ın kendi kolon başlıklarıyla, ham veri.

    Raises:
        FintablesError: oturum yoksa, sayfa açılamazsa/zaman aşımına
            uğrarsa, başlıklar okunamazsa ya da hiç geçerli veri satırı
            bulunamazsa; kullanıcıya gösterilebilecek anlaşılır bir
            mesajla.
    """
    _ensure_playwright()
    from playwright.sync_api import sync_playwright

    if not has_saved_session():
        raise FintablesError(
            "Kayıtlı bir Fintables oturumu bulunamadı. Önce "
            "'Tarayıcıyı Aç ve Giriş Yap' butonuyla giriş yapın."
        )

    page_url = page_url or RADAR_URL_VARSAYILAN

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(storage_state=str(SESSION_PATH))
            page = context.new_page()
            page.goto(page_url, timeout=timeout_ms)
            df = _radar_sayfasindan_df_olustur(page, timeout_ms=timeout_ms)
            browser.close()
    except FintablesError:
        raise
    except Exception as e:
        raise FintablesError(
            f"Fintables Radar sayfası açılırken/okunurken hata oluştu: {e}\n"
            "Oturumunuzun süresi dolmuş olabilir; 'Tarayıcıyı Aç ve Giriş "
            "Yap' ile yeniden giriş yapmayı deneyin."
        ) from e

    return df


def update_from_fintables(config):
    """config/watchlist.yaml -> fintables ayarlarını okuyup Fintables
    Hisse Radar'dan ham veriyi çeker (fetch_radar_table) ve data_mapper
    ile otomatik kolon eşleştirme önerisi üretir. app.py'daki
    "Fintables'tan Güncelle" butonu bunu çağırır.

    Returns:
        (df_ham: pd.DataFrame, oneri_mapping: dict)

    Raises:
        FintablesError: veri çekme sırasında bir sorun oluşursa.
    """
    import data_mapper

    fintables_cfg = config.get("fintables", {})
    page_url = fintables_cfg.get("screener_url") or RADAR_URL_VARSAYILAN
    headless = fintables_cfg.get("headless", True)

    df_ham = fetch_radar_table(page_url=page_url, headless=headless)
    oneri = data_mapper.suggest_mapping(df_ham.columns)
    return df_ham, oneri


def fetch_technical_detail(ticker, config=None, headless=True, timeout_ms=30_000, fiyat=None):
    """Tek bir hissenin detay/işlem ekranı sayfasını KENDİ tarayıcı
    oturumuyla açıp RSI/MACD/EMA20/EMA50/EMA200/ADX/ATR değerlerini okur.

    Bu, tek bir hisseyi tekil test etmek için kullanışlıdır (örn. yeni
    bir hissede gösterge kurulumunu doğrularken). `run_full_update()`
    bunu ÇAĞIRMAZ — orada tüm adaylar için TEK bir paylaşılan tarayıcı
    oturumu kullanılır (bkz. run_full_update, fetch_technical_for_symbol),
    her hisse için ayrı tarayıcı açmak hem yavaş hem de gereksiz olurdu.

    Args:
        ticker: hisse kodu (örn. "SASA")
        config: watchlist.yaml içeriği (dict)
        headless: True ise tarayıcı görünmez çalışır
        timeout_ms: sayfa/element bekleme zaman aşımı (ms)
        fiyat: verilirse ATR mutlak değeri buna bölünerek "atr_pct"
            (yüzde) hesaplanır; verilmezse atr_pct None kalır.

    Returns:
        dict: {"hisse": ticker, "rsi": ..., "macd_signal": ...,
        "ema20": ..., "ema50": ..., "ema200": ..., "adx": ...,
        "atr_pct": ...}

    Raises:
        FintablesError: kayıtlı oturum yoksa veya sayfa hiç açılamazsa.
    """
    _ensure_playwright()
    from playwright.sync_api import sync_playwright

    if not has_saved_session():
        raise FintablesError(
            "Kayıtlı bir Fintables oturumu bulunamadı. Önce "
            "'Tarayıcıyı Aç ve Giriş Yap' butonuyla giriş yapın."
        )

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(storage_state=str(SESSION_PATH))
            page = context.new_page()
            sonuc = fetch_technical_for_symbol(page, ticker, config)
            browser.close()
    except FintablesError:
        raise
    except Exception as e:
        raise FintablesError(
            f"{ticker} detay/Teknik Analiz sayfası açılırken/okunurken "
            f"hata oluştu: {e}"
        ) from e

    atr_ham = sonuc.pop("atr_ham", None)
    if atr_ham is not None and fiyat:
        try:
            sonuc["atr_pct"] = round(atr_ham / float(fiyat) * 100, 2)
        except (TypeError, ValueError, ZeroDivisionError):
            sonuc["atr_pct"] = None
    else:
        sonuc["atr_pct"] = None

    return sonuc


def run_full_update(config, on_progress=None):
    """Johnny Terminal v1.0 FINAL REVİZYONU akışı: Radar oku -> ön eleme
    (ilk N aday) -> bu adayların RSI/MACD/EMA20/EMA50/EMA200/ADX/ATR
    değerlerini TradingView'den al -> Radar + teknik veriyi birleştir.
    Nihai Johnny Score hesaplama ve Top 3 gösterimi bu fonksiyonun
    DIŞINDA (app.py -> data_mapper -> scoring/johnny_score) değişmeden
    yapılmaya devam eder; bu fonksiyon sadece o hatta giden HAM
    (birleştirilmiş) DataFrame'i üretir.

    ÖNEMLİ (REVİZYON NEDENİ): Önceki sürüm teknik göstergeleri
    Fintables'ın hisse detay sayfasındaki TradingView grafiğinin
    "legend" metin kutularından okuyordu (bkz.
    fetch_technical_for_symbol, read_technical_indicators - hâlâ
    modülde duruyor ama artık BURADAN ÇAĞRILMIYOR/PASİF). Bu yöntem
    güvenilir değildi: EMA20/EMA50/EMA200 gibi göstergeler grafiğe elle
    eklenmemişse hiç görünmüyordu. Bunun yerine artık TradingView'in
    KENDİ herkese açık teknik analiz uç noktası kullanılıyor (bkz.
    integrations/tradingview_indicators.py) - giriş/hesap gerekmez,
    tarayıcı otomasyonu yoktur, basit bir HTTP isteğidir.

    Adımlar (her biri on_progress ile loglanır):
        1. Fintables Radar okundu (tarayıcı otomasyonuyla, kayıtlı
           oturum üzerinden - bu kısım DEĞİŞMEDİ)
        2. Ön eleme tamamlandı
        3. İlk N aday seçildi ("640 hisse detayına girme" kuralı burada
           uygulanır)
        4. Her aday için: TradingView {SEMBOL} teknik veri alındı/alınamadı
        5. Her aday için: F/K, PD/DD Fintables'ın "Piyasa Çarpanları"
           sayfasından, ROE (varsa Net Borç/FAVÖK) "Rasyo Analiz
           Tablosu" sayfasından okunmaya çalışılır (bkz.
           fetch_fundamental_for_symbol). Bu sayfalar Cloudflare bot
           koruması arkasında olabilir; bu koruma tespit edilirse
           aşılmaya ÇALIŞILMAZ, sadece o sayfanın/hissenin ilgili
           alanları None bırakılır.
        6. Teknik + fundamental veriler birleştirildi (Radar satırı +
           TradingView göstergeleri + Piyasa Çarpanları/Rasyo Analiz
           Tablosu verisi tek bir kayıtta)

    Bir hisse için TradingView'den ya da Fintables oran analizi
    sayfalarından veri alınamazsa (ağ hatası, sembol bulunamadı, bot
    koruması vb.) o hisse ATLANMAZ - sadece ilgili alanlar None kalır ve
    loglanır; scoring katmanı bunu nötr varsayımlarla ele alır (bkz.
    scoring/johnny_score.py, scoring/fundamental_engine.py).
    `hata_listesi` bu akışta sadece yapısal bir sorun olursa (örn. hisse
    kodu kolonu hiç bulunamazsa) doldurulur - normal koşullarda genelde
    boştur.

    Args:
        config: watchlist.yaml içeriği (dict)
        on_progress: opsiyonel callable(str) — her adımda çağrılır;
            app.py bunu st.status günlüğüne canlı yazdırmak için
            kullanır. Kendi içinde hata fırlatırsa yok sayılır (akışı
            bozmaz).

    Returns:
        (df_ham: pd.DataFrame, hata_listesi: list[tuple[str, str]])
            df_ham: Radar + TradingView teknik verilerinin birleştiği,
                data_mapper'a gönderilmeye hazır ham DataFrame (bir
                satır = bir aday hisse).
            hata_listesi: [(hisse_kodu, hata_mesaji), ...] — yapısal
                nedenlerle tamamen değerlendirilemeyen hisseler.

    Raises:
        FintablesError: kayıtlı oturum yoksa, Radar tablosu hiç
            okunamazsa (bu durumda ön eleme yapacak veri de yoktur),
            ya da hisse kodu kolonu bulunamazsa.
    """
    def _bildir(mesaj):
        print(f"[fintables_browser] {mesaj}")
        if on_progress:
            try:
                on_progress(mesaj)
            except Exception:
                pass

    _ensure_playwright()
    from playwright.sync_api import sync_playwright

    if not has_saved_session():
        raise FintablesError(
            "Kayıtlı bir Fintables oturumu bulunamadı. Önce "
            "'Tarayıcıyı Aç ve Giriş Yap' butonuyla giriş yapın."
        )

    fintables_cfg = config.get("fintables", {})
    radar_url = fintables_cfg.get("screener_url") or RADAR_URL_VARSAYILAN
    headless = fintables_cfg.get("headless", True)

    on_eleme_cfg = fintables_cfg.get("pre_screen", {}) or {}
    top_n = on_eleme_cfg.get("top_n", 20)

    detay_cfg = fintables_cfg.get("detay", {}) or {}
    radar_timeout_ms = detay_cfg.get("timeout_ms", 30_000)

    tv_cfg = config.get("tradingview", {}) or {}
    tv_screener = tv_cfg.get("screener", "turkey")
    tv_exchange = tv_cfg.get("exchange", "BIST")
    tv_interval = tv_cfg.get("interval", "1d")
    tv_timeout = tv_cfg.get("timeout_sn", 10)

    hata_listesi = []

    # 1) Radar ana tablosunu oku (SADECE bunun için tarayıcı gerekiyor -
    # teknik veri artık TradingView'den geldiği için tarayıcıyı adaylar
    # arasında açık tutmaya gerek yok, Radar okunur okunmaz kapatılır).
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(storage_state=str(SESSION_PATH))
            page = context.new_page()

            _bildir(f"Fintables Radar okunuyor: {radar_url}")
            page.goto(radar_url, timeout=radar_timeout_ms)
            df_radar = _radar_sayfasindan_df_olustur(page, timeout_ms=radar_timeout_ms)
            _bildir(f"Fintables Radar okundu: {len(df_radar)} hisse.")

            browser.close()
    except FintablesError:
        raise
    except Exception as e:
        raise FintablesError(
            f"Fintables Radar sayfası açılırken/okunurken hata oluştu: {e}\n"
            "Oturumunuzun süresi dolmuş olabilir; 'Tarayıcıyı Aç ve Giriş "
            "Yap' ile yeniden giriş yapmayı deneyin."
        ) from e

    # 2-3) Ön eleme: ilk top_n aday (640 hissenin TAMAMI DEĞİL)
    adaylar = pre_screen_candidates(df_radar, top_n=top_n)

    from scoring import pre_screen as _pre_screen_mod
    hisse_kolonu = _pre_screen_mod.find_ticker_column(adaylar.columns)
    if hisse_kolonu is None:
        raise FintablesError(
            "Ön elemeden geçen adaylarda hisse kodu kolonu bulunamadı; "
            "TradingView'e hangi hisseler için istek atılacağı "
            "belirlenemiyor."
        )

    aday_kodlari = [str(x).strip() for x in adaylar[hisse_kolonu].tolist()]
    _bildir(
        f"İlk {len(aday_kodlari)} aday seçildi: {', '.join(aday_kodlari)}"
    )

    # 4) TradingView'den teknik göstergeleri al (tarayıcı GEREKMEZ - basit
    # bir HTTP isteği; bkz. integrations/tradingview_indicators.py)
    from integrations import tradingview_indicators

    try:
        tv_df = tradingview_indicators.fetch_indicators_for_candidates(
            aday_kodlari, screener=tv_screener, exchange=tv_exchange,
            interval=tv_interval, on_progress=on_progress, timeout=tv_timeout,
        )
    except tradingview_indicators.TradingViewIndicatorError as e:
        raise FintablesError(str(e)) from e

    # 5) Fundamental veri (Piyasa Çarpanları + Rasyo Analiz Tablosu) -
    # AYRI bir tarayıcı oturumu gerekir (Radar için açılan oturum adım
    # 1'de zaten kapatıldı). Bu sayfalar Cloudflare bot koruması
    # arkasında olabilir (bkz. modül docstring'i); çıkarsa aşılmaya
    # ÇALIŞILMAZ, o hissenin/sayfanın alanları None kalır, akış DURMAZ,
    # diğer adaylarla devam eder.
    import random

    bekleme_min = detay_cfg.get("bekleme_min_sn", 2.0)
    bekleme_max = detay_cfg.get("bekleme_max_sn", 4.0)

    fundamental_kayitlari = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(storage_state=str(SESSION_PATH))
            page = context.new_page()

            for i, ticker in enumerate(aday_kodlari):
                kayit = fetch_fundamental_for_symbol(
                    page, ticker, config, on_progress=on_progress
                )
                fundamental_kayitlari.append(kayit)
                if i < len(aday_kodlari) - 1:
                    bekleme_ms = int(random.uniform(bekleme_min, bekleme_max) * 1000)
                    page.wait_for_timeout(bekleme_ms)

            browser.close()
    except Exception as e:
        _bildir(
            f"Fundamental veri alınırken beklenmeyen bir hata oluştu "
            f"({e}); tüm adaylar için bu alanlar boş bırakılıyor, "
            "akışa devam ediliyor."
        )
        fundamental_kayitlari = [
            {"hisse": t, "fk": None, "pddd": None, "roe": None, "net_borc_favok": None}
            for t in aday_kodlari
        ]

    fundamental_df = pd.DataFrame(fundamental_kayitlari)

    # 6) Radar + TradingView + fundamental verilerini birleştir.
    # Eşleştirme hisse kodunun normalize edilmiş (boşluksuz, büyük harf)
    # haliyle yapılır - Radar'daki kolon adı ne olursa olsun (örn. "640
    # Hisse").
    adaylar = adaylar.copy()
    adaylar["_anahtar"] = adaylar[hisse_kolonu].astype(str).str.strip().str.upper()
    tv_df["_anahtar"] = tv_df["hisse"].astype(str).str.strip().str.upper()
    fundamental_df["_anahtar"] = fundamental_df["hisse"].astype(str).str.strip().str.upper()

    df_ham = adaylar.merge(tv_df.drop(columns=["hisse"]), on="_anahtar", how="left")
    df_ham = df_ham.merge(fundamental_df.drop(columns=["hisse"]), on="_anahtar", how="left")
    df_ham = df_ham.drop(columns=["_anahtar"])
    df_ham["hisse"] = df_ham[hisse_kolonu]

    _bildir("Teknik ve fundamental veriler birleştirildi.")
    _bildir(f"Tamamlandı: {len(df_ham)} hisse işlendi.")

    return df_ham, hata_listesi
