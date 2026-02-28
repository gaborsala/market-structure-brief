#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

DEFENSIVE = {"XLP", "XLU", "XLV"}
CYCLICAL = {"XLF", "XLI", "XLB", "XLY", "XLK"}  # NZ2 cyclical set  # keep XLE cyclical here for tilt context


def load_summary(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    required = {"Rank", "Ticker", "Direction", "Leadership"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"weekly_structure_summary.csv missing columns: {sorted(missing)}")
    df = df.sort_values("Rank").reset_index(drop=True)
    return df


def load_classification(json_path: Path) -> Dict:
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def fmt_list(items: List[str]) -> str:
    return ", ".join(items) if items else "n/a"


def compute_top_bottom(df: pd.DataFrame) -> Tuple[List[str], List[str]]:
    top3 = df.head(3)["Ticker"].tolist()
    bot3 = df.tail(3)["Ticker"].tolist()
    return top3, bot3


def compute_counts(df: pd.DataFrame) -> Dict[str, int]:
    directions = df["Direction"]
    return {
        "HH_HL": int((directions == "HH/HL").sum()),
        "LH_LL": int((directions == "LH/LL").sum()),
        "RANGE": int((directions == "RANGE").sum()),
        "TRANSITION": int((directions == "TRANSITION").sum()),
    }


def defensive_cyclical_counts(df: pd.DataFrame) -> Tuple[int, int]:
    def_hh = int(df[df["Ticker"].isin(DEFENSIVE) & (df["Direction"] == "HH/HL")].shape[0])
    cyc_hh = int(df[df["Ticker"].isin(CYCLICAL) & (df["Direction"] == "HH/HL")].shape[0])
    return def_hh, cyc_hh


def persistent_leaders(df: pd.DataFrame) -> List[str]:
    return df[df["Leadership"] == "Persistent Leader"]["Ticker"].tolist()


def transitions(df: pd.DataFrame) -> List[str]:
    return df[df["Direction"] == "TRANSITION"]["Ticker"].tolist()


def risk_state_from_rules(df: pd.DataFrame, tilt: str) -> Tuple[str, List[str]]:
    """
    Deterministic priority order:
    1) Risk-Off: >=5 LH/LL
    2) Defensive Shift: >=3 Defensive sectors in HH/HL
    3) Risk-On: >=4 sectors in HH/HL and Cyclical Tilt present
    4) Narrow Leadership: 1–2 Persistent Leaders only
    5) Fragmented: Mixed HH/HL and LH/LL without concentration
    else: Balanced
    """
    counts = compute_counts(df)
    def_hh, cyc_hh = defensive_cyclical_counts(df)
    pers = persistent_leaders(df)

    if counts["LH_LL"] >= 5:
        return "Risk-Off", [
            f"LH/LL sectors count: {counts['LH_LL']}.",
            f"HH/HL sectors count: {counts['HH_HL']}.",
            f"Tilt: {tilt}.",
        ]

    if def_hh >= 3:
        return "Defensive Shift", [
            f"Defensive sectors show {def_hh} HH/HL structures.",
            f"Cyclical sectors show {cyc_hh} HH/HL structures.",
            f"Breadth based on HH/HL count: {counts['HH_HL']}.",
        ]

    if counts["HH_HL"] >= 4 and tilt == "Cyclical Tilt":
        return "Risk-On", [
            f"HH/HL sectors count: {counts['HH_HL']}.",
            f"Tilt: {tilt}.",
            f"LH/LL sectors count: {counts['LH_LL']}.",
        ]

    if len(pers) in (1, 2):
        return "Narrow Leadership", [
            f"Persistent Leaders: {fmt_list(pers)}.",
            f"HH/HL sectors count: {counts['HH_HL']}.",
            f"Tilt: {tilt}.",
        ]

    if counts["HH_HL"] > 0 and counts["LH_LL"] > 0:
        return "Fragmented", [
            f"HH/HL sectors count: {counts['HH_HL']}.",
            f"LH/LL sectors count: {counts['LH_LL']}.",
            f"Tilt: {tilt}.",
        ]

    return "Balanced", [
        f"HH/HL sectors count: {counts['HH_HL']}.",
        f"LH/LL sectors count: {counts['LH_LL']}.",
        f"Tilt: {tilt}.",
    ]


def compute_change_vs_last_week(curr_df: pd.DataFrame, prev_df: pd.DataFrame | None) -> str:
    if prev_df is None:
        return "n/a"

    prev = prev_df.set_index("Ticker")[["Direction", "Leadership"]]
    curr = curr_df.set_index("Ticker")[["Direction", "Leadership"]]

    common = prev.index.intersection(curr.index)
    if common.empty:
        return "n/a"

    changed = 0
    for t in common:
        if (prev.loc[t, "Direction"] != curr.loc[t, "Direction"]) or (
            prev.loc[t, "Leadership"] != curr.loc[t, "Leadership"]
        ):
            changed += 1
    return str(changed)


def build_ranking_table(df: pd.DataFrame) -> str:
    lines = []
    lines.append("| Rank | ETF | 4W Direction | Leadership Status |")
    lines.append("|---:|:---:|:---:|:---|")
    for _, r in df.iterrows():
        lines.append(f"| {int(r['Rank'])} | {r['Ticker']} | {r['Direction']} | {r['Leadership']} |")
    return "\n".join(lines)


def replace_line(text: str, pattern: str, replacement_line: str) -> str:
    return re.sub(pattern, replacement_line, text, flags=re.MULTILINE)


def replace_section1_table(text: str, table_md: str) -> str:
    """Replace the markdown table inside '## 1. Relative Strength Ranking' with table_md."""
    pat = re.compile(
        r"(## 1\. Relative Strength Ranking\s*\n\s*\n)(\|\s*Rank\s*\|.*?\n\s*\n)",
        re.S,
    )
    m = pat.search(text)
    if not m:
        return text.replace("| Rank | ETF | 4W Direction | Leadership Status |", table_md, 1)
    return text[: m.start(2)] + table_md + "\n\n" + text[m.end(2) :]



def replace_market_risk_state_line(text: str, risk_state: str) -> str:
    """Replace the selected Risk State line under '## 4. Market Risk State' regardless of template option wording."""
    pat = re.compile(r"(## 4\. Market Risk State\s*\n\s*\n)([^\n]+)")
    m = pat.search(text)
    if not m:
        return text
    return text[: m.start(2)] + risk_state + text[m.end(2) :]



def ensure_transition_bullet(out: str) -> str:
    # Fix lines that start with "TRANSITION → ..." missing "- "
    out = re.sub(r"(?m)^(TRANSITION\s*→\s*.+)$", r"- \1", out)
    return out


def relabel_bottom3_by_rank(out: str) -> str:
    out = re.sub(r"(?m)^Bottom 3 Laggards:\s*(.*)$", r"Bottom 3 by 4W Rank: \1", out)
    out = re.sub(r"(?m)^Bottom 3 by 4W Rank:\s*(.*)$", r"Bottom 3 by 4W Rank: \1", out)
    return out


def normalize_rotation_line(out: str) -> str:
    # Remove accidental duplication
    out = re.sub(r"(?m)^- Rotation signals:\s*Rotation signals:\s*n/a\s*$", r"- Rotation signals: n/a", out)
    return out


def normalize_bullet_spacing(out: str) -> str:
    """
    Ensure markdown list items use '- ' (dash + space).
    Fixes: '-HH/HL' -> '- HH/HL', '-Emerging Leader' -> '- Emerging Leader'
    Does NOT touch tables ('| ...') or horizontal rules ('---').
    """
    # Only lines that start with '-' followed by a non-space and not another dash
    # (so we don't change '---' horizontal rules)
    out = re.sub(r"(?m)^-([^\s-])", r"- \1", out)
    return out


def fill_template(
    template_text: str,
    week: str,
    brief_date: str,
    df: pd.DataFrame,
    meta: Dict,
    change_vs_last: str,
) -> str:
    top3, bot3 = compute_top_bottom(df)
    def_hh, cyc_hh = defensive_cyclical_counts(df)
    pers = persistent_leaders(df)
    trans = transitions(df)

    breadth = meta.get("breadth", "n/a")
    tilt = meta.get("tilt", "n/a")

    risk_state, risk_just = risk_state_from_rules(df, tilt)

    out = template_text

    # Header
    out = replace_line(out, r"^Week:\s*.*$", f"Week: {week}")
    out = replace_line(out, r"^Date:\s*.*$", f"Date: {brief_date}")

    # Ranking table injection (first occurrence)
    ranking_table = build_ranking_table(df)
    out = replace_section1_table(out, ranking_table)

    # Simple fields
    out = replace_line(out, r"^Top 3 Leaders:.*$", f"Top 3 Leaders: {fmt_list(top3)}")
    out = replace_line(out, r"^Bottom 3 Laggards:.*$", f"Bottom 3 by 4W Rank: {fmt_list(bot3)}")
    out = replace_line(out, r"^Bottom 3 by 4W Rank:.*$", f"Bottom 3 by 4W Rank: {fmt_list(bot3)}")
    out = replace_line(out, r"^Breadth:.*$", f"Breadth: {breadth}")
    out = replace_line(out, r"^Tilt:.*$", f"Tilt: {tilt}")
    out = replace_line(out, r"^Change vs Last Week:.*$", f"Change vs Last Week: {change_vs_last}")

    # Structural Observations bullets (deterministic)
    leadership_conc = "Leadership concentrated in 3 sectors."
    def_line = f"Defensive sectors show {def_hh} HH/HL structure count."
    cyc_line = f"Cyclical sectors show {cyc_hh} HH/HL structure count."
    change_line = f"Change vs prior week: {change_vs_last} sectors shifted classification."

    out = replace_line(out, r"^- Leadership concentration:.*$", f"- {leadership_conc}")

    rot_text = f"TRANSITION sectors: {fmt_list(trans)}" if trans else "n/a"
    out = replace_line(out, r"^- Rotation signals:.*$", f"- Rotation signals: {rot_text}")

    out = replace_line(out, r"^- Defensive behavior:.*$", f"- {def_line}")
    out = replace_line(out, r"^- Cyclical confirmation:.*$", f"- {cyc_line}")

    # If bullets don't exist (template variant), insert a neutral paragraph block
    if "## 2. Structural Observations" in out and leadership_conc not in out:
        out = out.replace(
            "## 2. Structural Observations",
            "## 2. Structural Observations\n\n"
            f"{leadership_conc}\n\n"
            f"Defensive sectors show {def_hh} HH/HL structure count.\n\n"
            f"Cyclical sectors show {cyc_hh} HH/HL structure count.\n\n"
            f"{change_line}\n",
            1,
        )

    # Market Risk State selection line
    out = replace_market_risk_state_line(out, risk_state)
    if "Justification (max 3 lines)." in out:
        out = out.replace(
            "Justification (max 3 lines).",
            "Justification (max 3 lines).\n" + "\n".join(risk_just[:3]),
            1,
        )

    # Closing statement (neutral)
    closing = (
        f"Closing statement: Breadth classified as {breadth}. "
        f"Leadership concentrated in {len(pers)} sectors. "
        f"Tilt condition: {tilt}."
    )
    out = replace_line(out, r"^Neutral structural summary\.\s*$", closing)
    out = replace_line(out, r"^No forecast language\.\s*$", "No forecast language.")

    # Normalizations / patches
    out = ensure_transition_bullet(out)
    out = relabel_bottom3_by_rank(out)
    out = normalize_rotation_line(out)
    out = normalize_bullet_spacing(out)

    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", default="templates/2026_W01.md", help="Path to weekly template md")
    ap.add_argument("--summary", default="out/weekly_structure_summary.csv", help="Path to weekly_structure_summary.csv")
    ap.add_argument("--json", default="out/weekly_classification.json", help="Path to weekly_classification.json")
    ap.add_argument("--week", required=True, help="Week code, e.g. 2026_W01")
    ap.add_argument("--date", default=str(date.today()), help="Date string for the brief (default: today)")
    ap.add_argument("--out", default="", help="Output path. Default: briefs/<week>.md")
    ap.add_argument("--prev-summary", default="", help="Optional prior week summary CSV for Change vs Last Week")
    args = ap.parse_args()

    template_path = Path(args.template)
    summary_path = Path(args.summary)
    json_path = Path(args.json)

    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")
    if not summary_path.exists():
        raise FileNotFoundError(f"Summary CSV not found: {summary_path}")
    if not json_path.exists():
        raise FileNotFoundError(f"Classification JSON not found: {json_path}")

    template_text = template_path.read_text(encoding="utf-8")

    df = load_summary(summary_path)
    payload = load_classification(json_path)
    meta = payload.get("meta", {})

    prev_df = None
    if args.prev_summary:
        prev_path = Path(args.prev_summary)
        if prev_path.exists():
            prev_df = load_summary(prev_path)

    change_vs_last = compute_change_vs_last_week(df, prev_df)

    filled = fill_template(
        template_text=template_text,
        week=args.week,
        brief_date=args.date,
        df=df,
        meta=meta,
        change_vs_last=change_vs_last,
    )

    out_path = Path(args.out) if args.out else Path("briefs") / f"{args.week}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(filled, encoding="utf-8")

    print("Wrote:")
    print(f"- {out_path.resolve()}")


if __name__ == "__main__":
    main()