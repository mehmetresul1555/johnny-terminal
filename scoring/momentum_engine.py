"""
Momentum Engine
---------------
Johnny Score'un "Momentum" alt skorunu (maksimum 20 puan) ham verilerden
hesaplar.

Girdi kolonları (CSV'den gelir):
    fiyat, ema20, atr_pct, volume_ratio

Puan dağılımı (toplam 20):
    - Volume Ratio        : 8 puan  (ortalama hacmin üzerinde => yüksek puan)
    - ATR                 : 6 puan  (günlük trade için ideal volatilite bandı)
    - Fiyat momentumu     : 6 puan  (fiyatın EMA20'nin üzerinde oluşu, proxy)
"""

MAX_SCORE = 20
REQUIRED_COLUMNS = ["fiyat", "ema20", "atr_pct", "volume_ratio"]


def _safe_float(value, default=0.0):
    try:
        v = float(value)
        if v != v:  # NaN kontrolü
            return default
        return v
    except (TypeError, ValueError):
        return default


def _clip(value, lo, hi):
    return max(lo, min(value, hi))


def _volume_score(volume_ratio):
    """volume_ratio = güncel hacim / ortalama hacim. 1.0 = ortalama, 2.0 ve
    üzeri = tam puan."""
    volume_ratio = _safe_float(volume_ratio, default=1.0)
    return _clip(volume_ratio * 4, 0, 8)


def _atr_score(atr_pct):
    """Günlük trade için ne çok düşük (hareketsiz) ne çok yüksek (aşırı
    riskli) olmayan bir ATR idealdir; ~%2 civarı tam puan alır."""
    atr_pct = _safe_float(atr_pct, default=1.5)
    return _clip(6 * (1 - abs(atr_pct - 2.0) / 2.0), 0, 6)


def _price_momentum_score(fiyat, ema20):
    """Fiyatın EMA20'ye göre yüzde konumu, kısa vadeli fiyat momentumu için
    basit bir proxy olarak kullanılır. Fiyat EMA20'nin ne kadar üzerindeyse
    momentum o kadar güçlü kabul edilir (%3 ve üzeri => tam puan)."""
    fiyat = _safe_float(fiyat)
    ema20 = _safe_float(ema20)
    if ema20 <= 0:
        return 0.0
    momentum_pct = (fiyat - ema20) / ema20 * 100
    return _clip(momentum_pct * 2, 0, 6)


def compute_momentum_score(row):
    """Bir hisse satırından (pandas Series/dict) momentum skoru hesaplar.

    Returns:
        (score: float 0-20, detail: dict)
    """
    volume_score = _volume_score(row.get("volume_ratio"))
    atr_score = _atr_score(row.get("atr_pct"))
    momentum_score = _price_momentum_score(row.get("fiyat"), row.get("ema20"))

    total = _clip(volume_score + atr_score + momentum_score, 0, MAX_SCORE)

    detail = {
        "hacim_puan": round(volume_score, 1),
        "atr_puan": round(atr_score, 1),
        "fiyat_momentum_puan": round(momentum_score, 1),
    }
    return round(total, 1), detail
