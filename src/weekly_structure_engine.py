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
    df = pd.read_csv(path)
    if "Date" not in df.columns:
        raise ValueError(f"Missing 'Date' column in {path}")

    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").sort_index()

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


def apply_recent_structure_override(series: pd.Series, base_direction: str, cfg: Config) -> str:
    """
    Minimal NZ2-safe override:
    - If a recent HH/HL trend loses its near-term higher-low support, downgrade to TRANSITION.
    - If a recent LH/LL trend loses its near-term lower-high resistance, upgrade to TRANSITION.

    This prevents stale classifications when the 10-vs-10 window still looks strong,
    but the most recent 5 sessions clearly show a structural break.
    """
    s = series.dropna().tail(cfg.days)
    if len(s) < 10:
        return base_direction

    eps = cfg.epsilon

    prior_5 = s.iloc[-10:-5]
    recent_5 = s.iloc[-5:]

    if len(prior_5) < 5 or len(recent_5) < 5:
        return base_direction

    if base_direction == "HH/HL":
        broke_recent_hl = recent_5.min() < (prior_5.min() - eps)
        closed_below_recent_support = s.iloc[-1] < (prior_5.min() - eps)

        if broke_recent_hl or closed_below_recent_support:
            return "TRANSITION"

    if base_direction == "LH/LL":
        reclaimed_recent_lh = recent_5.max() > (prior_5.max() + eps)
        closed_above_recent_resistance = s.iloc[-1] > (prior_5.max() + eps)

        if reclaimed_recent_lh or closed_above_recent_resistance:
            return "TRANSITION"

    return base_direction


def direction_label(series: pd.Series, cfg: Config) -> str:
    s = series.dropna()
    if len(s) < cfg.days:
        s = series.tail(cfg.days).dropna()
    if len(s) < cfg.days:
        return "RANGE"

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
        base_direction = "HH/HL"
    elif lower_high and lower_low:
        base_direction = "LH/LL"
    elif (
        (higher_high and not higher_low)
        or (higher_low and not higher_high)
        or (lower_high and not lower_low)
        or (lower_low and not lower_high)
    ):
        base_direction = "TRANSITION"
    else:
        base_direction = "RANGE"

    return apply_recent_structure_override(s, base_direction, cfg)


def leadership_status(rank: int, direction: str, ret_4w: float, ret_5d: float) -> str:
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
    """
    Now Zone 2 breadth logic:
    - Broad Leadership: 4+ sectors in HH/HL
    - Narrow Leadership: 1–2 sectors in HH/HL
    - Fragmented: otherwise
    """
    hhhl = int((directions == "HH/HL").sum())

    if hhhl >= 4:
        return "Broad Leadership"
    if hhhl <= 2:
        return "Narrow Leadership"
    return "Fragmented"


def classify_tilt(directions: pd.Series) -> str:
    """
    Now Zone 2 tilt logic:
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
    ap.add_argument("--infile", default="out/ratios_wide.csv")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--days", type=int, default=20)
    ap.add_argument("--half", type=int, default=10)
    ap.add_argument("--epsilon", type=float, default=1e-4)
    args = ap.parse_args()

    cfg = Config(days=args.days, half=args.half, epsilon=args.epsilon)

    infile = Path(args.infile)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    ratios = load_ratios_wide(infile)
    ratios = tail_sessions(ratios, cfg.days)

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

    df = df.sort_values("Ret_4W", ascending=False, na_position="last").reset_index(drop=True)
    df["Rank"] = range(1, len(df) + 1)

    df["Leadership"] = [
        leadership_status(int(r["Rank"]), r["Direction"], r["Ret_4W"], r["Ret_5D"])
        for _, r in df.iterrows()
    ]

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

    summary_path = outdir / "weekly_structure_summary.csv"
    json_path = outdir / "weekly_classification.json"
    md_path = outdir / "weekly_brief_blocks.md"

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