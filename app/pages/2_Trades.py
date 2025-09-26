# app/pages/2_Trades.py
from __future__ import annotations

from datetime import date
from typing import Optional

import pandas as pd
import streamlit as st
import yfinance as yf

import app.services.trades as trades_svc
import app.services.portfolio as portfolio
import app.services.universe as universe
import app.services.db as dbsvc

PAGE_TITLE = "Trades"

@st.cache_resource(show_spinner=False)
def get_conn():
    conn = dbsvc.get_conn()
    dbsvc.ensure_schema(conn)
    return conn

@st.cache_data(show_spinner=False, ttl=300)
def yf_last_close(ticker: str) -> Optional[dict]:
    """
    Returnerar {"last_close": float, "ts": "YYYY-MM-DD"} eller None.
    Robust mot helger/helgdagar och tomma svar från yfinance.
    """
    try:
        tk = yf.Ticker(ticker)
        df = tk.history(period="14d", interval="1d", auto_adjust=False)
        if df is None or df.empty:
            # Andra försök via download()
            df = yf.download(
                tickers=ticker,
                period="14d",
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=False,
            )
        if df is None or df.empty:
            return None

        # Städar & tar sista stängningskursen
        if "Close" not in df.columns:
            return None
        df = df.dropna(subset=["Close"])
        if df.empty:
            return None

        last_close = float(df["Close"].iloc[-1])
        idx = df.index[-1]
        # Hanterar ev. tidszon
        try:
            ts_iso = idx.tz_convert("UTC").date().isoformat() if getattr(idx, "tzinfo", None) else idx.date().isoformat()
        except Exception:
            ts_iso = idx.date().isoformat()

        return {"last_close": last_close, "ts": ts_iso}

    except Exception:
        return None

def _fallback_latest_from_db(conn, ticker: str) -> Optional[dict]:
    try:
        lp = portfolio.latest_prices(conn, [ticker])
        if isinstance(lp, pd.DataFrame) and not lp.empty:
            return {"last_close": float(lp["last_close"].iloc[0]),
                    "ts": str(lp["ts"].iloc[0])}
    except Exception:
        pass
    return None

def _ensure_state_keys():
    st.session_state.setdefault("trade_ticker", "")
    st.session_state.setdefault("trade_price", 0.0)
    st.session_state.setdefault("trade_ts", date.today().isoformat())

def main():
    st.set_page_config(page_title=PAGE_TITLE, layout="wide")
    st.title(PAGE_TITLE)

    if "auth_ok" not in st.session_state or not st.session_state["auth_ok"]:
        st.warning("Du måste logga in via startsidan.")
        st.stop()

    user = st.session_state["user"]
    conn = get_conn()
    _ensure_state_keys()


    # Universe & ticker-väljare 
    df_univ = universe.load_universe("data/omx_securities.csv")
    st.subheader("Välj/sök ticker")

    name_to_sym = dict(zip(df_univ["name_display"], df_univ["yf_symbol"]))
    choice = st.selectbox(
        "Bolag",
        options=list(name_to_sym.keys()),
        index=None if len(name_to_sym) else None,
        placeholder="Välj bolag…",
    )
    ticker = name_to_sym.get(choice, "")
    st.session_state["trade_ticker"] = ticker

    fetch_col, _ = st.columns([1, 5])
    with fetch_col:
        if st.button("Hämta senaste pris"):
            if not ticker:
                st.error("Välj ett bolag först.")
            else:
                with st.spinner(f"Hämtar senaste pris för {ticker}…"):
                    data = yf_last_close(ticker)
                    if data is None:
                        data = _fallback_latest_from_db(conn, ticker)

                    if data is None:
                        st.error("Kunde inte hämta senaste pris just nu.")
                        with st.expander("Visa teknisk info"):
                            st.write("yfinance gav inget resultat och det fanns inget pris i DB för tickern.")
                    else:
                        st.session_state["trade_price"] = float(data["last_close"])
                        st.session_state["trade_ts"] = str(data["ts"])
                        st.success(
                            f"Pris uppdaterat: {st.session_state['trade_price']:.2f} "
                            f"(datum {st.session_state['trade_ts']})"
                        )

    st.divider()

        # Trade-rutan
    st.subheader("Registrera affär")
    with st.form("trade_form", clear_on_submit=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            d_default = date.fromisoformat(st.session_state.get("trade_ts", date.today().isoformat()))
            d = st.date_input("Datum", value=d_default, key="trade_date") # stäng denna? eftersom datum ändå hämtas via "hämta senaste pris"?
            ts = d.isoformat()
        with c2:
            side = st.selectbox("Köp/sälj", options=["BUY", "SELL"], key="trade_side")
        with c3:
            qty = st.number_input("Qty", min_value=0.0, value=0.0, step=1.0, format="%.2f", key="trade_qty")

        pcol, fcol = st.columns([2, 1])
        with pcol:
            st.text_input(
                "Pris (senaste Close)",
                value=f"{st.session_state.get('trade_price', 0.0):.2f}",
                disabled=True,
                key="trade_price_display",
            )
        with fcol:
            fee = st.number_input("Courtage", min_value=0.0, value=0.0, step=1.0, format="%.2f", key="trade_fee")

        # gör knappen alltid klickbar, validera efter submit
        saved = st.form_submit_button("Spara")

    if saved:
        try:
            price = float(st.session_state.get("trade_price", 0.0))
            qty = float(st.session_state.get("trade_qty", 0.0))
            fee = float(st.session_state.get("trade_fee", 0.0))
            side = st.session_state.get("trade_side", "BUY")

            if not ticker:
                st.error("Välj ett bolag först.")
            elif price <= 0:
                st.error("Hämta senaste pris innan du sparar.")
            elif qty <= 0:
                st.error("Qty måste vara > 0.")
            else:
                _id = trades_svc.record_trade(conn, user, ticker, side, qty, price, ts, fee)
                st.success(f"Affär sparad (id={_id}).")
                st.session_state["last_saved"] = _id
                st.rerun()
        except ValueError as e:
            st.error(str(e))
        except AssertionError as e:
            st.error(str(e))
        except Exception as e:
            st.exception(e)


    # Historik 
    st.subheader("Historik")
    df_hist = trades_svc.list_trades(conn, user)
    if df_hist.empty:
        st.info("Inga trades ännu – hämta pris och lägg till din första trade ovan.")
    else:
        st.dataframe(df_hist.sort_values(["ts", "id"]), use_container_width=True)

if __name__ == "__main__":
    main()
