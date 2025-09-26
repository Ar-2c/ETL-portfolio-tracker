from __future__ import annotations

from datetime import date, timedelta
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
import altair as alt # (använder detta för att få crosshair i grafen)

from app.config import START_CASH # (hämtas ur config.py)
from app.services import db as dbsvc
from app.services import portfolio


# hjälpfunktioner nedan:

def _to_index_df(obj: pd.Series | pd.DataFrame, name: str) -> pd.DataFrame:
    if isinstance(obj, pd.DataFrame):
        s = obj.iloc[:, 0].dropna()
    else:
        s = obj.dropna()
    if s.empty:
        return pd.DataFrame(columns=[name])
    s = s / s.iloc[0] * 100.0
    s.name = name
    return s.to_frame()

PAGE_TITLE = "Dashboard"

PERIOD_OPTIONS = ["1 dag", "1 vecka", "3 månader", "6 månader", "YTD", "1 år", "Allt"]
PERIOD_DAYS = {"1 dag": 1, "1 vecka": 7, "3 månader": 90, "6 månader": 180, "1 år": 365}


@st.cache_resource(show_spinner=False)
def get_conn():
    conn = dbsvc.get_conn()
    dbsvc.ensure_schema(conn)
    return conn


def _ytd_start(anchor: date) -> date:
    return date(anchor.year, 1, 1)


def _period_start_for(anchor: date, period: str) -> date | None:
    if period == "Allt":
        return None
    if period == "YTD":
        return _ytd_start(anchor)
    return anchor - timedelta(days=PERIOD_DAYS[period])


def _max_db_date(conn, tickers: list[str]) -> date | None:
    if not tickers:
        return None
    placeholders = ",".join(["?"] * len(tickers))
    sql = f"SELECT MAX(ts) FROM prices WHERE ticker IN ({placeholders})"
    row = conn.execute(sql, tickers).fetchone()
    if not row or not row[0]:
        return None
    return pd.to_datetime(row[0]).date()


def _load_price_panel(conn, tickers: list[str], start_date: date | None, end_date: date) -> pd.DataFrame:
    """Pivot: index=ts (datetime), columns=ticker, values=close."""
    if not tickers:
        return pd.DataFrame()
    placeholders = ",".join(["?"] * len(tickers))
    params: list = tickers[:]
    conds = [f"ticker IN ({placeholders})", "ts <= ?"]
    params.append(end_date.isoformat())
    if start_date is not None:
        conds.append("ts >= ?")
        params.append(start_date.isoformat())
    where = " AND ".join(conds)
    sql = f"SELECT ts, ticker, close FROM prices WHERE {where} ORDER BY ts"
    df = pd.read_sql_query(sql, conn, params=params)
    if df.empty:
        return pd.DataFrame()
    df["ts"] = pd.to_datetime(df["ts"])  # säkerställ datetimeindex
    pivot = df.pivot(index="ts", columns="ticker", values="close").sort_index()
    pivot = pivot.dropna(how="all", axis=1).interpolate(limit_direction="both")
    return pivot


def _load_trades(conn, user: str, end_date: date) -> pd.DataFrame:
    sql = """
      SELECT ts, ticker, side, qty, price, fee
      FROM trades
      WHERE user = ? AND ts <= ?
      ORDER BY ts, id
    """
    df = pd.read_sql_query(sql, conn, params=[user, end_date.isoformat()])
    if df.empty:
        return df
    df["ts"] = pd.to_datetime(df["ts"])  # datum
    df["qty_signed"] = df["qty"].where(df["side"] == "BUY", -df["qty"])  # + vid köp, - vid sälj
    df["cash_flow"] = df.apply(
        lambda r: -(r["price"] * r["qty"] + r["fee"]) if r["side"] == "BUY"
        else (r["price"] * r["qty"] - r["fee"]),
        axis=1,
    )
    return df


def _positions_qty_panel(trades: pd.DataFrame, price_index: pd.DatetimeIndex) -> pd.DataFrame:
    """
    Dagliga kvantiteter per ticker över hela price_index:
    - summera qty på handelsdagar
    - kumulera (cumsum) på originalets datum
    - fyll sedan framåt in i periodens datum (reindex med ffill)
    """
    if trades.empty:
        return pd.DataFrame(0.0, index=price_index, columns=[])
    qty = trades.pivot_table(index="ts", columns="ticker", values="qty_signed", aggfunc="sum").sort_index()
    qty = qty.cumsum()
    qty = qty.reindex(price_index, method="ffill").fillna(0.0)
    return qty


def _cash_series(trades: pd.DataFrame, price_index: pd.DatetimeIndex) -> pd.Series:
    if trades.empty:
        return pd.Series(START_CASH, index=price_index, name="cash")
    cf = trades.groupby("ts")["cash_flow"].sum().sort_index()
    cf = cf.reindex(price_index, fill_value=0.0)
    cash = START_CASH + cf.cumsum()
    return cash.rename("cash")


@st.cache_data(ttl=3600, show_spinner=False)
def _omxspi_series(start_date: date | None, end_date: date) -> pd.Series:
    kwargs = dict(interval="1d", auto_adjust=False, progress=False, threads=False)
    if start_date:
        hist = yf.download("^OMXSPI", start=start_date - timedelta(days=5), end=end_date + timedelta(days=1), **kwargs)
    else:
        hist = yf.download("^OMXSPI", period="max", **kwargs)
    if hist is None or hist.empty:
        return pd.Series(dtype="float64")
    s = hist["Adj Close"] if "Adj Close" in hist.columns else hist["Close"]
    s = s.dropna()
    s.index = pd.to_datetime(s.index)
    if start_date:
        s = s[s.index.date >= start_date]
    s = s[s.index.date <= end_date]
    return s


# Fyll saknade last_close/market_value från DB och Yahoo vid behov 
def _fill_missing_last_close_and_mv(conn, df_pos: pd.DataFrame, anchor: date) -> pd.DataFrame:
    if df_pos.empty:
        return df_pos

    # Säkerställ numerik
    for c in ("last_close", "market_value", "qty"):
        if c in df_pos.columns:
            df_pos[c] = pd.to_numeric(df_pos[c], errors="coerce")

    miss_mask = df_pos["last_close"].isna() if "last_close" in df_pos.columns else pd.Series(False, index=df_pos.index)
    if miss_mask.any():
        tickers = df_pos.loc[miss_mask, "ticker"].dropna().unique().tolist()
        if tickers:
            placeholders = ",".join(["?"] * len(tickers))
            sql = f"""
                SELECT p.ticker, p.close
                FROM prices p
                JOIN (
                    SELECT ticker, MAX(ts) AS max_ts
                    FROM prices
                    WHERE ticker IN ({placeholders}) AND date(ts) <= ?
                    GROUP BY ticker
                ) mx
                ON p.ticker = mx.ticker AND p.ts = mx.max_ts
            """
            rows = conn.execute(sql, tickers + [anchor.isoformat()]).fetchall()
            db_map = {t: c for (t, c) in rows if c is not None}
            if db_map:
                df_pos.loc[df_pos["ticker"].isin(db_map.keys()), "last_close"] = df_pos["ticker"].map(db_map)

        still = df_pos.loc[df_pos["last_close"].isna(), "ticker"].dropna().unique().tolist()
        for t in still:
            try:
                hist = yf.download(
                    t, start=anchor - timedelta(days=7), end=anchor + timedelta(days=1),
                    interval="1d", auto_adjust=False, progress=False, threads=False
                )
                if hist is not None and not hist.empty:
                    s = hist["Adj Close"] if "Adj Close" in hist.columns else hist["Close"]
                    val = float(s.dropna().iloc[-1])
                    df_pos.loc[df_pos["ticker"] == t, "last_close"] = val
            except Exception:
                pass

    # Market value
    if "market_value" in df_pos.columns:
        mv_missing = df_pos["market_value"].isna()
        if mv_missing.any():
            df_pos.loc[mv_missing, "market_value"] = df_pos.loc[mv_missing, "qty"] * df_pos.loc[mv_missing, "last_close"]
    else:
        df_pos["market_value"] = df_pos["qty"] * df_pos["last_close"]

    return df_pos


# beräkning av orealiserad avkastning 

def _compute_now_unrealized(df_pos: pd.DataFrame) -> tuple[pd.DataFrame, float, float]:
    """Beräknar invested, unreal_pnl, utveckling_% per rad + total %/SEK.
    Kräver kolumnerna: qty, avg_buy_price, last_close (market_value fylls om saknas).
    """
    df = df_pos.copy()
    req = {"qty", "avg_buy_price", "last_close", "market_value"}
    if not req.issubset(df.columns):
        return df, float("nan"), float("nan")

    for c in ("qty", "avg_buy_price", "last_close", "market_value"):
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["invested"] = df["qty"] * df["avg_buy_price"]
    df["unreal_pnl"] = df["market_value"] - df["invested"]
    df["utveckling_%"] = np.where(df["invested"] > 0, (df["unreal_pnl"] / df["invested"]) * 100.0, np.nan)

    total_inv = float(df["invested"].sum())
    total_mv  = float(df["market_value"].sum())
    total_pnl = total_mv - total_inv
    total_pct = (total_pnl / total_inv * 100.0) if total_inv > 0 else float("nan")

    return df, total_pct, total_pnl



# ---------------------------MAIN---------------------------


def main():
    st.set_page_config(page_title=PAGE_TITLE, layout="wide")
    st.title(PAGE_TITLE)

    if "auth_ok" not in st.session_state or not st.session_state["auth_ok"]:
        st.warning("Du måste logga in via startsidan.")
        st.stop()

    user = st.session_state["user"]
    conn = get_conn()

    # Översikt (nutid)
    try:
        df_pos = portfolio.overview(conn, user)
    except Exception as e:
        st.error(f"Kunde inte läsa portföljöversikt: {e}")
        st.stop()

    tickers = df_pos["ticker"].dropna().unique().tolist() if not df_pos.empty else []
    if not tickers:
        st.info("Inga innehav ännu. Gå till **Trades** och registrera din första affär.")
        return

    anchor = _max_db_date(conn, tickers)
    if not anchor:
        st.info("Hittade inga prisdata i databasen för dina tickers.")
        st.stop()

    # last_close/market_value
    df_pos = _fill_missing_last_close_and_mv(conn, df_pos, anchor)

    # KPI:er Likvida medel, Portföljvärde, Totalt värde
    cash_now = portfolio.cash_balance(conn, user)

    port_value_now = float(pd.to_numeric(df_pos.get("market_value"), errors="coerce").fillna(0.0).sum())
    total_value_now = cash_now + port_value_now

    
    df_pos, tot_pct_now, tot_pnl_now = _compute_now_unrealized(df_pos)

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.metric("Likvida medel", f"{cash_now:,.0f} SEK")
    with k2:
        st.metric("Portföljvärde", f"{port_value_now:,.0f} SEK")
    with k3:
        st.metric("Totalt värde", f"{total_value_now:,.0f} SEK")
    with k4:
        
        st.metric(
            label="Portföljutveckling",
            value=f"{tot_pct_now:+.2f} %",
            delta=f"{tot_pnl_now:,.0f} SEK",
            help="Orealiserad avkastning baserat på GAV. Ex. cash.",
        )

    # Innehavstabell 
    st.subheader("Innehav")
    cols = ["ticker", "qty", "avg_buy_price", "last_close", "market_value", "unreal_pnl", "utveckling_%"]
    show = [c for c in cols if c in df_pos.columns]
    st.dataframe(df_pos[show].sort_values("market_value", ascending=False), use_container_width=True)

    # Portföljens utveckling (interaktiv graf – period/TWR)
    st.subheader("Portfölj (viktad) – tidsserie")
    period = st.radio("Period", PERIOD_OPTIONS, horizontal=True, index=2)

    start_date = _period_start_for(anchor, period)

    price_panel = _load_price_panel(conn, tickers, start_date, anchor)
    if price_panel.empty:
        st.info("Hittade inga prisdata för perioden. Kör ETL för att fylla historik.")
        st.stop()

    trades = _load_trades(conn, user, anchor)
    qty_panel = _positions_qty_panel(trades, price_panel.index)
    qty_panel = qty_panel.reindex(columns=price_panel.columns, fill_value=0.0)

    # Time-Weighted Return (TWR) om historik finns
    ret = price_panel.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    hold_val = (qty_panel.shift(1) * price_panel.shift(1))
    tot_val = hold_val.sum(axis=1)

    have_any = tot_val.gt(0)
    twr_possible = have_any.any()
    base_val = None

    if twr_possible:
        first_hold_day = have_any.idxmax()
        hold_val = hold_val.loc[first_hold_day:]
        ret = ret.loc[first_hold_day:]
        tot_val = tot_val.loc[first_hold_day:]

        weights = hold_val.div(tot_val, axis=0).fillna(0.0)
        port_ret = (weights * ret).sum(axis=1)

        portfolio_index = (1.0 + port_ret).cumprod() * 100.0
        base_val = float(tot_val.loc[first_hold_day])
        plot_df = portfolio_index.rename("Portfölj").to_frame()
    else:
        plot_df = pd.DataFrame()

    # Fallback: statisk korg av dagens innehav
    if plot_df.empty or plot_df.shape[0] < 5:
        qty_now = df_pos.set_index("ticker")["qty"].reindex(price_panel.columns).fillna(0.0)
        pv = (price_panel.mul(qty_now, axis=1)).sum(axis=1)
        pv = pv[pv > 0]
        if not pv.empty:
            portfolio_index = (pv / pv.iloc[0] * 100.0).rename("Portfölj")
            base_val = float(pv.iloc[0])
            plot_df = portfolio_index.to_frame()
        else:
            st.info("Ingen tidsserie att visa ännu.")
            st.stop()

    # OMXSPI (index=100)
    omx = _omxspi_series(plot_df.index.min().date(), anchor)
    if omx is not None and not omx.empty:
        omx = omx.reindex(plot_df.index).ffill()
        if isinstance(omx, pd.DataFrame):
            omx = omx.iloc[:, 0]
        omx_idx = (omx / omx.iloc[0] * 100.0)
        omx_idx = omx_idx.to_frame(name="^OMXSPI")
        plot_df = plot_df.join(omx_idx, how="left")

    # Tooltip-serier
    if "Portfölj" in plot_df.columns and not plot_df["Portfölj"].empty:
        port_series = plot_df["Portfölj"].astype(float)
        plot_df["Portfölj_SEK"] = port_series / 100.0 * float(base_val)
        plot_df["Portfölj_%"] = port_series - 100.0

        # Periodens KPI (för grafen) – separat från NU-KPI:n ovan
        k4_pct = float(port_series.iloc[-1] - 100.0)
        k4_sek = float(plot_df["Portfölj_SEK"].iloc[-1] - plot_df["Portfölj_SEK"].iloc[0])
        st.metric(
            "Portföljutveckling (period)",
            f"{k4_pct:+.2f}%",
            delta=f"{k4_sek:,.0f} SEK",
            help="Avkastning för vald period i grafen. Exkl. cash.",
        )

    if "^OMXSPI" in plot_df.columns:
        plot_df["OMXSPI_%"] = plot_df["^OMXSPI"] - 100.0

    # Altair-graf
    chart_df = plot_df.reset_index()
    first_col = chart_df.columns[0]
    if first_col != "Datum":
        chart_df = chart_df.rename(columns={first_col: "Datum"})

    value_cols = [c for c in ["Portfölj", "^OMXSPI"] if c in chart_df.columns]
    long_df = chart_df.melt(id_vars=["Datum"], value_vars=value_cols, var_name="Serie", value_name="Index")

    hover = alt.selection_point(fields=["Datum"], nearest=True, on="mousemove", empty=False)

    line = (
        alt.Chart(long_df)
        .mark_line()
        .encode(
            x=alt.X("Datum:T", title="Datum"),
            y=alt.Y("Index:Q", title="Index (100 = start)"),
            color=alt.Color("Serie:N", title=None),
        )
        .properties(height=360)
    )

    rule = alt.Chart(long_df).mark_rule(color="#888").encode(x="Datum:T").transform_filter(hover)
    points = (
        alt.Chart(long_df).mark_circle(size=36).encode(x="Datum:T", y="Index:Q", color="Serie:N").transform_filter(hover)
    )

    tooltip_base = (
        alt.Chart(chart_df)
        .mark_rule(opacity=0)
        .encode(
            x="Datum:T",
            tooltip=[
                alt.Tooltip("Datum:T", title="Datum"),
                alt.Tooltip("Portfölj_SEK:Q", title="Portfölj (SEK)", format=",.0f"),
                alt.Tooltip("Portfölj_%:Q", title="Portfölj (%)", format="+.2f"),
                alt.Tooltip("OMXSPI_%:Q", title="OMXSPI (%)", format="+.2f"),
            ],
        )
        .add_params(hover)
    )

    st.altair_chart((line + points + rule + tooltip_base).interactive(), use_container_width=True)

    st.caption(
        "Portfölj = avkastning på aktieinnehaven (utan cash), normaliserad till 100. "
        "Bygger på TWR när affärshistorik finns, annars statisk korg av dagens innehav. "
        "^OMXSPI från Yahoo Finance."
    )


if __name__ == "__main__":
    main()










