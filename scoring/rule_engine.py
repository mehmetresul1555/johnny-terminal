"""
Rule Engine (v0.3)
-------------------
Johnny Score artık sadece alt skorların lineer toplamı değildir. Bu modül,
göstergeler arasındaki KOŞULLU kombinasyonları (confluence) IF/THEN
mantığıyla tespit edip sabit bonus puanlar ekler.

Her kural üç şeyden oluşur:
    - kosul(row) -> bool   : koşul(lar) sağlanıyor mu?
    - puan                  : koşul sağlanırsa eklenecek bonus puan
    - aciklama               : insan-okunur açıklama ("Johnny bu hisseye
                               neden X verdi?" sorusunun madde madde
                               cevabı için kullanılır)

Yeni bir kural eklemek için RULES listesine bir tane daha eklemek yeterli;
johnny_score.py ve app.py başka bir değişiklik gerektirmez.
"""

MAX_RULE_BONUS_INFO = "Kurallar birbirinden bağımsızdır; birden fazla kural aynı anda tetiklenebilir."


def _safe_float(value, default=0.0):
    """Bozuk/eksik/NaN veriyi varsayılan değere çevirir."""
    try:
        v = float(value)
        if v != v:  # NaN kontrolü
            return default
        return v
    except (TypeError, ValueError):
        return default


def _to_bool(value):
    """CSV'den 0/1, True/False, 'evet'/'hayır' gibi farklı biçimlerde
    gelebilecek bayrak kolonlarını booleana çevirir."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    try:
        return bool(int(value))
    except (TypeError, ValueError):
        pass
    return str(value).strip().lower() in ("1", "true", "evet", "yes")


# ---------------------------------------------------------------------------
# Kural koşulları
# ---------------------------------------------------------------------------

def _kosul_teknik_confluence(row):
    """EMA20 > EMA50 > EMA200 (tam pozitif dizilim) + MACD pozitif +
    ADX > 25 (güçlü trend) aynı anda gerçekleşiyor mu?"""
    ema20 = _safe_float(row.get("ema20"))
    ema50 = _safe_float(row.get("ema50"))
    ema200 = _safe_float(row.get("ema200"))
    macd = _safe_float(row.get("macd_signal"))
    adx = _safe_float(row.get("adx"))
    return ema20 > ema50 > ema200 and macd > 0 and adx > 25


def _kosul_rsi_hacim(row):
    """RSI ideal bantta (55-65) ve hacim ortalamanın 1.5 katından fazla mı?"""
    rsi = _safe_float(row.get("rsi"))
    volume_ratio = _safe_float(row.get("volume_ratio"))
    return 55 <= rsi <= 65 and volume_ratio > 1.5


def _kosul_guclu_bilanco(row):
    """ROE %25'in üzerinde ve Net Borç/FAVÖK 2x'in altında mı (güçlü,
    düşük kaldıraçlı bilanço)?"""
    roe = _safe_float(row.get("roe"))
    net_borc_favok = _safe_float(row.get("net_borc_favok"), default=99)
    return roe > 25 and net_borc_favok < 2


def _kosul_yeni_is_iliskisi(row):
    """Yeni bir iş ilişkisi/ortaklık (yeni_is_iliskisi=1) VE kurumsal
    beklenti yüksek (kurumsal_puani >= 8) mi?"""
    yeni_is = _to_bool(row.get("yeni_is_iliskisi", 0))
    kurumsal_puani = _safe_float(row.get("kurumsal_puani"))
    return yeni_is and kurumsal_puani >= 8


# ---------------------------------------------------------------------------
# Kural kataloğu
# ---------------------------------------------------------------------------

RULES = [
    {
        "id": "R1",
        "aciklama": (
            "EMA20 > EMA50 > EMA200 tam pozitif dizilim + MACD pozitif + "
            "ADX > 25 (güçlü trend teyidi)"
        ),
        "kosul": _kosul_teknik_confluence,
        "puan": 10,
    },
    {
        "id": "R2",
        "aciklama": "RSI 55-65 ideal bantta + Hacim ortalamanın 1.5 katından fazla",
        "kosul": _kosul_rsi_hacim,
        "puan": 8,
    },
    {
        "id": "R3",
        "aciklama": "ROE %25 üzeri + Net Borç/FAVÖK 2x altı (güçlü, düşük kaldıraçlı bilanço)",
        "kosul": _kosul_guclu_bilanco,
        "puan": 8,
    },
    {
        "id": "R4",
        "aciklama": "Yeni iş ilişkisi/ortaklık + kurumsal beklenti yüksek",
        "kosul": _kosul_yeni_is_iliskisi,
        "puan": 7,
    },
]


def evaluate_rules(row):
    """Tüm kuralları bir hisse satırına (pandas Series/dict) uygular.

    Returns:
        (bonus_total: float, fired_rules: list[dict])
        fired_rules -> her biri {"id", "aciklama", "puan"} içeren, sadece
        tetiklenen kuralların listesi (sırayla, "Johnny neden bu puanı
        verdi?" açıklaması için kullanılır).
    """
    fired_rules = []
    bonus_total = 0.0

    for rule in RULES:
        try:
            tetiklendi = bool(rule["kosul"](row))
        except Exception:
            # Bozuk/eksik veri kuralı çökertmesin; sadece tetiklenmemiş say
            tetiklendi = False

        if tetiklendi:
            fired_rules.append({
                "id": rule["id"],
                "aciklama": rule["aciklama"],
                "puan": rule["puan"],
            })
            bonus_total += rule["puan"]

    return round(bonus_total, 1), fired_rules
