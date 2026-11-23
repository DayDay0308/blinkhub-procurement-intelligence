# Analysis (Path B)

| File | Purpose |
|---|---|
| `01_procurement_analysis.ipynb` | Answers the 7 investigation questions; findings, recommendations, assumptions |
| `data/raw/` | Case-study tables transcribed exactly as printed (cleaning is part of the analysis) |
| `data/synthetic/` | Snapshot of the synthetic-year dbt marts, so the notebook runs without a database |
| `build_notebook.py` | Generates the notebook (keeps it reviewable as code) |
| `export_synthetic_snapshot.py` | Refreshes `data/synthetic/` from the `analytics` schema |

Re-run everything (from the `analytics` folder, with the stack running):

```bash
uv sync --group analysis
uv run python ../analysis/export_synthetic_snapshot.py
uv run python ../analysis/build_notebook.py
uv run jupyter nbconvert --to notebook --execute --inplace ../analysis/01_procurement_analysis.ipynb
```

Or open the notebook in VS Code and select the `analytics/.venv` kernel.
