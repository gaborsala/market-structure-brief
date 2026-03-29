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
CYCLICAL = {"XLF", "XLI", "XLB", "XLY", "XLK"}  # NZ2 cyclical set

ALLOWED_BREADTH = {"Broad Leadership", "Narrow Leadership", "Fragmented"}
ALLOWED_TILT = {"Defensive Tilt", "Cyclical Tilt", "Balanced"}


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


def week_to_num(week: str) -> Tuple[int, int]:
    m = re.fullmatch(r"(\d{4})_W(\d{2})", week)
    if not m:
        raise ValueError(f"Invalid week format: {week}. Expected YYYY_WNN")
    return int(m.group(1)), int(m.group(2))


def previous_week_code(week: str) -> str | None:
    year, wk = week_to_num(week)
    if wk <= 1:
        return None
    return f"{year}_W{wk-1:02d}"


def infer_previous_paths(
    current_summary: Path,
    current_json: Path,
    current_week: str,
) -> Tuple[Path | None, Path | None]:
    """
    If current files are in week folders like out/2026_W03/...,
    infer out/2026_W02/... automatically.
    """
    prev_week = previous_week_code(current_week)
    if prev_week is None:
        return None, None

    summary_str = str(current_summary)
    json_str = str(current_json)

    prev_summary = Path(summary_str.replace(current_week, prev_week))
    prev_json = Path(json_str.replace(current_week, prev_week))

    if not prev_summary.exists():
        prev_summary = None
    if not prev_json.exists():
        prev_json = None

    return prev_summary, prev_json


def fmt_list(items: List[str]) -> str:
    return ", ".join(items) if items else "n/a"


def compute_top_bottom(df: pd.DataFrame) -> Tuple[List[str], List[str]]:
    """
    Top 3: highest ranked sectors.
    Bottom 3: prefer lowest-ranked LH/LL sectors first so the published laggards
    reflect actual weak structure. If fewer than 3 LH/LL sectors exist, fall back
    to the lowest-ranked remaining sectors.
    """
    top3 = df.head(3)["Ticker"].tolist()

    laggards = (
        df[df["Direction"] == "LH/LL"]
        .sort_values("Rank", ascending=False)
        .head(3)["Ticker"]
        .tolist()
    )

    if len(laggards) < 3:
        fallback = (
            df[~df["Ticker"].isin(laggards)]
            .sort_values("Rank", ascending=False)
            .head(3 - len(laggards))["Ticker"]
            .tolist()
        )
        laggards.extend(fallback)

    return top3, laggards


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


def normalize_breadth(raw: str, hh_hl_count: int) -> str:
    """
    Enforce Now Zone 2 breadth vocabulary.
    If JSON provides non-standard wording, map or recompute deterministically.
    """
    if not raw:
        raw = "n/a"

    mapping = {
        "Broad Participation": "Broad Leadership",
        "Broad": "Broad Leadership",
        "Narrow": "Narrow Leadership",
    }
    raw = mapping.get(raw, raw)

    if raw in ALLOWED_BREADTH:
        return raw

    if hh_hl_count >= 4:
        return "Broad Leadership"
    if hh_hl_count <= 2:
        return "Narrow Leadership"
    return "Fragmented"


def normalize_tilt(raw: str, def_hh: int, cyc_hh: int) -> str:
    """
    Enforce tilt vocabulary.
    If JSON contains unexpected wording, compute deterministically.
    """
    if not raw:
        raw = "n/a"

    mapping = {
        "Defensive": "Defensive Tilt",
        "Cyclical": "Cyclical Tilt",
        "Neutral": "Balanced",
    }
    raw = mapping.get(raw, raw)

    if raw in ALLOWED_TILT:
        return raw

    if def_hh >= 3:
        return "Defensive Tilt"
    if cyc_hh >= 3:
        return "Cyclical Tilt"
    return "Balanced"


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


def compare_current_vs_previous(
    curr_df: pd.DataFrame,
    curr_meta: Dict,
    prev_df: pd.DataFrame | None,
    prev_meta: Dict | None,
) -> Dict | None:
    if prev_df is None or prev_meta is None:
        return None

    prev = prev_df.set_index("Ticker")[["Direction", "Leadership", "Rank"]]
    curr = curr_df.set_index("Ticker")[["Direction", "Leadership", "Rank"]]

    common = prev.index.intersection(curr.index)
    if common.empty:
        return None

    direction_shift_count = 0
    leadership_shift_count = 0
    rank_change_count = 0

    for t in common:
        if prev.loc[t, "Direction"] != curr.loc[t, "Direction"]:
            direction_shift_count += 1
        if prev.loc[t, "Leadership"] != curr.loc[t, "Leadership"]:
            leadership_shift_count += 1
        if int(prev.loc[t, "Rank"]) != int(curr.loc[t, "Rank"]):
            rank_change_count += 1

    result = {
        "direction_shift_count": direction_shift_count,
        "leadership_shift_count": leadership_shift_count,
        "rank_change_count": rank_change_count,
        "hhhl_delta": int(curr_meta.get("count_HH_HL", 0)) - int(prev_meta.get("count_HH_HL", 0)),
        "lhll_delta": int(curr_meta.get("count_LH_LL", 0)) - int(prev_meta.get("count_LH_LL", 0)),
        "range_delta": int(curr_meta.get("count_RANGE", 0)) - int(prev_meta.get("count_RANGE", 0)),
        "transition_delta": int(curr_meta.get("count_TRANSITION", 0)) - int(prev_meta.get("count_TRANSITION", 0)),
        "breadth_changed": curr_meta.get("breadth", "n/a") != prev_meta.get("breadth", "n/a"),
        "tilt_changed": curr_meta.get("tilt", "n/a") != prev_meta.get("tilt", "n/a"),
        "previous_breadth": prev_meta.get("breadth", "n/a"),
        "current_breadth": curr_meta.get("breadth", "n/a"),
        "previous_tilt": prev_meta.get("tilt", "n/a"),
        "current_tilt": curr_meta.get("tilt", "n/a"),
    }
    return result


def signed_sector_text(value: int, label: str) -> str:
    sign = "+" if value > 0 else ""
    plural = "sector" if abs(value) == 1 else "sectors"
    return f"{sign}{value} {label} {plural}"


def generate_change_vs_last_week(compare_result: Dict | None) -> str:
    if compare_result is None:
        return "baseline week"

    parts: List[str] = []

    n = compare_result["direction_shift_count"]
    if n > 0:
        noun = "sector" if n == 1 else "sectors"
        parts.append(f"{n} {noun} changed direction classification")

    if compare_result["hhhl_delta"] != 0:
        parts.append(signed_sector_text(compare_result["hhhl_delta"], "HH/HL"))

    if compare_result["lhll_delta"] != 0:
        parts.append(signed_sector_text(compare_result["lhll_delta"], "LH/LL"))

    if compare_result["breadth_changed"]:
        parts.append(
            f"Breadth changed from {compare_result['previous_breadth']} to {compare_result['current_breadth']}"
        )

    if compare_result["tilt_changed"]:
        parts.append(
            f"Tilt changed from {compare_result['previous_tilt']} to {compare_result['current_tilt']}"
        )

    if not parts:
        return "No structural change detected versus prior week."

    return "; ".join(parts) + "."


def generate_change_vs_prior_week(compare_result: Dict | None) -> str:
    if compare_result is None:
        return "Change vs prior week: baseline week."

    n = compare_result["direction_shift_count"]
    noun = "sector" if n == 1 else "sectors"
    return f"Change vs prior week: {n} {noun} shifted classification."


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


def replace_market_risk_state_section(text: str, risk_state: str, risk_just: List[str]) -> str:
    """
    Replace the full body of '## 4. Market Risk State' so no legacy template lines survive.
    """
    body = risk_state + "\n\n" + "\n".join(risk_just[:3])
    pat = re.compile(r"(## 4\. Market Risk State\s*\n)(.*?)(\n## 5\.)", re.S)
    m = pat.search(text)
    if not m:
        return text.rstrip() + "\n\n## 4. Market Risk State\n\n" + body + "\n\n## 5. Closing Statement\n"
    return text[: m.start(2)] + "\n" + body.strip() + "\n\n" + text[m.start(3):]


def replace_watchlist_section(out: str, watchlist_text: str) -> str:
    """
    Replace the entire Tactical Watchlist body with a deterministic null-state sentence.
    """
    pat = re.compile(r"(## 3\. Tactical Watchlist.*?\n)(.*?)(\n## 4\.)", re.S)
    m = pat.search(out)
    if not m:
        return out
    return out[:m.start(2)] + "\n" + watchlist_text.strip() + "\n\n" + out[m.start(3):]


def ensure_transition_bullet(out: str) -> str:
    out = re.sub(r"(?m)^(TRANSITION\s*→\s*.+)$", r"- \1", out)
    return out


def relabel_bottom3_by_rank(out: str) -> str:
    out = re.sub(r"(?m)^Bottom 3 Laggards:\s*(.*)$", r"Bottom 3 by 4W Rank: \1", out)
    out = re.sub(r"(?m)^Bottom 3 by 4W Rank:\s*(.*)$", r"Bottom 3 by 4W Rank: \1", out)
    return out


def normalize_rotation_line(out: str) -> str:
    out = re.sub(r"(?m)^- Rotation signals:\s*Rotation signals:\s*n/a\s*$", r"- Rotation signals: n/a", out)
    return out


def normalize_bullet_spacing(out: str) -> str:
    out = re.sub(r"(?m)^-([^\s-])", r"- \1", out)
    return out


def replace_closing_section(out: str, closing_text: str) -> str:
    """
    Robustly inject a closing statement under '## 5. Closing Statement'
    by replacing everything in that section until the next '##' or end of file.
    """
    pat = re.compile(r"(## 5\. Closing Statement\s*\n)(.*?)(\n##\s|\Z)", re.S)
    m = pat.search(out)
    if not m:
        return out.rstrip() + "\n\n## 5. Closing Statement\n\n" + closing_text + "\n"
    before = out[: m.start(2)]
    after = out[m.end(2) :]
    return before + "\n" + closing_text.strip() + "\n\n" + after.lstrip("\n")


def strip_template_instructions(out: str) -> str:
    """
    Remove template-only instructional text so the final brief is publishable.
    Keeps the section headers and the populated content, but removes guidance blocks.
    """
    lines = out.splitlines()
    cleaned: List[str] = []

    skip_starts = (
        "Allowed Structure Labels",
        "Allowed sentence formats",
        "Forbidden",
        "Risk State Determination",
        "Watchlist entry format",
        "Use only if valid structural setup exists",
        "No creative wording",
        "Do not use prediction language",
        "Do not use confidence language",
        "Use only these labels",
        "Only include sectors currently in",
        "If no valid setup exists",
        "Select one:",
    )

    skip_contains = (
        "Allowed Structure Labels",
        "Allowed sentence formats",
        "Risk State Determination",
        "Watchlist entry format",
        "No creative wording",
        "Do not use prediction language",
        "Do not use confidence language",
        "Use only these labels",
        "Use only if valid structural setup exists",
        "If no valid setup exists",
    )

    exact_remove = {
        "- Leadership concentration:",
        "- Rotation signals:",
        "- Defensive behavior:",
        "- Cyclical confirmation:",
        "- Change vs prior week:",
        "[ETF] — [Structure label] — [One-line structural reason]",
        "Justification (max 3 lines).",
        "Leadership concentrated in ___ sectors.",
        "Breadth classified as ___ (Broad / Narrow / Fragmented).",
        "Defensive sectors show ___ structure count.",
        "Cyclical sectors show ___ structure count.",
        "Change vs prior week: ___ sectors shifted classification.",
        "“Momentum building”",
        "“Market preparing”",
        "“Likely continuation”",
        "“Potential breakout”",
        '"Momentum building"',
        '"Market preparing"',
        '"Likely continuation"',
        '"Potential breakout"',
        "Only description.",
        "No alternatives.",
        "No emotional phrasing.",
        "Tactical entries must be triggered by structural break only.",
        "Relative break of prior 4-week high or low.",
        "No anticipation entries.",
        "Invalidation must be structure-based.",
        "Risk Context must be one of:",
    }

    for line in lines:
        stripped = line.strip()

        if not stripped:
            cleaned.append(line)
            continue

        if "___" in stripped:
            continue

        if stripped in exact_remove:
            continue

        if stripped.startswith(skip_starts):
            continue

        if any(token in stripped for token in skip_contains):
            continue

        if stripped.startswith("- Allowed"):
            continue
        if stripped.startswith("- Forbidden"):
            continue
        if stripped.startswith("- Use only"):
            continue
        if stripped.startswith("- Do not use"):
            continue
        if stripped.startswith("- If no valid"):
            continue
        if stripped.startswith("- Select one"):
            continue

        cleaned.append(line)

    text = "\n".join(cleaned)

    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"(?m)^\s*-\s*-\s*", "- ", text)
    text = re.sub(r"[ \t]+\n", "\n", text)

    return text.strip() + "\n"


def fill_template(
    template_text: str,
    week: str,
    brief_date: str,
    df: pd.DataFrame,
    meta: Dict,
    change_vs_last: str,
    change_vs_prior_week_line: str,
) -> str:
    top3, bot3 = compute_top_bottom(df)
    def_hh, cyc_hh = defensive_cyclical_counts(df)
    pers = persistent_leaders(df)
    trans = transitions(df)
    counts = compute_counts(df)

    raw_breadth = meta.get("breadth", "n/a")
    raw_tilt = meta.get("tilt", "n/a")
    breadth = normalize_breadth(raw_breadth, counts["HH_HL"])
    tilt = normalize_tilt(raw_tilt, def_hh, cyc_hh)

    risk_state, risk_just = risk_state_from_rules(df, tilt)

    out = template_text

    out = replace_line(out, r"^Week:\s*.*$", f"Week: {week}")
    out = replace_line(out, r"^Date:\s*.*$", f"Date: {brief_date}")

    ranking_table = build_ranking_table(df)
    out = replace_section1_table(out, ranking_table)

    out = replace_line(out, r"^Top 3 Leaders:.*$", f"Top 3 Leaders: {fmt_list(top3)}")
    out = replace_line(out, r"^Bottom 3 Laggards:.*$", f"Bottom 3 by 4W Rank: {fmt_list(bot3)}")
    out = replace_line(out, r"^Bottom 3 by 4W Rank:.*$", f"Bottom 3 by 4W Rank: {fmt_list(bot3)}")
    out = replace_line(out, r"^Breadth:.*$", f"Breadth: {breadth}")
    out = replace_line(out, r"^Tilt:.*$", f"Tilt: {tilt}")
    out = replace_line(out, r"^Change vs Last Week:.*$", f"Change vs Last Week: {change_vs_last}")

    leadership_conc = f"Leadership concentrated in {len(pers)} sectors."
    def_line = f"Defensive sectors show {def_hh} HH/HL structure count."
    cyc_line = f"Cyclical sectors show {cyc_hh} HH/HL structure count."
    change_line = change_vs_prior_week_line
    rot_text = f"TRANSITION sectors: {fmt_list(trans)}" if trans else "n/a"

    out = replace_line(out, r"^- Leadership concentration:.*$", f"- {leadership_conc}")
    out = replace_line(out, r"^- Rotation signals:.*$", f"- Rotation signals: {rot_text}")
    out = replace_line(out, r"^- Defensive behavior:.*$", f"- {def_line}")
    out = replace_line(out, r"^- Cyclical confirmation:.*$", f"- {cyc_line}")
    out = replace_line(out, r"^- Change vs prior week:.*$", f"- {change_line}")

    if "## 2. Structural Observations" in out and leadership_conc not in out:
        out = out.replace(
            "## 2. Structural Observations",
            "## 2. Structural Observations\n\n"
            f"- {leadership_conc}\n"
            f"- Rotation signals: {rot_text}\n"
            f"- {def_line}\n"
            f"- {cyc_line}\n"
            f"- {change_line}\n",
            1,
        )

    out = replace_watchlist_section(out, "No valid structural watchlist candidate this week.")
    out = replace_market_risk_state_section(out, risk_state, risk_just)

    closing_text = (
        f"Market structure reflects {breadth} based on {counts['HH_HL']} sectors in HH/HL classification. "
        f"Leadership concentration is defined by {len(pers)} Persistent Leaders. "
        f"Tilt condition: {tilt}."
    )
    out = replace_closing_section(out, closing_text)

    out = ensure_transition_bullet(out)
    out = relabel_bottom3_by_rank(out)
    out = normalize_rotation_line(out)
    out = normalize_bullet_spacing(out)
    out = strip_template_instructions(out)

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
    prev_meta = None

    if args.prev_summary:
        prev_summary_path = Path(args.prev_summary)
        if prev_summary_path.exists():
            prev_df = load_summary(prev_summary_path)

    inferred_prev_summary, inferred_prev_json = infer_previous_paths(
        current_summary=summary_path,
        current_json=json_path,
        current_week=args.week,
    )

    if prev_df is None and inferred_prev_summary is not None and inferred_prev_summary.exists():
        prev_df = load_summary(inferred_prev_summary)

    if inferred_prev_json is not None and inferred_prev_json.exists():
        prev_payload = load_classification(inferred_prev_json)
        prev_meta = prev_payload.get("meta", {})

    compare_result = compare_current_vs_previous(
        curr_df=df,
        curr_meta=meta,
        prev_df=prev_df,
        prev_meta=prev_meta,
    )

    change_vs_last = generate_change_vs_last_week(compare_result)
    change_vs_prior_week_line = generate_change_vs_prior_week(compare_result)

    filled = fill_template(
        template_text=template_text,
        week=args.week,
        brief_date=args.date,
        df=df,
        meta=meta,
        change_vs_last=change_vs_last,
        change_vs_prior_week_line=change_vs_prior_week_line,
    )

    out_path = Path(args.out) if args.out else Path("briefs") / f"{args.week}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(filled, encoding="utf-8")

    print("Wrote:")
    print(f"- {out_path.resolve()}")


if __name__ == "__main__":
    main()