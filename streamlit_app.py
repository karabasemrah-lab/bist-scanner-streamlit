# -*- coding: utf-8 -*-
from __future__ import annotations

import gc
import io
import pandas as pd
import streamlit as st

from fusion_core import analyze_symbol
from continuation_core import analyze_continuation
from symbols import FALLBACK_SYMBOLS
from tradingview_scanner import fetch_bist_universe


st.set_page_config(
    page_title="BIST Scanner",
    page_icon="🎯",
    layout="wide"
)

st.title("🎯 BIST Scanner")
st.caption(
    "Fusion Faz Tarayıcı + Trend Devam Kırılım Tarayıcı"
)


# ─────────────────────────────────────────────
# ORTAK YARDIMCILAR
# ─────────────────────────────────────────────

def parse_symbols(text):
    result = []
    seen = set()

    for raw in text.replace("\n", ",").split(","):
        symbol = raw.strip().upper().removesuffix(".IS")

        if symbol and symbol not in seen:
            seen.add(symbol)
            result.append(symbol)

    return result


def get_scan_symbols(source, special, max_candidates, min_avg_volume):

    if source == "TradingView Ön Eleme":

        try:
            tv_rows = fetch_bist_universe(
                min_avg_volume=float(min_avg_volume),
                max_rows=int(max_candidates)
            )

            symbols = [
                row["symbol"]
                for row in tv_rows
            ][:max_candidates]

            return symbols, None

        except Exception as exc:

            symbols = FALLBACK_SYMBOLS[:max_candidates]

            return symbols, str(exc)

    symbols = parse_symbols(
        special
    )[:max_candidates]

    return symbols, None


# ─────────────────────────────────────────────
# ORTAK SOL PANEL
# ─────────────────────────────────────────────

with st.sidebar:

    st.header("Tarama Ayarları")

    source = st.radio(
        "Evren",
        [
            "Özel Liste",
            "TradingView Ön Eleme"
        ],
        index=0
    )

max_candidates = st.slider(
    "İşlenecek maksimum hisse",
    min_value=5,
    max_value=1000,
    value=100,
    step=5
)

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

    st.divider()

    st.caption(
        "Önce küçük listeyle test et; "
        "sonra TradingView Ön Eleme kullan."
    )


# ─────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────

if "fusion_results" not in st.session_state:
    st.session_state.fusion_results = []

if "continuation_results" not in st.session_state:
    st.session_state.continuation_results = []


# ─────────────────────────────────────────────
# ANA SEKME YAPISI
# ─────────────────────────────────────────────

tab_fusion, tab_continuation = st.tabs(
    [
        "🎯 Fusion Faz",
        "🟣 Trend Devam"
    ]
)


# ═════════════════════════════════════════════
# 🎯 FUSION FAZ TARAYICI
# ═════════════════════════════════════════════

with tab_fusion:

    st.subheader("🎯 Fusion Faz Tarayıcı")

    st.caption(
        "🔵 Birikim → 🚀 Taze Kırılım → "
        "🟢 Güçlü Fusion → 🟠 Yaşlanma / Dağıtım"
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        one_line = st.number_input(
            "Momentum çizgisi",
            value=0.30,
            step=0.05,
            format="%.2f",
            key="fusion_one_line"
        )

    with col2:
        near_zero = st.number_input(
            "0 yaklaşım bandı",
            value=0.15,
            step=0.05,
            format="%.2f",
            key="fusion_near_zero"
        )

    with col3:
        mature = st.slider(
            "Normal momentum ömrü",
            10,
            100,
            30,
            5,
            key="fusion_mature"
        )

    with col4:
        only_core = st.checkbox(
            "Sadece ana fazları göster",
            value=True,
            key="fusion_only_core"
        )

    if st.button(
        "🚀 Fusion Taramasını Başlat",
        type="primary",
        use_container_width=True,
        key="fusion_scan_button"
    ):

        symbols, universe_error = get_scan_symbols(
            source,
            special,
            max_candidates,
            min_avg_volume
        )

        if universe_error:
            st.warning(
                "TradingView ön elemesi alınamadı. "
                "Yedek liste kullanılıyor.\n\n"
                + universe_error
            )

        if source == "TradingView Ön Eleme":
            st.success(
                f"Ön eleme tamamlandı: "
                f"{len(symbols)} hisse."
            )

        rows = []

        progress = st.progress(0)
        status = st.empty()

        for i, symbol in enumerate(
            symbols,
            start=1
        ):

            status.info(
                f"{symbol} analiz ediliyor · "
                f"{i}/{len(symbols)}"
            )

            try:

                row = analyze_symbol(
                    symbol,
                    one_line=float(one_line),
                    near_zero=float(near_zero),
                    mature_bars=int(mature)
                )

                if row:
                    rows.append(row)

            except Exception:
                pass

            progress.progress(
                int(
                    i
                    / max(len(symbols), 1)
                    * 100
                )
            )

            if i % 5 == 0:
                gc.collect()

        st.session_state.fusion_results = rows

        status.success(
            f"Tarama tamamlandı · "
            f"{len(rows)} geçerli sonuç"
        )

        progress.progress(100)


    fusion_rows = st.session_state.fusion_results

    if fusion_rows:

        df = pd.DataFrame(
            fusion_rows
        )

        main_phases = {
            "🔵 BİRİKİM",
            "🚀 TAZE KIRILIM",
            "🟢 GÜÇLÜ FUSION",
            "🟠 YAŞLANMA / DAĞITIM",
            "🟠 OLGUN TREND"
        }

        if only_core:

            shown = df[
                df["phase"].isin(
                    main_phases
                )
            ].copy()

        else:

            shown = df.copy()

        phase_order = {
            "🚀 TAZE KIRILIM": 0,
            "🔵 BİRİKİM": 1,
            "🟢 GÜÇLÜ FUSION": 2,
            "🟠 YAŞLANMA / DAĞITIM": 3,
            "🟠 OLGUN TREND": 4,
            "🟢 ATAK": 5,
            "🟡 SOĞUMA": 6,
            "⚪ İZLEME": 7
        }

        shown["_order"] = (
            shown["phase"]
            .map(phase_order)
            .fillna(99)
        )

        shown = (
            shown
            .sort_values(
                ["_order", "score"],
                ascending=[True, False]
            )
            .drop(
                columns="_order"
            )
        )

        st.subheader(
            f"📊 Fusion Sonuçları · "
            f"{len(shown)} hisse"
        )

        st.dataframe(
            shown.rename(
                columns={
                    "symbol": "Hisse",
                    "phase": "Faz",
                    "rotation": "Rotasyon",
                    "distance": "Mesafe",
                    "current_distance": "Current",
                    "relative_strength": "Rölatif Güç",
                    "fx_impact": "Kur Etkisi",
                    "mtf_positive": "MTF",
                    "fatigue_pct": "Yorgunluk %",
                    "score": "Skor",
                    "close": "Fiyat"
                }
            ),
            use_container_width=True,
            hide_index=True,
            height=600
        )

        buffer = io.BytesIO()

        with pd.ExcelWriter(
            buffer,
            engine="xlsxwriter"
        ) as writer:

            df.to_excel(
                writer,
                sheet_name="Fusion Tarama",
                index=False
            )

        st.download_button(
            "📥 Fusion Excel Raporu",
            buffer.getvalue(),
            "bist_fusion_tarama.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="fusion_excel"
        )

    else:

        st.info(
            "Fusion taramasını başlat."
        )


# ═════════════════════════════════════════════
# 🟣 TREND DEVAM TARAYICI
# ═════════════════════════════════════════════

with tab_continuation:

    st.subheader(
        "🟣 Trend Devam Kırılım Tarayıcı"
    )

    st.caption(
        "Trend → Konsolidasyon → "
        "Önceki tepe kırılımı → Yeni momentum"
    )

    c1, c2, c3 = st.columns(3)

    with c1:

        continuation_bars = st.slider(
            "Konsolidasyon süresi (bar)",
            5,
            30,
            10,
            1
        )

    with c2:

        continuation_range = st.number_input(
            "Maksimum sıkışma genişliği %",
            min_value=2.0,
            max_value=30.0,
            value=12.0,
            step=1.0
        )

    with c3:

        continuation_volume = st.number_input(
            "Minimum hacim oranı",
            min_value=0.0,
            max_value=5.0,
            value=0.80,
            step=0.10,
            format="%.2f"
        )

    st.info(
        "🟣 Devam Kırılımı, zaten yükseliş trendinde "
        "olan ve kısa süre sıkıştıktan sonra "
        "yeniden yukarı kıran hisseleri arar."
    )

    if st.button(
        "🟣 Trend Devam Taramasını Başlat",
        type="primary",
        use_container_width=True,
        key="continuation_scan_button"
    ):

        symbols, universe_error = get_scan_symbols(
            source,
            special,
            max_candidates,
            min_avg_volume
        )

        if universe_error:

            st.warning(
                "TradingView ön elemesi alınamadı. "
                "Yedek liste kullanılıyor.\n\n"
                + universe_error
            )

        if source == "TradingView Ön Eleme":

            st.success(
                f"Ön eleme tamamlandı: "
                f"{len(symbols)} hisse."
            )

        rows = []

        progress = st.progress(0)
        status = st.empty()

        for i, symbol in enumerate(
            symbols,
            start=1
        ):

            status.info(
                f"{symbol} trend devam analizi · "
                f"{i}/{len(symbols)}"
            )

            try:

                row = analyze_continuation(
                    symbol,
                    consolidation_bars=int(
                        continuation_bars
                    ),
                    max_range_pct=float(
                        continuation_range
                    ),
                    min_volume_ratio=float(
                        continuation_volume
                    )
                )

                if row:
                    rows.append(row)

            except Exception:
                pass

            progress.progress(
                int(
                    i
                    / max(len(symbols), 1)
                    * 100
                )
            )

            if i % 5 == 0:
                gc.collect()

        st.session_state.continuation_results = rows

        status.success(
            f"Trend devam taraması tamamlandı · "
            f"{len(rows)} geçerli sonuç"
        )

        progress.progress(100)


    continuation_rows = (
        st.session_state.continuation_results
    )

    if continuation_rows:

        cont_df = pd.DataFrame(
            continuation_rows
        )

        matches = cont_df[
            cont_df[
                "continuation_breakout"
            ] == True
        ].copy()

        matches = matches.sort_values(
            "score",
            ascending=False
        )

        st.subheader(
            f"🟣 Devam Kırılımı · "
            f"{len(matches)} hisse"
        )

        if matches.empty:

            st.warning(
                "Şu anda kriterlere uyan "
                "Devam Kırılımı bulunamadı."
            )

        else:

            st.dataframe(
                matches.rename(
                    columns={
                        "symbol": "Hisse",
                        "phase": "Durum",
                        "close": "Fiyat",
                        "breakout_level":
                            "Kırılım Seviyesi",
                        "consolidation_range_pct":
                            "Sıkışma %",
                        "volume_ratio":
                            "Hacim Oranı",
                        "ema20": "EMA20",
                        "ema50": "EMA50",
                        "score": "Skor"
                    }
                ),
                use_container_width=True,
                hide_index=True,
                height=600
            )

        cont_buffer = io.BytesIO()

        with pd.ExcelWriter(
            cont_buffer,
            engine="xlsxwriter"
        ) as writer:

            cont_df.to_excel(
                writer,
                sheet_name="Trend Devam",
                index=False
            )

        st.download_button(
            "📥 Trend Devam Excel Raporu",
            cont_buffer.getvalue(),
            "bist_trend_devam_tarama.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="continuation_excel"
        )

    else:

        st.info(
            "Trend Devam taramasını başlat."
        )


st.divider()

st.caption(
    "BIST Scanner Streamlit · "
    "Fusion Faz + Trend Devam"
)
