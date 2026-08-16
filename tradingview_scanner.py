# -*- coding: utf-8 -*-
from __future__ import annotations
import requests

URL = "https://scanner.tradingview.com/turkey/scan"
COLS = ["name", "close", "change", "volume", "relative_volume_10d_calc", "RSI", "ADX", "average_volume_30d_calc"]
BASE = [
    {"left": "is_primary", "operation": "equal", "right": True},
    {"left": "typespecs", "operation": "has", "right": ["common"]},
]
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/plain,*/*", "Content-Type": "application/json"}


def _scan(filters, max_rows=2000, timeout=20):
    payload = {
        "symbols": {"query": {"types": []}, "tickers": []},
        "options": {"lang": "tr"},
        "columns": COLS,
        "sort": {"sortBy": "relative_volume_10d_calc", "sortOrder": "desc"},
        "range": [0, int(max_rows)],
        "filter": filters,
    }
    r = requests.post(URL, json=payload, timeout=timeout, headers=HEADERS)
    r.raise_for_status()
    return r.json()


def fetch_bist_universe(min_avg_volume=250000, max_rows=2000, timeout=20, with_counts=False):
    # Ham sayı: yalnız BIST birincil/common pay evreni. Hacim/fiyat filtresi yok.
    raw_json = _scan(BASE, max_rows=max_rows, timeout=timeout)
    raw_total = int(raw_json.get("totalCount", len(raw_json.get("data", []))))

    filtered_json = _scan(BASE + [
        {"left": "close", "operation": "greater", "right": 1},
        {"left": "average_volume_30d_calc", "operation": "greater", "right": float(min_avg_volume)},
    ], max_rows=max_rows, timeout=timeout)
    filtered_total = int(filtered_json.get("totalCount", len(filtered_json.get("data", []))))

    rows = []
    for item in filtered_json.get("data", []):
        sym = str(item.get("s", "")).replace("BIST:", "").strip().upper()
        d = list(item.get("d", []))
        while len(d) < len(COLS):
            d.append(None)
        if sym:
            rows.append({
                "symbol": sym, "name": d[0], "close": d[1], "change": d[2], "volume": d[3],
                "relative_volume": d[4], "rsi": d[5], "adx": d[6], "average_volume_30d": d[7],
            })
    if with_counts:
        return rows, raw_total, filtered_total
    return rows
