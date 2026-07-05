"""
Johnny Terminal - Uçtan uca CANLI test scripti (v1.0 FINAL REVİZYONU)
----------------------------------------------------------------------
Bu script GERÇEK Fintables oturumunuzu ve GERÇEK TradingView API'sini
kullanarak tam akışı tek seferde çalıştırır:

    Fintables Radar oku -> ilk 20 aday seç -> TradingView'den teknik
    veri al -> Johnny Score hesapla -> Top 3'ü terminale yazdır

Kullanım:
    cd ~/Desktop/johnny-terminal
    python3 test_full_flow.py

Ön koşullar:
    - pip3 install -r requirements.txt  (tradingview-ta, playwright dahil)
    - playwright install chromium
    - Daha önce "streamlit run app.py" üzerinden "🌐 Tarayıcıyı Aç ve
      Giriş Yap" ile bir Fintables oturumu kaydedilmiş olmalı (bkz.
      README "Fintables Kurulumu"). Bu script GİRİŞ YAPMAZ, sadece
      kayıtlı oturumu kullanır.

Bu script otomatik/periyodik çalışma için değildir; manuel, tek seferlik
bir doğrulama aracıdır.
"""
import sys
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import data_mapper  # noqa: E402
from integrations import fintables_browser  # noqa: E402
from scoring.johnny_score import (  # noqa: E402
    NO_OPPORTUNITY_MESSAGE,
    OPTIONAL_COLUMNS,
    REQUIRED_COLUMNS,
    filter_tradeable,
    score_dataframe,
)

CONFIG_PATH = BASE_DIR / "config" / "watchlist.yaml"


def log(mesaj):
    print(f">>> {mesaj}")


def main():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if not fintables_browser.has_saved_session():
        print(
            "HATA: Kayıtlı bir Fintables oturumu yok.\n"
            "Önce 'streamlit run app.py' ile açıp '🌐 Tarayıcıyı Aç ve "
            "Giriş Yap' butonuyla bir kez giriş yapmanız gerekiyor."
        )
        sys.exit(1)

    print("=" * 60)
    print("JOHNNY TERMINAL - CANLI UÇTAN UCA TEST")
    print("=" * 60)

    try:
        df_ham, hata_listesi = fintables_browser.run_full_update(config, on_progress=log)
    except fintables_browser.FintablesError as e:
        print(f"\nHATA (Fintables/TradingView aşaması): {e}")
        sys.exit(1)

    print("\n--- Ham veri (Radar + TradingView) ---")
    onemli_kolonlar = [
        c for c in ["hisse", "rsi", "macd_signal", "ema20", "ema50", "ema200", "adx", "atr_pct"]
        if c in df_ham.columns
    ]
    print(df_ham[onemli_kolonlar].to_string(index=False))

    if hata_listesi:
        print(f"\nUYARI: {len(hata_listesi)} hisse yapısal nedenle işlenemedi:")
        for hisse, hata in hata_listesi:
            print(f"  - {hisse}: {hata}")

    # Kolon eşleştirme (otomatik öneriyle; bu script interaktif değil)
    oneri = data_mapper.suggest_mapping(df_ham.columns)
    eksikler = data_mapper.missing_required_columns(oneri, REQUIRED_COLUMNS)
    if eksikler:
        print(
            f"\nJohnny Score HESAPLANAMADI: şu zorunlu kolonlar Radar "
            f"verisinde/otomatik eşleştirmede bulunamadı: {', '.join(eksikler)}\n"
            "Bu genelde F/K, PD/DD, ROE, Net Borç/FAVÖK gibi temel "
            "(fundamental) verilerin Fintables Radar'ın varsayılan "
            "görünümünde bulunmamasından kaynaklanır. Bu alanları "
            "'streamlit run app.py' üzerinden Kolon Eşleştirme ekranında "
            "elle eşleştirebilirsiniz."
        )
        sys.exit(1)

    df_temiz = data_mapper.apply_mapping(df_ham, oneri)

    try:
        sonuc = score_dataframe(df_temiz, config)
    except ValueError as e:
        print(f"\nJohnny Score HESAPLANAMADI: {e}")
        print(f"Gerekli kolonlar: {', '.join(REQUIRED_COLUMNS)} (opsiyonel: {', '.join(OPTIONAL_COLUMNS)})")
        sys.exit(1)

    log("Johnny Score hesaplandı.")

    # v1.0 REVİZYON (kullanıcı isteği - "Johnny artık bir puanlama motoru
    # değil, bir TRADE ASİSTANI"): kullanıcıya ASLA "UZAK DUR" etiketli
    # hisseler Top 3 olarak gösterilmez - sonuc.head(3) yerine sadece
    # gerçekten işlem yapılabilir (AL/İZLE) adaylar (bkz. filter_tradeable)
    # kullanılır. Hiçbir aday bu seviyeye ulaşmıyorsa NO_OPPORTUNITY_MESSAGE
    # gösterilir.
    firsatlar = filter_tradeable(sonuc)

    print("\n" + "=" * 60)
    print("TRADE EDİLEBİLİR FIRSATLAR")
    print("=" * 60)
    if firsatlar.empty:
        print(f"\n{NO_OPPORTUNITY_MESSAGE}")
    else:
        for _, row in firsatlar.head(3).iterrows():
            print(f"\n{row['Hisse']} - {row['Durum']} ({row['Johnny Score']:.0f} puan)")
            print(
                f"  Fiyat: {row['Fiyat']}  Alım Aralığı: {row['Alım Aralığı']}  "
                f"Stop: {row['Stop']}  Hedef 1: {row['Hedef 1']}  Hedef 2: {row['Hedef 2']}"
            )
            print(f"  Gerekçe: {row['Gerekçe']}")

    log("Fırsat taraması tamamlandı.")


if __name__ == "__main__":
    main()
