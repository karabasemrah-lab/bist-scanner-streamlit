# -*- coding: utf-8 -*-
from __future__ import annotations
import io
import pandas as pd
import streamlit as st
from fusion_core import analyze_symbol
from continuation_core import analyze_continuation
from symbols import FALLBACK_SYMBOLS
from tradingview_scanner import fetch_bist_universe
from job_manager import start_job, latest_job

st.set_page_config(page_title="BIST Scanner", page_icon="🎯", layout="wide", initial_sidebar_state="collapsed")
st.markdown("<style>[data-testid='stSidebar'],[data-testid='collapsedControl']{display:none!important}</style>", unsafe_allow_html=True)
st.title("🎯 BIST Scanner")
st.caption("Fusion Faz Tarayıcı + Trend Devam Kırılım Tarayıcı")


def parse_symbols(text):
    out=[]; seen=set()
    for raw in text.replace("\n",",").split(","):
        s=raw.strip().upper().removesuffix(".IS")
        if s and s not in seen: seen.add(s); out.append(s)
    return out

st.subheader("Tarama Ayarları")
a,b,c=st.columns([1.1,1,2])
with a:
    source=st.radio("Evren",["Özel Liste","TradingView Ön Eleme"],horizontal=True)
with b:
    min_avg_volume=st.number_input("Min. 30G ortalama hacim",min_value=0,value=250000,step=50000)
with c:
    special=st.text_area("Özel liste","ASELS,THYAO,EREGL,TUPRS,GARAN",height=75)
if source=="TradingView Ön Eleme": st.caption("TradingView BIST evreni alınır; ham toplam ve hacim filtresi sonrası sayı ayrı gösterilir.")
else: st.caption("Özel listedeki tüm hisseler taranır.")
st.divider()


def universe():
    if source=="Özel Liste":
        syms=parse_symbols(special); return syms,None,len(syms),len(syms)
    try:
        rows,raw,filtered=fetch_bist_universe(float(min_avg_volume),2000,20,True)
        return [r["symbol"] for r in rows],None,raw,filtered
    except Exception as exc:
        return list(FALLBACK_SYMBOLS),str(exc),None,len(FALLBACK_SYMBOLS)


def job_status(kind, label):
    job=latest_job(kind)
    if not job:
        st.info(f"{label} taramasını başlat."); return None
    if job.get("raw_total") is not None:
        st.caption(f"BIST ham evren: {job['raw_total']} · Filtre sonrası: {job['filtered_total']} · Taranacak: {job['total']}")
    if job["status"] in ("queued","running"):
        cur=job["current"] or 0; total=max(job["total"] or 1,1)
        st.progress(min(cur/total,1.0))
        st.info(f"{job['current_symbol'] or 'Hazırlanıyor'} analiz ediliyor · {cur}/{job['total']} — Bu tarama sunucu tarafında çalışıyor; sayfadan geçici olarak ayrılsan da iş devam edebilir.")
    elif job["status"]=="done":
        st.progress(1.0)
        failed_count = len(job.get("failures") or [])
        st.success(
            f"Tarama tamamlandı · {len(job['results'])} geçerli sonuç"
            + (f" · {failed_count} veri alınamayan/işlenemeyen hisse" if failed_count else "")
        )
    else: st.error("Tarama hatası: "+(job.get("error") or "Bilinmeyen hata"))
    return job


def excel_button(main_df, main_sheet, filename, key, all_df=None, all_sheet="Tüm Analiz", failures=None):
    """Okunaklı, filtrelenebilir ve Türkçe başlıklı Excel raporu üret."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        workbook = writer.book
        header_fmt = workbook.add_format({
            "bold": True, "font_color": "white", "bg_color": "#1F4E78",
            "border": 1, "align": "center", "valign": "vcenter"
        })
        text_fmt = workbook.add_format({"valign": "vcenter"})
        num_fmt = workbook.add_format({"num_format": "0.00", "valign": "vcenter"})
        int_fmt = workbook.add_format({"num_format": "0", "valign": "vcenter"})

        def write_sheet(df, sheet_name):
            safe = df.copy()
            safe.to_excel(writer, sheet_name=sheet_name[:31], index=False)
            ws = writer.sheets[sheet_name[:31]]
            ws.freeze_panes(1, 1)
            ws.autofilter(0, 0, max(len(safe), 1), max(len(safe.columns)-1, 0))
            ws.set_row(0, 24)
            for col_idx, col in enumerate(safe.columns):
                ws.write(0, col_idx, col, header_fmt)
                values = safe[col].astype(str).replace("nan", "") if len(safe) else pd.Series(dtype=str)
                max_len = max([len(str(col))] + [len(v) for v in values.head(500)])
                width = min(max(max_len + 2, 11), 28)
                fmt = text_fmt
                if pd.api.types.is_numeric_dtype(safe[col]):
                    fmt = int_fmt if col in {"Skor"} else num_fmt
                ws.set_column(col_idx, col_idx, width, fmt)
            if len(safe):
                ws.set_row(1, None)

        write_sheet(main_df, main_sheet)
        if all_df is not None:
            write_sheet(all_df, all_sheet)
        if failures:
            fail_df = pd.DataFrame(failures).rename(columns={"symbol":"Hisse", "reason":"Neden"})
            write_sheet(fail_df, "İşlenemeyenler")

    st.download_button(
        "📥 Excel Raporu", buf.getvalue(), filename,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True, key=key
    )


def tradingview_table(df, symbol_column="Hisse", height=600):
    """Hisse adını tıklanabilir TradingView bağlantısı olarak göster."""
    display_df = df.copy()

    if symbol_column in display_df.columns:
        display_df[symbol_column] = display_df[symbol_column].astype(str).map(
            lambda symbol: f"https://tr.tradingview.com/chart/?symbol=BIST:{symbol}"
        )

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        height=height,
        column_config={
            symbol_column: st.column_config.LinkColumn(
                symbol_column,
                help="TradingView grafiğini aç",
                display_text=r"symbol=BIST:(.*)$",
                pinned=True,
            )
        } if symbol_column in display_df.columns else None,
    )

fusion_tab,cont_tab=st.tabs(["🎯 Fusion Faz","🟣 Trend Devam"])
with fusion_tab:
    st.subheader("🎯 Fusion Faz Tarayıcı")
    st.caption("🔵 Birikim → 🚀 Taze Kırılım → 🟢 Güçlü Fusion → 🟠 Yaşlanma / Dağıtım")
    c1,c2,c3,c4=st.columns(4)
    with c1: one_line=st.number_input("Momentum çizgisi",value=.30,step=.05,format="%.2f",key="f1")
    with c2: near_zero=st.number_input("0 yaklaşım bandı",value=.15,step=.05,format="%.2f",key="f2")
    with c3: mature=st.slider("Normal momentum ömrü",10,100,30,5,key="f3")
    with c4: only_core=st.checkbox("Sadece ana fazları göster",True,key="f4")
    if st.button("🚀 Fusion Taramasını Başlat",type="primary",use_container_width=True):
        syms,err,raw,filtered=universe()
        if err: st.warning("TradingView alınamadı; yedek liste kullanılıyor: "+err)
        start_job("fusion",syms,{"one_line":float(one_line),"near_zero":float(near_zero),"mature_bars":int(mature)},analyze_symbol,raw,filtered)
        st.rerun()

    @st.fragment(run_every="2s")
    def fusion_live():
        job=job_status("fusion","Fusion")
        if not job or not job["results"]: return
        df=pd.DataFrame(job["results"])
        shown=df.copy()
        if only_core and "phase" in shown:
            shown=shown[shown["phase"].isin({"🔵 BİRİKİM","🚀 TAZE KIRILIM","🟢 GÜÇLÜ FUSION","🟠 YAŞLANMA / DAĞITIM","🟠 OLGUN TREND"})]
        if "score" in shown: shown=shown.sort_values("score",ascending=False)
        st.subheader(f"📊 Fusion Sonuçları · {len(shown)} hisse")
        fusion_display = shown.rename(columns={"symbol":"Hisse","phase":"Faz","rotation":"Rotasyon","distance":"Mesafe","current_distance":"Current","relative_strength":"Rölatif Güç","fx_impact":"Kur Etkisi","mtf_positive":"MTF","fatigue_pct":"Yorgunluk %","score":"Skor","close":"Fiyat"})
        tradingview_table(fusion_display, "Hisse", 600)
        if job["status"]=="done":
            failures = job.get("failures") or []
            fusion_excel = fusion_display.copy()
            fusion_all = df.rename(columns={"symbol":"Hisse","phase":"Faz","rotation":"Rotasyon","distance":"Mesafe","current_distance":"Current","relative_strength":"Rölatif Güç","fx_impact":"Kur Etkisi","mtf_positive":"MTF","fatigue_pct":"Yorgunluk %","score":"Skor","close":"Fiyat"})
            wanted = ["Hisse","Faz","Rotasyon","Mesafe","Current","Rölatif Güç","Kur Etkisi","MTF","Yorgunluk %","Skor","Fiyat"]
            fusion_excel = fusion_excel[[c for c in wanted if c in fusion_excel.columns]]
            fusion_all = fusion_all[[c for c in wanted if c in fusion_all.columns]]
            excel_button(fusion_excel,"Fusion Sonuçları","bist_fusion_tarama.xlsx","fx",fusion_all,"Tüm Analiz",failures)
            if failures:
                with st.expander(f"⚠️ Veri alınamayan / işlenemeyen hisseler · {len(failures)}"):
                    fail_df = pd.DataFrame(failures).rename(
                        columns={"symbol":"Hisse","reason":"Neden"}
                    )
                    tradingview_table(
                        fail_df,
                        "Hisse",
                        min(500, 40 + len(fail_df) * 35),
                    )
    fusion_live()

with cont_tab:
    st.subheader("🟣 Trend Devam Kırılım Tarayıcı")
    st.caption("Trend → Konsolidasyon → Önceki tepe kırılımı → Yeni momentum")
    a1,a2,a3=st.columns(3)
    with a1: bars=st.slider("Konsolidasyon süresi (bar)",5,30,10,1)
    with a2: rng=st.number_input("Maksimum sıkışma genişliği %",2.0,30.0,12.0,1.0)
    with a3: vol=st.number_input("Minimum hacim oranı",0.0,5.0,.80,.10,format="%.2f")
    if st.button("🟣 Trend Devam Taramasını Başlat",type="primary",use_container_width=True):
        syms,err,raw,filtered=universe()
        if err: st.warning("TradingView alınamadı; yedek liste kullanılıyor: "+err)
        start_job("continuation",syms,{"consolidation_bars":int(bars),"max_range_pct":float(rng),"min_volume_ratio":float(vol)},analyze_continuation,raw,filtered)
        st.rerun()

    @st.fragment(run_every="2s")
    def cont_live():
        job=job_status("continuation","Trend Devam")
        if not job or not job["results"]: return
        df=pd.DataFrame(job["results"])
        matches=df[df["continuation_breakout"]==True].copy() if "continuation_breakout" in df else df
        if "score" in matches: matches=matches.sort_values("score",ascending=False)
        st.subheader(f"🟣 Devam Kırılımı · {len(matches)} hisse")
        if matches.empty: st.warning("Şu anda kriterlere uyan Devam Kırılımı bulunamadı.")
        else:
            cont_display = matches.rename(columns={"symbol":"Hisse","phase":"Durum","close":"Fiyat","breakout_level":"Kırılım Seviyesi","consolidation_range_pct":"Sıkışma %","volume_ratio":"Hacim Oranı","ema20":"EMA20","ema50":"EMA50","score":"Skor"})
            tradingview_table(cont_display, "Hisse", 600)
        if job["status"]=="done":
            failures = job.get("failures") or []
            trend_excel = matches.rename(columns={"symbol":"Hisse","phase":"Durum","close":"Fiyat","breakout_level":"Kırılım Seviyesi","consolidation_range_pct":"Sıkışma %","volume_ratio":"Hacim Oranı","ema20":"EMA20","ema50":"EMA50","score":"Skor"})
            trend_all = df.rename(columns={"symbol":"Hisse","phase":"Durum","close":"Fiyat","breakout_level":"Kırılım Seviyesi","consolidation_range_pct":"Sıkışma %","volume_ratio":"Hacim Oranı","ema20":"EMA20","ema50":"EMA50","score":"Skor"})
            wanted = ["Hisse","Durum","Fiyat","Kırılım Seviyesi","Sıkışma %","Hacim Oranı","EMA20","EMA50","Skor"]
            trend_excel = trend_excel[[c for c in wanted if c in trend_excel.columns]]
            trend_all = trend_all[[c for c in wanted if c in trend_all.columns]]
            excel_button(trend_excel,"Devam Kırılımları","bist_trend_devam_tarama.xlsx","cx",trend_all,"Tüm Analiz",failures)
            if failures:
                with st.expander(f"⚠️ Veri alınamayan / işlenemeyen hisseler · {len(failures)}"):
                    fail_df = pd.DataFrame(failures).rename(
                        columns={"symbol":"Hisse","reason":"Neden"}
                    )
                    tradingview_table(
                        fail_df,
                        "Hisse",
                        min(500, 40 + len(fail_df) * 35),
                    )
    cont_live()

st.divider(); st.caption("BIST Scanner Streamlit v0.8 · Düzenli Excel Raporları + Hızlı Paralel Tarama + TradingView Bağlantıları")
