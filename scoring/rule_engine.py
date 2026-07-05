"""
Rule Engine (v0.4 - otomasyon verisine göre yeniden tasarım)
---------------------------------------------------------------
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

BUG FIX (kullanıcı canlı testte fark etti - "Top 3 sürekli UZAK DUR
çıkıyor"): eski R2/R3/R4, Fintables + TradingView otomasyonunun HİÇBİR
ZAMAN sağlamadığı kolonlara (volume_ratio, net_borc_favok,
yeni_is_iliskisi) bağlıydı - bu yüzden otomatik "Fintables'tan Güncelle"
akışında bu üç kural pratikte HİÇ tetiklenemiyordu, sadece R1 (+10)
ulaşılabilir kalıyordu ve toplam skor 70 (İZLE) eşiğinin çok altında
sıkışıyordu. R2/R3/R4 artık SADECE otomasyonda GERÇEKTEN gelen alanlara
(gün %, 1 hafta/1 ay/3 ay getiri - Fintables Radar'ın "Getiri" sekmesi
bunları HER ZAMAN sağlar, bkz. scoring/pre_screen.RADAR_POZISYONEL_INDEKS
- ve ROE/F-K/PD-DD, RSI, MACD, EMA gibi zaten güvenilir alanlara)
dayanıyor. Eşikler/puanlar ŞİŞİRİLMEDİ (Johnny hâlâ seçici) - sadece
kuralların KOŞULLARI, otomasyonun gerçekten üretebildiği verilerle
tetiklenebilir hale getirildi.
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


def _deger_eksik_mi(value):
    """None, boş string ya da NaN ise 'eksik' kabul edilir (fundamental_engine
    ile aynı mantık - kuralın MİSSİNG veriyi bir yöne YANLIŞLIKLA yormaması
    için önce eksiklik ayrı kontrol edilir)."""
    if value is None:
        return True
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value).strip() == ""
    return f != f  # NaN kontrolü


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
    ADX > 25 (güçlü trend) aynı anda gerçekleşiyor mu? (Değişmedi - zaten
    sadece TradingView'den GÜVENİLİR şekilde gelen alanları kullanıyordu.)"""
    ema20 = _safe_float(row.get("ema20"))
    ema50 = _safe_float(row.get("ema50"))
    ema200 = _safe_float(row.get("ema200"))
    macd = _safe_float(row.get("macd_signal"))
    adx = _safe_float(row.get("adx"))
    return ema20 > ema50 > ema200 and macd > 0 and adx > 25


def _kosul_rsi_gun_getiri(row):
    """YENİ (v0.4): RSI ideal-geniş bantta (50-68) + Gün % pozitif + Son 1
    haftalık getiri pozitif mi? Eskiden "RSI 55-65 + volume_ratio>1.5"
    idi - volume_ratio Fintables'tan HİÇBİR ZAMAN gelmediği için bu kural
    otomasyonda asla tetiklenemiyordu. gün %/1 haftalık getiri, Fintables
    Radar'ın HER ZAMAN sağladığı alanlardır."""
    rsi = _safe_float(row.get("rsi"))
    gun_yuzde = _safe_float(row.get("gun_yuzde"))
    getiri_1h = _safe_float(row.get("getiri_1h"))
    return 50 <= rsi <= 68 and gun_yuzde > 0 and getiri_1h > 0


def _kosul_makul_deger(row):
    """YENİ (v0.4): ROE varsa ROE > %15 mi? ROE eksikse, F/K VE PD/DD
    "makul" (aşırı pahalı olmayan) aralıktaysa yine bonus verir. Eskiden
    "ROE>25 + Net Borç/FAVÖK<2" idi - net_borc_favok Fintables'ın Rasyo
    Analiz Tablosu sayfasında sıklıkla ayrı bir kalem olarak bulunmuyor
    (bkz. fundamental_engine.py notları); bu yüzden kural neredeyse hiç
    tetiklenemiyordu. Artık net_borc_favok eksik olduğunda kural TAMAMEN
    KİLİTLENMİYOR, F/K+PD/DD üzerinden değerlendirmeye devam ediyor."""
    roe_ham = row.get("roe")
    if not _deger_eksik_mi(roe_ham):
        return _safe_float(roe_ham) > 15

    fk_ham, pddd_ham = row.get("fk"), row.get("pddd")
    if _deger_eksik_mi(fk_ham) or _deger_eksik_mi(pddd_ham):
        return False  # ne ROE ne F/K+PD/DD mevcut - veri yetersiz, bonus YOK
    fk = _safe_float(fk_ham)
    pddd = _safe_float(pddd_ham)
    return 0 < fk <= 15 and 0 < pddd <= 2.5


def _kosul_orta_vadeli_trend(row):
    """YENİ (v0.4): Fiyatın 1 aylık trendi pozitif + 3 aylık trendi "çok
    negatif" değil (> -%10) + TradingView teknik özeti olumlu (RSI>50,
    MACD histogram pozitif, EMA20>EMA50) mi? Eskiden "yeni iş ilişkisi +
    kurumsal beklenti" idi - bu ikisi de Fintables'tan HİÇBİR ZAMAN
    gelmiyor (Johnny'nin kendi öznel/gelecekteki KAP entegrasyonu alanları),
    bu yüzden otomasyonda asla tetiklenemiyordu. Artık HER ZAMAN mevcut
    olan getiri_1a/getiri_3a + TradingView göstergelerine dayanıyor."""
    getiri_1a = _safe_float(row.get("getiri_1a"))
    getiri_3a = _safe_float(row.get("getiri_3a"), default=-999)
    rsi = _safe_float(row.get("rsi"))
    macd = _safe_float(row.get("macd_signal"))
    ema20 = _safe_float(row.get("ema20"))
    ema50 = _safe_float(row.get("ema50"))
    teknik_ozet_olumlu = rsi > 50 and macd > 0 and ema20 > ema50
    return getiri_1a > 0 and getiri_3a > -10 and teknik_ozet_olumlu


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
        "aciklama": (
            "RSI 50-68 (geniş ideal bant) + Gün % pozitif + Son 1 haftalık "
            "getiri pozitif"
        ),
        "kosul": _kosul_rsi_gun_getiri,
        "puan": 8,
    },
    {
        "id": "R3",
        "aciklama": (
            "ROE %15 üzeri (yoksa F/K ve PD/DD makul aralıkta) - "
            "değerleme/karlılık açısından makul"
        ),
        "kosul": _kosul_makul_deger,
        "puan": 8,
    },
    {
        "id": "R4",
        "aciklama": (
            "1 aylık getiri pozitif + 3 aylık getiri çok negatif değil "
            "(> -%10) + TradingView teknik özeti olumlu (orta vadeli trend teyidi)"
        ),
        "kosul": _kosul_orta_vadeli_trend,
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
