# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

DB = Path(__file__).with_name("scanner_jobs.sqlite3")
_LOCK = threading.Lock()
_RUNNING = {}


def _conn():
    c = sqlite3.connect(DB, timeout=30)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("""CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY,
        kind TEXT,
        status TEXT,
        created REAL,
        updated REAL,
        current INTEGER,
        total INTEGER,
        current_symbol TEXT,
        results TEXT,
        error TEXT,
        params TEXT,
        raw_total INTEGER,
        filtered_total INTEGER,
        failures TEXT
    )""")

    # v0.5 veritabanından v0.6'ya sorunsuz geçiş.
    cols = {row[1] for row in c.execute("PRAGMA table_info(jobs)").fetchall()}
    if "failures" not in cols:
        c.execute("ALTER TABLE jobs ADD COLUMN failures TEXT DEFAULT '[]'")

    c.commit()
    return c


def latest_job(kind):
    with _conn() as c:
        row = c.execute(
            """SELECT id,kind,status,created,updated,current,total,current_symbol,
                      results,error,params,raw_total,filtered_total,failures
               FROM jobs
               WHERE kind=?
               ORDER BY created DESC
               LIMIT 1""",
            (kind,),
        ).fetchone()

    if not row:
        return None

    keys = [
        "id","kind","status","created","updated","current","total",
        "current_symbol","results","error","params",
        "raw_total","filtered_total","failures"
    ]
    d = dict(zip(keys, row))
    d["results"] = json.loads(d["results"] or "[]")
    d["params"] = json.loads(d["params"] or "{}")
    d["failures"] = json.loads(d["failures"] or "[]")
    return d


def start_job(kind, symbols, params, analyzer, raw_total=None, filtered_total=None):
    with _LOCK:
        existing = latest_job(kind)

        if (
            existing
            and existing["status"] in ("queued", "running")
            and existing["id"] in _RUNNING
        ):
            return existing["id"], False

        jid = uuid.uuid4().hex
        now = time.time()

        with _conn() as c:
            c.execute(
                """INSERT INTO jobs
                   (id,kind,status,created,updated,current,total,current_symbol,
                    results,error,params,raw_total,filtered_total,failures)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    jid, kind, "queued", now, now, 0, len(symbols), "",
                    "[]", "", json.dumps(params),
                    raw_total, filtered_total, "[]",
                ),
            )
            c.commit()

        t = threading.Thread(
            target=_worker,
            args=(jid, symbols, params, analyzer),
            daemon=True,
            name=f"scanner-{kind}-{jid[:6]}",
        )
        _RUNNING[jid] = t
        t.start()
        return jid, True


def _worker(jid, symbols, params, analyzer):
    results = []
    failures = []

    # Yahoo Finance tarafını gereksiz zorlamadan belirgin hız kazanımı.
    max_workers = min(6, max(1, len(symbols)))

    def analyze_one(symbol):
        try:
            row = analyzer(symbol, **params)
            if row:
                return symbol, row, None
            return symbol, None, "Geçerli analiz sonucu üretilemedi"
        except Exception as exc:
            return symbol, None, f"{type(exc).__name__}: {exc}"

    try:
        with _conn() as c:
            c.execute(
                "UPDATE jobs SET status='running',updated=? WHERE id=?",
                (time.time(), jid),
            )
            c.commit()

        completed = 0

        with ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=f"scan-{jid[:6]}",
        ) as executor:
            futures = {
                executor.submit(analyze_one, symbol): symbol
                for symbol in symbols
            }

            for future in as_completed(futures):
                symbol, row, reason = future.result()
                completed += 1

                if row:
                    results.append(row)
                else:
                    failures.append({
                        "symbol": symbol,
                        "reason": reason or "Geçerli analiz sonucu üretilemedi",
                    })

                with _conn() as c:
                    c.execute(
                        """UPDATE jobs
                           SET current=?, current_symbol=?, results=?, failures=?, updated=?
                           WHERE id=?""",
                        (
                            completed,
                            symbol,
                            json.dumps(results, ensure_ascii=False, default=str),
                            json.dumps(failures, ensure_ascii=False, default=str),
                            time.time(),
                            jid,
                        ),
                    )
                    c.commit()

        with _conn() as c:
            c.execute(
                """UPDATE jobs
                   SET status='done', results=?, failures=?, updated=?
                   WHERE id=?""",
                (
                    json.dumps(results, ensure_ascii=False, default=str),
                    json.dumps(failures, ensure_ascii=False, default=str),
                    time.time(),
                    jid,
                ),
            )
            c.commit()

    except Exception as exc:
        with _conn() as c:
            c.execute(
                "UPDATE jobs SET status='error',error=?,updated=? WHERE id=?",
                (str(exc), time.time(), jid),
            )
            c.commit()

    finally:
        with _LOCK:
            _RUNNING.pop(jid, None)
