"""
Johnny Terminal - BIST Günlük Trade Karar Destek Sistemi (MVP)

Çalıştırmak için:
    pip install -r requirements.txt
    streamlit run app.py

Bu araç otomatik emir GÖNDERMEZ. Sadece analiz / karar desteği sunar.
"""

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

import data_mapper  # noqa: E402
from integrations import fintables_browser  # noqa: E402
from scoring import market_journal, performance_tracker  # noqa: E402
from scoring.johnny_score import (  # noqa: E402
    NO_OPPORTUNITY_MESSAGE,
    OPTIONAL_COLUMNS,
    REQUIRED_COLUMNS,
    filter_tradeable,
    score_dataframe,
)

CONFIG_PATH = BASE_DIR / "config" / "watchlist.yaml"
OUTPUTS_DIR = BASE_DIR / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)

st.set_page_config(page_title="Johnny Terminal", page_icon="📈", layout="wide")


@st.cache_data
def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def durum_style(durum: str) -> str:
    return {
        "AL": "background-color:#1e5631;color:#ffffff;font-weight:600;",
        "İZLE": "background-color:#7a5c00;color:#ffffff;font-weight:600;",
        "UZAK DUR": "background-color:#3a3a3a;color:#bbbbbb;",
    }.get(durum, "")


def style_table(df: pd.DataFrame):
    def row_style(row):
        return [durum_style(row["Durum"])] * len(row)
    return df.style.apply(row_style, axis=1)


def render_kolon_eslestirme(df_ham: pd.DataFrame, anahtar_onek: str) -> pd.DataFrame:
    """Ham (kaynağı ne olursa olsun - dosya ya da Fintables) bir
    DataFrame için Kolon Eşleştirme arayüzünü çizer ve onaylanan
    eşleştirmeyle temizlenmiş DataFrame'i döner. Zorunlu kolonlardan
    biri eşleştirilmemişse hata gösterip st.stop() ile durur."""
    st.subheader("🔗 Kolon Eşleştirme")
    st.caption(
        "Kaynaktaki kolon adları Johnny'nin standart kolonlarıyla birebir "
        "aynı olmak zorunda değil. Aşağıda otomatik önerilen eşleştirmeyi "
        "kontrol edip gerekirse düzeltin."
    )

    with st.expander("📄 Kaynaktaki kolonlar", expanded=False):
        st.write(list(df_ham.columns))

    oneri = data_mapper.suggest_mapping(df_ham.columns)

    BOS_SECENEK = "(boş bırak)"
    secenekler = [BOS_SECENEK] + list(df_ham.columns)

    mapping = {}
    map_cols = st.columns(3)
    for i, johnny_col in enumerate(data_mapper.STANDARD_COLUMNS):
        zorunlu = johnny_col in REQUIRED_COLUMNS
        onerilen = oneri.get(johnny_col)
        varsayilan_index = secenekler.index(onerilen) if onerilen in secenekler else 0
        etiket = f"{johnny_col}{' *' if zorunlu else ' (opsiyonel)'}"
        with map_cols[i % 3]:
            secim = st.selectbox(
                etiket,
                secenekler,
                index=varsayilan_index,
                key=f"map_{anahtar_onek}_{johnny_col}",
            )
        mapping[johnny_col] = None if secim == BOS_SECENEK else secim

    eksikler = data_mapper.missing_required_columns(mapping, REQUIRED_COLUMNS)
    if eksikler:
        st.error(
            "Eşleştirilmemiş zorunlu kolonlar var, devam etmeden önce "
            f"yukarıdan seçin: {', '.join(eksikler)}"
        )
        st.stop()

    st.success("Tüm zorunlu kolonlar eşleştirildi.")
    df_temiz = data_mapper.apply_mapping(df_ham, mapping)
    st.divider()
    return df_temiz


config = load_config()
default_data_path = BASE_DIR / config.get("data", {}).get("default_file", "data/sample_data.csv")

st.title("📈 Johnny Terminal")
st.caption(
    "BIST Günlük Trade Karar Destek Sistemi — otomatik emir göndermez, "
    "her sabah en iyi 3 adayı bulmanıza yardımcı olur."
)

with st.sidebar:
    st.header("Veri Kaynağı")
    kaynak = st.radio(
        "Kaynak seçin",
        ["Fintables (Tarayıcı Otomasyonu)", "Dosya yükle (CSV / Excel)", "Örnek veri"],
        index=0,
    )

    uploaded_file = None

    if kaynak == "Fintables (Tarayıcı Otomasyonu)":
        st.caption(
            "Johnny, kendi Fintables Pro oturumunuzu kullanarak Hisse "
            "Radar sayfasını okur. Şifreniz hiçbir yerde saklanmaz; "
            "ilk giriş her zaman elle yapılır."
        )

        if fintables_browser.has_saved_session():
            st.success(f"✅ Oturum kayıtlı ({fintables_browser.session_info()})")
        else:
            st.warning("⚠️ Kayıtlı oturum yok, önce giriş yapın.")

        if st.button("🌐 Tarayıcıyı Aç ve Giriş Yap", use_container_width=True):
            with st.spinner("Tarayıcı açılıyor... açılan pencerede giriş yapıp kapatın."):
                try:
                    fintables_browser.launch_login_session(
                        config.get("fintables", {}).get("login_url")
                    )
                    st.success("Oturum kaydedildi.")
                except fintables_browser.FintablesError as e:
                    st.error(str(e))
            st.rerun()

        if st.button("🔄 Fintables'tan Güncelle", use_container_width=True, type="primary"):
            # v1.0 FINAL REVİZYONU akışı: Radar oku -> ilk N aday seç ->
            # bu adayların RSI/MACD/EMA20/50/200/ADX/ATR değerlerini
            # Fintables'tan değil TradingView'in herkese açık uç
            # noktasından al -> birleştir (bkz. integrations/
            # fintables_browser.py -> run_full_update ve integrations/
            # tradingview_indicators.py). TradingView'den veri alınamayan
            # bir hisse ATLANMAZ, sadece teknik alanları None kalır.
            # Johnny Score hesaplama ve Top 3 seçimi bu adımın DIŞINDA,
            # aşağıdaki Kolon Eşleştirme onayından sonra gerçekleşir
            # (bkz. altındaki not).
            with st.status("Fintables'tan güncelleniyor...", expanded=True) as durum:
                def _ilerleme_yaz(mesaj):
                    durum.write(mesaj)

                try:
                    df_fintables, hata_listesi = fintables_browser.run_full_update(
                        config, on_progress=_ilerleme_yaz
                    )
                    st.session_state["fintables_df_ham"] = df_fintables
                    st.session_state["fintables_hata_listesi"] = hata_listesi
                    # v1.2 (Market Journal): bu YENİ veri için bir snapshot/
                    # journal/ledger kaydı yapılması gerektiğini işaretle -
                    # aksi halde Streamlit'in her widget etkileşiminde
                    # script'i baştan çalıştırması, aynı veri için tekrar
                    # tekrar (yanlışlıkla) yeni snapshot kaydına yol açardı.
                    st.session_state["fintables_yeni_veri_bekliyor"] = True
                    durum.write(
                        "Ham veri hazır. Johnny Score hesaplaması, aşağıdaki "
                        "Kolon Eşleştirme onaylandıktan sonra otomatik olarak "
                        "yapılacak ve Top 3 gösterilecek."
                    )
                    durum.update(
                        label=f"Tamamlandı: {len(df_fintables)} hisse işlendi.",
                        state="complete",
                    )
                except fintables_browser.FintablesError as e:
                    durum.update(label="Hata oluştu", state="error")
                    st.error(str(e))

        if st.session_state.get("fintables_hata_listesi"):
            with st.expander(
                f"⚠️ Atlanan hisseler ({len(st.session_state['fintables_hata_listesi'])})"
            ):
                for ticker, hata_mesaji in st.session_state["fintables_hata_listesi"]:
                    st.write(f"**{ticker}**: {hata_mesaji}")

        with st.expander("Oturum yönetimi"):
            st.caption(
                "Oturumunuzda sorun yaşıyorsanız (örn. süresi dolmuşsa) "
                "kayıtlı oturumu silip yeniden giriş yapabilirsiniz."
            )
            if st.button("🗑️ Oturumu Sil"):
                fintables_browser.clear_session()
                st.session_state.pop("fintables_df_ham", None)
                st.session_state.pop("fintables_hata_listesi", None)
                st.info("Oturum silindi.")
                st.rerun()

    elif kaynak == "Dosya yükle (CSV / Excel)":
        uploaded_file = st.file_uploader("CSV veya Excel dosyası", type=["csv", "xlsx", "xls"])

    st.divider()
    st.subheader("Johnny Score Eşikleri")
    al_esik = config["thresholds"]["al"]
    izle_esik = config["thresholds"]["izle"]
    st.write(f"🟢 **AL**: {al_esik}+ puan")
    st.write(f"🟡 **İZLE**: {izle_esik}–{al_esik - 1} puan")
    st.write(f"⚪ **UZAK DUR**: {izle_esik} altı")

    st.divider()
    sadece_watchlist = st.checkbox(
        "Sadece config/watchlist.yaml içindeki hisseleri göster", value=False
    )

    st.divider()
    st.caption(f"Tarih: {datetime.now().strftime('%d.%m.%Y')}")
    with st.expander("Johnny Score v3 nasıl hesaplanır?"):
        st.markdown(
            "**Taban puan** (6 alt skor, motorlarca hesaplanır):\n"
            "- Teknik: 30\n"
            "- Momentum: 20\n"
            "- Bilanço/Temel: 20\n"
            "- Haber/KAP/Katalizör: 10\n"
            "- Kurumsal beklenti: 10\n"
            "- Piyasa rejimi: 10\n\n"
            f"Taban puan toplama işlemine göre değil, `base_damping` "
            f"({config.get('scoring', {}).get('base_damping', 0.6)}) ile "
            "sıkıştırılarak son skora katılır.\n\n"
            "**Kural motoru bonusu** (scoring/rule_engine.py): birden "
            "fazla sinyalin AYNI ANDA gerçekleşmesi (confluence) ekstra "
            "puan kazandırır. Asıl farklılaştırıcı puan buradan gelir — "
            "her hissenin kartındaki 'Johnny neden bu puanı verdi?' "
            "bölümünden tetiklenen kuralları görebilirsiniz."
        )

# --- Veri yükle ---
df_ham = None
anahtar_onek = None

if kaynak == "Fintables (Tarayıcı Otomasyonu)":
    df_ham = st.session_state.get("fintables_df_ham")
    anahtar_onek = "fintables"
elif kaynak == "Dosya yükle (CSV / Excel)" and uploaded_file is not None:
    try:
        df_ham = data_mapper.read_table(uploaded_file)
    except Exception as e:
        st.error(f"Dosya okunamadı: {e}")
        st.stop()
    anahtar_onek = f"{uploaded_file.name}_{uploaded_file.size}"

if df_ham is not None:
    df_raw = render_kolon_eslestirme(df_ham, anahtar_onek)
else:
    if kaynak == "Fintables (Tarayıcı Otomasyonu)":
        st.info(
            "Henüz Fintables'tan veri çekilmedi. Soldan '🔄 Fintables'tan "
            "Güncelle' butonuna basın — şimdilik örnek veri gösteriliyor."
        )
    elif kaynak == "Dosya yükle (CSV / Excel)":
        st.info("Dosya seçilmedi — şimdilik örnek veri gösteriliyor.")
    try:
        df_raw = pd.read_csv(default_data_path)
    except Exception as e:
        st.error(f"Veri okunamadı: {e}")
        st.stop()

if sadece_watchlist:
    watchlist = [t.upper() for t in config.get("watchlist", [])]
    df_raw = df_raw[df_raw["hisse"].str.upper().isin(watchlist)]

if df_raw.empty:
    st.warning("Gösterilecek veri yok. Filtreleri kontrol edin.")
    st.stop()

# --- Skorla ---
try:
    sonuc = score_dataframe(df_raw, config)
except ValueError as e:
    st.error(str(e))
    st.info(f"Gerekli kolonlar: {', '.join(REQUIRED_COLUMNS)} (opsiyonel: gerekce_notu, {', '.join(OPTIONAL_COLUMNS)})")
    st.stop()

if kaynak == "Fintables (Tarayıcı Otomasyonu)" and st.session_state.get("fintables_df_ham") is not None:
    st.success("✅ Johnny Score hesaplandı. Top 3 hazır.")

# v1.2 (Market Journal - kullanıcı isteği): SADECE yeni bir Fintables
# güncellemesi sonrası (fintables_yeni_veri_bekliyor bayrağı) bir
# snapshot kaydedilir + Piyasa Günlüğü üretilir + performans defteri
# güncellenir. Streamlit HER widget etkileşiminde bu script'i baştan
# çalıştırdığı için, bu bayrak olmadan her sayfa yenilemesinde yanlışlıkla
# tekrar tekrar snapshot kaydedilirdi.
if kaynak == "Fintables (Tarayıcı Otomasyonu)" and st.session_state.get("fintables_yeni_veri_bekliyor"):
    _snapshot_path, _ts = market_journal.save_snapshot(sonuc, BASE_DIR)
    _gunluk_metni, _gunluk_veri = market_journal.generate_market_journal(BASE_DIR, sonuc, _ts)
    performance_tracker.record_recommendations(sonuc, _ts, BASE_DIR)
    performance_tracker.update_open_recommendations(BASE_DIR)
    st.session_state["son_gunluk_metni"] = _gunluk_metni
    st.session_state["son_snapshot_ts"] = _ts
    st.session_state["fintables_yeni_veri_bekliyor"] = False

# --- Trade edilebilir fırsatlar ---
# v1.0 REVİZYON (kullanıcı isteği - "Johnny artık bir puanlama motoru
# değil, bir TRADE ASİSTANI"): kullanıcıya ASLA "UZAK DUR" etiketli
# hisseler burada gösterilmez - sonuc.head(3) yerine sadece gerçekten
# işlem yapılabilir (AL/İZLE) adaylar (bkz. filter_tradeable) kullanılır.
# Hiçbir aday bu seviyeye ulaşmıyorsa NO_OPPORTUNITY_MESSAGE gösterilir;
# "en iyi kötü hisse" gibi bir sonuç asla sunulmaz.
st.subheader("🏆 Bugünün Fırsatları")
firsatlar = filter_tradeable(sonuc)
if firsatlar.empty:
    st.info(f"ℹ️ {NO_OPPORTUNITY_MESSAGE}")
else:
    top3 = firsatlar.head(3)
    cols = st.columns(len(top3))
    for i, (_, row) in enumerate(top3.iterrows()):
        with cols[i]:
            st.markdown(f"### {row['Hisse']}")
            st.markdown(f"**{row['Durum']}** · {row['Johnny Score']:.0f} puan")
            st.write(f"Fiyat: {row['Fiyat']}")
            st.write(f"**Alım Aralığı:** {row['Alım Aralığı']}")
            st.write(f"**Stop:** {row['Stop']}")
            st.write(f"**Hedef 1:** {row['Hedef 1']}")
            st.write(f"**Hedef 2:** {row['Hedef 2']}")
            st.write(
                f"**Güven Skoru:** %{row['Güven Skoru (%)']:.0f} · "
                f"**Risk/Getiri:** {row['Risk/Getiri Oranı']}"
            )
            st.caption(f"Kurallar: {row['Rule Bonusları']}")
            st.caption(row["Gerekçe"])
            with st.expander("🔍 Johnny neden bu puanı verdi?"):
                st.markdown(row["Neden"])

st.divider()

# --- Piyasa Günlüğü (v1.2 Market Journal) ---
# Bir önceki analiz snapshot'ıyla otomatik karşılaştırma: yeni giren/
# çıkan hisseler, en çok kazanan/kaybeden, Top 3 değişimi, en istikrarlı/
# en hızlı yükselen-zayıflayan adaylar. SADECE yeni bir Fintables
# güncellemesi sonrası üretilir (bkz. yukarıdaki fintables_yeni_veri_
# bekliyor bayrağı) - sayfa yenilemelerinde son üretilen metin gösterilir.
if st.session_state.get("son_gunluk_metni"):
    st.subheader("📓 Piyasa Günlüğü")
    st.text(st.session_state["son_gunluk_metni"])
    st.divider()

# --- Tam tablo ---
# NOT: bu tablo şeffaflık/araştırma amaçlıdır ve "UZAK DUR" adayları da
# İÇEREBİLİR - yukarıdaki "Bugünün Fırsatları" bölümünün aksine bu bir
# öneri listesi DEĞİLDİR, sadece taranan tüm adayların tam dökümüdür.
st.subheader("📋 Tüm Adaylar (araştırma amaçlı - öneri değildir)")
tablo_kolonlari = ["Hisse", "Fiyat", "Johnny Score", "Durum", "Alım Aralığı", "Stop", "Hedef 1", "Hedef 2", "Gerekçe"]
st.dataframe(style_table(sonuc[tablo_kolonlari]), use_container_width=True, hide_index=True)

# --- Madde madde detaylı gerekçeler (tüm hisseler) ---
with st.expander("🔍 Tüm hisseler için 'Johnny neden bu puanı verdi?' detayları"):
    for _, row in sonuc.iterrows():
        st.markdown(f"**{row['Hisse']} — {row['Johnny Score']:.0f} puan ({row['Durum']})**")
        st.markdown(row["Neden"])
        st.markdown("---")

# --- Dışa aktar ---
st.divider()
col_a, col_b = st.columns([1, 3])
with col_a:
    if st.button("💾 outputs/ klasörüne kaydet"):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = OUTPUTS_DIR / f"johnny_terminal_{ts}.csv"
        sonuc.to_csv(out_path, index=False, encoding="utf-8-sig")
        st.success(f"Kaydedildi: {out_path.name}")
with col_b:
    st.download_button(
        "⬇️ CSV indir",
        data=sonuc.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"johnny_terminal_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )

# --- Geçmiş Analizler (v1.2 Market Journal) ---
# Her analiz bir snapshot olarak history/snapshots/ altına kaydedilir;
# burada geçmiş herhangi bir snapshot tekrar açılıp o anki öneriler
# incelenebilir.
st.divider()
st.subheader("🗂️ Geçmiş Analizler")
gecmis_dosyalar = market_journal.list_snapshot_files(BASE_DIR)
if not gecmis_dosyalar:
    st.caption("Henüz kaydedilmiş bir analiz snapshot'ı yok.")
else:
    etiketler = [market_journal.ts_from_path(f) for f in reversed(gecmis_dosyalar)]
    secilen_ts = st.selectbox("Bir analiz tarihi/saati seçin", etiketler, key="gecmis_secim")
    if secilen_ts:
        secilen_yol = next(f for f in gecmis_dosyalar if market_journal.ts_from_path(f) == secilen_ts)
        gecmis_df = market_journal.load_snapshot(secilen_yol)
        gecmis_kolonlari = [c for c in tablo_kolonlari if c in gecmis_df.columns]
        st.dataframe(style_table(gecmis_df[gecmis_kolonlari]), use_container_width=True, hide_index=True)
        journal_eslesen = [f for f in market_journal.list_journal_files(BASE_DIR) if market_journal.ts_from_path(f) == secilen_ts]
        if journal_eslesen:
            with st.expander(f"📓 {secilen_ts} Piyasa Günlüğü"):
                st.text(journal_eslesen[0].read_text(encoding="utf-8"))

# --- Performans Raporu (v1.2 Market Journal) ---
# Johnny'nin kendi geçmiş AL/İZLE önerilerinin GERÇEK sonucunu (+1/+3/
# +5/+10 iş günü checkpoint'leri) ölçtüğü rapor. Ledger'da hiç
# değerlendirilmiş öneri yoksa (henüz yeterli zaman geçmediyse) bu net
# şekilde belirtilir - sistem asla uydurma bir sayı göstermez.
st.divider()
st.subheader("📊 Performans Raporu")
st.caption(
    "Johnny'nin geçmiş önerilerinin gerçek piyasa sonucu - kendi tarama "
    "örneklerinden (günde birkaç kez) hesaplanır, gerçek sürekli intraday "
    "veri değildir (bkz. rapor altındaki not)."
)
checkpoint_secimi = st.selectbox(
    "Referans checkpoint (kaç iş günü sonrasına bakılsın?)",
    performance_tracker.CHECKPOINT_GUNLERI, index=2, key="checkpoint_secimi",
)
if st.button("📊 Performans Raporunu Oluştur"):
    rapor = performance_tracker.generate_performance_report(BASE_DIR, checkpoint_gun=checkpoint_secimi)
    st.text(rapor["metin"])

st.caption(
    "⚠️ Bu araç yatırım tavsiyesi değildir ve otomatik emir göndermez. "
    "Sadece karar destek amaçlıdır."
)
