import logging
import sqlite3
from pathlib import Path

# Projektrot: ETL-finance/
ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "data.db"

# Enkel logger
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Öppnar SQLite-anslutning mot %s", DB_PATH)

    # Viktigt: tillåt användning från flera trådar i Streamlit
    conn = sqlite3.connect(
        DB_PATH,
        check_same_thread=False,  # <-- fixen
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
    )

    # Rekommenderade pragman för läs/skriv och concurrency
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")   # bättre parallella reads
    conn.execute("PRAGMA synchronous = NORMAL;") # snabbare med WAL

    return conn

def ensure_schema(conn: sqlite3.Connection) -> None:
    """
    Skapar nödvändiga tabeller om de saknas.
    Lämnar eventuell befintlig tabell 'prices' orörd.
    """
    logger.info("Säkerställer schema (trades, watchlist).")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS trades(
          id INTEGER PRIMARY KEY,
          user TEXT NOT NULL,
          ticker TEXT NOT NULL,
          ts TEXT NOT NULL,
          side TEXT NOT NULL,      -- BUY/SELL
          qty REAL NOT NULL,
          price REAL NOT NULL,
          fee REAL DEFAULT 0.0
        );

        CREATE TABLE IF NOT EXISTS watchlist(
          id INTEGER PRIMARY KEY,
          user TEXT NOT NULL,
          ticker TEXT NOT NULL,
          UNIQUE(user, ticker)
        );
        """
    )
    conn.commit()
    logger.info("Schema klart.")

# Testsektion (kör bara om man kör filen direkt)
if __name__ == "__main__":
    conn = get_conn()
    ensure_schema(conn)

    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    print("Tabeller i databasen:", [r[0] for r in cur.fetchall()])