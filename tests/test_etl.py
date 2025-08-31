import sys, sqlite3
from pathlib import Path
import pandas as pd

# gör src importbar utan paketering
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from etl import extract, load

def test_extract_shape():
    df = extract(tickers=("AAPL",), period="5d", interval="1d")
    assert set(df.columns) == {"ts","ticker","close"}
    assert not df.empty

def test_load_inserts_into_temp_db(tmp_path):
    db = tmp_path / "test.db"
    row = pd.DataFrame([{"ts":"2025-08-30","ticker":"TEST","close":123.45}])
    load(row, db_path=db)
    with sqlite3.connect(db) as conn:
        cur = conn.cursor()
        cur.execute("SELECT ticker, close FROM prices WHERE ticker='TEST'")
        assert cur.fetchone() == ("TEST", 123.45)