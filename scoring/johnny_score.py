"""
Johnny Score v1
-----------------
BIST gunluk trade karar destek sistemi icin skorlama motoru.

Toplam 100 puan uzerinden 6 alt skor:
- teknik_skor        (max 30)
- momentum_skor      (max 20)
- bilanco_skor       (max 20)   -> bilanco / temel
- haber_skor         (max 10)   -> haber / KAP / katalizor
- kurumsal_skor      (max 10)   -> kurumsal beklenti (analist/hedef fiyat vb.)
- piyasa_rejimi_skor (max 10)

Durum kurallari:
- 85+           -> AL
- 70-84         -> IZLE
- 70 alti       -> UZAK DUR

Risk kurallari:
- Stop mesafesi maksimum %2
- Hedef 1 minimum %1.5
- Hedef 2 minimum %3

Bu modul, veri kaynagi ne olursa olsun (CSV/Excel bugun, Fintables yarin)
ayni skorlama sozlesmesini kullanir: girdi olarak alt skorlari, fiyati ve
(varsa) ATR yuzdesini icken bir DataFrame bekler.
"""

import pandas as pd

# Her alt skorun ustunden gecemeyecegi maksimum deger
SUB_SCORE_MAX = {
    "teknik_skor": 30,
    "momentum_skor": 20,
    "bilanco_skor": 20,
    "haber_skor": 10,
    "kurumsal_skor": 10,
    "piyasa_rejimi_skor": 10,
}

# Skorlama icin zorunlu kolonlar (atr_pct ve gerekce_notu opsiyoneldir)
REQUIRED_COLUMNS = ["hisse", "fiyat"] + list(SUB_SCORE_MAX.keys())

LABELS = {
    "teknik_skor": "Teknik",
    "momentum_skor": "Momentum",
    "bilanco_skor": "Bilanço/Temel",
    "haber_skor": "Haber/KAP",
    "kurumsal_skor": "Kurumsal beklenti",
    "piyasa_rejimi_skor": "Piyasa rejimi",
}


def _clip(value, max_value):
    """Bir alt skoru 0 ile max_value arasina sikistirir. Bozuk/eksik veri
    icin 0 dondurur (sistemi kirmamak icin)."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 0.0
    return max(0.0, min(value, max_value))


def compute_total_score(row):
    """Alt skorlari sinirlar icine cekip toplam Johnny Score'u hesaplar.

    Returns:
        (total_score: float, clipped_scores: dict)
    """
    total = 0.0
    clipped = {}
    for col, max_val in SUB_SCORE_MAX.items():
        v = _clip(row.get(col, 0), max_val)
        clipped[col] = v
        total += v
    return round(total, 1), clipped


def determine_durum(total_score, thresholds):
    """Toplam skora gore AL / IZLE / UZAK DUR karari verir."""
    al_esik = thresholds.get("al", 85)
    izle_esik = thresholds.get("izle", 70)
    if total_score >= al_esik:
        return "AL"
    elif total_score >= izle_esik:
        return "İZLE"
    return "UZAK DUR"


def compute_trade_levels(fiyat, atr_pct, risk_cfg):
    """Alim araligi, stop, hedef1 ve hedef2 seviyelerini hesaplar.

    Kurallar (config/watchlist.yaml -> risk):
        - stop mesafesi <= stop_max_pct (varsayilan %2)
        - hedef1 >= hedef1_min_pct     (varsayilan %1.5)
        - hedef2 >= hedef2_min_pct     (varsayilan %3)

    atr_pct verilmemis/gecersizse gunluk trade icin makul bir varsayim
    (yuzde 1.5 volatilite) kullanilir.
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
    """Alt skorlarin dagilimina bakarak otomatik kisa bir gerekce cumlesi
    uretir. Varsa analistin (CSV'deki gerekce_notu kolonu) elle girdigi
    not basa eklenir."""
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
    """Ham veriden (CSV/Excel/ileride Fintables) Johnny Terminal cikti
    tablosunu uretir.

    df kolonlari: hisse, fiyat, teknik_skor, momentum_skor, bilanco_skor,
                  haber_skor, kurumsal_skor, piyasa_rejimi_skor,
                  [atr_pct], [gerekce_notu]

    Returns:
        pd.DataFrame  (Johnny Score'a gore azalan sirada), kolonlar:
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
        total, clipped = compute_total_score(row)
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
