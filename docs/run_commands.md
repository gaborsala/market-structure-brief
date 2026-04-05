Run commands (your normal workflow)

Generate ratios (unchanged):

python src/sector_ratios_vs_spy.py --days 30 --outdir out\2026_W06


Run patched structure engine:

python src/weekly_structure_engine.py --infile out/2026_W06/ratios_wide.csv --outdir out/2026_W06

Fill template with filler:
python src/fill_weekly_template.py --template template/2026_W01_template.md --summary out/2026_W06/weekly_structure_summary.csv --json out/2026_W06/weekly_classification.json --week 2026_W06 --date 2026-04-05 --out briefs/2026_W06.md
