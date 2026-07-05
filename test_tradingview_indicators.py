"""
TradingView Entegrasyonu - İzole CANLI test scripti
------------------------------------------------------
Amaç: TradingView'den teknik gösterge çekme sorununu (canlı testte
20/20 aday için "teknik veri alınamadı" görüldü), Radar/Fintables/
Johnny Score gibi diğer tüm bileşenleri devreye SOKMADAN, tek başına
ve İYİ BİLİNEN 5 büyük BIST hissesiyle (AKBNK, ASELS, THYAO, EREGL,
SASA) izole olarak test eder.

Bu 5 hisse Borsa İstanbul'un en likit/bilinen hisseleri arasındadır;
bunlar bile TradingView'de bulunamıyorsa, sorun Fintables'tan gelen
belirli sembollere özgü değil, "turkey" screener'ı / "BIST" borsa kodu
kombinasyonuna (ya da genel bir ağ/API sorununa) işaret eder.

Kullanım:
    cd ~/Desktop/johnny-terminal
    python3 test_tradingview_indicators.py

Bu script sadece OKUR (herhangi bir veri değiştirmez, oturum/giriş
gerektirmez) - TradingView'in herkese açık, kimlik doğrulama
gerektirmeyen scan uç noktasına istek atar.
"""
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from integrations import tradingview_indicators as tvi  # noqa: E402

TEST_HISSELERI = ["AKBNK", "ASELS", "THYAO", "EREGL", "SASA"]


def log(mesaj):
    print(f">>> {mesaj}")


def main():
    print("=" * 60)
    print("TRADINGVIEW ENTEGRASYONU - İZOLE CANLI TEST")
    print("=" * 60)
    print(f"Test edilecek hisseler: {', '.join(TEST_HISSELERI)}")
    print(f"Screener: {tvi.DEFAULT_SCREENER}  Exchange: {tvi.DEFAULT_EXCHANGE}  "
          f"Interval: {tvi.DEFAULT_INTERVAL}")
    print()

    # --- 1) Toplu istek (get_multiple_analysis) - normal/gerçek akışta
    #        kullanılan birincil yöntem ---
    print("--- 1) TOPLU İSTEK (get_multiple_analysis) ---")
    df = tvi.fetch_indicators_for_candidates(TEST_HISSELERI, on_progress=log)
    print("\nSonuç DataFrame:")
    print(df)

    basarili = df["rsi"].notna().sum()
    toplam = len(df)
    oran = basarili / toplam if toplam else 0
    print(f"\nBaşarı oranı: {basarili}/{toplam} (%{oran*100:.0f})")

    # --- 2) Tek tek (TA_Handler) - toplu istekten bağımsız, doğrudan
    #        karşılaştırma için ---
    print("\n--- 2) TEK TEK (TA_Handler.get_analysis) - bağımsız doğrulama ---")
    tekil_basarili = 0
    for hisse in TEST_HISSELERI:
        kayit = tvi.fetch_tradingview_indicators(hisse)
        bulundu = kayit.get("rsi") is not None
        tekil_basarili += int(bulundu)
        durum = "✅ BULUNDU" if bulundu else "❌ BULUNAMADI"
        print(f"  {hisse} ({tvi.normalize_bist_symbol(hisse)}): {durum} -> {kayit}")

    print(f"\nTek tek başarı oranı: {tekil_basarili}/{len(TEST_HISSELERI)}")

    print("\n" + "=" * 60)
    if basarili / max(toplam, 1) >= 0.8 or tekil_basarili / len(TEST_HISSELERI) >= 0.8:
        print("SONUÇ: TradingView entegrasyonu bu 5 bilinen hisse için "
              "büyük ölçüde ÇALIŞIYOR (hedef %80 karşılandı).")
    else:
        print("SONUÇ: TradingView'den bu 5 ÇOK BİLİNEN/likit hisse için bile "
              "veri alınamadı. Bu, belirli Fintables sembollerine özgü bir "
              "sorun DEĞİL - muhtemelen 'turkey' screener'ı / 'BIST' borsa "
              "kodu kombinasyonuna ya da genel bir ağ/API sorununa işaret "
              "ediyor. Yukarıdaki '>>> UYARI: ... Türkiye sorgusu -> ...' "
              "satırındaki HTTP durumu ve yanıt önizlemesini paylaşın.")
    print("=" * 60)


if __name__ == "__main__":
    main()
