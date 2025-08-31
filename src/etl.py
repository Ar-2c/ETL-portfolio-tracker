import logging
import sqlite3
from pathlib import Path
import pandas as pd
import yfinance as yf

# Paths
ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "data.db"
LOG_PATH = ROOT / "logs" / "etl.log"
DB_PATH.parent.mkdir(exist_ok=True)
LOG_PATH.parent.mkdir(exist_ok=True)

# Logger
log = logging.getLogger("etl")
log.setLevel(logging.INFO)
if not log.handlers:
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    fh = logging.FileHandler(LOG_PATH, encoding="utf-8"); fh.setFormatter(fmt)
    sh = logging.StreamHandler();                         sh.setFormatter(fmt)
    log.addHandler(fh); log.addHandler(sh)

# Extract + transform
def extract(tickers=("AAPL","INVE-B.ST"), period="5d", interval="1d") -> pd.DataFrame: # Fetching for Apple and Investor AB.
    log.info(f"Hämtar data: {tickers}, period={period}, interval={interval}")
    df = yf.download(tickers, period=period, interval=interval,
                     progress=False, auto_adjust=False)
    if df.empty:
        return pd.DataFrame(columns=["ts","ticker","close"])

    if isinstance(df.columns, pd.MultiIndex):
        col = "Adj Close" if "Adj Close" in df.columns.levels[0] else "Close"
        tidy = (df[col].reset_index()
                  .melt(id_vars="Date", var_name="ticker", value_name="close")
                  .rename(columns={"Date":"ts"}))
    else:
        col = "Adj Close" if "Adj Close" in df.columns else "Close"
        tidy = (df[[col]].rename(columns={col:"close"})
                  .reset_index().assign(ticker=tickers[0])
                  .rename(columns={"Date":"ts"}))

    tidy["ts"] = pd.to_datetime(tidy["ts"]).dt.tz_localize(None).astype(str)
    return tidy.dropna(subset=["close"])[["ts","ticker","close"]]

# Load 
def load(df: pd.DataFrame, db_path: Path | str = DB_PATH) -> int:
    if df.empty:
        return 0
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS prices(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ticker TEXT NOT NULL,
              ts TEXT NOT NULL,
              close REAL NOT NULL
            )
        """)
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_prices ON prices(ticker, ts)")
        cur.executemany(
            "INSERT OR IGNORE INTO prices(ticker, ts, close) VALUES (?,?,?)",
            list(df[["ticker","ts","close"]].itertuples(index=False, name=None))
        )
        conn.commit()
        return cur.rowcount

def main():
    df = extract()
    tried = load(df)
    log.info(f"Inserted {len(df)} rows (duplicates ignored). Tried inserts: {tried}")

if __name__ == "__main__":
    main()