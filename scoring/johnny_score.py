"""
Johnny Score v3
-----------------
BIST günlük trade karar destek sistemi için skorlama motoru.

v3 ile birlikte Johnny Score artık alt skorların DÜZ (lineer) toplamı
DEĞİLDİR. Puanlama iki katmandan oluşur:

    1. Taban puan   -> teknik/momentum/bilanço motorları + haber/kurumsal/
                        piyasa rejimi puanlarının toplamı, SUB_SCORE_MAX
                        kadar hesaplanır ama son skora tam ağırlığıyla
                        yansımaz; `scoring.base_damping` katsayısıyla
                        sıkıştırılır (bkz. config/watchlist.yaml).
    2. Kural bonusu -> scoring/rule_engine.py içindeki IF/THEN kuralları
                        (confluence: birden fazla göstergenin AYNI ANDA
                        sağlanması) tetiklenirse sabit bonus puan ekler.
                        Asıl farklılaştırıcı puan artık buradan gelir;
                        ortalama-iyi ama hiçbir kombinasyonu tam
                        tetiklemeyen hisseler artık yüksek puan alamaz.

    Toplam = clip(taban_puan * base_damping + kural_bonusu, 0, 100)

Motorlar:
    scoring/technical_engine.py    -> Teknik skor       (max 30)
    scoring/momentum_engine.py     -> Momentum skor      (max 20)
    scoring/fundamental_engine.py  -> Bilanço/Temel skor (max 20)
    scoring/rule_engine.py         -> IF/THEN kural bonusları

Geri kalan üç alt skor CSV'de doğrudan puan olarak verilebilir, ama
v0.5'ten itibaren OPSİYONELDİR (Fintables bu üçünü hiçbir zaman
sağlamaz, çünkü bunlar Johnny'nin kendi öznel değerlendirmeleridir):
    haber_puani         -> Haber/KAP/Katalizör skoru      (max 10)
                           Eksikse varsayılan: 5/10.
                           TODO (gelecek): KAP bildirimlerinden otomatik
                           üretilecek (KAP entegrasyonu).
    kurumsal_puani      -> Kurumsal beklenti skoru         (max 10)
                           Eksikse varsayılan: 5/10.
                           TODO (gelecek): analist hedef fiyatları ve
                           kurum beklentilerinden otomatik üretilecek.
    piyasa_rejimi       -> Piyasa rejimi skoru             (max 10)
                           Eksikse varsayılan: 5/10.
                           TODO (gelecek): Johnny tarafından otomatik
                           hesaplanacak - BIST100 günlük değişim, XBANK,
                           XUSIN, işlem hacmi, VIX (opsiyonel) ve
                           USD/TRY (opsiyonel) verilerine bakılarak.
                           Kullanıcı bu üç kolonu manuel doldurmayacak.

Taban puanın 6 bileşeni (toplamda 100 puana denk gelir, ama son skora
damping uygulanmış haliyle katılır):
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
aynı skorlama sözleşmesini kullanır. Eski mimarinin dış davranışı
(score_dataframe çıktı kolonları, eşikler, risk kuralları) değişmedi;
sadece toplam skorun NASIL üretildiği değişti.
"""

import pandas as pd

from scoring import fundamental_engine, momentum_engine, rule_engine, technical_engine

# Her alt skorun üstünden geçemeyeceği maksimum değer
SUB_SCORE_MAX = {
    "teknik_skor": 30,
    "momentum_skor": 20,
    "bilanco_skor": 20,
    "haber_skor": 10,
    "kurumsal_skor": 10,
    "piyasa_rejimi_skor": 10,
}

# Taban puanın son skora ne kadar ağırlıkla yansıyacağı (bkz. config
# watchlist.yaml -> scoring.base_damping). 1.0 = eski (v2) lineer davranış.
DEFAULT_BASE_DAMPING = 0.6

# haber_puani / kurumsal_puani / piyasa_rejimi Fintables'tan hiçbir zaman
# gelmez (bunlar Johnny'nin kendi öznel puanlarıdır) - eksik olduklarında
# kullanılacak nötr varsayılan (10 üzerinden 5 = tam ortada, ne olumlu ne
# olumsuz bir sinyal).
DEFAULT_HABER_PUANI = 5.0
DEFAULT_KURUMSAL_PUANI = 5.0
DEFAULT_PIYASA_REJIMI = 5.0

# v1.0 FINAL: Fintables tarayıcı otomasyonu bir hissenin Teknik Analiz
# sayfasından bu göstergeleri okuyamayabilir (örn. gösterge bir
# canvas/grafik üzerinde render ediliyorsa DOM'da metin olarak
# bulunamaz). technical_engine/momentum_engine bu durumda zaten nötr
# varsayılanlarla çalışır (bkz. ilgili modüller); burada sadece HANGİ
# göstergelerin eksik olduğu tespit edilip kullanıcıya "neden bu puan"
# açıklamasında şeffafça gösterilir.
TEKNIK_GOSTERGE_ETIKETLERI = {
    "rsi": "RSI",
    "macd_signal": "MACD",
    "ema20": "EMA20",
    "ema50": "EMA50",
    "ema200": "EMA200",
    "adx": "ADX",
    "atr_pct": "ATR",
}

# v1.0 FINAL REVİZYONU: F/K, PD/DD Fintables'ın "Piyasa Çarpanları"
# sayfasından, ROE (varsa Net Borç/FAVÖK) "Rasyo Analiz Tablosu"
# sayfasından okunmaya çalışılır (integrations/fintables_browser.py ->
# fetch_fundamental_for_symbol). Bu sayfalar bot koruması (Cloudflare)
# arkasında olabilir; çıkarsa ya da veri bulunamazsa bu alanlar None
# kalır. fundamental_engine bu durumda zaten nötr (2.5/5) puanlarla
# çalışır (asla çökmez); burada sadece HANGİ alanların eksik olduğu
# tespit edilip kullanıcıya "neden bu puan" açıklamasında gösterilir.
FUNDAMENTAL_ALAN_ETIKETLERI = {
    "fk": "F/K",
    "pddd": "PD/DD",
    "roe": "ROE",
    "net_borc_favok": "Net Borç/FAVÖK",
}


def _deger_eksik_mi(deger):
    """Bir hücrenin skorlama açısından 'eksik' sayılıp sayılmadığını
    kontrol eder: None, boş string ya da NaN ise eksiktir."""
    if deger is None:
        return True
    try:
        f = float(deger)
    except (TypeError, ValueError):
        # Sayıya çevrilemeyen boş olmayan bir string (örn. "") de eksik
        # kabul edilir; gerçek bir sayısal değilse güvenilir değildir.
        return str(deger).strip() == ""
    return f != f  # NaN kontrolü


def _eksik_teknik_gostergeler(row):
    """Bir hisse satırında RSI/MACD/EMA20/EMA50/EMA200/ADX/ATR
    göstergelerinden hangilerinin eksik (None/NaN/boş) olduğunu
    tespit eder.

    Returns:
        list[str]: eksik göstergelerin kullanıcı dostu etiketleri
        (örn. ["RSI", "MACD"]). Hiçbiri eksik değilse boş liste.
    """
    eksikler = []
    for kolon, etiket in TEKNIK_GOSTERGE_ETIKETLERI.items():
        if _deger_eksik_mi(row.get(kolon)):
            eksikler.append(etiket)
    return eksikler


def _eksik_fundamental_alanlar(row):
    """Bir hisse satırında F/K, PD/DD, ROE, Net Borç/FAVÖK'ten
    hangilerinin eksik (None/NaN/boş) olduğunu tespit eder.

    Returns:
        list[str]: eksik alanların kullanıcı dostu etiketleri
        (örn. ["F/K", "ROE"]). Hiçbiri eksik değilse boş liste.
    """
    eksikler = []
    for kolon, etiket in FUNDAMENTAL_ALAN_ETIKETLERI.items():
        if _deger_eksik_mi(row.get(kolon)):
            eksikler.append(etiket)
    return eksikler

# Skorlama için zorunlu ham kolonlar (hepsi CSV'de bulunmalı). Not:
# haber_puani/kurumsal_puani/piyasa_rejimi burada YOK - bkz. OPTIONAL_COLUMNS.
REQUIRED_COLUMNS = (
    ["hisse", "fiyat"]
    + technical_engine.REQUIRED_COLUMNS
    + momentum_engine.REQUIRED_COLUMNS
    + fundamental_engine.REQUIRED_COLUMNS
)
# Yinelenen kolonları (örn. fiyat/atr_pct/ema20 birden fazla motor kullanabilir) temizle
REQUIRED_COLUMNS = list(dict.fromkeys(REQUIRED_COLUMNS))

# Opsiyonel kolonlar: yoksa (veya NaN/boşsa) varsayılan değerle çalışılır
OPTIONAL_COLUMNS = ["yeni_is_iliskisi", "haber_puani", "kurumsal_puani", "piyasa_rejimi"]

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


def _opsiyonel_puan(row, kolon_adi, varsayilan, max_value):
    """haber_puani / kurumsal_puani / piyasa_rejimi gibi opsiyonel puan
    kolonları için: kolon hiç yoksa ya da değer boş/NaN ise varsayılanı
    kullanır (ve kullanıldığını True olarak işaretler), aksi halde
    değeri 0-max_value arasına sıkıştırır.

    Returns:
        (skor: float, varsayilan_kullanildi: bool)
    """
    deger = row.get(kolon_adi, None)
    if deger is None:
        return varsayilan, True
    try:
        f = float(deger)
    except (TypeError, ValueError):
        return varsayilan, True
    if f != f:  # NaN kontrolü
        return varsayilan, True
    return _clip(f, max_value), False


def compute_total_score(row, base_damping=DEFAULT_BASE_DAMPING):
    """Taban puan (üç motor + haber/kurumsal/piyasa) ile kural motoru
    bonuslarını birleştirip toplam Johnny Score'u hesaplar.

    Önemli: taban puan artık TEK BAŞINA final skor değildir. `base_damping`
    ile sıkıştırılır; asıl farklılaştırıcı katkı rule_engine'den gelen
    confluence bonuslarıdır. Böylece "her şeyde ortalama iyi" bir hisse ile
    "birden fazla güçlü sinyali aynı anda taşıyan" bir hisse artık aynı
    şekilde puanlanmaz.

    Returns:
        dict: {
            "total": float,                # 0-100 final Johnny Score
            "clipped": dict,                # 6 alt skor (taban, damping'siz)
            "varsayilan_kullanildi": dict,   # haber/kurumsal/piyasa_rejimi_skor
                                             # icin varsayilan deger kullanildi mi?
            "engine_detail": dict,          # motorların ayrıntılı kırılımı
            "base_score": float,            # taban puan * base_damping
            "rule_bonus": float,            # tetiklenen kuralların toplamı
            "fired_rules": list[dict],      # tetiklenen kurallar (id/açıklama/puan)
        }
    """
    teknik_skor, teknik_detay = technical_engine.compute_technical_score(row)
    momentum_skor, momentum_detay = momentum_engine.compute_momentum_score(row)
    bilanco_skor, bilanco_detay = fundamental_engine.compute_fundamental_score(row)

    haber_skor, haber_varsayilan = _opsiyonel_puan(
        row, "haber_puani", DEFAULT_HABER_PUANI, SUB_SCORE_MAX["haber_skor"]
    )
    kurumsal_skor, kurumsal_varsayilan = _opsiyonel_puan(
        row, "kurumsal_puani", DEFAULT_KURUMSAL_PUANI, SUB_SCORE_MAX["kurumsal_skor"]
    )
    piyasa_skor, piyasa_varsayilan = _opsiyonel_puan(
        row, "piyasa_rejimi", DEFAULT_PIYASA_REJIMI, SUB_SCORE_MAX["piyasa_rejimi_skor"]
    )

    eksik_teknik_gostergeler = _eksik_teknik_gostergeler(row)
    eksik_fundamental_alanlar = _eksik_fundamental_alanlar(row)

    clipped = {
        "teknik_skor": teknik_skor,
        "momentum_skor": momentum_skor,
        "bilanco_skor": bilanco_skor,
        "haber_skor": haber_skor,
        "kurumsal_skor": kurumsal_skor,
        "piyasa_rejimi_skor": piyasa_skor,
    }
    varsayilan_kullanildi = {
        "haber_skor": haber_varsayilan,
        "kurumsal_skor": kurumsal_varsayilan,
        "piyasa_rejimi_skor": piyasa_varsayilan,
    }
    engine_detail = {
        "teknik": teknik_detay,
        "momentum": momentum_detay,
        "bilanco": bilanco_detay,
    }

    taban_toplam = sum(clipped.values())
    base_score = round(taban_toplam * base_damping, 1)

    rule_bonus, fired_rules = rule_engine.evaluate_rules(row)

    total = round(_clip(base_score + rule_bonus, 100), 1)

    return {
        "total": total,
        "clipped": clipped,
        "varsayilan_kullanildi": varsayilan_kullanildi,
        "engine_detail": engine_detail,
        "base_score": base_score,
        "rule_bonus": rule_bonus,
        "fired_rules": fired_rules,
        "eksik_teknik_gostergeler": eksik_teknik_gostergeler,
        "eksik_fundamental_alanlar": eksik_fundamental_alanlar,
    }


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


def generate_reason_bullets(score_result):
    """"Johnny bu hisseye neden bu puanı verdi?" sorusunun madde madde
    cevabını üretir: önce taban puanın 6 bileşeni, ardından tetiklenen
    kural bonusları.

    Args:
        score_result: compute_total_score(row) çıktısı (dict).

    Returns:
        list[str]: her biri bir madde (bullet) olacak metin listesi.
    """
    clipped = score_result["clipped"]
    varsayilan_kullanildi = score_result.get("varsayilan_kullanildi", {})
    fired_rules = score_result["fired_rules"]
    base_score = score_result["base_score"]
    rule_bonus = score_result["rule_bonus"]

    eksik_teknik_gostergeler = score_result.get("eksik_teknik_gostergeler", [])
    eksik_fundamental_alanlar = score_result.get("eksik_fundamental_alanlar", [])

    bullets = []
    for key in ["teknik_skor", "momentum_skor", "bilanco_skor", "haber_skor", "kurumsal_skor", "piyasa_rejimi_skor"]:
        etiket = f"{LABELS[key]}: {clipped[key]:.0f}/{SUB_SCORE_MAX[key]} puan"
        if varsayilan_kullanildi.get(key):
            etiket += " (veri yok, nötr varsayılan kullanıldı)"
        elif key in ("teknik_skor", "momentum_skor") and eksik_teknik_gostergeler:
            etiket += " (bazı göstergeler eksik, kısmen varsayılan kullanıldı)"
        elif key == "bilanco_skor" and eksik_fundamental_alanlar:
            etiket += " (Fundamental veri eksik, nötr varsayım kullanıldı)"
        else:
            etiket += " (taban analiz)"
        bullets.append(etiket)

    if eksik_teknik_gostergeler:
        bullets.append(
            "Teknik göstergelerden eksik olanlar: "
            f"{', '.join(eksik_teknik_gostergeler)} (Fintables Teknik Analiz "
            "sayfasından okunamadı; nötr/varsayılan değerlerle hesaplandı)"
        )

    if eksik_fundamental_alanlar:
        bullets.append(
            "Fundamental veri eksik, nötr varsayım kullanıldı: "
            f"{', '.join(eksik_fundamental_alanlar)} (Fintables Piyasa "
            "Çarpanları/Rasyo Analiz Tablosu sayfalarından okunamadı ya "
            "da bot koruması nedeniyle atlandı)"
        )

    bullets.append(f"Taban puan (damping uygulanmış): {base_score:.1f} puan")

    if fired_rules:
        for r in fired_rules:
            bullets.append(f"Kural {r['id']} tetiklendi: {r['aciklama']} → +{r['puan']:.0f} bonus puan")
    else:
        bullets.append("Hiçbir bonus kural tetiklenmedi (güçlü bir sinyal kombinasyonu yakalanmadı).")

    bullets.append(f"Toplam kural bonusu: +{rule_bonus:.1f} puan")
    return bullets


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
        Hedef 2, Gerekçe, Neden (madde madde detaylı gerekçe metni)
    """
    thresholds = config.get("thresholds", {"al": 85, "izle": 70})
    risk_cfg = config.get("risk", {})
    base_damping = config.get("scoring", {}).get("base_damping", DEFAULT_BASE_DAMPING)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Eksik kolon(lar): {', '.join(missing)}")

    rows = []
    for _, row in df.iterrows():
        score_result = compute_total_score(row, base_damping=base_damping)
        total = score_result["total"]
        clipped = score_result["clipped"]
        durum = determine_durum(total, thresholds)

        atr_pct = row.get("atr_pct", None)
        analist_notu = row.get("gerekce_notu", None)
        gerekce = generate_gerekce(clipped, analist_notu)
        neden_maddeleri = generate_reason_bullets(score_result)
        neden_metin = "\n".join(f"- {madde}" for madde in neden_maddeleri)

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
            "Neden": neden_metin,
        })

    result = pd.DataFrame(rows)
    result = result.sort_values("Johnny Score", ascending=False).reset_index(drop=True)
    return result
