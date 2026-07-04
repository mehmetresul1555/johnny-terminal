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

from scoring.johnny_score import REQUIRED_COLUMNS, score_dataframe  # noqa: E402

CONFIG_PATH = BASE_DIR / "config" / "watchlist.yaml"
OUTPUTS_DIR = BASE_DIR / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)

st.set_page_config(page_title="Johnny Terminal", page_icon="📈", layout="wide")


@st.cache_data
def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_dataframe(uploaded_file, default_path: Path):
    if uploaded_file is not None:
        if uploaded_file.name.lower().endswith(".csv"):
            return pd.read_csv(uploaded_file)
        return pd.read_excel(uploaded_file)
    return pd.read_csv(default_path)


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
        ["Örnek veri", "Dosya yükle (CSV / Excel)", "Fintables (yakında)"],
    )

    uploaded_file = None
    if kaynak == "Dosya yükle (CSV / Excel)":
        uploaded_file = st.file_uploader("CSV veya Excel dosyası", type=["csv", "xlsx", "xls"])
        if uploaded_file is None:
            st.info("Dosya seçilmedi — örnek veri gösteriliyor.")
    elif kaynak == "Fintables (yakında)":
        st.info(
            "Fintables Pro entegrasyonu bu MVP'de aktif değil. "
            "Şimdilik Fintables'tan aldığınız tabloyu CSV/Excel olarak "
            "kaydedip 'Dosya yükle' seçeneğinden yükleyebilirsiniz."
        )

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
try:
    if kaynak == "Dosya yükle (CSV / Excel)" and uploaded_file is not None:
        df_raw = load_dataframe(uploaded_file, default_data_path)
    else:
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
    st.info(f"Gerekli kolonlar: {', '.join(REQUIRED_COLUMNS)} (opsiyonel: gerekce_notu, yeni_is_iliskisi)")
    st.stop()

# --- Top 3 ---
st.subheader("🏆 Günün En İyi 3 Adayı")
top3 = sonuc.head(3)
cols = st.columns(3)
for i, (_, row) in enumerate(top3.iterrows()):
    with cols[i]:
        st.markdown(f"### {row['Hisse']}")
        st.markdown(f"**{row['Durum']}** · {row['Johnny Score']:.0f} puan")
        st.write(f"Fiyat: {row['Fiyat']}")
        st.write(f"**Alım Aralığı:** {row['Alım Aralığı']}")
        st.write(f"**Stop:** {row['Stop']}")
        st.write(f"**Hedef 1:** {row['Hedef 1']}")
        st.write(f"**Hedef 2:** {row['Hedef 2']}")
        st.caption(row["Gerekçe"])
        with st.expander("🔍 Johnny neden bu puanı verdi?"):
            st.markdown(row["Neden"])

st.divider()

# --- Tam tablo ---
st.subheader("📋 Tüm Adaylar")
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

st.caption(
    "⚠️ Bu araç yatırım tavsiyesi değildir ve otomatik emir göndermez. "
    "Sadece karar destek amaçlıdır."
)
