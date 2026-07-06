"""
Pre-Screen (Ön Eleme)
-----------------------
Fintables Hisse Radar ana tablosu ~640 hisse içerir. Bunların hepsinin
detay/Teknik Analiz sayfasına tek tek girmek hem çok yavaş olur hem de
gereksiz yere Fintables'a çok sayıda istek göndermek anlamına gelir. Bu
modül, Radar tablosundaki ham veriye bakarak SADECE en umut vaat eden
ilk N adayı (varsayılan 10) seçer; yalnızca bunların detay sayfasına
girilir (bkz. integrations/fintables_browser.py -> run_full_update).

ÖNEMLİ: Burada üretilen "_on_eleme_skoru" Johnny Score DEĞİLDİR. Sadece
kaba, şeffaf bir ilk elemedir (hacim + kısa vadeli getiriye dayalı basit
bir kompozit sıralama). Nihai Johnny Score, teknik detaylar okunduktan
sonra scoring/johnny_score.py ile hesaplanır.

Fintables Radar tablosundaki sayılar Türkçe formatlıdır (binlik nokta,
ondalık virgül, % işareti, "mn"/"mr" hacim ekleri, "N/A" boş değer vb.)
- bu modül bunları sayıya çevirir.
"""

import re

import pandas as pd

DEFAULT_TOP_N = 10

_TR_MAP = str.maketrans({
    "ç": "c", "Ç": "c", "ğ": "g", "Ğ": "g", "ı": "i", "İ": "i",
    "ö": "o", "Ö": "o", "ş": "s", "Ş": "s", "ü": "u", "Ü": "u",
})


def _normalize(name):
    """data_mapper._normalize ile aynı mantık (kolon adı karşılaştırması
    için); bağımsız kalması için burada küçük bir kopyası tutulur."""
    if name is None:
        return ""
    text = str(name).strip().lower().translate(_TR_MAP)
    return re.sub(r"[^a-z0-9]+", "", text)


def _sayiya_cevir(deger):
    """Türkçe formatlı bir Fintables hücresini (örn. '1.234,56', '-1,19',
    '90,48 mn', 'N/A', '%') float'a çevirir. Çevrilemezse None döner."""
    if deger is None:
        return None
    metin = str(deger).strip()
    if not metin or metin.upper() in ("N/A", "NA", "-", "—", ""):
        return None

    metin_kucuk = metin.lower()
    carpan = 1.0
    if "mr" in metin_kucuk or "milyar" in metin_kucuk:
        carpan = 1_000_000_000.0
    elif "mn" in metin_kucuk or "milyon" in metin_kucuk:
        carpan = 1_000_000.0
    elif "bin" in metin_kucuk:
        carpan = 1_000.0

    temiz = re.sub(r"[^0-9,.\-]", "", metin)
    if not temiz or temiz == "-":
        return None

    # Türkçe format: binlik ayraç nokta, ondalık ayraç virgül.
    if "," in temiz:
        temiz = temiz.replace(".", "").replace(",", ".")

    try:
        return float(temiz) * carpan
    except ValueError:
        return None


def _kolon_bul(columns, anahtar_kelimeler, haric=None):
    """Verilen anahtar kelimelerden herhangi birini (normalize edilmiş
    haliyle) içeren İLK kolon adını döner; bulunamazsa None."""
    haric = haric or []
    for col in columns:
        if col in haric:
            continue
        norm = _normalize(col)
        for anahtar in anahtar_kelimeler:
            if _normalize(anahtar) in norm:
                return col
    return None


def _index_benzeri_kolon_mu(sayisal_seri, toplam_satir):
    """BUG FIX (canlı testte bulundu): Fintables Radar tablosunun ilk
    kolonu genelde '#' başlıklı, sadece satırın sayfadaki SIRA NUMARASINI
    (1'den ~640'a, Fintables'ın kendi varsayılan - genelde alfabetik -
    sıralamasına göre) içerir; gerçek bir piyasa sinyali DEĞİLDİR.

    Önceden bu kolon, hacim/gün/getiri kolonları isimden bulunamadığında
    devreye giren "tüm sayısal kolonları kullan" yedek mantığına
    yanlışlıkla dahil ediliyordu. Bu, "_on_eleme_skoru"nun gerçek
    hacim/momentum sinyalinden ÇOK, Fintables'ın satırları hangi sırada
    listelediğine (örn. alfabetik) göre çarpıtılmasına yol açıyordu -
    canlı testte doğrulandı: seçilen top-20'nin '#' değerlerinin
    ortalaması, gerçek bir sinyal olmadığı durumda beklenen ~320
    (640/2) yerine ~434 çıktı ve adaylar neredeyse tam alfabetik
    ters sırada geldi (Z...'dan başlayan hisseler öne çıktı).

    Bu fonksiyon, bir sayısal kolonun "1'den N'e kadar sıra numarası"
    gibi görünüp görünmediğini (yani gerçek bir piyasa ölçütü değil, bir
    DİZİN/SIRA artefaktı olup olmadığını) tespit eder: değerlerin büyük
    çoğunluğu BENZERSİZ ve [1, satır_sayısı] aralığına yakınsa, bu bir
    indeks kolonu kabul edilir ve puanlamadan HARİÇ TUTULUR.
    """
    if toplam_satir <= 0:
        return False
    gecerli = sayisal_seri.dropna()
    if len(gecerli) < max(3, toplam_satir * 0.9):
        return False
    # Değerlerin tamsayıya çok yakın olması gerekir (sıra numaraları
    # ondalıklı olmaz).
    if not all(abs(v - round(v)) < 1e-9 for v in gecerli):
        return False
    benzersiz_sayi = gecerli.nunique()
    if benzersiz_sayi < 0.95 * len(gecerli):
        return False
    return (
        gecerli.min() >= 1
        and gecerli.max() <= toplam_satir * 1.05
    )


# YENİ ÖZELLİK (kullanıcı isteği - kaba filtre): Radar'ın thead'i genelde
# SADECE 1-2 gerçek başlık sağlıyor ('#' ve bazen bir tane daha); geri
# kalan kolonlar otomatik 'Kolon_N' adını alıyor (bkz.
# integrations/fintables_browser.py şema tespiti) - bu yüzden hacim/gün/
# fiyat kolonları İSİMDEN çoğu zaman bulunamıyor. AMA bu oturumdaki
# TÜM canlı testlerde tekrar tekrar doğrulanan sabit bir örüntü var:
# Radar'ın 13 kolonlu satırlarında kolon SIRASI HER ZAMAN aynı:
#   [0]=# (sıra no), [1]=Hisse, [2]=Fiyat, [3]=Gün % değişim,
#   [4]=Hacim, [5..12]=çeşitli vadeli Getiri yüzdeleri.
# Bu POZİSYONEL bilgi, isim-tabanlı arama başarısız olduğunda güvenilir
# bir yedek olarak kullanılır - SADECE otomatik üretilmiş ('Kolon_N' ya
# da '#' gibi) isimler için; gerçek/tanınabilir bir isim varsa ASLA
# üzerine yazılmaz.
#
# GÜNCELLEME (kullanıcı ekran görüntüsüyle DOĞRULADI - "Johnny pipeline
# düzeltmesi" / rule_engine yeniden tasarımı): 5-12 arası kolonların tam
# olarak neye karşılık geldiği teyit edildi: Getiri % (Son 1 hafta),
# Getiri % (Son 1 ay), Getiri % (Son 3 ay), Getiri % (Son 6 ay), Getiri %
# (Yılbaşından bugüne), Getiri % (Son 1 yıl), Getiri % (Son 3 yıl),
# Getiri % (Son 5 yıl). Şimdilik rule_engine'in kullandığı 1 hafta/1 ay/
# 3 ay eklendi; ihtiyaç olursa diğerleri de aynı şekilde eklenebilir.
RADAR_POZISYONEL_TOPLAM_KOLON = 13
RADAR_POZISYONEL_INDEKS = {
    "fiyat": 2, "gun": 3, "hacim": 4,
    "getiri_1h": 5, "getiri_1a": 6, "getiri_3a": 7,
}


def _isim_otomatik_uretilmis_mi(kolon_adi):
    """Bir kolon adının 'Kolon_N' (otomatik üretilmiş) ya da '#' olup
    olmadığını kontrol eder - _radar_sayfasindan_df_olustur'un ürettiği
    isimlerle birebir eşleşir."""
    if kolon_adi == "#":
        return True
    return bool(re.match(r"^Kolon_\d+$", str(kolon_adi)))


def _pozisyonel_kolon_bul(columns, anahtar):
    """İsim-tabanlı arama başarısız olduğunda, Radar'ın bilinen SABİT
    13-kolonlu düzenine göre (bkz. RADAR_POZISYONEL_INDEKS) ilgili
    kolonu POZİSYONA göre bulur. Kolon sayısı 13 değilse ya da o
    pozisyondaki isim otomatik üretilmiş GÖRÜNMÜYORSA (yani gerçek,
    tanınabilir bir isimse - bu durumda isim-tabanlı arama zaten
    başarılı olurdu, buraya hiç gelinmezdi ama yine de güvenlik için
    kontrol edilir) None döner."""
    columns = list(columns)
    if len(columns) != RADAR_POZISYONEL_TOPLAM_KOLON:
        return None
    indeks = RADAR_POZISYONEL_INDEKS.get(anahtar)
    if indeks is None or indeks >= len(columns):
        return None
    aday = columns[indeks]
    if not _isim_otomatik_uretilmis_mi(aday):
        return None
    return aday


def kaba_filtrele(df_radar, hisse_kolonu=None, min_hacim_percentile=0.20, on_progress=None):
    """YENİ ÖZELLİK (kullanıcı isteği): ön elemeye (select_top_candidates)
    girmeden ÖNCE, Radar'ın ~640 satırından çok düşük hacimli ya da
    fiyat/hacim verisi anlamsız/eksik olan satırları AÇIKÇA VE KESİN
    OLARAK hariç tutar ("sert" eleme). Önceden bu tür satırlar sadece
    düşük bir percentile rank alıp elenmeye ÇALIŞILIYORDU ("yumuşak"
    eleme, yine de teorik olarak seçilebilirlerdi); artık tamamen
    havuzun dışında bırakılıyorlar.

    Fiyat/hacim kolonu (isimden ya da - bulunamazsa - Radar'ın bilinen
    sabit kolon sırasından, bkz. _pozisyonel_kolon_bul) TESPİT
    EDİLEMEZSE, bu filtre GÜVENLİ ŞEKİLDE ATLANIR (df_radar değişmeden
    döner) - asla çökmez, asla yanlış bir kolonu filtrelemeye çalışmaz.

    Args:
        df_radar: fetch_radar_table() çıktısı (ham DataFrame)
        hisse_kolonu: hisse kodu kolonu (biliniyorsa; fiyat/hacim
            aramasında hariç tutulur, isim-tabanlı yanlış eşleşmeyi
            önlemek için)
        min_hacim_percentile: hacme göre alt yüzdelik dilim eşiği
            (varsayılan 0.20 = en düşük hacimli %20 hariç tutulur).
            0 ya da None verilirse bu percentile-tabanlı adım atlanır
            (sadece eksik/sıfır hacim/fiyat filtrelenir).
        on_progress: opsiyonel callable(str) - kaç satırın/hangi
            nedenle elendiğini loglar; kendi içinde hata fırlatırsa
            yok sayılır (akışı bozmaz).

    Returns:
        pd.DataFrame: filtrelenmiş DataFrame (index sıfırlanmış).
    """
    def _bildir(mesaj):
        if on_progress:
            try:
                on_progress(mesaj)
            except Exception:
                pass

    df = df_radar.copy()
    baslangic_sayisi = len(df)
    haric = [c for c in [hisse_kolonu, "#"] if c]

    fiyat_kolonu = _kolon_bul(df.columns, ["fiyat"], haric=haric) or _pozisyonel_kolon_bul(df.columns, "fiyat")
    hacim_kolonu = _kolon_bul(df.columns, ["hacim"], haric=haric) or _pozisyonel_kolon_bul(df.columns, "hacim")

    if fiyat_kolonu is None and hacim_kolonu is None:
        _bildir(
            "Bilgi: kaba filtre atlandı - fiyat/hacim kolonu (isimden ya "
            "da bilinen kolon sırasından) tespit edilemedi."
        )
        return df.reset_index(drop=True)

    # BUG FIX (canlı testte bulundu - 640 hisseden 640'ı elendi, 0 kaldı,
    # akış aşağıda çökmüştü): Fintables Radar'ın Fiyat/Hacim hücreleri
    # BEKLENMEDİK bir formatta gelirse (örn. site formatı değişti, çok
    # erken piyasa açılışında hacim geçici olarak tuhaf görünüyor, ya da
    # DOM'dan okuma sırasında bir bozulma oldu) _sayiya_cevir TÜM
    # satırlar için None/0 dönebilir - bu durumda filtre "kaba filtre"
    # olmaktan çıkıp "her şeyi eleyen bir filtre" haline geliyordu. Artık
    # bir filtre adımı TÜM satırları elerse (0 kalırsa) o adım GÜVENLİ
    # ŞEKİLDE ATLANIR (filtre uygulanmadan önceki hale geri dönülür) ve
    # açıkça bir UYARI loglanır - kaba filtrenin amacı "aşırı uçları
    # temizlemek", yanlışlıkla "her şeyi silmek" değildir.
    if fiyat_kolonu is not None and fiyat_kolonu in df.columns:
        fiyat_sayisal = df[fiyat_kolonu].map(_sayiya_cevir)
        oncesi = len(df)
        df_fiyat_filtreli = df[(fiyat_sayisal.notna() & (fiyat_sayisal > 0)).values]
        if df_fiyat_filtreli.empty and oncesi > 0:
            ornekler = df[fiyat_kolonu].astype(str).head(3).tolist()
            _bildir(
                f"UYARI: fiyat filtresi TÜM {oncesi} hisseyi eleyecekti - bu "
                "beklenmeyen bir durum (Radar formatı değişmiş olabilir), "
                f"filtre bu turda ATLANIYOR. Örnek ham fiyat değerleri: {ornekler}"
            )
        else:
            df = df_fiyat_filtreli
            elenen = oncesi - len(df)
            if elenen:
                _bildir(f"Kaba filtre: {elenen} hisse fiyat verisi eksik/anlamsız olduğu için elendi.")

    if hacim_kolonu is not None and hacim_kolonu in df.columns:
        hacim_sayisal = df[hacim_kolonu].map(_sayiya_cevir)
        oncesi = len(df)
        gecerli_maske = (hacim_sayisal.notna() & (hacim_sayisal > 0)).values
        df_hacim_filtreli = df[gecerli_maske]
        if df_hacim_filtreli.empty and oncesi > 0:
            ornekler = df[hacim_kolonu].astype(str).head(3).tolist()
            _bildir(
                f"UYARI: hacim filtresi TÜM {oncesi} hisseyi eleyecekti - bu "
                "beklenmeyen bir durum (Radar formatı değişmiş, piyasa henüz "
                "açılmamış ya da hacim verisi geçici olarak okunamıyor "
                f"olabilir), filtre bu turda ATLANIYOR. Örnek ham hacim "
                f"değerleri: {ornekler}"
            )
        else:
            df = df_hacim_filtreli
            elenen = oncesi - len(df)
            if elenen:
                _bildir(f"Kaba filtre: {elenen} hisse hacim verisi eksik/sıfır olduğu için elendi.")

        if min_hacim_percentile and 0 < min_hacim_percentile < 1 and len(df) > 0:
            # BUG FIX (canlı testte bulundu - yukarıdaki "hepsini eleme"
            # korumasından SONRA bile bu adım hâlâ TÜM satırları
            # eleyebiliyordu): hacim değerlerinin TAMAMI parse edilemezse
            # (hepsi NaN), quantile() de NaN döner ve `>= NaN`
            # karşılaştırması HER ZAMAN False sonuçlanır - yani bu adım
            # da "kaba filtre" değil "her şeyi silen bir filtre" haline
            # geliyordu. Aynı "tüm satırları eleyecekse atla" korumasını
            # burada da uygula.
            hacim_sayisal_guncel = df[hacim_kolonu].map(_sayiya_cevir)
            if hacim_sayisal_guncel.notna().sum() == 0:
                _bildir(
                    "UYARI: hacim yüzdelik dilim filtresi atlandı - hacim "
                    "değerlerinin hiçbiri sayıya çevrilemedi (hepsi eksik/"
                    "boş görünüyor)."
                )
            else:
                esik_deger = hacim_sayisal_guncel.quantile(min_hacim_percentile)
                oncesi = len(df)
                df_percentile_filtreli = df[(hacim_sayisal_guncel >= esik_deger).values]
                if df_percentile_filtreli.empty and oncesi > 0:
                    _bildir(
                        f"UYARI: hacim yüzdelik dilim filtresi TÜM {oncesi} "
                        "hisseyi eleyecekti, bu turda ATLANIYOR."
                    )
                else:
                    df = df_percentile_filtreli
                    elenen = oncesi - len(df)
                    if elenen:
                        _bildir(
                            f"Kaba filtre: en düşük hacimli %{int(min_hacim_percentile * 100)} "
                            f"({elenen} hisse) elendi."
                        )

    toplam_elenen = baslangic_sayisi - len(df)
    if toplam_elenen:
        _bildir(
            f"Kaba filtre tamamlandı: {baslangic_sayisi} hisseden "
            f"{toplam_elenen} tanesi elendi, {len(df)} hisse kaldı."
        )

    return df.reset_index(drop=True)


def _rank_normalize(seri):
    """Bir sayısal pandas Series'i 0-1 arası percentile rank'e çevirir.
    NaN değerler en düşük (0) kabul edilir (eksik veri ön elemede
    avantaj sağlamasın diye)."""
    if seri.notna().sum() == 0:
        return pd.Series([0.0] * len(seri), index=seri.index)
    return seri.rank(pct=True, na_option="bottom").fillna(0.0)


def find_ticker_column(columns):
    """Bir kolon listesinde hisse kodu kolonunu bulmaya çalışır (örn.
    '640 Hisse', 'Sembol', 'Kod'). Bulunamazsa None döner. run_full_update
    ile select_top_candidates aynı mantığı kullansın diye ayrı bir
    fonksiyon olarak dışa açıldı."""
    return _kolon_bul(columns, ["hisse", "sembol", "symbol", "kod"])


def select_top_candidates(df_radar, top_n=DEFAULT_TOP_N, hisse_kolonu=None):
    """Radar tablosundan (ham, Fintables'ın kendi başlıklarıyla) basit,
    şeffaf bir ön eleme ile ilk top_n adayı seçer.

    Sezgisel: bulunabilirse "hacim", "gün" (günlük değişim) ve en kısa
    vadeli "getiri" kolonlarının percentile rank toplamı; hiçbiri
    bulunamazsa tablodaki tüm sayısal kolonların rank toplamı kullanılır.
    Hiç sayısal kolon yoksa (aşırı uç durum) tablonun ilk top_n satırı
    olduğu gibi döner (asla hata fırlatıp sistemi durdurmaz).

    Args:
        df_radar: fetch_radar_table() çıktısı (ham DataFrame, ~640 satır)
        top_n: kaç aday seçilecek (varsayılan 10)
        hisse_kolonu: hisse kodu kolonunun adı biliniyorsa verin; yoksa
            otomatik bulunmaya çalışılır

    Returns:
        pd.DataFrame: en iyi top_n aday, orijinal Radar kolonları +
        "_on_eleme_skoru" (0-1, yüksek = daha güçlü aday) kolonu, azalan
        sırada.

    Raises:
        ValueError: hisse kodu kolonu hiçbir şekilde bulunamazsa (bu
            durumda hangi satırın hangi hisseye ait olduğu bilinemez).
    """
    df = df_radar.copy()

    if hisse_kolonu is None:
        hisse_kolonu = find_ticker_column(df.columns)
    if hisse_kolonu is None or hisse_kolonu not in df.columns:
        raise ValueError(
            "Radar tablosunda hisse kodu kolonu bulunamadı; ön eleme "
            "yapılamıyor. Tablonun ilk birkaç kolonunu kontrol edin."
        )

    # BUG FIX: Fintables Radar'ın '#' (sıra numarası) kolonu gerçek bir
    # piyasa sinyali değildir - bkz. _index_benzeri_kolon_mu docstring'i.
    # Adı zaten '#' olan kolon (en yaygın/bilinen hâli) burada baştan
    # hariç tutulur; aşağıdaki fallback döngüsünde de değer-bazlı genel
    # tespitle (isim ne olursa olsun) ayrıca korunuyoruz.
    haric_kolonlar = [hisse_kolonu, "#"]

    # YENİ ÖZELLİK: isim-tabanlı arama başarısız olursa (Radar'ın thead'i
    # genelde gerçek kolon adlarını sağlamıyor - bkz. _pozisyonel_kolon_bul
    # docstring'i), Radar'ın bilinen SABİT kolon sırasına göre pozisyonel
    # yedek denenir. Bu, "_on_eleme_skoru"nun rastgele/genel bir sayısal
    # kolon karışımı yerine GERÇEKTEN hacim/gün değişimine dayanmasını
    # sağlar.
    hacim_kolonu = _kolon_bul(df.columns, ["hacim"], haric=haric_kolonlar) or _pozisyonel_kolon_bul(df.columns, "hacim")
    gun_kolonu = _kolon_bul(df.columns, ["gun"], haric=haric_kolonlar) or _pozisyonel_kolon_bul(df.columns, "gun")
    getiri_kolonlari = [
        c for c in df.columns
        if c not in (hisse_kolonu, hacim_kolonu, gun_kolonu, "#") and "getiri" in _normalize(c)
    ]
    # En kısa vadeli getiri kolonunu tercih et (genelde en momentum-benzeri
    # sinyal); Fintables kolon sırası genelde kısa->uzun vade şeklindedir.
    # İsim-tabanlı hiç "getiri" bulunamazsa (yine thead eksikliği nedeniyle)
    # Radar'ın bilinen sabit sırasında ilk getiri kolonu (index 5) denenir.
    kisa_getiri_kolonu = getiri_kolonlari[0] if getiri_kolonlari else None
    if kisa_getiri_kolonu is None and len(df.columns) == RADAR_POZISYONEL_TOPLAM_KOLON:
        aday = df.columns[5]
        if _isim_otomatik_uretilmis_mi(aday) and aday not in (hisse_kolonu, hacim_kolonu, gun_kolonu, "#"):
            kisa_getiri_kolonu = aday

    kullanilan_kolonlar = [c for c in [hacim_kolonu, gun_kolonu, kisa_getiri_kolonu] if c]

    if not kullanilan_kolonlar:
        # Hiçbir tanıdık kolon bulunamadıysa: tablodaki sayıya çevrilebilen
        # tüm kolonları dene (hisse kodu hariç). BUG FIX: '#' gibi bir
        # SIRA/İNDEKS kolonu da (ismi ne olursa olsun) burada yanlışlıkla
        # gerçek bir sinyalmiş gibi puanlamaya sızabilirdi - bu yüzden her
        # aday kolon _index_benzeri_kolon_mu ile de kontrol edilip
        # index-benzeri olanlar dışlanır.
        for c in df.columns:
            if c == hisse_kolonu or c == "#":
                continue
            sayisal = df[c].map(_sayiya_cevir)
            if sayisal.notna().sum() > 0 and not _index_benzeri_kolon_mu(sayisal, len(df)):
                kullanilan_kolonlar.append(c)

    if not kullanilan_kolonlar:
        # Hâlâ hiçbir sayısal sinyal yoksa: sıralama yapamayız, tabloyu
        # olduğu gibi ilk top_n satırla döndür (asla çökme).
        sonuc = df.head(top_n).copy()
        sonuc["_on_eleme_skoru"] = None
        return sonuc

    skor_toplam = pd.Series([0.0] * len(df), index=df.index)
    for c in kullanilan_kolonlar:
        sayisal = df[c].map(_sayiya_cevir)
        skor_toplam = skor_toplam + _rank_normalize(sayisal)

    df["_on_eleme_skoru"] = round(skor_toplam / len(kullanilan_kolonlar), 4)

    sonuc = df.sort_values("_on_eleme_skoru", ascending=False).head(top_n).reset_index(drop=True)
    return sonuc
