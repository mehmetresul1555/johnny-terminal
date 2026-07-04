"""
Technical Engine
----------------
Johnny Score'un "Teknik" alt skorunu (maksimum 30 puan) ham teknik
göstergelerden hesaplar.

Girdi kolonları (CSV'den/Fintables'tan gelir):
    rsi, macd_signal, ema20, ema50, ema200, adx

v1.0 FINAL: bu kolonların hepsi artık OPSİYONELDİR. Fintables tarayıcı
otomasyonu bir hissenin Teknik Analiz sayfasından bu göstergeleri
okuyamazsa (örn. gösterge bir canvas/grafik üzerinde render ediliyorsa
ve DOM'da metin olarak bulunamıyorsa) ilgili alan(lar) None/NaN olarak
gelir. Aşağıdaki her `_x_score` fonksiyonu zaten eksik veri için makul
bir varsayılanla nötr/ortalama bir puan üretir (asla çökmez); hangi
göstergelerin eksik olduğu (kullanıcıya "neden bu puan" açıklamasında
göstermek için) `scoring/johnny_score.py` -> `_eksik_teknik_gostergeler`
tarafından ayrıca tespit edilir.

Puan dağılımı (toplam 30):
    - RSI              : 10 puan  (50-70 bandı ideal; eksikse RSI=50 varsayılır)
    - EMA hizalanması  : 10 puan  (ema20 > ema50 > ema200 => tam pozitif; eksikse 0 varsayılır)
    - ADX              : 5 puan   (güçlü trend => yüksek puan; eksikse 0 varsayılır)
    - MACD             : 5 puan   (pozitif => yüksek puan; eksikse nötr/0 varsayılır)
"""

MAX_SCORE = 30
# v1.0 FINAL: hiçbiri artık zorunlu değil (bkz. modül docstring'i).
REQUIRED_COLUMNS = []


def _safe_float(value, default=0.0):
    """Bozuk/eksik/NaN veriyi varsayılan değere çevirir."""
    try:
        v = float(value)
        if v != v:  # NaN kontrolü
            return default
        return v
    except (TypeError, ValueError):
        return default


def _clip(value, lo, hi):
    return max(lo, min(value, hi))


def _rsi_score(rsi):
    """RSI 50-70 arasında ideal kabul edilir (tam puan). Bandın altına
    inildikçe ya da aşırı alım bölgesine (70 üstü) çıkıldıkça puan azalır."""
    rsi = _safe_float(rsi, default=50.0)
    if 50 <= rsi <= 70:
        return 10.0
    elif rsi < 50:
        return _clip(10 - (50 - rsi) * 0.35, 0, 10)
    else:  # rsi > 70 -> aşırı alım riski
        return _clip(10 - (rsi - 70) * 0.45, 0, 10)


def _ema_score(ema20, ema50, ema200):
    """ema20 > ema50 > ema200 tam pozitif diziliş kabul edilir. Üç ikili
    karşılaştırmadan kaçı doğruysa puan orantılı verilir."""
    ema20 = _safe_float(ema20)
    ema50 = _safe_float(ema50)
    ema200 = _safe_float(ema200)
    conditions = [ema20 > ema50, ema50 > ema200, ema20 > ema200]
    return 10.0 * sum(conditions) / len(conditions)


def _adx_score(adx):
    """ADX 15 altı zayıf/yatay trend, 30 üstü güçlü trend kabul edilir."""
    adx = _safe_float(adx)
    return _clip((adx - 15) / 15 * 5, 0, 5)


def _macd_score(macd_signal):
    """MACD sinyali pozitifse tam puan, negatifse puan yok."""
    macd_signal = _safe_float(macd_signal)
    if macd_signal > 0:
        return 5.0
    elif macd_signal == 0:
        return 2.5
    return 0.0


def compute_technical_score(row):
    """Bir hisse satırından (pandas Series/dict) teknik skoru hesaplar.

    Returns:
        (score: float 0-30, detail: dict)
    """
    rsi_score = _rsi_score(row.get("rsi"))
    ema_score = _ema_score(row.get("ema20"), row.get("ema50"), row.get("ema200"))
    adx_score = _adx_score(row.get("adx"))
    macd_score = _macd_score(row.get("macd_signal"))

    total = _clip(rsi_score + ema_score + adx_score + macd_score, 0, MAX_SCORE)

    detail = {
        "rsi_puan": round(rsi_score, 1),
        "ema_hizalama_puan": round(ema_score, 1),
        "adx_puan": round(adx_score, 1),
        "macd_puan": round(macd_score, 1),
    }
    return round(total, 1), detail
