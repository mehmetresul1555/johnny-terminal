"""
Performance Tracker (v1.2 - Market Journal)
---------------------------------------------
Johnny'nin kendi önerilerinin GERÇEK piyasa sonucunu ölçmesini sağlayan
katman: her AL/İZLE önerisi bir "ledger" (defter) kaydına dönüşür,
+1/+3/+5/+10 gün sonra (iş günü) o önerinin ne olduğu (stop çalıştı mı,
hedef1/2'ye ulaşıldı mı, maksimum getiri/geri çekilme ne oldu)
değerlendirilir; bu veriden aylık/yıllık başarı raporları ve kural
(R1-R4) bazlı başarı oranları üretilir.

ÖNEMLİ VERİ KAYNAĞI SINIRLAMASI (kullanıcıya açıkça belirtilmeli):
Johnny'nin gerçek zamanlı/sürekli bir fiyat akışı (tick verisi) YOKTUR -
sadece kendi taramalarını (manuel ya da zamanlanmış, günde birkaç kez)
çalıştırdığında bir fiyat "örneği" alır. Bu yüzden "en yüksek görülen
fiyat", "en düşük görülen fiyat" gibi metrikler GERÇEK günlük en yüksek/
en düşük (intraday high/low) DEĞİL, Johnny'nin o dönemde aldığı
ÖRNEKLERİN en yüksek/en düşüğüdür - tarama sıklığı arttıkça (şu an
hafta içi günde 5 kez) bu yaklaşım gerçeğe yaklaşır ama birebir aynı
değildir. Bu modülün ürettiği tüm raporlarda bu sınırlama açıkça
belirtilir.

Dizin yapısı (proje kök dizinine göre):
    history/ledger/ledger.csv   -> tüm öneriler + checkpoint sonuçları

Bu modül scoring/market_journal.py'nin snapshot altyapısını (özellikle
Fiyat örneklemesi için) kullanır ama ondan bağımsız çalışabilir.
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from scoring import market_journal as mj

LEDGER_DIRNAME = Path("history") / "ledger"
LEDGER_FILENAME = "ledger.csv"

CHECKPOINT_GUNLERI = (1, 3, 5, 10)

VERI_KAYNAGI_UYARISI = (
    "Not: 'en yüksek/en düşük görülen fiyat' Johnny'nin kendi tarama "
    "örneklerinden (günde birkaç kez) hesaplanır - gerçek sürekli "
    "intraday en yüksek/en düşük değildir, bir yaklaşıklıktır."
)


def _ledger_dir(base_dir):
    d = Path(base_dir) / LEDGER_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ledger_path(base_dir):
    return _ledger_dir(base_dir) / LEDGER_FILENAME


def _rec_id(hisse, rec_ts):
    return f"{hisse}__{rec_ts}"


def add_business_days(start_date, n):
    """start_date'e n İŞ GÜNÜ (Pazartesi-Cuma) ekler. Resmi tatiller
    HESABA KATILMAZ (basit bir yaklaşımdır, kullanıcıya bildirilmelidir)."""
    d = start_date
    eklenen = 0
    while eklenen < n:
        d = d + timedelta(days=1)
        if d.weekday() < 5:
            eklenen += 1
    return d


def _fired_rule_ids(rule_bonuslari_metni):
    """score_dataframe()'in ürettiği 'Rule Bonusları' metninden
    (örn. 'R1 (+10), R2 (+8)') sadece kural id'lerini çıkarır -> ['R1','R2'].
    Hiçbir kural tetiklenmediyse ('Yok') boş liste döner."""
    if not rule_bonuslari_metni or rule_bonuslari_metni == "Yok":
        return []
    return [parca.strip().split(" ")[0] for parca in str(rule_bonuslari_metni).split(",")]


def load_ledger(base_dir):
    """Ledger'ı DataFrame olarak yükler; hiç yoksa boş bir DataFrame
    (doğru kolonlarla) döner."""
    path = _ledger_path(base_dir)
    if not path.exists():
        return _bos_ledger()
    return pd.read_csv(path, dtype={f"checkpoint_{g}": str for g in CHECKPOINT_GUNLERI})


def _bos_ledger():
    kolonlar = [
        "rec_id", "hisse", "rec_ts", "rec_tarih", "durum", "johnny_score",
        "giris_fiyat", "stop_fiyat", "hedef1_fiyat", "hedef2_fiyat", "fired_rules",
    ]
    for g in CHECKPOINT_GUNLERI:
        kolonlar += [f"checkpoint_{g}_tarih", f"checkpoint_{g}"]
    return pd.DataFrame(columns=kolonlar)


def save_ledger(ledger_df, base_dir):
    ledger_df.to_csv(_ledger_path(base_dir), index=False, encoding="utf-8-sig")


def record_recommendations(sonuc_df, rec_ts, base_dir):
    """score_dataframe() çıktısındaki AL/İZLE önerilerini ledger'a
    (henüz değerlendirilmemiş, 'açık' kayıtlar olarak) ekler.

    Aynı (hisse, rec_ts) çifti zaten ledger'da varsa TEKRAR eklenmez
    (aynı analiz snapshot'ı için record_recommendations iki kez
    çağrılırsa - örn. tekrar deneme - yinelenen kayıt oluşmaz).

    Returns:
        int: yeni eklenen kayıt sayısı
    """
    from scoring.johnny_score import filter_tradeable

    firsatlar = filter_tradeable(sonuc_df)
    if firsatlar.empty:
        return 0

    ledger = load_ledger(base_dir)
    mevcut_idler = set(ledger["rec_id"]) if not ledger.empty else set()

    rec_tarihi = datetime.strptime(rec_ts, mj.TS_FORMAT).date()
    yeni_kayitlar = []

    for _, row in firsatlar.iterrows():
        hisse = row["Hisse"]
        rec_id = _rec_id(hisse, rec_ts)
        if rec_id in mevcut_idler:
            continue

        stop_fiyat = row.get("Stop Fiyat")
        hedef1_fiyat = row.get("Hedef 1 Fiyat")
        hedef2_fiyat = row.get("Hedef 2 Fiyat")
        if pd.isna(stop_fiyat) or pd.isna(hedef1_fiyat):
            # Risk seviyeleri hesaplanmamışsa (beklenmez - AL/İZLE için
            # her zaman hesaplanır - ama veri bütünlüğü için kontrol
            # edilir) bu öneriyi takip edemeyiz, atla.
            continue

        kayit = {
            "rec_id": rec_id,
            "hisse": hisse,
            "rec_ts": rec_ts,
            "rec_tarih": rec_tarihi.isoformat(),
            "durum": row.get("Durum"),
            "johnny_score": row.get("Johnny Score"),
            "giris_fiyat": row.get("Fiyat"),
            "stop_fiyat": stop_fiyat,
            "hedef1_fiyat": hedef1_fiyat,
            "hedef2_fiyat": hedef2_fiyat,
            "fired_rules": ",".join(_fired_rule_ids(row.get("Rule Bonusları"))),
        }
        for g in CHECKPOINT_GUNLERI:
            kayit[f"checkpoint_{g}_tarih"] = add_business_days(rec_tarihi, g).isoformat()
            kayit[f"checkpoint_{g}"] = ""  # henüz değerlendirilmedi

        yeni_kayitlar.append(kayit)

    if not yeni_kayitlar:
        return 0

    yeni_df = pd.DataFrame(yeni_kayitlar)
    ledger = yeni_df if ledger.empty else pd.concat([ledger, yeni_df], ignore_index=True)
    save_ledger(ledger, base_dir)
    return len(yeni_kayitlar)


def gather_price_samples(base_dir, hisse, ts_baslangic, tarih_bitis, key_col="Hisse", fiyat_col="Fiyat"):
    """`hisse` için, `ts_baslangic` (snapshot zaman damgası, dahil değil
    - giriş fiyatı zaten ledger'da ayrıca saklanıyor) SONRASINDAKİ ve
    `tarih_bitis` (date objesi, dahil) tarihine kadarki tüm snapshot
    örneklerinden Fiyat değerlerini kronolojik sırada [(ts, fiyat), ...]
    olarak döner. Hisse o snapshot'ta bulunamıyorsa (o gün ilk 20'ye
    girmemiş olabilir) o örnek sessizce atlanır."""
    baslangic_dt = datetime.strptime(ts_baslangic, mj.TS_FORMAT)
    sonuclar = []
    for f in mj.list_snapshot_files(base_dir):
        ts = mj.ts_from_path(f)
        try:
            ts_dt = datetime.strptime(ts, mj.TS_FORMAT)
        except ValueError:
            continue
        if ts_dt <= baslangic_dt or ts_dt.date() > tarih_bitis:
            continue
        df = mj.load_snapshot(f)
        if key_col not in df.columns or fiyat_col not in df.columns:
            continue
        eslesen = df[df[key_col] == hisse]
        if eslesen.empty:
            continue
        fiyat = eslesen.iloc[0][fiyat_col]
        if pd.isna(fiyat):
            continue
        sonuclar.append((ts, float(fiyat)))
    return sonuclar


def _checkpoint_degerlendir(giris_fiyat, stop_fiyat, hedef1_fiyat, hedef2_fiyat, rec_tarih_iso, ornekler):
    """Bir checkpoint penceresi için (giriş fiyatı + o ana kadarki
    kronolojik örnekler) sonuç sözlüğünü hesaplar. `ornekler`:
    [(ts, fiyat), ...] kronolojik sırada, giriş SONRASI örnekler."""
    tum_fiyatlar = [giris_fiyat] + [f for _, f in ornekler]
    en_yuksek = max(tum_fiyatlar)
    en_dusuk = min(tum_fiyatlar)

    ilk_stop_idx = None
    ilk_hedef1_idx = None
    for i, (_, fiyat) in enumerate(ornekler):
        if ilk_stop_idx is None and fiyat <= stop_fiyat:
            ilk_stop_idx = i
        if ilk_hedef1_idx is None and fiyat >= hedef1_fiyat:
            ilk_hedef1_idx = i

    stop_calisti = ilk_stop_idx is not None
    hedef1_ulasti = any(f >= hedef1_fiyat for _, f in ornekler)
    hedef2_ulasti = any(f >= hedef2_fiyat for _, f in ornekler)

    if ilk_hedef1_idx is not None and (ilk_stop_idx is None or ilk_hedef1_idx <= ilk_stop_idx):
        basari = True
        ilk_tetik_ts = ornekler[ilk_hedef1_idx][0]
    elif ilk_stop_idx is not None:
        basari = False
        ilk_tetik_ts = ornekler[ilk_stop_idx][0]
    else:
        basari = None  # henüz ne stop ne hedef1 tetiklendi - belirsiz/açık
        ilk_tetik_ts = ornekler[-1][0] if ornekler else None

    elde_tutma_gun = None
    if ilk_tetik_ts:
        rec_tarih = date.fromisoformat(rec_tarih_iso)
        tetik_tarih = datetime.strptime(ilk_tetik_ts, mj.TS_FORMAT).date()
        elde_tutma_gun = (tetik_tarih - rec_tarih).days

    kapanis_fiyat = ornekler[-1][1] if ornekler else giris_fiyat

    return {
        "kapanis_fiyat": round(kapanis_fiyat, 2),
        "en_yuksek": round(en_yuksek, 2),
        "en_dusuk": round(en_dusuk, 2),
        "stop_calisti": stop_calisti,
        "hedef1_ulasti": hedef1_ulasti,
        "hedef2_ulasti": hedef2_ulasti,
        "maks_getiri_pct": round((en_yuksek - giris_fiyat) / giris_fiyat * 100, 2),
        "maks_cekilme_pct": round((en_dusuk - giris_fiyat) / giris_fiyat * 100, 2),
        "basari": basari,
        "elde_tutma_gun": elde_tutma_gun,
        "ornek_sayisi": len(ornekler),
    }


def update_open_recommendations(base_dir, bugun=None):
    """Vadesi gelmiş (checkpoint tarihi <= bugün) ama henüz
    değerlendirilmemiş ledger kayıtlarını, Johnny'nin kendi snapshot
    örneklerinden (bkz. VERI_KAYNAGI_UYARISI) değerlendirir.

    Returns:
        int: değerlendirilen (yeni doldurulan) checkpoint sayısı
    """
    bugun = bugun or date.today()
    ledger = load_ledger(base_dir)
    if ledger.empty:
        return 0

    guncellenen = 0
    for idx, row in ledger.iterrows():
        for g in CHECKPOINT_GUNLERI:
            mevcut = row.get(f"checkpoint_{g}")
            if isinstance(mevcut, str) and mevcut.strip():
                continue  # zaten değerlendirilmiş
            checkpoint_tarihi = date.fromisoformat(row[f"checkpoint_{g}_tarih"])
            if checkpoint_tarihi > bugun:
                continue  # henüz vadesi gelmedi

            ornekler = gather_price_samples(base_dir, row["hisse"], row["rec_ts"], checkpoint_tarihi)
            if not ornekler:
                continue  # bu pencerede hiç veri toplanamamış, sonra tekrar denenir

            sonuc = _checkpoint_degerlendir(
                float(row["giris_fiyat"]), float(row["stop_fiyat"]),
                float(row["hedef1_fiyat"]), float(row["hedef2_fiyat"]),
                row["rec_tarih"], ornekler,
            )
            ledger.at[idx, f"checkpoint_{g}"] = json.dumps(sonuc, ensure_ascii=False)
            guncellenen += 1

    if guncellenen:
        save_ledger(ledger, base_dir)
    return guncellenen


def _checkpoint_verisi(row, gun):
    ham = row.get(f"checkpoint_{gun}")
    if not isinstance(ham, str) or not ham.strip():
        return None
    try:
        return json.loads(ham)
    except (TypeError, ValueError):
        return None


def generate_performance_report(base_dir, checkpoint_gun=5, baslangic_tarih=None, bitis_tarih=None):
    """Ledger'daki değerlendirilmiş kayıtlardan bir performans raporu
    üretir (aylık/yıllık - `baslangic_tarih`/`bitis_tarih` ile filtrelenir).

    `checkpoint_gun`: başarı oranı/ortalama kazanç-kayıp hesaplarında
    hangi checkpoint'in (1/3/5/10) referans alınacağı (varsayılan +5 gün
    - yaklaşık bir işlem haftası).

    Returns:
        dict: rapor verisi (bkz. kod içindeki alan adları) + "metin"
        (doğrudan gösterilebilir Türkçe özet).
    """
    ledger = load_ledger(base_dir)
    if ledger.empty:
        return {"toplam_oneri": 0, "metin": "Henüz hiçbir öneri kaydedilmedi - rapor üretilecek veri yok."}

    if baslangic_tarih:
        ledger = ledger[ledger["rec_tarih"] >= baslangic_tarih]
    if bitis_tarih:
        ledger = ledger[ledger["rec_tarih"] <= bitis_tarih]

    toplam_oneri = len(ledger)
    if toplam_oneri == 0:
        return {"toplam_oneri": 0, "metin": "Bu tarih aralığında hiçbir öneri yok."}

    degerlendirilenler = []
    for _, row in ledger.iterrows():
        veri = _checkpoint_verisi(row, checkpoint_gun)
        if veri is None:
            continue
        degerlendirilenler.append((row, veri))

    if not degerlendirilenler:
        return {
            "toplam_oneri": toplam_oneri,
            "metin": (
                f"Toplam {toplam_oneri} öneri kaydedildi ama henüz hiçbiri "
                f"+{checkpoint_gun} gün checkpoint'ine ulaşmadı - rapor "
                "için biraz daha zaman gerekiyor."
            ),
        }

    def _oran(pay, payda):
        return round(100 * pay / payda, 1) if payda else None

    al_kayitlari = [(r, v) for r, v in degerlendirilenler if r["durum"] == "AL"]
    izle_kayitlari = [(r, v) for r, v in degerlendirilenler if r["durum"] == "İZLE"]

    def _basari_orani(kayitlar):
        karar_verilenler = [(r, v) for r, v in kayitlar if v["basari"] is not None]
        basarili = [v for _, v in karar_verilenler if v["basari"] is True]
        return _oran(len(basarili), len(karar_verilenler)), len(karar_verilenler)

    al_basari, al_n = _basari_orani(al_kayitlari)
    izle_basari, izle_n = _basari_orani(izle_kayitlari)

    kazananlar = [v["maks_getiri_pct"] for _, v in degerlendirilenler if v["basari"] is True]
    kaybedenler = [v["maks_cekilme_pct"] for _, v in degerlendirilenler if v["basari"] is False]
    ort_kazanc = round(sum(kazananlar) / len(kazananlar), 2) if kazananlar else None
    ort_kayip = round(sum(kaybedenler) / len(kaybedenler), 2) if kaybedenler else None

    hedef1_orani = _oran(sum(1 for _, v in degerlendirilenler if v["hedef1_ulasti"]), len(degerlendirilenler))
    hedef2_orani = _oran(sum(1 for _, v in degerlendirilenler if v["hedef2_ulasti"]), len(degerlendirilenler))

    tutma_sureleri = [v["elde_tutma_gun"] for _, v in degerlendirilenler if v["elde_tutma_gun"] is not None]
    ort_tutma = round(sum(tutma_sureleri) / len(tutma_sureleri), 1) if tutma_sureleri else None

    # Kural bazlı başarı oranı: bir öneri birden fazla kuralı birden
    # tetiklemiş olabilir - her tetiklenen kural kendi payına düşen
    # başarı/başarısızlığı alır (bir öneri birden fazla kuralın
    # istatistiğine katkı yapabilir, bu kasıtlıdır - amaç "bu kural
    # tetiklendiğinde genelde ne oluyor" sorusuna cevap vermektir).
    kural_istatistik = {}
    for row, veri in degerlendirilenler:
        if veri["basari"] is None:
            continue
        fired = str(row.get("fired_rules") or "")
        for rule_id in [r for r in fired.split(",") if r]:
            kural_istatistik.setdefault(rule_id, {"basarili": 0, "toplam": 0})
            kural_istatistik[rule_id]["toplam"] += 1
            if veri["basari"] is True:
                kural_istatistik[rule_id]["basarili"] += 1

    kural_basari_oranlari = {
        rule_id: _oran(s["basarili"], s["toplam"]) for rule_id, s in kural_istatistik.items()
    }

    rapor = {
        "toplam_oneri": toplam_oneri,
        "degerlendirilen_oneri": len(degerlendirilenler),
        "checkpoint_gun": checkpoint_gun,
        "al_basari_orani": al_basari,
        "al_orneklem": al_n,
        "izle_basari_orani": izle_basari,
        "izle_orneklem": izle_n,
        "ortalama_kazanc_pct": ort_kazanc,
        "ortalama_kayip_pct": ort_kayip,
        "hedef1_basari_orani": hedef1_orani,
        "hedef2_basari_orani": hedef2_orani,
        "ortalama_elde_tutma_gun": ort_tutma,
        "kural_basari_oranlari": kural_basari_oranlari,
    }

    satirlar = [
        f"Toplam öneri: {toplam_oneri} (bunlardan {len(degerlendirilenler)} tanesi +{checkpoint_gun} gün checkpoint'ine ulaştı)",
        "",
        f"AL önerileri: başarı oranı: {'%' + str(al_basari) if al_basari is not None else 'N/A'} (n={al_n})",
        f"İZLE önerileri: başarı oranı: {'%' + str(izle_basari) if izle_basari is not None else 'N/A'} (n={izle_n})",
        "",
        f"Ortalama kazanç: {('+' + str(ort_kazanc) + '%') if ort_kazanc is not None else 'N/A'}",
        f"Ortalama kayıp: {(str(ort_kayip) + '%') if ort_kayip is not None else 'N/A'}",
        "",
        f"Hedef 1 başarı oranı: {'%' + str(hedef1_orani) if hedef1_orani is not None else 'N/A'}",
        f"Hedef 2 başarı oranı: {'%' + str(hedef2_orani) if hedef2_orani is not None else 'N/A'}",
        f"Ortalama elde tutma süresi: {ort_tutma if ort_tutma is not None else 'N/A'} gün",
        "",
        "Kural bazlı başarı oranları:",
    ]
    if kural_basari_oranlari:
        for rule_id in sorted(kural_basari_oranlari):
            satirlar.append(f"  {rule_id} başarı oranı: %{kural_basari_oranlari[rule_id]}")
    else:
        satirlar.append("  (henüz yeterli veri yok)")
    satirlar.append("")
    satirlar.append(VERI_KAYNAGI_UYARISI)

    rapor["metin"] = "\n".join(satirlar)
    return rapor
