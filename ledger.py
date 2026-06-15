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
    source TEXT,                    -- model that produced it, e.g. "groq:..." (for second-opinion tracking)
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
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opened TEXT NOT NULL,
    symbol TEXT NOT NULL,
    shares INTEGER NOT NULL,
    entry_price REAL NOT NULL,
    stop_price REAL,
    account_size REAL,              -- book size at open, for exposure %
    thesis_id INTEGER,              -- link back to the reasoning
    status TEXT DEFAULT 'OPEN',     -- OPEN | CLOSED
    closed TEXT,
    exit_price REAL,
    realized_pnl REAL,              -- rupees, set on close
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
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        """Idempotently add columns introduced after a DB was first created
        (CREATE TABLE IF NOT EXISTS won't alter an existing table)."""
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(theses)")}
        if "source" not in cols:
            self.conn.execute("ALTER TABLE theses ADD COLUMN source TEXT")

    def record(self, t: Thesis) -> int:
        cur = self.conn.execute(
            """INSERT INTO theses (created, symbol, name, catalyst, conviction,
               suggested_action, reference_price, credibility_flag, narrated,
               source, payload)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (t.as_of, t.symbol, t.name, t.catalyst, t.conviction,
             t.suggested_action, t.reference_price, t.credibility_flag,
             int(t.narrated), t.source, t.to_json()))
        self.conn.commit()
        return cur.lastrowid

    def open_theses(self) -> list[sqlite3.Row]:
        return list(self.conn.execute(
            "SELECT * FROM theses WHERE status='OPEN' ORDER BY created DESC"))

    def count_created_on(self, day: str) -> int:
        """How many theses were logged on a given date (YYYY-MM-DD) — used by the
        max-trades-per-day circuit breaker."""
        return self.conn.execute(
            "SELECT COUNT(*) FROM theses WHERE created=?", (day,)).fetchone()[0]

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
            SELECT t.conviction, t.source, g.verdict, g.pnl_pct
            FROM grades g JOIN theses t ON t.id = g.thesis_id"""))
        if not rows:
            return {"graded": 0, "note": "no graded theses yet — come back after calls mature."}
        pnls = [r["pnl_pct"] for r in rows if r["pnl_pct"] is not None]
        right = sum(1 for r in rows if r["verdict"] == "RIGHT")
        by_conv: dict[str, list[float]] = {}
        # Per-model scoreboard: which LLM actually makes the better calls? Keyed by
        # short source ("groq"/"gemini"/"offline"); tracks hit rate and avg P&L.
        by_source: dict[str, dict] = {}
        for r in rows:
            if r["pnl_pct"] is not None:
                by_conv.setdefault(r["conviction"], []).append(r["pnl_pct"])
            src = (r["source"] or "unknown").split(":", 1)[0]
            s = by_source.setdefault(src, {"n": 0, "right": 0, "pnls": []})
            s["n"] += 1
            s["right"] += 1 if r["verdict"] == "RIGHT" else 0
            if r["pnl_pct"] is not None:
                s["pnls"].append(r["pnl_pct"])
        return {
            "graded": len(rows),
            "hit_rate": round(right / len(rows), 2),
            "avg_pnl_pct": round(sum(pnls) / len(pnls), 4) if pnls else None,
            "avg_pnl_by_conviction": {
                k: round(sum(v) / len(v), 4) for k, v in by_conv.items()},
            "by_source": {
                src: {"graded": s["n"],
                      "hit_rate": round(s["right"] / s["n"], 2),
                      "avg_pnl_pct": round(sum(s["pnls"]) / len(s["pnls"]), 4)
                      if s["pnls"] else None}
                for src, s in by_source.items()},
        }

    # ------------------------------------------------------------------
    # Positions — what you actually took (real exposure, not a thesis count)
    # ------------------------------------------------------------------

    def open_position(self, symbol: str, shares: int, entry_price: float,
                      stop_price: float | None = None, account_size: float | None = None,
                      thesis_id: int | None = None, note: str = "",
                      opened: str | None = None) -> int:
        cur = self.conn.execute(
            """INSERT INTO positions (opened, symbol, shares, entry_price,
               stop_price, account_size, thesis_id, note)
               VALUES (?,?,?,?,?,?,?,?)""",
            (opened or date.today().isoformat(), symbol.upper(), int(shares),
             entry_price, stop_price, account_size, thesis_id, note))
        self.conn.commit()
        return cur.lastrowid

    def open_positions(self) -> list[sqlite3.Row]:
        return list(self.conn.execute(
            "SELECT * FROM positions WHERE status='OPEN' ORDER BY opened DESC"))

    def get_position(self, pos_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM positions WHERE id=?", (pos_id,)).fetchone()

    def positions_opened_on(self, day: str) -> int:
        """Open positions taken on a given date — backs the trades-per-day cap."""
        return self.conn.execute(
            "SELECT COUNT(*) FROM positions WHERE opened=?", (day,)).fetchone()[0]

    def close_position(self, pos_id: int, exit_price: float, note: str = "") -> dict:
        row = self.get_position(pos_id)
        if not row:
            raise ValueError(f"position {pos_id} not found")
        if row["status"] != "OPEN":
            raise ValueError(f"position {pos_id} is already {row['status']}")
        realized = (exit_price - row["entry_price"]) * row["shares"]
        self.conn.execute(
            """UPDATE positions SET status='CLOSED', closed=?, exit_price=?,
               realized_pnl=?, note=COALESCE(NULLIF(?, ''), note) WHERE id=?""",
            (date.today().isoformat(), exit_price, realized, note, pos_id))
        self.conn.commit()
        cost = row["entry_price"] * row["shares"]
        return {"position_id": pos_id, "symbol": row["symbol"],
                "realized_pnl": round(realized, 2),
                "pnl_pct": (realized / cost) if cost else None}

    def exposure(self) -> dict:
        """Aggregate open exposure: rupees invested, capital at risk (portfolio
        'heat'), and the open count. A position with no stop counts its FULL value
        as at-risk — no defined exit means all of it is exposed."""
        rows = self.open_positions()
        invested = sum(r["shares"] * r["entry_price"] for r in rows)
        at_risk = 0.0
        for r in rows:
            value = r["shares"] * r["entry_price"]
            if r["stop_price"] is None:
                at_risk += value
            else:
                at_risk += r["shares"] * max(0.0, r["entry_price"] - r["stop_price"])
        return {"open": len(rows), "invested": round(invested, 2),
                "at_risk": round(at_risk, 2), "positions": rows}

    def close(self):
        self.conn.close()
