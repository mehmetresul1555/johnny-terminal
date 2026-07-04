"""
Fundamental Engine
-------------------
Johnny Score'un "Bilanço/Temel" alt skorunu (maksimum 20 puan) ham bilanço
verilerinden hesaplar.

Girdi kolonları (CSV'den gelir):
    fk, pddd, roe, net_borc_favok

Puan dağılımı (toplam 20):
    - F/K            : 5 puan  (düşük F/K => yüksek puan)
    - PD/DD          : 5 puan  (düşük PD/DD => yüksek puan)
    - ROE            : 5 puan  (yüksek özkaynak karlılığı => yüksek puan)
    - Net Borç/FAVÖK : 5 puan  (düşük kaldıraç => yüksek puan)
"""

MAX_SCORE = 20
REQUIRED_COLUMNS = ["fk", "pddd", "roe", "net_borc_favok"]


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


def _fk_score(fk):
    """F/K negatif veya sıfırsa (zarar eden şirket) puan verilmez. Düşük
    F/K (ucuz) daha yüksek puan alır; F/K 5 ve altı tam puan, 15 ve üzeri 0."""
    fk = _safe_float(fk, default=-1)
    if fk <= 0:
        return 0.0
    return _clip(5 - (fk - 5) / 2, 0, 5)


def _pddd_score(pddd):
    """PD/DD negatif veya sıfırsa puan verilmez. 0.5 ve altı tam puan,
    2.5 ve üzeri 0 puan."""
    pddd = _safe_float(pddd, default=2.5)
    if pddd <= 0:
        return 0.0
    return _clip(5 * (2.5 - pddd) / 2.0, 0, 5)


def _roe_score(roe):
    """ROE %30 ve üzeri tam puan alır, %0 ve altı 0 puan."""
    roe = _safe_float(roe)
    return _clip(roe / 30 * 5, 0, 5)


def _net_debt_score(net_borc_favok):
    """Net Borç/FAVÖK 0 ve altı (net nakit pozisyonu) tam puan, 5x ve
    üzeri yüksek kaldıraç kabul edilip 0 puan alır."""
    net_borc_favok = _safe_float(net_borc_favok, default=5.0)
    return _clip(5 - net_borc_favok, 0, 5)


def compute_fundamental_score(row):
    """Bir hisse satırından (pandas Series/dict) bilanço/temel skoru
    hesaplar.

    Returns:
        (score: float 0-20, detail: dict)
    """
    fk_score = _fk_score(row.get("fk"))
    pddd_score = _pddd_score(row.get("pddd"))
    roe_score = _roe_score(row.get("roe"))
    debt_score = _net_debt_score(row.get("net_borc_favok"))

    total = _clip(fk_score + pddd_score + roe_score + debt_score, 0, MAX_SCORE)

    detail = {
        "fk_puan": round(fk_score, 1),
        "pddd_puan": round(pddd_score, 1),
        "roe_puan": round(roe_score, 1),
        "net_borc_favok_puan": round(debt_score, 1),
    }
    return round(total, 1), detail
