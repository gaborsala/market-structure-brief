Run commands (your normal workflow)

Generate ratios (unchanged):

python src/sector_ratios_vs_spy.py --days 30 --outdir out\2026_W14


Run patched structure engine:

python src/weekly_structure_engine.py --infile out/2026_W14/ratios_wide.csv --outdir out/2026_W14

Fill template with filler(watch out "date"):
python src/fill_weekly_template.py --template template/2026_W01_template.md --summary out/2026_W14/weekly_structure_summary.csv --json out/2026_W14/weekly_classification.json --week 2026_W14 --date 2026-05-31 --out briefs/2026_W14.md

Transition traking:

python src/update_transition_tracking.py --json out/2026_W14/weekly_classification.json --tracking logs/transition/tracking/transition_tracking.csv --week 2026_W14

Weekly transition snapshot:

python src/update_weekly_transition_snapshot.py --week 2026_W14 --date 2026-05-31 --classification out/2026_W14/weekly_classification.json --snapshot logs/transition/weekly_transition_snapshot.csv