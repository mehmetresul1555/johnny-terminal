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

DURUM (Hisse Detay / Teknik Analiz sayfası): v1.0 ile eklenen
`fetch_technical_detail()` ve `run_full_update()`, RSI/MACD/EMA/ADX/ATR
değerlerini bir hissenin detay sayfasından okumaya çalışır. BU SAYFANIN
DOM YAPISI HENÜZ DOĞRULANMADI — `DETAY_URL_TEMPLATE_VARSAYILAN` ve
`config/watchlist.yaml` -> `fintables.detay.selectors` altındaki
değerler YER TUTUCUDUR (tahmindir). Radar tablosunda yaptığımız gibi,
gerçek bir hissenin Teknik Analiz sayfasını açıp
`integrations/explore_fintables_dom.py` benzeri bir DOM taraması
yapmadan bu seçiciler güvenilir değildir. Seçici boş/yanlışsa ilgili
alan sessizce None döner (sistem çökmez), ama veri de gelmez.
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

# YER TUTUCU - DOĞRULANMADI. Fintables'ın genel URL kalıbına göre
# (fintables.com/sirketler/{TICKER}) tahmin edilmiştir; "teknik-analiz"
# alt yolunun/sekmesinin gerçekte var olup olmadığı, ya da bu bilginin
# aynı sayfada bir sekme/scroll ile mi geldiği DOĞRULANMALIDIR.
DETAY_URL_TEMPLATE_VARSAYILAN = "https://fintables.com/sirketler/{ticker}/teknik-analiz"


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


def _teknik_analiz_sayfasindan_oku(page, selectors, timeout_ms=10_000):
    """Zaten açılmış bir hisse detay/Teknik Analiz `page`'inden, verilen
    `selectors` sözlüğüne göre RSI/MACD/EMA/ADX/ATR değerlerini okur.

    UYARI: Bu fonksiyonun kullandığı seçiciler HENÜZ gerçek bir Fintables
    hisse detay sayfasında DOĞRULANMADI (bkz. modül docstring'i). Bir
    alan için seçici boşsa ya da sayfada bulunamazsa, o alan sessizce
    None olarak döner — tek bir yanlış/eksik seçici tüm hissenin
    atlanmasına yol açmaz.

    Args:
        page: Playwright page (zaten ilgili hissenin detay sayfasına
            gitmiş olmalı)
        selectors: {"rsi": "css-secici", "macd_signal": "...", ...} —
            config/watchlist.yaml -> fintables.detay.selectors
        timeout_ms: her bir alan için azami bekleme (ms)

    Returns:
        dict: {"rsi": deger_veya_None, "macd_signal": ..., "ema20": ...,
        "ema50": ..., "ema200": ..., "adx": ..., "atr_pct": ...}
        (değerler ham metin olarak döner; sayıya çevirme scoring
        katmanında/data_mapper'da yapılır)
    """
    alanlar = ["rsi", "macd_signal", "ema20", "ema50", "ema200", "adx", "atr_pct"]
    sonuc = {}
    selectors = selectors or {}

    for alan in alanlar:
        secici = (selectors.get(alan) or "").strip()
        if not secici:
            sonuc[alan] = None
            continue
        try:
            loc = page.locator(secici).first
            if loc.count() == 0:
                sonuc[alan] = None
                continue
            sonuc[alan] = loc.inner_text(timeout=timeout_ms).strip()
        except Exception:
            # Seçici hatalıysa/sayfada yoksa bu ALANI atla, tüm hisseyi
            # değil (bkz. modül docstring'i, "seçici boş/yanlışsa None").
            sonuc[alan] = None

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


def fetch_technical_detail(ticker, config=None, headless=True, timeout_ms=30_000):
    """Tek bir hissenin Teknik Analiz sayfasını KENDİ tarayıcı oturumuyla
    açıp RSI/MACD/EMA20/EMA50/EMA200/ADX/ATR değerlerini okur.

    Bu, tek bir hisseyi tekil test etmek için kullanışlıdır (örn. yeni
    seçicileri doğrularken). `run_full_update()` bunu ÇAĞIRMAZ — orada
    10 aday için TEK bir paylaşılan tarayıcı oturumu kullanılır
    (bkz. run_full_update), her hisse için ayrı tarayıcı açmak hem yavaş
    hem de gereksiz olurdu.

    UYARI: config/watchlist.yaml -> fintables.detay altındaki
    url_template ve selectors HENÜZ gerçek bir sayfa üzerinde
    doğrulanmadı (bkz. modül docstring'i). Seçici eksik/yanlışsa ilgili
    alan None döner, hata fırlatılmaz.

    Args:
        ticker: hisse kodu (örn. "SASA")
        config: watchlist.yaml içeriği (dict); verilmezse yer tutucu
            varsayılanlar kullanılır
        headless: True ise tarayıcı görünmez çalışır
        timeout_ms: sayfa/element bekleme zaman aşımı (ms)

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

    fintables_cfg = (config or {}).get("fintables", {})
    detay_cfg = fintables_cfg.get("detay", {})
    url_template = detay_cfg.get("url_template") or DETAY_URL_TEMPLATE_VARSAYILAN
    selectors = detay_cfg.get("selectors", {})
    page_url = url_template.format(ticker=ticker)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(storage_state=str(SESSION_PATH))
            page = context.new_page()
            page.goto(page_url, timeout=timeout_ms)
            sonuc = _teknik_analiz_sayfasindan_oku(page, selectors, timeout_ms=timeout_ms)
            browser.close()
    except FintablesError:
        raise
    except Exception as e:
        raise FintablesError(
            f"{ticker} Teknik Analiz sayfası açılırken/okunurken hata "
            f"oluştu: {e}"
        ) from e

    sonuc["hisse"] = ticker
    return sonuc


def run_full_update(config, on_progress=None):
    """Johnny Terminal v1.0 "final akış": Radar -> ön eleme (ilk N aday)
    -> SADECE bu adayların Teknik Analiz sayfasını oku -> Radar + teknik
    veriyi birleştir. Nihai Johnny Score hesaplama ve Top 3 gösterimi
    bu fonksiyonun DIŞINDA (app.py -> data_mapper -> scoring/johnny_score)
    değişmeden yapılmaya devam eder; bu fonksiyon sadece o hatta giden
    HAM (birleştirilmiş) DataFrame'i üretir.

    Adımlar:
        1. Radar ana tablosunu oku (_radar_sayfasindan_df_olustur)
        2. scoring/pre_screen.select_top_candidates ile ilk top_n adayı
           seç (varsayılan 10) — "640 hisse detayına girme" kuralı
           burada uygulanır.
        3. Sadece bu adayların Teknik Analiz sayfasına SIRAYLA gir,
           aralarına kısa/rastgele bir bekleme koy (config'den
           ayarlanabilir; "yavaş ve güvenli" çalışma isteği).
        4. Bir adayda hata olursa (sayfa açılmaz, zaman aşımı, seçici
           bulunamaz vb.) o aday ATLANIR ve loglanır; kalan adaylarla
           devam edilir, sistem asla durmaz.
        5. Radar satırı + teknik verileri tek bir kayıtta birleştirir.

    Tasarım notu: Radar + tüm aday detay sayfaları TEK bir tarayıcı
    (browser/context/page) oturumunda, arka arkaya gezilir — her hisse
    için ayrı bir tarayıcı başlatmak hem yavaş olur hem de "oturumu
    kullanarak sayfaları aç" ilkesine daha az uygun düşer.

    Args:
        config: watchlist.yaml içeriği (dict)
        on_progress: opsiyonel callable(str) — her adımda çağrılır;
            app.py bunu st.status günlüğüne canlı yazdırmak için
            kullanır. Kendi içinde hata fırlatırsa yok sayılır (akışı
            bozmaz).

    Returns:
        (df_ham: pd.DataFrame, hata_listesi: list[tuple[str, str]])
            df_ham: Radar + teknik verilerin birleştiği, data_mapper'a
                gönderilmeye hazır ham DataFrame (bir satır = bir aday
                hisse).
            hata_listesi: [(hisse_kodu, hata_mesaji), ...] — atlanan
                hisseler ve nedenleri.

    Raises:
        FintablesError: kayıtlı oturum yoksa, Radar tablosu hiç
            okunamazsa (bu durumda ön eleme yapacak veri de yoktur),
            ya da hiçbir aday için teknik veri okunamazsa.
    """
    import random
    import time

    import data_mapper
    from scoring import pre_screen

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
    top_n = on_eleme_cfg.get("top_n", pre_screen.DEFAULT_TOP_N)

    detay_cfg = fintables_cfg.get("detay", {}) or {}
    url_template = detay_cfg.get("url_template") or DETAY_URL_TEMPLATE_VARSAYILAN
    selectors = detay_cfg.get("selectors", {})
    bekleme_min = detay_cfg.get("bekleme_min_sn", 2.0)
    bekleme_max = detay_cfg.get("bekleme_max_sn", 4.0)
    timeout_ms = detay_cfg.get("timeout_ms", 30_000)

    hata_listesi = []
    birlesik_kayitlar = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(storage_state=str(SESSION_PATH))
            page = context.new_page()

            # 1) Radar ana tablosunu oku
            _bildir(f"Radar tablosu açılıyor: {radar_url}")
            page.goto(radar_url, timeout=timeout_ms)
            df_radar = _radar_sayfasindan_df_olustur(page, timeout_ms=timeout_ms)
            _bildir(f"Radar tablosu okundu: {len(df_radar)} hisse.")

            # 2-3) Ön eleme: ilk top_n aday (640 hissenin TAMAMI değil)
            try:
                adaylar = pre_screen.select_top_candidates(df_radar, top_n=top_n)
            except ValueError as e:
                browser.close()
                raise FintablesError(str(e)) from e

            hisse_kolonu = pre_screen.find_ticker_column(adaylar.columns)
            if hisse_kolonu is None:
                browser.close()
                raise FintablesError(
                    "Ön elemeden geçen adaylarda hisse kodu kolonu "
                    "bulunamadı; teknik detay sayfalarına hangi hisse "
                    "için gidileceği belirlenemiyor."
                )

            aday_kodlari = [str(x).strip() for x in adaylar[hisse_kolonu].tolist()]
            _bildir(
                f"Ön eleme tamamlandı, {len(aday_kodlari)} aday seçildi: "
                f"{', '.join(aday_kodlari)}"
            )

            # 4-5) SADECE bu adayların Teknik Analiz sayfasına gir
            toplam = len(adaylar)
            for i, (_, aday_satiri) in enumerate(adaylar.iterrows(), start=1):
                ticker = str(aday_satiri[hisse_kolonu]).strip()
                _bildir(f"[{i}/{toplam}] {ticker} - Teknik Analiz sayfası okunuyor...")

                detay_url = url_template.format(ticker=ticker)
                try:
                    page.goto(detay_url, timeout=timeout_ms)
                    teknik = _teknik_analiz_sayfasindan_oku(page, selectors, timeout_ms=timeout_ms)
                except Exception as e:
                    hata_mesaji = str(e)
                    _bildir(f"[{i}/{toplam}] UYARI: {ticker} atlandı - {hata_mesaji}")
                    hata_listesi.append((ticker, hata_mesaji))
                    continue

                kayit = aday_satiri.to_dict()
                kayit.update(teknik)
                kayit["hisse"] = ticker
                birlesik_kayitlar.append(kayit)

                # Hisseler arasında kısa, rastgele bekleme (yavaş ve
                # güvenli çalışma isteği).
                if i < toplam:
                    bekleme = random.uniform(bekleme_min, bekleme_max)
                    time.sleep(bekleme)

            browser.close()
    except FintablesError:
        raise
    except Exception as e:
        raise FintablesError(
            f"Fintables tam güncelleme akışı sırasında beklenmeyen bir "
            f"hata oluştu: {e}\n"
            "Oturumunuzun süresi dolmuş olabilir; 'Tarayıcıyı Aç ve Giriş "
            "Yap' ile yeniden giriş yapmayı deneyin."
        ) from e

    if not birlesik_kayitlar:
        raise FintablesError(
            "Ön elemeden geçen hiçbir aday için teknik veri okunamadı "
            f"({len(hata_listesi)} hisse atlandı). Bunun en olası nedeni, "
            "hisse detay sayfası adresinin/seçicilerinin "
            "(config/watchlist.yaml -> fintables.detay) henüz gerçek "
            "sayfa yapısıyla DOĞRULANMAMIŞ olmasıdır. "
            "integrations/explore_fintables_dom.py benzeri bir DOM "
            "taramasını bir hissenin Teknik Analiz sayfası için de "
            "yapmanız gerekebilir."
        )

    _bildir(
        f"Tamamlandı: {len(birlesik_kayitlar)} hisse başarıyla işlendi, "
        f"{len(hata_listesi)} hisse atlandı."
    )

    df_ham = pd.DataFrame(birlesik_kayitlar)
    return df_ham, hata_listesi
