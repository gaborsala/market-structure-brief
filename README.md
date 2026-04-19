# Market Structure Brief

A reproducible, rule-based market structure reporting pipeline built in Python.

This project demonstrates how raw financial data can be transformed into structured, deterministic weekly reports using a fully automated CLI workflow. The system is intentionally designed around process discipline, clarity, and reproducibility — not prediction.

---

## Project Purpose

This repository exists as a portfolio demonstration of:

- End-to-end analytical pipeline construction
- Deterministic rule-based classification systems
- Automated report generation
- Reproducible data workflows
- Scope-controlled analytical discipline

The focus is structural observation — not forecasting, optimization, or strategy claims.

---

## What This System Does

Each week, the pipeline:

1. Downloads sector ETF price data
2. Computes relative performance vs SPY
3. Applies explicit classification rules
4. Generates a standardized weekly market structure brief
5. Tracks structural state duration (TRANSITION → resolution)

The output is consistent, reproducible, and version-controlled.

---

## Universe

**Benchmark:** SPY

**Sector ETFs:**  
XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV, XLY, XLC, XLRE

**Data source:**

- yfinance
- Stooq fallback (if needed)

---

## Repository Structure

```text
market-structure-brief/
├── briefs/                     # Published weekly reports
├── docs/                       # Classification & methodology documentation
├── logs/                       # Process tracking
├── out/
│   ├── YYYY_WXX/               # Weekly outputs
│   └── tracking/               # Cross-week tracking files
│       └── transition_tracking.csv
├── src/                        # Core pipeline scripts
│   ├── sector_ratios_vs_spy.py
│   ├── weekly_structure_engine.py
│   ├── fill_weekly_template.py
│   └── update_transition_tracking.py
├── template/
│   └── weekly_template.md
├── requirements.txt
├── DISCLAIMER.md
├── LICENSE.txt
└── README.md
Pipeline Overview
1) Data Ingestion & Ratio Calculation
python src/sector_ratios_vs_spy.py --days 30

Outputs:

out/ratios_wide.csv
out/ratios_long.csv
2) Structural Classification
python src/weekly_structure_engine.py --week 2026_W01

Outputs:

out/2026_W01/weekly_structure_summary.csv
out/2026_W01/weekly_classification.json
3) Report Generation
python src/fill_weekly_template.py \
  --week 2026_W01 \
  --template template/weekly_template.md \
  --summary out/2026_W01/weekly_structure_summary.csv \
  --json out/2026_W01/weekly_classification.json \
  --out briefs/2026_W01.md
4) Transition Duration Tracking (NEW)

Tracks how long sectors remain in TRANSITION before resolving into HH/HL or LH/LL.

python src/update_transition_tracking.py \
  --json out/2026_W01/weekly_classification.json \
  --tracking out/tracking/transition_tracking.csv \
  --week 2026_W01

Output:

out/tracking/transition_tracking.csv
Important Rules
Weeks must be processed in chronological order
This file is append-only and stateful
No modification of classification logic
Pure observation layer (no scoring, no prediction)
Example Output

See: briefs/2026_W01.md

Skills Demonstrated
Python (CLI-based tooling)
pandas data processing
Financial data ingestion
Deterministic rule systems
Structured reporting automation
Reproducible research workflows
Version-controlled analytical publishing
Temporal state tracking (structure duration)
Design Principles

The system intentionally avoids:

Forecasting language
Strategy optimization
Performance claims
Indicator proliferation
Macro overlays

Each weekly brief is a structural snapshot, not a trade signal.

The transition tracking layer adds time-based observation, without altering classification logic.

Installation
git clone https://github.com/gaborsala/market-structure-brief.git
cd market-structure-brief

python -m venv .venv

# Windows:
#   .venv\Scripts\activate

# Linux/macOS:
#   source .venv/bin/activate

pip install -r requirements.txt