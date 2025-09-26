import sqlite3
import pandas as pd
from app.config import START_CASH

def positions(conn: sqlite3.Connection, user: str) -> pd.DataFrame:
    # qty per ticker (BUY - SELL)
    q = """
    SELECT ticker,
           SUM(CASE WHEN side='BUY' THEN qty ELSE -qty END) AS qty
    FROM trades
    WHERE user=?
    GROUP BY ticker
    HAVING qty <> 0
    """
    df = pd.read_sql_query(q, conn, params=(user,))
    return df

def running_avg_costs(conn: sqlite3.Connection, user: str) -> pd.DataFrame:
    q = """
    SELECT ticker, ts, id, side, qty, price, fee
    FROM trades
    WHERE user=?
    ORDER BY ticker, ts, id
    """
    rows = conn.execute(q, (user,)).fetchall()
    state = {}
    for ticker, ts, _id, side, qty, price, fee in rows:
        qty = float(qty); price = float(price); fee = float(fee)
        q0, avg0 = state.get(ticker, (0.0, 0.0))
        if side == "BUY":
            cost_before = q0 * avg0
            cost_added  = qty * price + fee
            q1 = q0 + qty
            avg1 = (cost_before + cost_added) / q1 if q1 > 0 else 0.0
            state[ticker] = (q1, avg1)
        else:  # SELL
            sell_qty = min(qty, q0)
            state[ticker] = (q0 - sell_qty, avg0)
    # Bygg DataFrame
    out = [{"ticker": t, "avg_buy_price": avg} for t, (q, avg) in state.items() if q > 0]
    return pd.DataFrame(out)

def latest_prices(conn: sqlite3.Connection, tickers: list[str]) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame(columns=["ticker","last_close","last_ts"])
    placeholders = ",".join("?"*len(tickers))
    q = f"""
    WITH latest AS (
      SELECT p.ticker, MAX(p.ts) AS m_ts
      FROM prices p
      WHERE p.ticker IN ({placeholders})
      GROUP BY p.ticker
    )
    SELECT p.ticker, p.close AS last_close, p.ts AS last_ts
    FROM prices p
    JOIN latest l
      ON l.ticker=p.ticker AND l.m_ts=p.ts
    """
    return pd.read_sql_query(q, conn, params=tickers)

def cash_balance(conn: sqlite3.Connection, user: str) -> float:
    # START_CASH + (sum SELL - sum BUY - fees)
    q = """
    SELECT
      COALESCE(SUM(CASE WHEN side='SELL' THEN qty*price ELSE 0 END),0)
    - COALESCE(SUM(CASE WHEN side='BUY'  THEN qty*price ELSE 0 END),0)
    - COALESCE(SUM(fee),0)
    FROM trades
    WHERE user=?
    """
    (delta_cash,) = conn.execute(q, (user,)).fetchone()
    return float(START_CASH + (delta_cash or 0.0))

def realized_pnl_avgcost(conn: sqlite3.Connection, user: str) -> float:
    """
    Beräkna realiserad P&L med löpande genomsnittlig kostnad:
    - sortera trades per ticker efter ts,id
    - håll current_qty och avg_cost
    - vid SELL: realized += (sell_price - avg_cost)*sell_qty; qty minskar
    - vid BUY: uppdatera avg_cost = (qty*avg_cost + buy_qty*buy_price + fee) / (qty+buy_qty)
    """
    q = """
    SELECT ticker, ts, id, side, qty, price, fee
    FROM trades
    WHERE user=?
    ORDER BY ticker, ts, id
    """
    import math
    rows = conn.execute(q, (user,)).fetchall()
    realized = 0.0
    state = {}  # ticker -> (qty, avg_cost)

    for ticker, ts, _id, side, qty, price, fee in rows:
        qty = float(qty); price = float(price); fee = float(fee)
        q0, c0 = state.get(ticker, (0.0, 0.0))
        if side == "BUY":
            # ny vägd genomsnittskostnad
            cost_before = q0 * c0
            cost_added  = qty * price + fee
            q1 = q0 + qty
            c1 = (cost_before + cost_added) / q1 if q1 > 0 else 0.0
            state[ticker] = (q1, c1)
        else:  
            if q0 <= 0:
                continue
            sell_qty = min(qty, q0)
            realized += (price - c0) * sell_qty  
            state[ticker] = (q0 - sell_qty, c0)

    return float(realized)

def overview(conn: sqlite3.Connection, user: str) -> pd.DataFrame:
    pos  = positions(conn, user)
    if pos.empty:
        return pd.DataFrame(columns=["ticker","qty","avg_buy_price","last_close","market_value","unreal_pnl"])

    costs = running_avg_costs(conn, user)
    last  = latest_prices(conn, pos["ticker"].tolist())

    df = (pos.merge(costs, on="ticker", how="left")
             .merge(last, on="ticker", how="left")
             .rename(columns={"avg_cost":"avg_buy_price"}))

    df["market_value"] = df["qty"] * df["last_close"]
    df["unreal_pnl"]   = (df["last_close"] - df["avg_buy_price"]) * df["qty"]
    cols = ["ticker","qty","avg_buy_price","last_close","market_value","unreal_pnl"]
    return df[cols].sort_values("ticker").reset_index(drop=True)

# ---------- Testkörning ----------
if __name__ == "__main__":
    from app.services import db, trades
    from datetime import date
    
    conn = db.get_conn()
    db.ensure_schema(conn)

    conn.execute("DELETE FROM trades WHERE user=? AND ticker=?", ("demo", "INVE-B.ST"))
    conn.commit()

    user = "demo"
    ticker = "INVE-B.ST"
    today = date.today().isoformat()

    print("Startar portfolio self-test…")

    # Lägger till några trades för demo
    print("1) Köp 10 @ 200")
    trades.record_trade(conn, user, ticker, "BUY", 10, 200.0, today)

    print("2) Sälj 4 @ 220")
    trades.record_trade(conn, user, ticker, "SELL", 4, 220.0, today)

    print("3) Köp 6 @ 210")
    trades.record_trade(conn, user, ticker, "BUY", 6, 210.0, today)

    # Visa översikt
    print("\n--- Overview ---")
    print(overview(conn, user))

    # Visa cash balance
    print("\nCash balance:", cash_balance(conn, user))

    # Visa realiserad P&L
    print("Realized P&L:", realized_pnl_avgcost(conn, user))

    print("Klart.")