#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import io
import time
from pathlib import Path
from urllib.parse import quote

import pandas as pd

SECTOR_ETFS = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY", "XLC", "XLRE"]
BENCHMARK = "SPY"


def fetch_yahoo_closes(tickers: list[str], lookback: str) -> pd.DataFrame:
    """Fetch daily CLOSE prices for tickers from Yahoo via yfinance.

    Notes:
    - yfinance is occasionally rate-limited or returns partial data.
    - We explicitly reindex columns to the requested tickers so missing
      tickers remain visible as NaN (instead of silently disappearing).
    """
    import yfinance as yf

    # yfinance prints "Failed downloads" to stderr.
    # Silence it so your terminal stays clean.
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        # Pass tickers positionally for maximum compatibility across yfinance versions.
        df = yf.download(
            tickers,  # positional
            period=lookback,
            interval="1d",
            auto_adjust=False,
            group_by="ticker",
            progress=False,
            threads=True,
        )

    if df is None or len(df) == 0:
        raise RuntimeError("Yahoo returned empty dataframe (blocked/rate-limited/offline).")

    # yfinance returns:
    # - MultiIndex columns when multiple tickers
    # - Single-index columns when a single ticker
    if isinstance(df.columns, pd.MultiIndex):
        closes = pd.DataFrame(index=df.index)
        for t in tickers:
            if (t, "Close") in df.columns:
                closes[t] = df[(t, "Close")]
        # Keep all requested tickers as columns (missing ones will be NaN)
        closes = closes.reindex(columns=tickers)
    else:
        # Single ticker case: columns like ['Open','High','Low','Close',...]
        if "Close" not in df.columns:
            raise RuntimeError("Yahoo dataframe missing Close column.")
        closes = pd.DataFrame(index=df.index)
        # In single-ticker mode, yfinance returns a series of OHLC for that ticker.
        # We map it to the first requested ticker name.
        if len(tickers) != 1:
            # This can happen if yfinance unexpectedly returned non-multiindex
            # for multiple tickers; be defensive.
            raise RuntimeError("Yahoo returned non-multiindex columns for multiple tickers.")
        closes[tickers[0]] = df["Close"]
        closes = closes.reindex(columns=tickers)

    closes.index = pd.to_datetime(closes.index).tz_localize(None)
    closes = closes.sort_index()
    # Drop rows where all closes are NaN (but keep partial rows)
    closes = closes.dropna(how="all")
    return closes


def stooq_symbol(ticker: str) -> str:
    return f"{ticker.lower()}.us"


def fetch_stooq_close_one(ticker: str) -> pd.Series:
    sym = stooq_symbol(ticker)
    url = f"https://stooq.com/q/d/l/?s={quote(sym)}&i=d"

    df = pd.read_csv(url)  # Date,Open,High,Low,Close,Volume
    if df.empty or "Close" not in df.columns:
        raise RuntimeError(f"Stooq returned empty/invalid CSV for {ticker} ({sym}).")

    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date")
    s = df.set_index("Date")["Close"].rename(ticker)
    s.index = s.index.tz_localize(None)
    return s


def fetch_stooq_closes(tickers: list[str]) -> pd.DataFrame:
    series: list[pd.Series] = []
    errors: list[tuple[str, str]] = []
    for t in tickers:
        try:
            series.append(fetch_stooq_close_one(t))
        except Exception as e:
            errors.append((t, str(e)))

    if not series:
        msg = "Stooq failed for all tickers:\n" + "\n".join([f"{t}: {err}" for t, err in errors])
        raise RuntimeError(msg)

    closes = pd.concat(series, axis=1).sort_index()
    closes = closes.reindex(columns=tickers)  # preserve all requested tickers
    closes = closes.dropna(how="all")
    return closes


def fetch_closes(tickers: list[str], lookback: str, source: str) -> tuple[pd.DataFrame, str]:
    """Fetch closes from a selected source.

    source: 'auto' | 'yahoo' | 'stooq'
    """
    source = source.lower().strip()

    if source == "stooq":
        return fetch_stooq_closes(tickers), "stooq(forced)"

    if source == "yahoo":
        return fetch_yahoo_closes(tickers, lookback), "yahoo(forced)"

    if source != "auto":
        raise ValueError("--source must be one of: auto, yahoo, stooq")

    # auto: try Yahoo once, then Stooq
    try:
        return fetch_yahoo_closes(tickers, lookback), "yahoo(auto)"
    except Exception as e:
        time.sleep(0.5)
        return fetch_stooq_closes(tickers), f"stooq(fallback after yahoo failed: {e})"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=20, help="Trading days to keep (default: 20)")
    ap.add_argument("--lookback", default="90d", help='Yahoo lookback period (default: "90d")')
    ap.add_argument("--outdir", default="out", help="Output folder (default: out)")
    ap.add_argument("--per-ticker", action="store_true", help="Also write per-ticker CSV files")
    ap.add_argument("--source", default="auto", help="Data source: auto | yahoo | stooq (default: auto)")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    tickers = SECTOR_ETFS + [BENCHMARK]
    closes, source_used = fetch_closes(tickers=tickers, lookback=args.lookback, source=args.source)

    # IMPORTANT: align on rows where SPY exists so ratios don't get distorted by NaN SPY rows.
    closes = closes.dropna(how="all")
    closes = closes.dropna(subset=[BENCHMARK])

    closes_last = closes.tail(args.days)

    if BENCHMARK not in closes_last.columns or closes_last[BENCHMARK].dropna().empty:
        raise RuntimeError("SPY data missing/empty after fetch.")

    spy = closes_last[BENCHMARK]

    # Wide ratios
    wide_df = pd.DataFrame(index=closes_last.index)
    for tkr in SECTOR_ETFS:
        if tkr in closes_last.columns:
            wide_df[tkr] = closes_last[tkr] / spy
        else:
            wide_df[tkr] = pd.NA
    wide_df.index.name = "Date"

    # Long output
    long_rows: list[pd.DataFrame] = []
    for tkr in SECTOR_ETFS:
        if tkr not in closes_last.columns:
            continue
        etf = closes_last[tkr]
        # Skip tickers that are entirely missing
        if etf.dropna().empty:
            continue
        long_rows.append(
            pd.DataFrame(
                {
                    "Date": closes_last.index,
                    "Ticker": tkr,
                    "ETF_Close": etf.values,
                    "SPY_Close": spy.values,
                    "Ratio": (etf / spy).values,
                }
            )
        )

    if not long_rows:
        raise RuntimeError("No sector ETF data available to compute ratios.")

    long_df = pd.concat(long_rows, ignore_index=True).sort_values(["Ticker", "Date"])

    wide_path = outdir / "ratios_wide.csv"
    long_path = outdir / "ratios_long.csv"
    wide_df.to_csv(wide_path, float_format="%.6f")
    long_df.to_csv(long_path, index=False, float_format="%.6f")

    if args.per_ticker:
        for tkr in SECTOR_ETFS:
            if tkr not in closes_last.columns:
                continue
            if closes_last[tkr].dropna().empty:
                continue
            per = pd.DataFrame(
                {
                    "ETF_Close": closes_last[tkr],
                    "SPY_Close": spy,
                    "Ratio": closes_last[tkr] / spy,
                }
            )
            per.index.name = "Date"
            per.to_csv(outdir / f"{tkr}_vs_SPY_last{args.days}.csv", float_format="%.6f")

    print(f"Data source: {source_used}")
    print(f"Wrote:\n- {wide_path}\n- {long_path}")
    if args.per_ticker:
        print(f"- Per-ticker CSVs in {outdir.resolve()}")


if __name__ == "__main__":
    main()
