"""
TradingView Teknik Gösterge Entegrasyonu (v1.0 FINAL REVİZYON)
-----------------------------------------------------------------
GEÇMİŞ: v1.0 FINAL'de RSI/MACD/EMA/ADX/ATR değerlerini Fintables'ın
hisse detay/işlem ekranı sayfasındaki TradingView grafiğinin "legend"
metin kutularından okumaya çalışıyorduk (bkz. integrations/
fintables_browser.py -> read_technical_indicators, artık PASİF).
Bu yaklaşım güvenilir değildi: EMA20/EMA50/EMA200 gibi göstergeler
kullanıcı grafiğe elle eklemediyse hiç görünmüyordu, ve genel olarak
tarayıcı DOM'una bağımlı kırılgan bir yöntemdi.

YENİ YAKLAŞIM: Teknik göstergeler artık Fintables'tan DEĞİL, doğrudan
TradingView'in kendi herkese açık teknik analiz veri uç noktasından
(`https://scanner.tradingview.com/{screener}/scan`) alınıyor. Bu uç
nokta, TradingView'in kendi web sitesindeki "Teknik Analiz" widget'ının
kullandığı, KİMLİK DOĞRULAMA GEREKTİRMEYEN herkese açık bir uç
noktadır - tarayıcı otomasyonu, giriş/oturum, CAPTCHA aşma YOKTUR.

Kullanılan kütüphane: `tradingview-ta` (PyPI)
    pip install tradingview-ta
    GitHub: https://github.com/AnalyzerREST/python-tradingview-ta
    "Unofficial TradingView technical analysis API wrapper" - basit bir
    HTTP POST isteği atar, giriş/hesap gerektirmez. MIT lisanslı, aktif
    ve yaygın kullanılan bir kütüphane.

Sembol formatı: Borsa İstanbul hisseleri için TradingView'de
"BIST:{KOD}" (örn. "BIST:AKBNK") kullanılır; screener="turkey",
exchange="BIST".

ÖNEMLİ - hata toleransı: Bir hisse için veri alınamazsa (ağ hatası,
sembol TradingView'de bulunamadı, zaman aşımı vb.) o hissenin TÜM
teknik alanları None olarak döner ve loglanır; ne o hisse için ne de
toplu akış için bir istisna (exception) fırlatılmaz - çağıran taraf
(run_full_update) diğer hisselerle sorunsuz devam eder.
"""

import time

import pandas as pd

DEFAULT_SCREENER = "turkey"
DEFAULT_EXCHANGE = "BIST"
DEFAULT_INTERVAL = "1d"

# tradingview_ta'nın varsayılan gösterge listesinde ATR yok; ekstra
# istenmesi gerekiyor (bkz. TA_Handler.add_indicators /
# get_multiple_analysis'in additional_indicators parametresi).
EK_GOSTERGELER = ["ATR"]

# Yedek (fallback) modda ardışık istekler arasında kısa bir bekleme -
# TradingView'in herkese açık uç noktasına karşı "yavaş ve güvenli"
# davranmak için (agresif/art arda istek göndermemek).
YEDEK_ISTEK_BEKLEME_SN = 0.5


class TradingViewIndicatorError(Exception):
    """Kullanıcıya doğrudan gösterilebilecek, anlaşılır hata mesajları
    üretmek için kullanılan özel hata sınıfı."""


def _ham_scanner_teshisi(tv_semboller, screener, interval, timeout):
    """Toplu istek TÜM adaylar için None döndürdüğünde (0% başarı - canlı
    testte tam olarak bu görüldü: 20/20 hisse "teknik veri alınamadı"),
    bunun NEDENİNİ (ağ engeli/proxy, TradingView'in bot koruması, uç
    noktanın şema değişikliği, geçersiz screener/exchange vb.) KÖR KÖRÜNE
    tahmin etmek yerine DOĞRUDAN teşhis eder: TradingView'in scan uç
    noktasına aynı isteği tekrar atıp HTTP durum kodunu ve yanıt
    gövdesinin bir kısmını döner. Bu, "teknik veri alınamadı" mesajının
    ARKASINDAKİ gerçek nedeni bir sonraki canlı testte hemen ortaya
    çıkarır (Radar hata ayıklamasında kullanılan "zengin teşhis" ilkesiyle
    aynı yaklaşım - bkz. integrations/fintables_browser.py).

    SADECE teşhis amaçlıdır (ekstra, tek seferlik bir HTTP isteği);
    herhangi bir hata bu fonksiyonun DIŞINA asla sızmaz - sonuç sadece
    bir log/teşhis metnidir, akışı etkilemez.
    """
    try:
        import requests

        from tradingview_ta import TradingView

        indicators_key = TradingView.indicators.copy() + EK_GOSTERGELER
        data = TradingView.data(tv_semboller, interval, indicators_key)
        scan_url = f"{TradingView.scan_url}{screener.lower()}/scan"
        headers = {"User-Agent": "tradingview_ta_johnny_terminal_teshis"}
        yanit = requests.post(scan_url, json=data, headers=headers, timeout=timeout)
        govde_onizleme = yanit.text[:300].replace("\n", " ")
        tr_sonuc = (
            f"Türkiye sorgusu -> HTTP {yanit.status_code}, URL: {scan_url}, "
            f"yanıt önizlemesi: {govde_onizleme!r}"
        )
    except Exception as e:
        tr_sonuc = f"Türkiye sorgusu da başarısız oldu ({type(e).__name__}): {e}"

    # BUG TEŞHİSİ (2. adım): Türkiye sorgusu boş dönerse, bunun TÜM
    # TradingView entegrasyonunun (ağ/proxy/bot koruması nedeniyle)
    # genel olarak çalışmadığını mı, yoksa SADECE Türkiye/BIST
    # sorgusuna özgü bir sorunu mu (örn. "turkey" screener adının ya da
    # "BIST" borsa kodunun artık farklı olması) gösterdiğini ayırt etmek
    # için, İYİ BİLİNEN bir referans sembol (NASDAQ:AAPL, "america"
    # screener'ı) aynı mekanizmayla SORGULANIR. Referans da boş dönerse
    # sorun genel (ağ/API); referans BAŞARILI olup Türkiye boş dönerse
    # sorun Türkiye/BIST sorgusuna özgüdür.
    try:
        import requests

        from tradingview_ta import TradingView

        referans_semboller = ["NASDAQ:AAPL"]
        ref_data = TradingView.data(
            referans_semboller, interval, TradingView.indicators.copy()
        )
        ref_url = f"{TradingView.scan_url}america/scan"
        ref_yanit = requests.post(
            ref_url, json=ref_data,
            headers={"User-Agent": "tradingview_ta_johnny_terminal_teshis"},
            timeout=timeout,
        )
        ref_onizleme = ref_yanit.text[:200].replace("\n", " ")
        ref_sonuc = (
            f"Referans sorgusu (NASDAQ:AAPL) -> HTTP {ref_yanit.status_code}, "
            f"önizleme: {ref_onizleme!r}"
        )
    except Exception as e:
        ref_sonuc = f"Referans sorgusu da başarısız oldu ({type(e).__name__}): {e}"

    return f"{tr_sonuc} | {ref_sonuc}"


def _ensure_tradingview_ta():
    """tradingview-ta kütüphanesi kurulu değilse anlaşılır bir hata
    fırlatır."""
    try:
        import tradingview_ta  # noqa: F401
    except ImportError as e:
        raise TradingViewIndicatorError(
            "tradingview-ta kütüphanesi kurulu değil. Terminal'de şunu "
            "çalıştırın:\n  pip install tradingview-ta"
        ) from e


def normalize_bist_symbol(symbol, exchange=DEFAULT_EXCHANGE):
    """Bir hisse kodunu ('AKBNK', 'akbnk', zaten 'BIST:AKBNK' olabilir)
    TradingView'in beklediği 'EXCHANGE:SEMBOL' formatına çevirir.

    Örnek:
        normalize_bist_symbol("AKBNK") -> "BIST:AKBNK"
        normalize_bist_symbol("bist:akbnk") -> "BIST:AKBNK"
    """
    s = str(symbol).strip().upper()
    if ":" in s:
        return s
    return f"{exchange}:{s}"


def _analysis_to_dict(analysis, hisse):
    """Bir `tradingview_ta` Analysis nesnesini (veya None'ı) Johnny'nin
    standart teknik kolonlarına çevirir.

    Returns:
        dict: {"hisse": hisse, "rsi": ..., "macd_signal": ...,
        "ema20": ..., "ema50": ..., "ema200": ..., "adx": ...,
        "atr_pct": ...}
        `analysis` None ise (veri bulunamadıysa) teknik alanların
        hepsi None'dır - hisse ATLANMAZ, sadece bu alanlar boş kalır.
    """
    sonuc = {
        "hisse": hisse, "rsi": None, "macd_signal": None, "ema20": None,
        "ema50": None, "ema200": None, "adx": None, "atr_pct": None,
    }
    if analysis is None:
        return sonuc

    ind = getattr(analysis, "indicators", None) or {}

    sonuc["rsi"] = ind.get("RSI")
    sonuc["ema20"] = ind.get("EMA20")
    sonuc["ema50"] = ind.get("EMA50")
    sonuc["ema200"] = ind.get("EMA200")
    sonuc["adx"] = ind.get("ADX")

    macd = ind.get("MACD.macd")
    macd_sinyal = ind.get("MACD.signal")
    if macd is not None and macd_sinyal is not None:
        # Johnny'nin "macd_signal" kolonu MACD histogramını (MACD -
        # Sinyal farkı) temsil eder (bkz. data_mapper.py alias yorumları).
        try:
            sonuc["macd_signal"] = round(float(macd) - float(macd_sinyal), 4)
        except (TypeError, ValueError):
            sonuc["macd_signal"] = None

    atr = ind.get("ATR")
    kapanis = ind.get("close")
    if atr is not None and kapanis:
        try:
            sonuc["atr_pct"] = round(float(atr) / float(kapanis) * 100, 2)
        except (TypeError, ValueError, ZeroDivisionError):
            sonuc["atr_pct"] = None

    return sonuc


def fetch_tradingview_indicators(
    symbol, screener=DEFAULT_SCREENER, exchange=DEFAULT_EXCHANGE,
    interval=DEFAULT_INTERVAL, timeout=10,
):
    """Tek bir hisse için TradingView'den teknik göstergeleri çeker.

    Args:
        symbol: hisse kodu (örn. "AKBNK" ya da "BIST:AKBNK")
        screener/exchange/interval: TradingView parametreleri
            (config/watchlist.yaml -> tradingview altından ayarlanabilir)
        timeout: istek zaman aşımı (saniye)

    Returns:
        dict: {"hisse": symbol, "rsi": ..., "macd_signal": ...,
        "ema20": ..., "ema50": ..., "ema200": ..., "adx": ...,
        "atr_pct": ...}. Veri alınamazsa tüm alanlar None (hata
        fırlatmaz).
    """
    _ensure_tradingview_ta()
    from tradingview_ta import TA_Handler

    tv_kod = normalize_bist_symbol(symbol, exchange).split(":", 1)[1]

    try:
        handler = TA_Handler(
            symbol=tv_kod, exchange=exchange, screener=screener,
            interval=interval, timeout=timeout,
        )
        handler.add_indicators(EK_GOSTERGELER)
        analysis = handler.get_analysis()
    except Exception as e:
        print(f"[tradingview_indicators] {symbol}: veri alınamadı - {e}")
        analysis = None

    return _analysis_to_dict(analysis, symbol)


def fetch_indicators_for_candidates(
    symbols, screener=DEFAULT_SCREENER, exchange=DEFAULT_EXCHANGE,
    interval=DEFAULT_INTERVAL, on_progress=None, timeout=10,
):
    """Aday hisse listesi için TradingView'den teknik göstergeleri
    ÖNCE tek bir toplu istekte (get_multiple_analysis) çekmeyi dener -
    bu, N ayrı istek yerine tek bir HTTP isteğiyle tüm adayları alır ve
    hem daha hızlı hem de TradingView'in uç noktasına karşı daha
    "kibar"dır. Toplu istek tamamen başarısız olursa (örn. ağ hatası),
    HER HİSSE için TEK TEK deneyen bir yedek moda geçilir (aralarında
    kısa bir bekleme ile) - böylece tek bir ağ sorunu TÜM adayların
    verisiz kalmasına yol açmaz.

    Args:
        symbols: hisse kodları listesi (örn. ["AKBNK", "SASA", ...])
        on_progress: opsiyonel callable(str) - her hisse için
            "alındı"/"alınamadı" bilgisini loglar

    Returns:
        pd.DataFrame: her satır bir hisse (kolon: "hisse" + rsi,
        macd_signal, ema20, ema50, ema200, adx, atr_pct). Veri
        bulunamayan hisseler için ilgili alanlar None/NaN'dir, ama
        satır yine de DataFrame'de yer alır (Radar verisiyle
        birleştirilmeye hazır) - hiçbir hisse bu adımda "atlanmaz".
    """
    def _bildir(mesaj):
        print(f"[tradingview_indicators] {mesaj}")
        if on_progress:
            try:
                on_progress(mesaj)
            except Exception:
                pass

    _ensure_tradingview_ta()
    from tradingview_ta import get_multiple_analysis

    symbols = list(symbols)
    tv_semboller = [normalize_bist_symbol(s, exchange) for s in symbols]

    sonuc_map = None
    try:
        sonuc_map = get_multiple_analysis(
            screener=screener, interval=interval, symbols=tv_semboller,
            additional_indicators=EK_GOSTERGELER, timeout=timeout,
        )
    except Exception as e:
        _bildir(
            f"TradingView toplu isteği başarısız oldu ({e}); tek tek "
            "denenecek."
        )
        sonuc_map = None

    kayitlar = []

    if sonuc_map is not None:
        for orijinal, tv_sembol in zip(symbols, tv_semboller):
            analysis = sonuc_map.get(tv_sembol.upper())
            if analysis is None:
                _bildir(f"TradingView {orijinal} teknik veri alınamadı.")
            else:
                _bildir(f"TradingView {orijinal} teknik veri alındı.")
            kayitlar.append(_analysis_to_dict(analysis, orijinal))
    else:
        # Yedek mod: tek tek, aralarında kısa bekleme ile
        toplam = len(symbols)
        for i, orijinal in enumerate(symbols, start=1):
            kayit = fetch_tradingview_indicators(
                orijinal, screener=screener, exchange=exchange,
                interval=interval, timeout=timeout,
            )
            if kayit.get("rsi") is None and kayit.get("ema20") is None:
                _bildir(f"TradingView {orijinal} teknik veri alınamadı.")
            else:
                _bildir(f"TradingView {orijinal} teknik veri alındı.")
            kayitlar.append(kayit)
            if i < toplam:
                time.sleep(YEDEK_ISTEK_BEKLEME_SN)

    # BUG TEŞHİSİ (canlı testte görüldü: 20/20 aday için "teknik veri
    # alınamadı" - %0 başarı). Tek tek her hissenin TradingView'de
    # bulunamamış olması istatistiksel olarak pek olası değildir (KOZAL,
    # KOZAA gibi çok likit/bilinen hisseler dahil); bu yüzden %0 başarı
    # durumunda KÖR KÖRÜNE tahmin etmek yerine DOĞRUDAN bir teşhis
    # isteği atılıp HTTP durum kodu ve yanıt önizlemesi loglanır - bir
    # sonraki canlı testte gerçek nedenin (ağ engeli/proxy, bot koruması,
    # TradingView'in scan API şemasını değiştirmesi vb.) hemen ortaya
    # çıkması için.
    if kayitlar and all(k.get("rsi") is None for k in kayitlar):
        teshis = _ham_scanner_teshisi(
            tv_semboller, screener=screener, interval=interval, timeout=timeout
        )
        _bildir(
            "UYARI: TradingView'den HİÇBİR aday için teknik veri "
            f"alınamadı (0/{len(kayitlar)} başarı). {teshis}"
        )

    return pd.DataFrame(kayitlar)
