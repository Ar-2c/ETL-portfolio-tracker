# app/services/trades.py
from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime
from typing import Optional
import pandas as pd

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

def _validate_inputs(user: str, ticker: str, side: str, qty: float, price: float, ts: str, fee: float) -> tuple[str, str]:
    assert isinstance(user, str) and user.strip(), "user måste vara en icke-tom sträng"
    assert isinstance(ticker, str) and ticker.strip(), "ticker måste vara en icke-tom sträng"
    side_norm = (side or "").strip().upper()
    assert side_norm in {"BUY", "SELL"}, "side måste vara 'BUY' eller 'SELL'"
    assert qty > 0, "qty måste vara > 0"
    assert price > 0, "price måste vara > 0"
    assert fee >= 0, "fee måste vara ≥ 0"
    try:
        datetime.fromisoformat(ts)
    except Exception as e:
        raise AssertionError(f"ts måste vara ISO8601 (YYYY-MM-DD). Fick: {ts!r}") from e
    return user.strip(), side_norm

def current_qty(conn: sqlite3.Connection, user: str, ticker: str) -> float:
    cur = conn.execute(
        """
        SELECT COALESCE(SUM(CASE WHEN side='BUY' THEN qty ELSE -qty END), 0.0)
        FROM trades
        WHERE user = ? AND ticker = ?
        """,
        (user, ticker),
    )
    (qty_now,) = cur.fetchone()
    return float(qty_now or 0.0)

def record_trade(
    conn: sqlite3.Connection,
    user: str,
    ticker: str,
    side: str,
    qty: float,
    price: float,
    ts: str,
    fee: float = 0.0,
) -> int:
    user, side_norm = _validate_inputs(user, ticker, side, qty, price, ts, fee)
    if side_norm == "SELL":
        qty_now = current_qty(conn, user, ticker)
        if qty > qty_now + 1e-12:
            raise ValueError("Kan inte sälja fler än du äger")

    cur = conn.execute(
        """
        INSERT INTO trades(user, ticker, ts, side, qty, price, fee)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (user, ticker, ts, side_norm, float(qty), float(price), float(fee)),
    )
    conn.commit()
    return int(cur.lastrowid)

def list_trades(conn: sqlite3.Connection, user: str, ticker: Optional[str] = None) -> pd.DataFrame:
    sql = """
        SELECT id, user, ticker, ts, side, qty, price, fee
        FROM trades
        WHERE user = ?
    """
    params = [user]
    if ticker:
        sql += " AND ticker = ?"
        params.append(ticker)
    sql += " ORDER BY ts, id"

    df = pd.read_sql_query(sql, conn, params=params)
    if not df.empty:
        df = df.astype({
            "id": "int64", "user": "string", "ticker": "string", "ts": "string",
            "side": "string", "qty": "float64", "price": "float64", "fee": "float64",
        })
    return df

#  Testkörning 
if __name__ == "__main__":
    print("Startar trades self-test…")
    from app.services import db as _db
    conn = _db.get_conn()
    _db.ensure_schema(conn)

    _user = "demo"
    _ticker = "INVE-B.ST"
    _today = date.today().isoformat()

    print("1) Köp 10 @ 200")
    record_trade(conn, _user, _ticker, "BUY", 10, 200.0, _today)

    print("2) Försök sälja 15 @ 210 (ska ge fel):")
    try:
        record_trade(conn, _user, _ticker, "SELL", 15, 210.0, _today)
    except ValueError as e:
        print("   Förväntat fel:", e)

    print("3) Sälj 5 @ 210 (ska funka)")
    record_trade(conn, _user, _ticker, "SELL", 5, 210.0, _today)

    print("4) Historik:")
    print(list_trades(conn, _user))

    print("5) Current qty:", current_qty(conn, _user, _ticker))
    print("Klart.")

