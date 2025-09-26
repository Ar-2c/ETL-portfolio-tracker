from datetime import timedelta, date
import pandas as pd
import yfinance as yf
from app.services import db as dbsvc


def backfill(tickers, start_iso: str, end_iso: str):
    conn = dbsvc.get_conn()
    dbsvc.ensure_schema(conn)

    inserted = 0
    for ticker in tickers:
        df = yf.download(ticker, start=start_iso, end=end_iso, progress=False)

        if df is None or df.empty:
            print(f"{ticker}: inga data.")
            continue

        # Välj Close i första hand, annars Adj Close
        if "Close" in df.columns:
            s = df["Close"]
        elif "Adj Close" in df.columns:
            s = df["Adj Close"]
        else:
            print(f"{ticker}: varken Close eller Adj Close hittades.")
            continue

        # Ta ned till en ren tabell med ts/close och normalisera datum
        tmp = s.dropna().reset_index()        # index -> kolumn
        tmp.columns = ["ts", "close"]         # säkerställ namn
        tmp["ts"] = pd.to_datetime(tmp["ts"], errors="coerce")  # safe parse
        tmp = tmp.dropna(subset=["ts", "close"])
        tmp["ts"] = tmp["ts"].dt.strftime("%Y-%m-%d")           # ISO-datum

        if tmp.empty:
            print(f"{ticker}: inga datapunkter efter rensning.")
            continue

        rows = [(ticker, ts, float(v)) for ts, v in zip(tmp["ts"], tmp["close"])]

        conn.executemany(
            "INSERT OR REPLACE INTO prices(ticker, ts, close) VALUES (?,?,?)",
            rows,
        )
        conn.commit()
        print(f"{ticker}: {len(rows)} rader infogade/uppdaterade.")
        inserted += len(rows)

    print(f"Klart. Totalt {inserted} rader.")


if __name__ == "__main__":
    conn = dbsvc.get_conn()
    dbsvc.ensure_schema(conn)

    # Hämta tickers från trades + jämförelseindex
    tickers = pd.read_sql_query(
        "SELECT DISTINCT ticker FROM trades", conn
    )["ticker"].tolist()
    tickers.append("^OMXSPI")
    tickers = sorted(set(tickers))

    end = date.today().isoformat()
    start = (date.today() - timedelta(days=365)).isoformat()

    backfill(tickers, start, end)


