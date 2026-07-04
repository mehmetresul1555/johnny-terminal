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

    hacim_kolonu = _kolon_bul(df.columns, ["hacim"], haric=[hisse_kolonu])
    gun_kolonu = _kolon_bul(df.columns, ["gun"], haric=[hisse_kolonu])
    getiri_kolonlari = [
        c for c in df.columns
        if c not in (hisse_kolonu, hacim_kolonu, gun_kolonu) and "getiri" in _normalize(c)
    ]
    # En kısa vadeli getiri kolonunu tercih et (genelde en momentum-benzeri
    # sinyal); Fintables kolon sırası genelde kısa->uzun vade şeklindedir.
    kisa_getiri_kolonu = getiri_kolonlari[0] if getiri_kolonlari else None

    kullanilan_kolonlar = [c for c in [hacim_kolonu, gun_kolonu, kisa_getiri_kolonu] if c]

    if not kullanilan_kolonlar:
        # Hiçbir tanıdık kolon bulunamadıysa: tablodaki sayıya çevrilebilen
        # tüm kolonları dene (hisse kodu hariç).
        for c in df.columns:
            if c == hisse_kolonu:
                continue
            sayisal = df[c].map(_sayiya_cevir)
            if sayisal.notna().sum() > 0:
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
