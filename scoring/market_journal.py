"""
Market Journal (v1.2)
----------------------
Johnny Terminal'in her analiz çalıştırmasını (manuel ya da zamanlanmış)
bir "snapshot" olarak kalıcı diske kaydeden, önceki snapshot'la otomatik
karşılaştırma yapan ve okunabilir bir "Piyasa Günlüğü" üreten katman.

ÖNEMLİ: bu modül MEVCUT tarama/puanlama/öneri mekanizmasını (fintables_
browser.run_full_update, scoring/johnny_score.score_dataframe) DEĞİŞTİRMEZ
- sadece score_dataframe()'in ÇIKTISINI alıp saklar ve geçmişle
karşılaştırır. run_full_update/score_dataframe'e hiçbir bağımlılığı
yoktur (tek yönlü: onların çıktısını girdi olarak alır).

Dizin yapısı (proje kök dizinine göre):
    history/snapshots/YYYY-MM-DD_HHMM.csv   -> her analizin TAM çıktısı
    history/journal/YYYY-MM-DD_HHMM.md      -> o analize ait Piyasa Günlüğü

Snapshot dosya adı formatı (YYYY-MM-DD_HHMM) kasıtlı seçildi: ISO tarih
öneki sayesinde dosya adına göre alfabetik sıralama otomatik olarak
KRONOLOJİK sıralamayla aynı sonucu verir - ayrı bir indeks/veritabanı
gerekmez.
"""

from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd

TS_FORMAT = "%Y-%m-%d_%H%M"
SNAPSHOT_DIRNAME = Path("history") / "snapshots"
JOURNAL_DIRNAME = Path("history") / "journal"

NO_HISTORY_MESSAGE = "İlk analiz - karşılaştırılacak geçmiş kayıt yok."


def _snapshot_dir(base_dir):
    d = Path(base_dir) / SNAPSHOT_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _journal_dir(base_dir):
    d = Path(base_dir) / JOURNAL_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def format_ts(dt):
    return dt.strftime(TS_FORMAT)


def ts_from_path(path):
    """Bir snapshot/journal dosya yolundan zaman damgası (dosya adının
    kendisi) çıkarır - örn. '.../2026-07-07_1015.csv' -> '2026-07-07_1015'."""
    return Path(path).stem


def save_snapshot(sonuc_df, base_dir, dt=None):
    """score_dataframe() çıktısını (sonuc_df) bir snapshot olarak
    history/snapshots/YYYY-MM-DD_HHMM.csv altına kaydeder.

    Aynı dakika içinde birden fazla çağrılırsa (örn. manuel + zamanlanmış
    çakışması) dosya SESSİZCE ÜZERİNE YAZILIR - bu kasıtlıdır, aynı
    dakikaya iki ayrı snapshot sığdırmanın bir anlamı yoktur.

    Returns:
        (path: Path, ts: str) - kaydedilen dosyanın yolu ve zaman damgası
    """
    dt = dt or datetime.now()
    ts = format_ts(dt)
    path = _snapshot_dir(base_dir) / f"{ts}.csv"
    sonuc_df.to_csv(path, index=False, encoding="utf-8-sig")
    return path, ts


def list_snapshot_files(base_dir):
    """Tüm snapshot dosyalarını KRONOLOJİK (eskiden yeniye) sırada
    döner. Dosya adı formatı (YYYY-MM-DD_HHMM) sayesinde alfabetik
    sıralama = kronolojik sıralama."""
    d = _snapshot_dir(base_dir)
    return sorted(d.glob("*.csv"))


def load_snapshot(path):
    """Bir snapshot CSV dosyasını DataFrame olarak okur."""
    return pd.read_csv(path)


def get_previous_snapshot_path(base_dir, exclude_ts=None):
    """En son (mevcut hariç) snapshot dosyasının yolunu döner; hiç yoksa
    None döner."""
    files = [f for f in list_snapshot_files(base_dir) if ts_from_path(f) != exclude_ts]
    return files[-1] if files else None


def compare_snapshots(prev_df, curr_df, key_col="Hisse", score_col="Johnny Score", durum_col="Durum"):
    """İki ardışık snapshot arasında hangi hisselerin YENİ girdiğini,
    hangilerinin listeden ÇIKTIĞINI ve ortak olanların skor/durum
    değişimini hesaplar.

    Returns:
        dict: {
            "yeni_girenler": list[str], "cikanlar": list[str],
            "ortak": list[str],
            "degisimler": {hisse: {
                "onceki_skor", "guncel_skor", "delta",
                "onceki_durum", "guncel_durum",
            }},
        }
    """
    prev_hisseler = set(prev_df[key_col]) if key_col in prev_df.columns else set()
    curr_hisseler = set(curr_df[key_col]) if key_col in curr_df.columns else set()

    yeni_girenler = sorted(curr_hisseler - prev_hisseler)
    cikanlar = sorted(prev_hisseler - curr_hisseler)
    ortak = sorted(curr_hisseler & prev_hisseler)

    def _satir(df, hisse):
        eslesen = df[df[key_col] == hisse]
        return eslesen.iloc[0] if not eslesen.empty else None

    degisimler = {}
    for hisse in ortak:
        onceki = _satir(prev_df, hisse)
        guncel = _satir(curr_df, hisse)
        if onceki is None or guncel is None:
            continue
        onceki_skor = float(onceki[score_col])
        guncel_skor = float(guncel[score_col])
        degisimler[hisse] = {
            "onceki_skor": onceki_skor,
            "guncel_skor": guncel_skor,
            "delta": round(guncel_skor - onceki_skor, 1),
            "onceki_durum": onceki.get(durum_col) if durum_col in onceki else None,
            "guncel_durum": guncel.get(durum_col) if durum_col in guncel else None,
        }

    return {
        "yeni_girenler": yeni_girenler,
        "cikanlar": cikanlar,
        "ortak": ortak,
        "degisimler": degisimler,
    }


def en_cok_degisenler(degisimler, n=3, yon="kazanan"):
    """`degisimler` (compare_snapshots çıktısı) içinden en çok puan
    kazanan (yon='kazanan') ya da kaybeden (yon='kaybeden') n hisseyi
    (hisse, bilgi) çiftleri olarak döner."""
    ters = yon == "kazanan"
    sirali = sorted(degisimler.items(), key=lambda kv: kv[1]["delta"], reverse=ters)
    if yon == "kaybeden":
        sirali = [kv for kv in sirali if kv[1]["delta"] < 0]
    else:
        sirali = [kv for kv in sirali if kv[1]["delta"] > 0]
    return sirali[:n]


def top3_karsilastir(prev_df, curr_df, key_col="Hisse", score_col="Johnny Score"):
    """Kullanıcının istediği formatta Top 3 (gerçekten işlem yapılabilir
    - AL/İZLE - ilk 3 aday) karşılaştırma satırlarını üretir, örn.:

        AKBNK
        Score: +6
        Sıralama değişmedi.

        ASELS
        Score: -4

        THYAO listeden çıktı.

        Yeni giriş: KOZAA

    Returns:
        list[str]: her biri bir veya birkaç satırlık, doğrudan
        yazdırılabilir metin parçaları.
    """
    # Döngüsel import'tan kaçınmak için burada, kullanılırken import edilir.
    from scoring.johnny_score import filter_tradeable

    prev_top3 = list(filter_tradeable(prev_df).head(3)[key_col]) if key_col in prev_df.columns else []
    curr_top3 = list(filter_tradeable(curr_df).head(3)[key_col]) if key_col in curr_df.columns else []

    def _skor(df, hisse):
        eslesen = df[df[key_col] == hisse]
        return float(eslesen.iloc[0][score_col]) if not eslesen.empty else None

    satirlar = []
    for hisse in prev_top3:
        if hisse in curr_top3:
            onceki_sira = prev_top3.index(hisse) + 1
            guncel_sira = curr_top3.index(hisse) + 1
            onceki_skor = _skor(prev_df, hisse)
            guncel_skor = _skor(curr_df, hisse)
            delta = (guncel_skor - onceki_skor) if (onceki_skor is not None and guncel_skor is not None) else None
            sira_metni = (
                "Sıralama değişmedi." if onceki_sira == guncel_sira
                else f"{onceki_sira}. sıradan {guncel_sira}. sıraya geçti."
            )
            delta_metni = f"Score: {delta:+.0f}" if delta is not None else "Score: -"
            satirlar.append(f"{hisse}\n{delta_metni}\n{sira_metni}")
        else:
            satirlar.append(f"{hisse} listeden çıktı.")

    for hisse in curr_top3:
        if hisse not in prev_top3:
            satirlar.append(f"Yeni giriş: {hisse}")

    return satirlar


def trend_metrikleri(gecmis_listesi, score_col="Johnny Score", key_col="Hisse", min_gozlem=2):
    """`gecmis_listesi` (kronolojik sırada [(ts, df), ...] - PENCEREDEKİ
    TÜM snapshot'ları, en güncel dahil, içerir) üzerinden:
      - en istikrarlı hisse (skor standart sapması en düşük),
      - en hızlı yükselen aday (skor eğimi en pozitif),
      - en hızlı zayıflayan aday (skor eğimi en negatif)
    hesaplar. Adil bir karşılaştırma için SADECE pencerenin TAMAMINDA
    (her snapshot'ta) mevcut olan hisseler değerlendirilir - aksi halde
    sadece 1-2 kez görünen bir hisse yanlışlıkla 'en istikrarlı' çıkabilir.

    Yeterli ortak geçmişi olan hisse yoksa (örn. ilk birkaç analizde)
    ilgili alanlar None döner - bu bir hata değildir, sadece henüz
    yeterli veri birikmediği anlamına gelir.
    """
    pencere_boyutu = len(gecmis_listesi)
    seri = defaultdict(list)
    for _, df in gecmis_listesi:
        if key_col not in df.columns or score_col not in df.columns:
            continue
        for _, row in df.iterrows():
            seri[row[key_col]].append(float(row[score_col]))

    en_istikrarli_hisse, en_dusuk_std = None, None
    en_yukselen_hisse, en_yuksek_egim = None, None
    en_zayiflayan_hisse, en_dusuk_egim = None, None

    for hisse, skorlar in seri.items():
        if len(skorlar) < max(min_gozlem, pencere_boyutu):
            continue  # pencerenin TAMAMINDA olmayan hisseler haric tutulur
        ortalama = sum(skorlar) / len(skorlar)
        varyans = sum((s - ortalama) ** 2 for s in skorlar) / len(skorlar)
        std = varyans ** 0.5
        if en_dusuk_std is None or std < en_dusuk_std:
            en_dusuk_std, en_istikrarli_hisse = std, hisse

        egim = (skorlar[-1] - skorlar[0]) / (len(skorlar) - 1)
        if en_yuksek_egim is None or egim > en_yuksek_egim:
            en_yuksek_egim, en_yukselen_hisse = egim, hisse
        if en_dusuk_egim is None or egim < en_dusuk_egim:
            en_dusuk_egim, en_zayiflayan_hisse = egim, hisse

    return {
        "pencere_boyutu": pencere_boyutu,
        "en_istikrarli": {
            "hisse": en_istikrarli_hisse,
            "std": round(en_dusuk_std, 2) if en_istikrarli_hisse else None,
        },
        "en_hizli_yukselen": {
            "hisse": en_yukselen_hisse,
            "egim": round(en_yuksek_egim, 2) if en_yukselen_hisse else None,
        },
        "en_hizli_zayiflayan": {
            "hisse": en_zayiflayan_hisse,
            "egim": round(en_dusuk_egim, 2) if en_zayiflayan_hisse else None,
        },
    }


def _journal_metni_olustur(curr_ts, karsilastirma, top3_satirlari, top3_simdiki, kazananlar, kaybedenler, trend):
    satirlar = [f"PİYASA GÜNLÜĞÜ - {curr_ts}", "=" * 50, "", "Top 3 değişimi:"]
    satirlar.extend(top3_satirlari if top3_satirlari else ["(karşılaştırılacak önceki Top 3 yok)"])
    satirlar.append("")

    yeni = karsilastirma["yeni_girenler"]
    cikan = karsilastirma["cikanlar"]
    satirlar.append(f"Yeni giren hisseler ({len(yeni)}): " + (", ".join(yeni) if yeni else "Yok"))
    satirlar.append(f"Listeden çıkan hisseler ({len(cikan)}): " + (", ".join(cikan) if cikan else "Yok"))
    satirlar.append("")

    satirlar.append("En fazla puan kazananlar:")
    if kazananlar:
        for hisse, bilgi in kazananlar:
            satirlar.append(f"  {hisse}: {bilgi['delta']:+.1f} puan ({bilgi['onceki_skor']:.0f} → {bilgi['guncel_skor']:.0f})")
    else:
        satirlar.append("  (yok)")

    satirlar.append("En fazla puan kaybedenler:")
    if kaybedenler:
        for hisse, bilgi in kaybedenler:
            satirlar.append(f"  {hisse}: {bilgi['delta']:+.1f} puan ({bilgi['onceki_skor']:.0f} → {bilgi['guncel_skor']:.0f})")
    else:
        satirlar.append("  (yok)")
    satirlar.append("")

    satirlar.append(
        "Günün en güçlü 3 hissesi (AL/İZLE): "
        + (", ".join(top3_simdiki) if top3_simdiki else "(bugün işlem yapmaya değer güçlü bir fırsat yok)")
    )
    satirlar.append("")

    ei = trend["en_istikrarli"]
    ey = trend["en_hizli_yukselen"]
    ez = trend["en_hizli_zayiflayan"]
    satirlar.append(
        f"En istikrarlı hisse (son {trend['pencere_boyutu']} tarama): {ei['hisse']} (std sapma: {ei['std']})"
        if ei["hisse"] else "En istikrarlı hisse: yeterli geçmiş yok."
    )
    satirlar.append(
        f"En hızlı yükselen aday: {ey['hisse']} (eğim: {ey['egim']:+.1f} puan/tarama)"
        if ey["hisse"] else "En hızlı yükselen aday: yeterli geçmiş yok."
    )
    satirlar.append(
        f"En hızlı zayıflayan aday: {ez['hisse']} (eğim: {ez['egim']:+.1f} puan/tarama)"
        if ez["hisse"] else "En hızlı zayıflayan aday: yeterli geçmiş yok."
    )
    return "\n".join(satirlar)


def generate_market_journal(base_dir, curr_df, curr_ts, gecmis_pencere=5):
    """Kaydedilmiş önceki snapshot'larla karşılaştırıp okunabilir bir
    "Piyasa Günlüğü" metni üretir ve history/journal/{curr_ts}.md olarak
    kaydeder.

    Args:
        base_dir: proje kök dizini (snapshot'ların altında yaşadığı yer)
        curr_df: score_dataframe() çıktısı (mevcut analiz)
        curr_ts: mevcut analizin zaman damgası (save_snapshot'tan dönen ts)
        gecmis_pencere: trend metrikleri (istikrar/eğim) için kaç
            snapshot'a (mevcut dahil) bakılacağı

    Returns:
        (metin: str, veri: dict) - metin doğrudan gösterilebilir/
        loglanabilir; veri programatik erişim için yapılandırılmış bilgi
        içerir.
    """
    tum_dosyalar = [f for f in list_snapshot_files(base_dir) if ts_from_path(f) != curr_ts]

    if not tum_dosyalar:
        veri = {"ilk_analiz": True}
        metin = f"PİYASA GÜNLÜĞÜ - {curr_ts}\n{'=' * 50}\n\n{NO_HISTORY_MESSAGE}"
        _journal_dosyasina_yaz(base_dir, curr_ts, metin)
        return metin, veri

    prev_path = tum_dosyalar[-1]
    prev_df = load_snapshot(prev_path)

    karsilastirma = compare_snapshots(prev_df, curr_df)
    top3_satirlari = top3_karsilastir(prev_df, curr_df)
    kazananlar = en_cok_degisenler(karsilastirma["degisimler"], n=3, yon="kazanan")
    kaybedenler = en_cok_degisenler(karsilastirma["degisimler"], n=3, yon="kaybeden")

    from scoring.johnny_score import filter_tradeable
    top3_simdiki = list(filter_tradeable(curr_df).head(3)["Hisse"]) if "Hisse" in curr_df.columns else []

    onceki_pencere = tum_dosyalar[-(gecmis_pencere - 1):] if gecmis_pencere > 1 else []
    trend_gecmis = [(ts_from_path(f), load_snapshot(f)) for f in onceki_pencere]
    trend_gecmis.append((curr_ts, curr_df))
    trend = trend_metrikleri(trend_gecmis)

    metin = _journal_metni_olustur(curr_ts, karsilastirma, top3_satirlari, top3_simdiki, kazananlar, kaybedenler, trend)
    veri = {
        "ilk_analiz": False,
        "karsilastirma": karsilastirma,
        "top3_satirlari": top3_satirlari,
        "top3_simdiki": top3_simdiki,
        "kazananlar": kazananlar,
        "kaybedenler": kaybedenler,
        "trend": trend,
    }
    _journal_dosyasina_yaz(base_dir, curr_ts, metin)
    return metin, veri


def _journal_dosyasina_yaz(base_dir, ts, metin):
    path = _journal_dir(base_dir) / f"{ts}.md"
    path.write_text(metin, encoding="utf-8")
    return path


def list_journal_files(base_dir):
    """Tüm Piyasa Günlüğü (.md) dosyalarını kronolojik sırada döner."""
    return sorted(_journal_dir(base_dir).glob("*.md"))
