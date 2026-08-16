# -*- coding: utf-8 -*-
from __future__ import annotations
import numpy as np
import pandas as pd
import yfinance as yf
import threading
from symbols import REFERENCE_TICKERS

_REFERENCE_CACHE = None
_REFERENCE_LOCK = threading.Lock()

def clean(df):
    if df is None or df.empty:
        return pd.DataFrame()
    x = df.copy()
    if isinstance(x.columns, pd.MultiIndex):
        x.columns = [str(c[0]) for c in x.columns]
    need = ["Open","High","Low","Close","Volume"]
    if not all(c in x.columns for c in need):
        return pd.DataFrame()
    x = x[need].replace([np.inf,-np.inf], np.nan)
    x = x.dropna(subset=["Open","High","Low","Close"]).sort_index()
    x["Volume"] = x["Volume"].fillna(0)
    return x

def download(ticker, period="2y", interval="1d"):
    try:
        return clean(yf.download(
            ticker, period=period, interval=interval,
            auto_adjust=False, actions=False, progress=False,
            threads=False, timeout=25
        ))
    except Exception:
        return pd.DataFrame()


def get_reference_data():
    """Referans endekslerini süreç boyunca bir kez indirip tekrar kullan."""
    global _REFERENCE_CACHE

    if _REFERENCE_CACHE is not None:
        return _REFERENCE_CACHE

    with _REFERENCE_LOCK:
        if _REFERENCE_CACHE is None:
            _REFERENCE_CACHE = {
                key: download(ticker)
                for key, ticker in REFERENCE_TICKERS.items()
            }

    return _REFERENCE_CACHE

def atr(df, n=14):
    p = df["Close"].shift(1)
    tr = pd.concat([
        df["High"]-df["Low"],
        (df["High"]-p).abs(),
        (df["Low"]-p).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False, min_periods=n).mean()

def na_skip_average(src, length):
    vals, out = [], []
    for v in src.tolist():
        if pd.notna(v):
            vals.append(float(v))
            if len(vals) > length:
                vals.pop(0)
        out.append(float(np.mean(vals)) if vals else np.nan)
    return pd.Series(out, index=src.index)

def distance_series(df, zig_hi=10, zig_lo=10, min_move_pct=0.160,
                    ma_period=20, signal_avg_len=10, normalize_atr=False):
    x = clean(df)
    if len(x) < 100:
        return pd.Series(dtype=float)
    h,l,c = x["High"],x["Low"],x["Close"]

    hp = h.eq(h.rolling(zig_hi).max())
    lp = l.eq(l.rolling(zig_lo).min())
    zh = h.where(hp)
    zl = l.where(lp)

    ph = zh.ffill().shift(1)
    pl = zl.ffill().shift(1)
    phc = c.where(hp).ffill().shift(1)
    plc = c.where(lp).ffill().shift(1)

    mm = c * min_move_pct / 100.0
    longc = hp & ph.notna() & phc.notna() & (h > ph) & ((c-phc) >= mm)
    shortc = lp & pl.notna() & plc.notna() & (l < pl) & ((plc-c) >= mm)

    struct = pd.Series(np.nan, index=x.index)
    struct = struct.mask(longc, l).mask(shortc, h)
    struct_avg = na_skip_average(struct, signal_avg_len)

    base = c.rolling(ma_period).mean()
    direct = pd.Series(np.nan, index=x.index)
    direct = direct.mask(c > base, l).mask(c < base, h)
    direct_avg = na_skip_average(direct, signal_avg_len)

    comb = pd.concat([struct_avg,direct_avg],axis=1).mean(axis=1,skipna=True)
    d = (c-comb)/comb.replace(0,np.nan)*100.0
    if normalize_atr:
        ap = atr(x)/c.replace(0,np.nan)*100
        d = d/ap.replace(0,np.nan)
    return d.ffill()

def percent_rank(s, lookback):
    def f(a):
        valid = a[~np.isnan(a)]
        return np.nan if len(valid) < 10 else float(np.mean(valid <= valid[-1]) * 100)
    return s.rolling(lookback, min_periods=10).apply(f, raw=True)

def analyze_symbol(symbol, one_line=0.30, near_zero=0.15, mature_bars=30):
    stock = download(symbol + ".IS")
    if len(stock) < 260:
        return None

    refs = get_reference_data()
    if refs["XU100"].empty or refs["XU030"].empty:
        return None

    cd = distance_series(stock)
    r1 = distance_series(refs["XU100"])
    r2 = distance_series(refs["XU030"])
    idx = cd.index.intersection(r1.index).intersection(r2.index)
    if len(idx) < 220:
        return None
    cd = cd.reindex(idx).ffill()
    r1 = r1.reindex(idx).ffill()
    r2 = r2.reindex(idx).ffill()

    rel = cd-r1
    fx = r1-r2
    zone = pd.Series(np.select(
        [cd>=one_line, cd>0, cd>=-near_zero],
        [4,3,2], default=1
    ), index=idx)

    dv = cd.rolling(20).std()
    sq_rank = percent_rank(dv, 200)
    accum_raw = (
        (sq_rank <= 25)
        & (cd.abs() <= near_zero*2.0)
        & ((rel-rel.shift(10)) > 0)
        & (cd < one_line)
    )

    ages=[]
    a=0
    for v in accum_raw.fillna(False):
        a = a+1 if v else 0
        ages.append(a)
    accum_age = pd.Series(ages,index=idx)
    accum_zone = accum_raw & (accum_age >= 5)
    accum_trigger = accum_zone & ~accum_zone.shift(1).fillna(False)

    fast = cd.rolling(5).mean()
    rising = fast > fast.shift(1)

    mags=[]
    m=0
    for v in (zone==4):
        m = m+1 if v else 0
        mags.append(m)
    momentum_age = pd.Series(mags,index=idx)
    fatigue = momentum_age*100/max(mature_bars,1)
    over = momentum_age >= mature_bars

    cross = (cd>one_line) & (cd.shift(1)<=one_line)
    bars_since=[]
    last=None
    for i,v in enumerate(accum_trigger):
        if v:
            last=i
        bars_since.append(np.nan if last is None else i-last)
    fresh = cross & pd.Series(bars_since,index=idx).le(60)

    # Pine'daki 5/5 sıralamasına karşılık: son 252 bar B&H göreceli liderlik.
    start = stock.index[-252]
    def ret(df):
        s = df.loc[df.index>=start,"Close"].dropna()
        return -999 if len(s)<2 or s.iloc[0]==0 else float(s.iloc[-1]/s.iloc[0]-1)
    sr = ret(stock)
    rr = {k:ret(v) for k,v in refs.items() if not v.empty}
    rot = sum(sr > rr.get(k,999) for k in ("XU100","XU030","XBANK","XUTUM","XBANA"))

    dist_score = int(cd.iloc[-1] > r1.iloc[-1]) + int(cd.iloc[-1] > r2.iloc[-1])
    fusion_full = rot==5 and dist_score==2 and cd.iloc[-1]>=one_line
    fusion_strong = rot>=4 and dist_score==2

    weekly = download(symbol+".IS", period="5y", interval="1wk")
    wd = distance_series(weekly)
    mtf = bool(len(wd) and wd.iloc[-1] > 0)

    if bool(fresh.iloc[-1]):
        phase = "🚀 TAZE KIRILIM"
    elif fusion_full or fusion_strong:
        phase = "🟢 GÜÇLÜ FUSION"
    elif bool(accum_zone.iloc[-1]):
        phase = "🔵 BİRİKİM"
    elif bool(zone.iloc[-1]>=3 and over.iloc[-1] and not rising.iloc[-1]):
        phase = "🟠 YAŞLANMA / DAĞITIM"
    elif bool(zone.iloc[-1]==4 and over.iloc[-1]):
        phase = "🟠 OLGUN TREND"
    elif bool(zone.iloc[-1]>=3 and rising.iloc[-1]):
        phase = "🟢 ATAK"
    elif bool(zone.iloc[-1]>=3):
        phase = "🟡 SOĞUMA"
    else:
        phase = "⚪ İZLEME"

    score = min(100, rot*12 + dist_score*12 + (8 if mtf else 0)
                + (5 if rel.iloc[-1]>0 else 0) + (3 if fx.iloc[-1]<=0 else 0))

    return {
        "symbol":symbol,
        "phase":phase,
        "rotation":f"{rot}/5",
        "distance":f"{dist_score}/2",
        "current_distance":round(float(cd.iloc[-1]),3),
        "relative_strength":round(float(rel.iloc[-1]),3),
        "fx_impact":round(float(fx.iloc[-1]),3),
        "mtf_positive":mtf,
        "fatigue_pct":round(float(fatigue.iloc[-1]),1),
        "score":int(score),
        "close":round(float(stock["Close"].iloc[-1]),2),
    }
