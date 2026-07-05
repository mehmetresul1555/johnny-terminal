"""
Data Mapper (v0.4)
-------------------
Fintables Pro'dan (veya başka bir kaynaktan) indirilen/kopyalanan CSV ve
Excel tablolarının kolon adları Johnny Terminal'in beklediği standart
kolon adlarıyla birebir uyuşmayabilir (örn. "Son Fiyat" yerine "fiyat",
"RSI(14)" yerine "rsi"). Bu modül:

    1. CSV/Excel dosyasını okur
    2. Kolon adlarını normalize eder (küçük harf, Türkçe karakter
       sadeleştirme, boşluk/noktalama temizliği)
    3. Bilinen takma adlar (alias) sözlüğüyle otomatik eşleştirme önerir
    4. Kalan/belirsiz kolonları raporlar; Streamlit arayüzünde kullanıcı
       elle seçebilsin diye bir öneri sözlüğü döner
    5. Onaylanan eşleştirmeye göre DataFrame'i Johnny standart kolon
       adlarına yeniden adlandırıp score_dataframe'e hazır hale getirir

Bu, doğrudan bir API/scraping entegrasyonu DEĞİLDİR: Fintables'tan elle
indirilen/kopyalanan bir CSV/Excel dosyasının kolonlarını Johnny'nin
anladığı standart forma çevirmeye yarayan bir "ön işlem" katmanıdır.

Mevcut scoring/ modülleri (rule_engine, johnny_score, technical_engine,
momentum_engine, fundamental_engine) bu dosyadan etkilenmez; data_mapper
sadece score_dataframe'e giden DataFrame'i hazırlar.
"""

import re

import pandas as pd

# Johnny Terminal'in beklediği standart kolonlar
STANDARD_COLUMNS = [
    "hisse", "fiyat", "rsi", "macd_signal", "ema20", "ema50", "ema200",
    "adx", "atr_pct", "volume_ratio", "fk", "pddd", "roe",
    "net_borc_favok", "haber_puani", "kurumsal_puani", "piyasa_rejimi",
    "yeni_is_iliskisi",
]

# Zorunlu olmayan (opsiyonel) standart kolonlar.
# - haber_puani/kurumsal_puani/piyasa_rejimi Fintables'tan hiçbir zaman
#   gelmez (Johnny'nin kendi öznel puanlarıdır); eksik olduklarında
#   scoring/johnny_score.py nötr bir varsayılan (5/10) kullanır.
# - rsi/macd_signal/ema20/ema50/ema200/adx/atr_pct: artık TradingView'in
#   herkese açık uç noktasından alınıyor (integrations/
#   tradingview_indicators.py); bir hisse TradingView'de bulunamazsa
#   eksik kalabilir. Eksik olduklarında scoring motorları nötr/varsayılan
#   değerlerle çalışır, sistem çökmez; "Johnny neden bu puanı verdi?"
#   bölümünde açıkça belirtilir.
# - fk/pddd/roe/net_borc_favok (v1.0 FINAL REVİZYONU): F/K ve PD/DD
#   Fintables'ın "Piyasa Çarpanları" sayfasından, ROE (varsa Net Borç/
#   FAVÖK) "Rasyo Analiz Tablosu" sayfasından okunmaya çalışılır
#   (integrations/fintables_browser.py -> fetch_fundamental_for_symbol).
#   Bu sayfalar bot koruması (Cloudflare) arkasında olabilir; çıkarsa ya
#   da veri bulunamazsa bu alanlar None kalır; scoring/
#   fundamental_engine.py nötr (2.5/5) puanlarla çalışır, sistem çökmez.
OPTIONAL_STANDARD_COLUMNS = [
    "yeni_is_iliskisi", "gerekce_notu",
    "haber_puani", "kurumsal_puani", "piyasa_rejimi",
    "rsi", "macd_signal", "ema20", "ema50", "ema200", "adx", "atr_pct",
    "fk", "pddd", "roe", "net_borc_favok",
]

# Her Johnny kolonu için bilinen Türkçe/İngilizce takma adlar (normalize
# edilmiş haliyle karşılaştırılır; bkz. _normalize). İlk eleman kanonik
# ad olacak şekilde sıralanmasına gerek yok, sırasız liste yeterli.
COLUMN_ALIASES = {
    "hisse": [
        "hisse", "sembol", "symbol", "kod", "hisse kodu", "ticker",
        "hisse adi", "pay adi", "kod adi",
    ],
    "fiyat": [
        "fiyat", "son fiyat", "kapanis", "kapanis fiyati", "close",
        "last", "guncel fiyat", "price", "son",
    ],
    "rsi": ["rsi", "rsi14", "rsi(14)", "rsi 14", "gorece guc endeksi"],
    "macd_signal": [
        "macd_signal", "macd sinyal", "macd sinyal farki",
        "macd histogram", "macd",
    ],
    "ema20": ["ema20", "ema 20", "ema(20)", "20 gunluk ema", "ema_20"],
    "ema50": ["ema50", "ema 50", "ema(50)", "50 gunluk ema", "ema_50"],
    "ema200": ["ema200", "ema 200", "ema(200)", "200 gunluk ema", "ema_200"],
    "adx": ["adx", "adx14", "adx(14)", "average directional index"],
    "atr_pct": [
        "atr_pct", "atr yuzde", "atr orani", "atr%", "atr",
        "gunluk volatilite", "volatilite",
    ],
    "volume_ratio": [
        "volume_ratio", "hacim orani", "relative volume", "rvol",
        "hacim ortalama orani", "hacim/ortalama",
    ],
    "fk": ["fk", "f/k", "fiyat kazanc", "fiyat/kazanc orani", "pe", "p/e"],
    "pddd": [
        "pddd", "pd/dd", "piyasa degeri defter degeri",
        "piyasa degeri/defter degeri", "pb", "p/b",
    ],
    "roe": ["roe", "ozkaynak karliligi", "ozkaynak getirisi", "return on equity"],
    "net_borc_favok": [
        "net_borc_favok", "net borc/favok", "net borc favok",
        "net debt/ebitda", "net borc ebitda", "net borc/favok orani",
    ],
    "haber_puani": [
        "haber_puani", "haber puani", "kap puani", "katalizor puani",
        "haber skoru",
    ],
    "kurumsal_puani": [
        "kurumsal_puani", "kurumsal puani", "analist puani",
        "hedef fiyat puani", "kurumsal beklenti",
    ],
    "piyasa_rejimi": [
        "piyasa_rejimi", "piyasa rejimi", "market regime",
        "piyasa durumu", "piyasa rejimi puani",
    ],
    "yeni_is_iliskisi": [
        "yeni_is_iliskisi", "yeni is iliskisi", "yeni ortaklik",
        "yeni sozlesme", "yeni anlasma", "yeni is birligi",
    ],
}

_TR_MAP = str.maketrans({
    "ç": "c", "Ç": "c",
    "ğ": "g", "Ğ": "g",
    "ı": "i", "İ": "i",
    "ö": "o", "Ö": "o",
    "ş": "s", "Ş": "s",
    "ü": "u", "Ü": "u",
})


def _normalize(name):
    """Kolon adını karşılaştırılabilir hale getirir: küçük harfe çevirir,
    Türkçe karakterleri sadeleştirir, boşluk/alt çizgi/noktalama
    farklarını yok sayar. Örn. 'RSI (14)' ve 'rsi_14' aynı normalize
    sonucu üretir: 'rsi14'."""
    if name is None:
        return ""
    text = str(name).strip().lower().translate(_TR_MAP)
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


def read_table(file_or_path):
    """CSV veya Excel dosyasını okuyup ham (orijinal kolon adlarıyla) bir
    DataFrame döner.

    `file_or_path`, bir dosya yolu (str/Path) veya Streamlit
    `file_uploader` çıktısı gibi bir dosya nesnesi olabilir.
    """
    name = getattr(file_or_path, "name", str(file_or_path))
    if str(name).lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(file_or_path)
    return pd.read_csv(file_or_path)


def suggest_mapping(source_columns):
    """Kaynak dosyadaki kolon adlarına bakarak her Johnny standart
    kolonu için en olası eşleşmeyi önerir.

    İki geçişli çalışır: önce tam (normalize edilmiş) eşleşme aranır,
    kalanlar için içerme (substring) bazlı esnek bir arama yapılır. Bir
    kaynak kolon en fazla bir Johnny kolonuna eşlenir.

    Args:
        source_columns: iterable[str] - yüklenen dosyadaki kolon adları

    Returns:
        dict: {johnny_kolonu: kaynak_kolonu_veya_None}
    """
    source_columns = list(source_columns)
    normalized_lookup = {}
    for col in source_columns:
        normalized_lookup.setdefault(_normalize(col), col)

    suggestion = {}
    used_sources = set()

    # 1. geçiş: tam (normalize edilmiş) eşleşme
    for johnny_col in STANDARD_COLUMNS:
        eslesme = None
        for alias in COLUMN_ALIASES.get(johnny_col, [johnny_col]):
            norm_alias = _normalize(alias)
            aday = normalized_lookup.get(norm_alias)
            if aday and aday not in used_sources:
                eslesme = aday
                break
        suggestion[johnny_col] = eslesme
        if eslesme:
            used_sources.add(eslesme)

    # 2. geçiş: eşleşmeyenler için içerme (substring) bazlı esnek arama
    for johnny_col in STANDARD_COLUMNS:
        if suggestion[johnny_col]:
            continue
        for alias in COLUMN_ALIASES.get(johnny_col, [johnny_col]):
            norm_alias = _normalize(alias)
            if len(norm_alias) < 3:
                continue  # çok kısa alias'larla substring aramak riskli
            bulundu = None
            for norm_col, orig_col in normalized_lookup.items():
                if orig_col in used_sources:
                    continue
                if norm_alias in norm_col or norm_col in norm_alias:
                    bulundu = orig_col
                    break
            if bulundu:
                suggestion[johnny_col] = bulundu
                used_sources.add(bulundu)
                break

    return suggestion


def missing_required_columns(mapping, required_columns):
    """Eşleştirmede (mapping) hâlâ karşılığı bulunamayan zorunlu
    kolonları listeler."""
    return [col for col in required_columns if not mapping.get(col)]


def apply_mapping(df, mapping):
    """Kullanıcının onayladığı eşleştirmeye göre DataFrame'i Johnny
    standart kolon adlarına dönüştürür.

    Args:
        df: ham (orijinal kolon adlı) DataFrame
        mapping: {johnny_kolonu: kaynak_kolonu_veya_None}

    Returns:
        pd.DataFrame: sadece eşleştirilen kolonları, Johnny standart
        adlarıyla içeren yeni bir DataFrame. Eşleştirilmeyen (None)
        Johnny kolonları çıktıda yer almaz.
    """
    yeni_df = pd.DataFrame(index=df.index)
    for johnny_col, kaynak_col in mapping.items():
        if kaynak_col and kaynak_col in df.columns:
            yeni_df[johnny_col] = df[kaynak_col]
    return yeni_df
