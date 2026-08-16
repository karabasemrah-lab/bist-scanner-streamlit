# -*- coding: utf-8 -*-
from __future__ import annotations
import requests

URL = "https://scanner.tradingview.com/turkey/scan"
COLS = [
    "name", "close", "change", "volume",
    "relative_volume_10d_calc", "RSI", "ADX",
    "average_volume_30d_calc",
]
BASE = [
    {"left": "is_primary", "operation": "equal", "right": True},
    {"left": "typespecs", "operation": "has", "right": ["common"]},
]


def fetch_bist_universe(min_avg_volume=250000, max_rows=1000, timeout=20):
    payload = {
        "symbols": {"query": {"types": []}, "tickers": []},
        "options": {"lang": "tr"},
        "columns": COLS,
        "sort": {"sortBy": "relative_volume_10d_calc", "sortOrder": "desc"},
        "range": [0, int(max_rows)],
        "filter": BASE + [
            {"left": "close", "operation": "greater", "right": 1},
            {"left": "average_volume_30d_calc", "operation": "greater", "right": float(min_avg_volume)},
        ],
    }

    r = requests.post(
        URL,
        json=payload,
        timeout=timeout,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json,text/plain,*/*",
            "Content-Type": "application/json",
        },
    )
    r.raise_for_status()

    rows = []
    for item in r.json().get("data", []):
        sym = str(item.get("s", "")).replace("BIST:", "").strip().upper()
        d = list(item.get("d", []))
        while len(d) < len(COLS):
            d.append(None)

        if sym:
            rows.append({
                "symbol": sym,
                "name": d[0],
                "close": d[1],
                "change": d[2],
                "volume": d[3],
                "relative_volume": d[4],
                "rsi": d[5],
                "adx": d[6],
                "average_volume_30d": d[7],
            })

    return rows
