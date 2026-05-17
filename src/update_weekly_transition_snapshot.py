import argparse
import json
from pathlib import Path
import pandas as pd


DIRECTION_COLS = {
    "HH/HL": "hh_hl_count",
    "LH/LL": "lh_ll_count",
    "RANGE": "range_count",
    "TRANSITION": "transition_count",
}


def load_current_classification(path: Path) -> tuple[dict, pd.DataFrame]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    meta = data.get("meta", {})
    table = pd.DataFrame(data.get("table", []))

    required = {"Ticker", "Direction"}
    missing = required - set(table.columns)
    if missing:
        raise ValueError(f"Missing columns in classification table: {missing}")

    return meta, table


def load_existing_snapshot(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()

    return pd.read_csv(path)


def get_previous_week_row(snapshot: pd.DataFrame, current_week: str) -> pd.Series | None:
    if snapshot.empty or "week" not in snapshot.columns:
        return None

    previous = snapshot[snapshot["week"] != current_week]

    if previous.empty:
        return None

    return previous.iloc[-1]


def parse_tickers(value) -> set[str]:
    if pd.isna(value) or value == "":
        return set()

    return {x.strip() for x in str(value).split("|") if x.strip()}


def build_snapshot_row(
    week: str,
    date: str,
    meta: dict,
    table: pd.DataFrame,
    previous_row: pd.Series | None,
) -> dict:
    direction_counts = table["Direction"].value_counts().to_dict()

    current_transition_tickers = set(
        table.loc[table["Direction"] == "TRANSITION", "Ticker"].astype(str)
    )

    previous_transition_tickers = set()
    if previous_row is not None and "transition_tickers" in previous_row:
        previous_transition_tickers = parse_tickers(previous_row["transition_tickers"])

    new_transitions = current_transition_tickers - previous_transition_tickers
    resolved_transitions = previous_transition_tickers - current_transition_tickers
    persistent_transitions = current_transition_tickers & previous_transition_tickers

    transition_count = int(direction_counts.get("TRANSITION", 0))

    if transition_count == 0:
        notes = "No active transition structures detected. Absence logged as valid weekly observation."
    else:
        notes = f"Active transition structures detected: {'|'.join(sorted(current_transition_tickers))}"

    return {
        "week": week,
        "date": date,
        "hh_hl_count": int(direction_counts.get("HH/HL", 0)),
        "lh_ll_count": int(direction_counts.get("LH/LL", 0)),
        "range_count": int(direction_counts.get("RANGE", 0)),
        "transition_count": transition_count,
        "new_transitions": int(len(new_transitions)),
        "resolved_transitions": int(len(resolved_transitions)),
        "persistent_transitions": int(len(persistent_transitions)),
        "breadth": meta.get("breadth", ""),
        "tilt": meta.get("tilt", ""),
        "transition_tickers": "|".join(sorted(current_transition_tickers)),
        "notes": notes,
    }


def upsert_snapshot_row(snapshot: pd.DataFrame, row: dict) -> pd.DataFrame:
    row_df = pd.DataFrame([row])

    if snapshot.empty:
        return row_df

    snapshot = snapshot[snapshot["week"] != row["week"]]
    snapshot = pd.concat([snapshot, row_df], ignore_index=True)

    return snapshot


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--week", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--classification", required=True)
    parser.add_argument("--snapshot", required=True)

    args = parser.parse_args()

    classification_path = Path(args.classification)
    snapshot_path = Path(args.snapshot)

    meta, table = load_current_classification(classification_path)
    snapshot = load_existing_snapshot(snapshot_path)

    previous_row = get_previous_week_row(snapshot, args.week)

    row = build_snapshot_row(
        week=args.week,
        date=args.date,
        meta=meta,
        table=table,
        previous_row=previous_row,
    )

    updated = upsert_snapshot_row(snapshot, row)

    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    updated.to_csv(snapshot_path, index=False)

    print(f"Updated weekly transition snapshot: {snapshot_path}")
    print(row)


if __name__ == "__main__":
    main()