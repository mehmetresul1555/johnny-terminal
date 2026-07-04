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

ÖNEMLİ NOT: Fintables'ın Hisse Radar sayfasının tam URL'i ve tablo
yapısı (CSS seçicileri) hesaba/plana göre değişebilir ve bu modül gerçek
sayfa üzerinde doğrulanmadan yazılmıştır. `config/watchlist.yaml` ->
`fintables.screener_url` ve `fintables.selectors` altındaki değerleri
kendi hesabınızda gördüğünüz gerçek sayfaya göre doldurmanız/ayarlamanız
gerekir (bkz. README "Fintables Kurulumu").
"""

from datetime import datetime
from pathlib import Path

import pandas as pd

SESSION_DIR = Path(__file__).resolve().parent / ".sessions"
SESSION_PATH = SESSION_DIR / "fintables_session.json"

FINTABLES_LOGIN_URL_VARSAYILAN = "https://fintables.com/auth/login"


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


def update_from_fintables(config):
    """config/watchlist.yaml -> fintables ayarlarını okuyup Fintables'tan
    ham veriyi çeker ve data_mapper ile otomatik kolon eşleştirme önerisi
    üretir. app.py'daki "Fintables'tan Güncelle" butonu bunu çağırır.

    Returns:
        (df_ham: pd.DataFrame, oneri_mapping: dict)

    Raises:
        FintablesError: screener_url tanımlı değilse veya veri çekme
            sırasında bir sorun oluşursa.
    """
    import data_mapper

    fintables_cfg = config.get("fintables", {})
    screener_url = fintables_cfg.get("screener_url")
    if not screener_url:
        raise FintablesError(
            "config/watchlist.yaml -> fintables.screener_url tanımlı "
            "değil. Fintables hesabınızda Hisse Radar/Tarama sayfasını "
            "açıp adres çubuğundaki URL'i buraya ekleyin."
        )

    selectors = fintables_cfg.get("selectors", {})
    table_selector = selectors.get("table", "table")
    row_selector = selectors.get("row", "tr")
    headless = fintables_cfg.get("headless", True)

    df_ham = fetch_screener_table(
        screener_url,
        table_selector=table_selector,
        row_selector=row_selector,
        headless=headless,
    )
    oneri = data_mapper.suggest_mapping(df_ham.columns)
    return df_ham, oneri
