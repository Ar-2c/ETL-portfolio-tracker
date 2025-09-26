from __future__ import annotations
from pathlib import Path
from typing import Union, Iterable, Optional
import re
import pandas as pd

# Primära kolumnnamn som appen använder
REQUIRED_COLS = ["yf_symbol", "name_display", "segment"]

# Tillåtna alias (om CSV råkar heta annorlunda)
ALIASES = {
    "ticker": "yf_symbol",
    "name": "name_display",
    "list": "segment",
}

def _normalize_text(s: str) -> str:
    if s is None:
        return ""
    s = str(s)
    s = s.replace("(publ)", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def load_universe(path: Union[Path, str]) -> pd.DataFrame:
    """
    Läser CSV, mappar ev. alias-kolumner, säkerställer str-datatyp,
    och bygger en 'search_blob' som vi söker i.
    """
    csv_path = Path(path)
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False, sep=None, engine="python", encoding="utf-8-sig")

    # Mappar alias → standardnamn
    cols_lower = {c.lower(): c for c in df.columns}
    for alias, target in ALIASES.items():
        if alias in cols_lower and target not in df.columns:
            df = df.rename(columns={cols_lower[alias]: target})

    # Säkerställer nödvändiga kolumner
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Saknar kolumner i {csv_path}: {missing}. Hittade: {list(df.columns)}")

    # Trim och typ
    for col in REQUIRED_COLS:
        df[col] = df[col].astype(str).map(_normalize_text)

    # search_blob: (gemener) av namn + ticker + variant utan .ST. Detta gör att man kan hitta samma aktie med olika inmatningar. 
    # Detta är hela anledningen till att jag tog in CSV-filen för universe så att man inte ska vara tvungen att söka på specifika Yahoo-tickers.
    base = df["yf_symbol"].str.replace(".ST", "", regex=False)
    df["search_blob"] = (
        (df["name_display"] + " " + df["yf_symbol"] + " " + base)
        .str.lower()
    )

    # Praktisk visningssträng till UI (kan användas i Streamlit format_func)
    df["display"] = df["name_display"] + " — " + df["yf_symbol"]

    # Behåller ordning & relevanta kolumner
    return df[REQUIRED_COLS + ["search_blob", "display"]].copy()

def search_by_name(
    df: pd.DataFrame,
    query: str,
    segments: Optional[Iterable[str]] = None,
    limit: Optional[int] = 50,
) -> pd.DataFrame:
    """
    Sök i namn + ticker (case-insensitive).
    Sorterar så att namn som *börjar* med sökordet kommer överst.
    """
    if not query:
        out = df.copy()
    else:
        q = _normalize_text(query).lower()
        mask = df["search_blob"].str.contains(q, na=False)
        out = df.loc[mask].copy()

        # enkel relevanssortering:
        startswith_name = df["name_display"].str.lower().str.startswith(q)
        startswith_ticker = df["yf_symbol"].str.lower().str.startswith(q)
        contains_name_pos = df["name_display"].str.lower().str.find(q)

        out = out.assign(
            _rank_name_starts=startswith_name.astype(int),
            _rank_ticker_starts=startswith_ticker.astype(int),
            _rank_pos=contains_name_pos.where(contains_name_pos >= 0, 9999),
        ).sort_values(
            by=["_rank_name_starts", "_rank_ticker_starts", "_rank_pos", "name_display"],
            ascending=[False, False, True, True],
        ).drop(columns=["_rank_name_starts", "_rank_ticker_starts", "_rank_pos"])

    # Segmentfilter om angivet
    if segments:
        segset = {s.lower() for s in segments}
        out = out[out["segment"].str.lower().isin(segset)]

    # Begränsa antal träffar
    if limit is not None:
        out = out.head(limit)

    return out.reset_index(drop=True)

if __name__ == "__main__":
    # Snabbtest
    df = load_universe("data/omx_securities.csv")
    print("Antal papper i univers:", len(df))

    for q in ["investor", "eric", "cellulosa", "SCA", "INVE-B", "VOLV"]:
        res = search_by_name(df, q, limit=5)
        print(f"\nSök '{q}':")
        print(res[["display", "segment"]])