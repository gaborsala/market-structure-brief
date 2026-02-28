#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd


SECTOR_ETFS = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY", "XLC", "XLRE"]

DEFENSIVE = ["XLP", "XLU", "XLV"]
CYCLICAL = ["XLF", "XLI", "XLB", "XLY", "XLK"]

DIRECTION_LABELS = ["HH/HL", "LH/LL", "RANGE", "TRANSITION"]


@dataclass
class Config:
    days: int = 20
    half: int = 10
    epsilon: float = 1e-4  # noise guard for ratio comparisons


def load_ratios_wide(path: Path) -> pd.DataFrame:
    """
    Expects: Date column + sector columns containing ratios.
    Returns: Date index, float columns.
    """
    df = pd.read_csv(path)
    if "Date" not in df.columns:
        raise ValueError(f"Missing 'Date' column in {path}")

    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").sort_index()

    # Keep only expected sector columns if present
    cols_present = [c for c in SECTOR_ETFS if c in df.columns]
    if not cols_present:
        raise ValueError(f"No sector columns found in {path}. Expected at least one of: {SECTOR_ETFS}")

    df = df[cols_present].apply(pd.to_numeric, errors="coerce")
    df = df.dropna(how="all")

    return df


def tail_sessions(df: pd.DataFrame, days: int) -> pd.DataFrame:
    out = df.tail(days)
    if len(out) < days:
        raise ValueError(f"Not enough rows for {days} sessions. Found only {len(out)}.")
    return out


def ratio_return(series: pd.Series) -> float:
    s = series.dropna()
    if len(s) < 2:
        return float("nan")
    return (s.iloc[-1] / s.iloc[0]) - 1.0


def direction_label(series: pd.Series, cfg: Config) -> str:
    """
    Split into 2 halves (10 + 10 for 20 sessions). Compare max/min of each half.
    HH/HL if max2>max1 AND min2>min1
    LH/LL if max2<max1 AND min2<min1
    TRANSITION if only one condition holds
    RANGE otherwise
    """
    s = series.dropna()
    if len(s) < cfg.days:
        # still attempt by taking last cfg.days from original series (may include NaNs)
        s = series.tail(cfg.days).dropna()
    if len(s) < cfg.days:
        return "RANGE"  # default conservative label if insufficient data

    s = s.tail(cfg.days)
    h1 = s.iloc[:cfg.half]
    h2 = s.iloc[cfg.half:]

    max1, min1 = h1.max(), h1.min()
    max2, min2 = h2.max(), h2.min()

    eps = cfg.epsilon
    higher_high = (max2 > max1 + eps)
    higher_low = (min2 > min1 + eps)
    lower_high = (max2 < max1 - eps)
    lower_low = (min2 < min1 - eps)

    if higher_high and higher_low:
        return "HH/HL"
    if lower_high and lower_low:
        return "LH/LL"

    # transition means one-side shift but not both
    if (higher_high and not higher_low) or (higher_low and not higher_high) or (lower_high and not lower_low) or (lower_low and not lower_high):
        return "TRANSITION"

    return "RANGE"


def leadership_status(rank: int, direction: str, ret_4w: float, ret_5d: float) -> str:
    """Structure-aligned leadership mapping (Now Zone 2 friendly)."""
    if direction == "LH/LL":
        return "Weak"
    if rank <= 3 and direction == "HH/HL":
        return "Persistent Leader"
    if direction == "HH/HL":
        return "Emerging Leader"
    if direction == "TRANSITION" and pd.notna(ret_4w) and ret_4w > 0:
        return "Fading"
    return "Neutral"



def classify_breadth(directions: pd.Series) -> str:
    """Now Zone 2 breadth logic:
    - Broad Participation: 4+ sectors in HH/HL
    - Narrow Leadership: 1–2 sectors in HH/HL (we use <=2)
    - Fragmented: otherwise
    """
    hhhl = int((directions == "HH/HL").sum())
    if hhhl >= 4:
        return "Broad Participation"
    if hhhl <= 2:
        return "Narrow Leadership"
    return "Fragmented"



def classify_tilt(directions: pd.Series) -> str:
    """Now Zone 2 tilt logic:
    - Defensive Tilt: 3+ defensive sectors in HH/HL
    - Cyclical Tilt: 3+ cyclical sectors in HH/HL
    - Balanced: otherwise
    """
    def_hh = int(directions.reindex(DEFENSIVE).eq("HH/HL").sum())
    cyc_hh = int(directions.reindex(CYCLICAL).eq("HH/HL").sum())

    if def_hh >= 3:
        return "Defensive Tilt"
    if cyc_hh >= 3:
        return "Cyclical Tilt"
    return "Balanced"



def make_markdown_blocks(summary_df: pd.DataFrame, meta: Dict) -> str:
    # Top/Bottom blocks
    top3 = summary_df.nsmallest(3, "Rank")[["Ticker", "Ret_4W", "Direction", "Leadership"]]
    bot3 = summary_df.nlargest(3, "Rank")[["Ticker", "Ret_4W", "Direction", "Leadership"]]

    def fmt_pct(x: float) -> str:
        return "n/a" if pd.isna(x) else f"{x*100:.2f}%"

    lines = []
    lines.append("# Weekly Brief Blocks (Copy/Paste)\n")

    lines.append("## Snapshot")
    lines.append(f"- Sessions used: {meta['sessions_used']}")
    lines.append(f"- Breadth: {meta['breadth']}")
    lines.append(f"- Tilt: {meta['tilt']}")
    lines.append("")

    lines.append("## Top 3 (4W Ratio Return)")
    for _, r in top3.iterrows():
        lines.append(f"- {r['Ticker']}: {fmt_pct(r['Ret_4W'])} | {r['Direction']} | {r['Leadership']}")
    lines.append("")

    lines.append("## Bottom 3 (4W Ratio Return)")
    for _, r in bot3.iterrows():
        lines.append(f"- {r['Ticker']}: {fmt_pct(r['Ret_4W'])} | {r['Direction']} | {r['Leadership']}")
    lines.append("")

    lines.append("## Full Ranking Table (for template)")
    # simple markdown table
    lines.append("| Rank | Ticker | 4W Ret | 5D Ret | Direction | Leadership |")
    lines.append("|---:|:---:|---:|---:|:---:|:---|")
    for _, r in summary_df.sort_values("Rank").iterrows():
        lines.append(
            f"| {int(r['Rank'])} | {r['Ticker']} | {fmt_pct(r['Ret_4W'])} | {fmt_pct(r['Ret_5D'])} | {r['Direction']} | {r['Leadership']} |"
        )

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--infile", default="out/ratios_wide.csv", help="Input ratios wide CSV (default: out/ratios_wide.csv)")
    ap.add_argument("--outdir", default="out", help="Output directory (default: out)")
    ap.add_argument("--days", type=int, default=20, help="Sessions used (default: 20)")
    ap.add_argument("--half", type=int, default=10, help="Half-window size (default: 10)")
    ap.add_argument("--epsilon", type=float, default=0.0, help="Noise epsilon for HH/HL comparisons (default: 0.0)")
    args = ap.parse_args()

    cfg = Config(days=args.days, half=args.half, epsilon=args.epsilon)

    infile = Path(args.infile)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    ratios = load_ratios_wide(infile)
    ratios = tail_sessions(ratios, cfg.days)

    # compute returns + directions
    rows: List[Dict] = []
    for tkr in [c for c in SECTOR_ETFS if c in ratios.columns]:
        s = ratios[tkr]
        ret_4w = ratio_return(s)
        ret_5d = ratio_return(s.tail(5))
        direction = direction_label(s, cfg)
        rows.append(
            {
                "Ticker": tkr,
                "Ret_4W": ret_4w,
                "Ret_5D": ret_5d,
                "Direction": direction,
            }
        )

    df = pd.DataFrame(rows)

    # rank by 4W return (descending best = rank 1)
    df = df.sort_values("Ret_4W", ascending=False, na_position="last").reset_index(drop=True)
    df["Rank"] = range(1, len(df) + 1)

    # leadership status
    df["Leadership"] = [
        leadership_status(int(r["Rank"]), r["Direction"], r["Ret_4W"], r["Ret_5D"]) for _, r in df.iterrows()
    ]

    # breadth & tilt
    directions = df.set_index("Ticker")["Direction"]
    meta = {
        "sessions_used": int(cfg.days),
        "breadth": classify_breadth(directions),
        "tilt": classify_tilt(directions),
        "count_HH_HL": int((directions == "HH/HL").sum()),
        "count_LH_LL": int((directions == "LH/LL").sum()),
        "count_RANGE": int((directions == "RANGE").sum()),
        "count_TRANSITION": int((directions == "TRANSITION").sum()),
    }

    # outputs
    summary_path = outdir / "weekly_structure_summary.csv"
    json_path = outdir / "weekly_classification.json"
    md_path = outdir / "weekly_brief_blocks.md"

    # stable column order
    df = df[["Rank", "Ticker", "Ret_4W", "Ret_5D", "Direction", "Leadership"]].sort_values("Rank")
    df.to_csv(summary_path, index=False, float_format="%.6f")

    payload = {
        "meta": meta,
        "table": df.to_dict(orient="records"),
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    md_path.write_text(make_markdown_blocks(df, meta), encoding="utf-8")

    print("Wrote:")
    print(f"- {summary_path}")
    print(f"- {json_path}")
    print(f"- {md_path}")
    print(f"Meta: Breadth={meta['breadth']} | Tilt={meta['tilt']} | HH/HL={meta['count_HH_HL']}")


if __name__ == "__main__":
    main()