Run commands (your normal workflow)

Generate ratios (unchanged):

python src/sector_ratios_vs_spy.py --days 30 --outdir out\2026_W04


Run patched structure engine:

python src/weekly_structure_engine.py --infile out/2026_W04/ratios_wide.csv --outdir out/2026_W04

Fill template with filler:
python src/fill_weekly_template.py --template template/2026_W01_template.md --summary out/2026_W04/weekly_structure_summary.csv --json out/2026_W04/weekly_classification.json --week 2026_W04 --date 2026-03-21 --out briefs/2026_W04.md

If you want, paste your new generated out/weekly_structure_summary.csv + the filled 2026_W01.md, and I’ll do a quick “NZ2 compliance audit” (labels, breadth, tilt, risk state, formatting) in one pass.