# -*- coding: utf-8 -*-
from __future__ import annotations

import gc
import io
import pandas as pd
import streamlit as st

from fusion_core import analyze_symbol
from symbols import FALLBACK_SYMBOLS
from tradingview_scanner import fetch_bist_universe

st.set_page_config(page_title="BIST Scanner Fusion", page_icon="🎯", layout="wide")
st.title("🎯 BIST Scanner — Fusion Faz Tarayıcı")
st.caption("🔵 Birikim → 🚀 Taze Kırılım → 🟢 Güçlü Fusion → 🟠 Yaşlanma / Dağıtım")

with st.sidebar:
    st.header("Tarama Ayarları")
    source = st.radio("Evren", ["Özel Liste", "TradingView Ön Eleme"], index=0)
    max_candidates = st.slider("İşlenecek maksimum hisse", 5, 120, 30, 5)
    min_avg_volume = st.number_input(
        "Min. 30G ortalama hacim",
        min_value=0,
        value=250000,
        step=50000
    )
    special = st.text_area(
        "Özel liste",
        "ASELS,THYAO,EREGL,TUPRS,GARAN",
        height=100
    )
    one_line = st.number_input("Momentum çizgisi", value=0.30, step=0.05, format="%.2f")
    near_zero = st.number_input("0 yaklaşım bandı", value=0.15, step=0.05, format="%.2f")
    mature = st.slider("Normal momentum ömrü (bar)", 10, 100, 30, 5)
    only_core = st.checkbox("Sadece 4 ana fazı göster", value=True)

if "fusion_results" not in st.session_state:
    st.session_state.fusion_results = []

def parse_symbols(text):
    out, seen = [], set()
    for raw in text.replace("\n", ",").split(","):
        s = raw.strip().upper().removesuffix(".IS")
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out

if st.button("🚀 Fusion Taramasını Başlat", type="primary", use_container_width=True):
    if source == "TradingView Ön Eleme":
        try:
            with st.spinner("TradingView BIST ön elemesi yapılıyor..."):
                tv_rows = fetch_bist_universe(
                    min_avg_volume=float(min_avg_volume),
                    max_rows=int(max_candidates)
                )
                symbols = [x["symbol"] for x in tv_rows][:max_candidates]
            st.success(f"Ön eleme tamamlandı: {len(symbols)} hisse.")
        except Exception as exc:
            st.warning(f"TradingView ön elemesi alınamadı: {exc}")
            symbols = FALLBACK_SYMBOLS[:max_candidates]
    else:
        symbols = parse_symbols(special)[:max_candidates]

    if not symbols:
        st.warning("Taranacak hisse bulunamadı.")
        st.stop()

    rows = []
    progress = st.progress(0)
    status = st.empty()

    for i, sym in enumerate(symbols, start=1):
        status.info(f"{sym} analiz ediliyor · {i}/{len(symbols)}")
        try:
            row = analyze_symbol(
                sym,
                one_line=float(one_line),
                near_zero=float(near_zero),
                mature_bars=int(mature)
            )
            if row:
                rows.append(row)
        except Exception:
            pass

        progress.progress(int(i / len(symbols) * 100))
        if i % 5 == 0:
            gc.collect()

    st.session_state.fusion_results = rows
    status.success(f"Tarama tamamlandı · {len(rows)} geçerli sonuç")
    progress.progress(100)

rows = st.session_state.fusion_results

if rows:
    df = pd.DataFrame(rows)

    main_phases = {
        "🔵 BİRİKİM",
        "🚀 TAZE KIRILIM",
        "🟢 GÜÇLÜ FUSION",
        "🟠 YAŞLANMA / DAĞITIM",
        "🟠 OLGUN TREND",
    }

    shown = df[df["phase"].isin(main_phases)].copy() if only_core else df.copy()

    order = {
        "🚀 TAZE KIRILIM":0,
        "🔵 BİRİKİM":1,
        "🟢 GÜÇLÜ FUSION":2,
        "🟠 YAŞLANMA / DAĞITIM":3,
        "🟠 OLGUN TREND":4,
        "🟢 ATAK":5,
        "🟡 SOĞUMA":6,
        "⚪ İZLEME":7,
    }
    shown["_order"] = shown["phase"].map(order).fillna(99)
    shown = shown.sort_values(["_order","score"], ascending=[True,False]).drop(columns="_order")

    st.subheader(f"📊 Sonuçlar · {len(shown)} hisse")
    st.dataframe(
        shown.rename(columns={
            "symbol":"Hisse",
            "phase":"Faz",
            "rotation":"Rotasyon",
            "distance":"Mesafe",
            "current_distance":"Current",
            "relative_strength":"Rölatif Güç",
            "fx_impact":"Kur Etkisi",
            "mtf_positive":"MTF",
            "fatigue_pct":"Yorgunluk %",
            "score":"Skor",
            "close":"Fiyat",
        }),
        use_container_width=True,
        hide_index=True,
        height=600,
    )

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name="Fusion Tarama", index=False)

    st.download_button(
        "📥 Excel Raporu",
        buffer.getvalue(),
        "bist_fusion_tarama.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
else:
    st.info("İlk test için Özel Liste ile 5–10 hisse taramanı öneririm.")

st.divider()
st.caption("v0.1 · Pine R4.4 Fusion mantığından türetilen ilk Streamlit prototipi")
