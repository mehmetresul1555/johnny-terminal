"""
Johnny Score v2
-----------------
BIST günlük trade karar destek sistemi için skorlama motoru.

v2 ile birlikte alt skorlar artık CSV'den hazır olarak okunmuyor; ham
teknik/temel göstergelerden üç ayrı motor tarafından hesaplanıyor:

    scoring/technical_engine.py    -> Teknik skor      (max 30)
    scoring/momentum_engine.py     -> Momentum skor     (max 20)
    scoring/fundamental_engine.py  -> Bilanço/Temel skor (max 20)

Geri kalan üç alt skor CSV'de doğrudan puan olarak verilir:
    haber_puani        -> Haber/KAP/Katalizör skoru      (max 10)
    kurumsal_puani      -> Kurumsal beklenti skoru        (max 10)
    piyasa_rejimi       -> Piyasa rejimi skoru            (max 10)

Toplam 100 puan üzerinden 6 alt skor:
- teknik_skor        (max 30)
- momentum_skor      (max 20)
- bilanco_skor       (max 20)   -> bilanço / temel
- haber_skor         (max 10)   -> haber / KAP / katalizör
- kurumsal_skor      (max 10)   -> kurumsal beklenti (analist/hedef fiyat vb.)
- piyasa_rejimi_skor (max 10)

Durum kuralları:
- 85+           -> AL
- 70-84         -> İZLE
- 70 altı       -> UZAK DUR

Risk kuralları:
- Stop mesafesi maksimum %2
- Hedef 1 minimum %1.5
- Hedef 2 minimum %3

Bu modül, veri kaynağı ne olursa olsun (CSV/Excel bugün, Fintables yarın)
aynı skorlama sözleşmesini kullanır: girdi olarak ham göstergeleri, fiyatı
ve (varsa) ATR yüzdesini içeren bir DataFrame bekler. Eski v1 mimarisinin
dış davranışı (score_dataframe çıktı kolonları, eşikler, risk kuralları)
değişmedi; sadece alt skorların nasıl üretildiği değişti.
"""

import pandas as pd

from scoring import fundamental_engine, momentum_engine, technical_engine

# Her alt skorun üstünden geçemeyeceği maksimum değer
SUB_SCORE_MAX = {
    "teknik_skor": 30,
    "momentum_skor": 20,
    "bilanco_skor": 20,
    "haber_skor": 10,
    "kurumsal_skor": 10,
    "piyasa_rejimi_skor": 10,
}

# Skorlama için zorunlu ham kolonlar (hepsi CSV'de bulunmalı)
REQUIRED_COLUMNS = (
    ["hisse", "fiyat"]
    + technical_engine.REQUIRED_COLUMNS
    + momentum_engine.REQUIRED_COLUMNS
    + fundamental_engine.REQUIRED_COLUMNS
    + ["haber_puani", "kurumsal_puani", "piyasa_rejimi"]
)
# Yinelenen kolonları (örn. fiyat/atr_pct/ema20 birden fazla motor kullanabilir) temizle
REQUIRED_COLUMNS = list(dict.fromkeys(REQUIRED_COLUMNS))

LABELS = {
    "teknik_skor": "Teknik",
    "momentum_skor": "Momentum",
    "bilanco_skor": "Bilanço/Temel",
    "haber_skor": "Haber/KAP",
    "kurumsal_skor": "Kurumsal beklenti",
    "piyasa_rejimi_skor": "Piyasa rejimi",
}


def _clip(value, max_value):
    """Bir alt skoru 0 ile max_value arasına sıkıştırır. Bozuk/eksik veri
    için 0 döndürür (sistemi kırmamak için)."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 0.0
    return max(0.0, min(value, max_value))


def compute_total_score(row):
    """Üç motoru (teknik/momentum/bilanço) ve CSV'deki doğrudan puanları
    (haber/kurumsal/piyasa rejimi) birleştirip toplam Johnny Score'u
    hesaplar.

    Returns:
        (total_score: float, clipped_scores: dict, engine_detail: dict)
    """
    teknik_skor, teknik_detay = technical_engine.compute_technical_score(row)
    momentum_skor, momentum_detay = momentum_engine.compute_momentum_score(row)
    bilanco_skor, bilanco_detay = fundamental_engine.compute_fundamental_score(row)

    haber_skor = _clip(row.get("haber_puani", 0), SUB_SCORE_MAX["haber_skor"])
    kurumsal_skor = _clip(row.get("kurumsal_puani", 0), SUB_SCORE_MAX["kurumsal_skor"])
    piyasa_skor = _clip(row.get("piyasa_rejimi", 0), SUB_SCORE_MAX["piyasa_rejimi_skor"])

    clipped = {
        "teknik_skor": teknik_skor,
        "momentum_skor": momentum_skor,
        "bilanco_skor": bilanco_skor,
        "haber_skor": haber_skor,
        "kurumsal_skor": kurumsal_skor,
        "piyasa_rejimi_skor": piyasa_skor,
    }
    engine_detail = {
        "teknik": teknik_detay,
        "momentum": momentum_detay,
        "bilanco": bilanco_detay,
    }
    total = round(sum(clipped.values()), 1)
    return total, clipped, engine_detail


def determine_durum(total_score, thresholds):
    """Toplam skora göre AL / İZLE / UZAK DUR kararı verir."""
    al_esik = thresholds.get("al", 85)
    izle_esik = thresholds.get("izle", 70)
    if total_score >= al_esik:
        return "AL"
    elif total_score >= izle_esik:
        return "İZLE"
    return "UZAK DUR"


def compute_trade_levels(fiyat, atr_pct, risk_cfg):
    """Alım aralığı, stop, hedef1 ve hedef2 seviyelerini hesaplar.

    Kurallar (config/watchlist.yaml -> risk):
        - stop mesafesi <= stop_max_pct (varsayılan %2)
        - hedef1 >= hedef1_min_pct     (varsayılan %1.5)
        - hedef2 >= hedef2_min_pct     (varsayılan %3)

    atr_pct verilmemiş/geçersizse günlük trade için makul bir varsayım
    (yüzde 1.5 volatilite) kullanılır.
    """
    fiyat = float(fiyat)
    try:
        atr_pct = float(atr_pct)
        if atr_pct <= 0:
            raise ValueError
    except (TypeError, ValueError):
        atr_pct = 1.5

    stop_max = risk_cfg.get("stop_max_pct", 2.0)
    hedef1_min = risk_cfg.get("hedef1_min_pct", 1.5)
    hedef2_min = risk_cfg.get("hedef2_min_pct", 3.0)
    giris_bant = risk_cfg.get("giris_bant_pct", 0.3)

    stop_pct = min(stop_max, max(0.8, atr_pct * 1.2))
    hedef1_pct = max(hedef1_min, atr_pct * 1.8)
    hedef2_pct = max(hedef2_min, atr_pct * 3.5)

    giris_alt = fiyat * (1 - giris_bant / 100)
    giris_ust = fiyat * (1 + giris_bant / 100)
    stop = fiyat * (1 - stop_pct / 100)
    hedef1 = fiyat * (1 + hedef1_pct / 100)
    hedef2 = fiyat * (1 + hedef2_pct / 100)

    return {
        "giris_alt": round(giris_alt, 2),
        "giris_ust": round(giris_ust, 2),
        "stop": round(stop, 2),
        "hedef1": round(hedef1, 2),
        "hedef2": round(hedef2, 2),
        "stop_pct": round(stop_pct, 2),
        "hedef1_pct": round(hedef1_pct, 2),
        "hedef2_pct": round(hedef2_pct, 2),
    }


def generate_gerekce(clipped_scores, analist_notu=None):
    """Alt skorların dağılımına bakarak otomatik kısa bir gerekçe cümlesi
    üretir. Varsa analistin (CSV'deki gerekce_notu kolonu) elle girdiği
    not başa eklenir."""
    ratios = {k: (v / SUB_SCORE_MAX[k]) for k, v in clipped_scores.items()}
    ranked = sorted(ratios.items(), key=lambda x: x[1], reverse=True)
    guclu = ranked[:2]
    zayif_k, _ = ranked[-1]

    guclu_txt = " ve ".join(
        f"{LABELS[k]} ({clipped_scores[k]:.0f}/{SUB_SCORE_MAX[k]})" for k, _ in guclu
    )
    zayif_txt = f"{LABELS[zayif_k]} ({clipped_scores[zayif_k]:.0f}/{SUB_SCORE_MAX[zayif_k]})"

    cumle = f"{guclu_txt} güçlü; {zayif_txt} zayıf."

    if analist_notu is not None:
        not_str = str(analist_notu).strip()
        if not_str and not_str.lower() != "nan":
            cumle = f"{not_str} {cumle}"
    return cumle


def score_dataframe(df, config):
    """Ham veriden (CSV/Excel/ileride Fintables) Johnny Terminal çıktı
    tablosunu üretir.

    df kolonları (bkz. REQUIRED_COLUMNS): hisse, fiyat, rsi, macd_signal,
                  ema20, ema50, ema200, adx, atr_pct, volume_ratio, fk,
                  pddd, roe, net_borc_favok, haber_puani, kurumsal_puani,
                  piyasa_rejimi

    Returns:
        pd.DataFrame  (Johnny Score'a göre azalan sırada), kolonlar:
        Hisse, Fiyat, Johnny Score, Durum, Alım Aralığı, Stop, Hedef 1,
        Hedef 2, Gerekçe
    """
    thresholds = config.get("thresholds", {"al": 85, "izle": 70})
    risk_cfg = config.get("risk", {})

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Eksik kolon(lar): {', '.join(missing)}")

    rows = []
    for _, row in df.iterrows():
        total, clipped, _engine_detail = compute_total_score(row)
        durum = determine_durum(total, thresholds)

        atr_pct = row.get("atr_pct", None)
        analist_notu = row.get("gerekce_notu", None)
        gerekce = generate_gerekce(clipped, analist_notu)

        if durum == "UZAK DUR":
            alim_araligi = "-"
            stop_txt = "-"
            hedef1_txt = "-"
            hedef2_txt = "-"
        else:
            lvl = compute_trade_levels(row["fiyat"], atr_pct, risk_cfg)
            alim_araligi = f"{lvl['giris_alt']:.2f} - {lvl['giris_ust']:.2f}"
            stop_txt = f"{lvl['stop']:.2f} (-%{lvl['stop_pct']:.1f})"
            hedef1_txt = f"{lvl['hedef1']:.2f} (+%{lvl['hedef1_pct']:.1f})"
            hedef2_txt = f"{lvl['hedef2']:.2f} (+%{lvl['hedef2_pct']:.1f})"

        rows.append({
            "Hisse": row["hisse"],
            "Fiyat": row["fiyat"],
            "Johnny Score": total,
            "Durum": durum,
            "Alım Aralığı": alim_araligi,
            "Stop": stop_txt,
            "Hedef 1": hedef1_txt,
            "Hedef 2": hedef2_txt,
            "Gerekçe": gerekce,
        })

    result = pd.DataFrame(rows)
    result = result.sort_values("Johnny Score", ascending=False).reset_index(drop=True)
    return result
