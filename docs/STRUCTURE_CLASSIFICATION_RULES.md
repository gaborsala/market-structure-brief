# STRUCTURE CLASSIFICATION RULES
## Now Zone 2 – Structural Discipline Phase

This document describes the exact deterministic rules implemented
in the Python classification engine.

The objective is structural regime classification.
This framework does NOT perform forecasting, optimization, or strategy backtesting.

---

# 1. Data Source Layer

Data is fetched using:

- Yahoo Finance (primary, via yfinance)
- Stooq (fallback)

Source logic is implemented in:
sector_ratios_vs_spy.py

Daily close prices are collected for:

XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV, XLY, XLC, XLRE
Benchmark: SPY

Ratios are computed as:

    ETF_Close / SPY_Close

Outputs:
- ratios_wide.csv
- ratios_long.csv

---

# 2. Analysis Window

Default configuration:

- Sessions used: 20 trading days
- Window split: 10 + 10 sessions
- Half window size: 10
- Optional epsilon noise guard (default: 0.0)

These values are configurable via CLI arguments.

---

# 3. Direction Classification Logic

Direction is determined using a 2-half comparison method:

Split last 20 sessions into:

- First half (sessions 1–10)
- Second half (sessions 11–20)

Compute:

- max1, min1 (first half)
- max2, min2 (second half)

Rules:

HH/HL  
If:
    max2 > max1
AND
    min2 > min1

LH/LL  
If:
    max2 < max1
AND
    min2 < min1

TRANSITION  
If only one of the above conditions holds.

RANGE  
If none of the above conditions are satisfied.

No alternative labels are permitted.

---

# 4. Ranking Logic

Each ETF is ranked by 4-week ratio return:

    (last_value / first_value) - 1

Descending order.
Highest return = Rank 1.

This ranking is purely relative performance over 20 sessions.

---

# 5. Leadership Classification

Leadership status is determined as follows:

If Direction == LH/LL:
    Leadership = Weak

If Rank <= 3 AND Direction == HH/HL:
    Leadership = Persistent Leader

If Direction == HH/HL:
    Leadership = Emerging Leader

If Direction == TRANSITION AND 4W return > 0:
    Leadership = Fading

Else:
    Leadership = Neutral

No discretionary override is applied.

---

# 6. Breadth Classification

Breadth is determined by the count of HH/HL sectors.

Rules:

If HH/HL count >= 4:
    Breadth = Broad Participation

If HH/HL count <= 2:
    Breadth = Narrow Leadership

Else:
    Breadth = Fragmented

Breadth is descriptive only.

---

# 7. Defensive vs Cyclical Tilt

Defensive sectors:
XLP, XLU, XLV

Cyclical sectors:
XLF, XLI, XLB, XLY, XLK

Rules:

If >= 3 Defensive sectors in HH/HL:
    Tilt = Defensive Tilt

If >= 3 Cyclical sectors in HH/HL:
    Tilt = Cyclical Tilt

Else:
    Tilt = Balanced

Tilt does not imply forecast bias.

---

# 8. Risk State Determination

Risk state is determined in a deterministic priority order:

1. Risk-Off  
   If >= 5 sectors in LH/LL

2. Defensive Shift  
   If >= 3 Defensive sectors in HH/HL

3. Risk-On  
   If >= 4 sectors in HH/HL AND Cyclical Tilt

4. Narrow Leadership  
   If 1–2 Persistent Leaders

5. Fragmented  
   If mixed HH/HL and LH/LL

Else:
Balanced

Priority order matters.
First satisfied condition is selected.

---

# 9. Change vs Last Week

Change vs Last Week is computed by comparing:

- Direction
- Leadership

Between current week and prior summary CSV.

Output = number of sectors that changed classification.

---

# 10. Phase Constraints

Now Zone 2 excludes:

- Indicator overlays
- Moving averages
- RSI
- Macro overlays
- Backtesting
- Automation expansion
- Strategy optimization

This phase builds:

- Structural clarity
- Regime awareness
- Consistent documentation discipline

Execution logic (trigger engineering) is intentionally excluded
until post Week 12 review.