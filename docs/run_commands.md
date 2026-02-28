Run commands (your normal workflow)

Generate ratios (unchanged):

python src/sector_ratios_vs_spy.py --days 30 --outdir out\2026_W01


Run patched structure engine:

python src/weekly_structure_engine.py --infile out/2026_W01/ratios_wide.csv --outdir out/2026_W01

Fill template with patched filler:

python src/fill_weekly_template.py --week 2026_W01 --template template/2026_W01_template.md --summary out/2026_W01/weekly_structure_summary.csv --json out/2026_W01/weekly_classification.json --out briefs/2026_W01.md

python src/fill_weekly_template.py `
  --week 2026_W02 `
  --template templates/weekly_template.md `
  --summary out/2026_W02/weekly_structure_summary.csv `
  --json out/2026_W02/weekly_classification.json `
  --out out/2026_W02/2026_W02.md `
  --prev-summary out/2026_W01/weekly_structure_summary.csv

If you want, paste your new generated out/weekly_structure_summary.csv + the filled 2026_W01.md, and I’ll do a quick “NZ2 compliance audit” (labels, breadth, tilt, risk state, formatting) in one pass.