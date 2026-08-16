# -*- coding: utf-8 -*-
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf


def clean(df):
    if df is None or df.empty:
        return pd.DataFrame()

    x = df.copy()

    if isinstance(x.columns, pd.MultiIndex):
        x.columns = [str(c[0]) for c in x.columns]

    need = ["Open", "High", "Low", "Close", "Volume"]
    if not all(c in x.columns for c in need):
        return pd.DataFrame()

    x = x[need].replace([np.inf, -np.inf], np.nan)
    x = x.dropna(subset=["Open", "High", "Low", "Close"]).sort_index()
    x["Volume"] = x["Volume"].fillna(0)
    return x


def download(ticker, period="2y", interval="1d"):
    try:
        return clean(
            yf.download(
                ticker,
                period=period,
                interval=interval,
                auto_adjust=False,
                actions=False,
                progress=False,
                threads=False,
                timeout=25,
            )
        )
    except Exception:
        return pd.DataFrame()


def analyze_continuation(
    symbol,
    consolidation_bars=10,
    max_range_pct=12.0,
    min_volume_ratio=0.80,
):
    df = download(symbol + ".IS")

    if len(df) < 120:
        return None

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()

    prior_high = high.shift(1).rolling(consolidation_bars).max()
    prior_low = low.shift(1).rolling(consolidation_bars).min()

    breakout_level = prior_high.iloc[-1]

    breakout = bool(
        pd.notna(breakout_level)
        and close.iloc[-1] > breakout_level
        and close.iloc[-2] <= prior_high.iloc[-2]
    )

    range_pct = np.nan
    if (
        pd.notna(prior_high.iloc[-1])
        and pd.notna(prior_low.iloc[-1])
        and prior_low.iloc[-1] != 0
    ):
        range_pct = (
            (prior_high.iloc[-1] - prior_low.iloc[-1])
            / prior_low.iloc[-1]
            * 100.0
        )

    consolidation_ok = bool(
        pd.notna(range_pct)
        and range_pct >= 1.0
        and range_pct <= max_range_pct
    )

    trend_ok = bool(
        close.iloc[-1] > ema20.iloc[-1] > ema50.iloc[-1]
        and close.iloc[-1] > close.iloc[-20]
    )

    avg_volume20 = volume.shift(1).rolling(20).mean()
    volume_ratio = np.nan

    if pd.notna(avg_volume20.iloc[-1]) and avg_volume20.iloc[-1] > 0:
        volume_ratio = volume.iloc[-1] / avg_volume20.iloc[-1]

    volume_ok = bool(
        pd.isna(volume_ratio)
        or volume_ratio >= min_volume_ratio
    )

    continuation = bool(
        breakout
        and consolidation_ok
        and trend_ok
        and volume_ok
    )

    score = 0
    if trend_ok:
        score += 35
    if consolidation_ok:
        score += 25
    if breakout:
        score += 25
    if volume_ok:
        score += 15

    return {
        "symbol": symbol,
        "continuation_breakout": continuation,
        "phase": "🟣 DEVAM KIRILIMI" if continuation else "⚪ UYGUN DEĞİL",
        "close": round(float(close.iloc[-1]), 2),
        "breakout_level": round(float(breakout_level), 2) if pd.notna(breakout_level) else np.nan,
        "consolidation_range_pct": round(float(range_pct), 2) if pd.notna(range_pct) else np.nan,
        "volume_ratio": round(float(volume_ratio), 2) if pd.notna(volume_ratio) else np.nan,
        "ema20": round(float(ema20.iloc[-1]), 2),
        "ema50": round(float(ema50.iloc[-1]), 2),
        "score": int(score),
    }
