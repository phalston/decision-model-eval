#!/bin/bash
# Render the two pages from what this repo holds (results/, data/): no API calls, no keys.
#   bash analysis/render.sh            -> analysis/decision-models.html (report) and analysis/decision-models-story.html (story)
# Needs quarto and R (jsonlite, ggplot2, knitr, rmarkdown); the story's first render downloads its font to embed it.
# Refresh the inputs first: python3 compare.py (writes results/report.md and results/verdicts.json);
# data/household-summary.json comes from the Pi-hole repo's scripts/mac/export_eval_summary.py.
set -uo pipefail
cd "$(dirname "$0")" || exit 1
for f in decision-models.qmd decision-models-story.qmd; do
  quarto render "$f" 2>&1 | grep -E 'ERROR|Error|Output created' || true
done
rm -rf story_figs decision-models_files decision-models-story_files
ls -l decision-models.html decision-models-story.html
