"""
SQLite ledger — the forward paper-tracking backbone.

Because honest backtesting of fundamentals is blocked by the point-in-time data
trap, this is where the real validation happens: every call is logged WITH its
full reasoning and a date, then graded as reality plays out. Over time this tells
you whether your model actually works — the thing a flattering backtest can't.
"""
from __future__ import annotations
import sqlite3
import json
from datetime import date
from dataclasses import asdict

import config
from thesis import Thesis

_SCHEMA = """
CREATE TABLE IF NOT EXISTS theses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created TEXT NOT NULL,
    symbol TEXT NOT NULL,
    name TEXT,
    catalyst TEXT,
    conviction TEXT,
    suggested_action TEXT,
    reference_price REAL,
    credibility_flag TEXT,
    narrated INTEGER,
    payload TEXT NOT NULL,          -- full thesis JSON
    status TEXT DEFAULT 'OPEN'      -- OPEN | GRADED | CLOSED
);
CREATE TABLE IF NOT EXISTS grades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thesis_id INTEGER NOT NULL,
    graded TEXT NOT NULL,
    price_then REAL,
    pnl_pct REAL,
    verdict TEXT,                   -- RIGHT | WRONG | EARLY | NOISE
    note TEXT,
    FOREIGN KEY (thesis_id) REFERENCES theses(id)
);
"""


class Ledger:
    def __init__(self, db_path: str | None = None):
        self.path = db_path or config.DB_PATH
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def record(self, t: Thesis) -> int:
        cur = self.conn.execute(
            """INSERT INTO theses (created, symbol, name, catalyst, conviction,
               suggested_action, reference_price, credibility_flag, narrated, payload)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (t.as_of, t.symbol, t.name, t.catalyst, t.conviction,
             t.suggested_action, t.reference_price, t.credibility_flag,
             int(t.narrated), t.to_json()))
        self.conn.commit()
        return cur.lastrowid

    def open_theses(self) -> list[sqlite3.Row]:
        return list(self.conn.execute(
            "SELECT * FROM theses WHERE status='OPEN' ORDER BY created DESC"))

    def get(self, thesis_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM theses WHERE id=?", (thesis_id,)).fetchone()

    def grade(self, thesis_id: int, price_now: float, verdict: str,
              note: str = "") -> dict:
        row = self.get(thesis_id)
        if not row:
            raise ValueError(f"thesis {thesis_id} not found")
        ref = row["reference_price"]
        pnl = ((price_now - ref) / ref) if (ref and ref != 0) else None
        self.conn.execute(
            """INSERT INTO grades (thesis_id, graded, price_then, pnl_pct, verdict, note)
               VALUES (?,?,?,?,?,?)""",
            (thesis_id, date.today().isoformat(), price_now,
             pnl, verdict.upper(), note))
        self.conn.execute("UPDATE theses SET status='GRADED' WHERE id=?", (thesis_id,))
        self.conn.commit()
        return {"thesis_id": thesis_id, "pnl_pct": pnl, "verdict": verdict.upper()}

    def performance(self) -> dict:
        rows = list(self.conn.execute("""
            SELECT t.conviction, g.verdict, g.pnl_pct
            FROM grades g JOIN theses t ON t.id = g.thesis_id"""))
        if not rows:
            return {"graded": 0, "note": "no graded theses yet — come back after calls mature."}
        pnls = [r["pnl_pct"] for r in rows if r["pnl_pct"] is not None]
        right = sum(1 for r in rows if r["verdict"] == "RIGHT")
        by_conv: dict[str, list[float]] = {}
        for r in rows:
            if r["pnl_pct"] is not None:
                by_conv.setdefault(r["conviction"], []).append(r["pnl_pct"])
        return {
            "graded": len(rows),
            "hit_rate": round(right / len(rows), 2),
            "avg_pnl_pct": round(sum(pnls) / len(pnls), 4) if pnls else None,
            "avg_pnl_by_conviction": {
                k: round(sum(v) / len(v), 4) for k, v in by_conv.items()},
        }

    def close(self):
        self.conn.close()
