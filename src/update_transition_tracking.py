import pandas as pd
import json
from pathlib import Path


def load_classification(json_path):
    with open(json_path, "r") as f:
        data = json.load(f)
    return {row["Ticker"]: row["Direction"] for row in data["table"]}


def load_tracking(path):
    columns = [
        "etf",
        "start_week",
        "last_seen_week",
        "end_week",
        "duration_weeks",
        "status",
        "resolution_type",
    ]

    if Path(path).exists():
        df = pd.read_csv(
            path,
            dtype={
                "etf": "string",
                "start_week": "string",
                "last_seen_week": "string",
                "end_week": "string",
                "duration_weeks": "Int64",
                "status": "string",
                "resolution_type": "string",
            },
        )
    else:
        df = pd.DataFrame(
            {
                "etf": pd.Series(dtype="string"),
                "start_week": pd.Series(dtype="string"),
                "last_seen_week": pd.Series(dtype="string"),
                "end_week": pd.Series(dtype="string"),
                "duration_weeks": pd.Series(dtype="Int64"),
                "status": pd.Series(dtype="string"),
                "resolution_type": pd.Series(dtype="string"),
            }
        )

    return df[columns]


def update_tracking(df, current, week):
    for etf, direction in current.items():
        open_rows = df[(df["etf"] == etf) & (df["status"] == "ongoing")]

        # --- TRANSITION ---
        if direction == "TRANSITION":
            if open_rows.empty:
                df.loc[len(df)] = [
                    etf,
                    week,
                    week,
                    pd.NA,
                    1,
                    "ongoing",
                    pd.NA,
                ]
            else:
                idx = open_rows.index[0]
                df.loc[idx, "last_seen_week"] = week
                df.loc[idx, "duration_weeks"] = int(df.loc[idx, "duration_weeks"]) + 1

        # --- RESOLUTION ---
        else:
            if not open_rows.empty:
                idx = open_rows.index[0]
                df.loc[idx, "last_seen_week"] = week
                df.loc[idx, "end_week"] = week
                df.loc[idx, "status"] = "resolved"
                df.loc[idx, "resolution_type"] = direction

    return df


def main(json_path, tracking_path, week):
    current = load_classification(json_path)
    df = load_tracking(tracking_path)
    df = update_tracking(df, current, week)

    Path(tracking_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(tracking_path, index=False)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--json", required=True)
    parser.add_argument("--tracking", required=True)
    parser.add_argument("--week", required=True)

    args = parser.parse_args()

    main(args.json, args.tracking, args.week)