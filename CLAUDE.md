# CLAUDE.md

Animal-welfare red-teaming suite for language models. Two active approaches, run through the [Inspect](https://inspect.aisi.org.uk/) framework:

1. **Inspect static red-teaming** — `redteam.py` (Inspect task) + `run_inspect.py` (CLI wrapper). Fixed single-turn prompts pulled **live** from a Google Sheet every run (`config.SHEET_URL`), scored by two judges (`public_judge`, `cmep_judge`). No sync step needed — edit the sheet, just re-run.
2. **Petri** — `petri/run_audit.py` + custom seeds/dimensions in `petri/seeds/`, `petri/dimensions/`. Agentic multi-turn auditing.

Both write Inspect eval logs to `logs/`, viewable with `inspect view`. See `README.md` for full run instructions and flags.

## Key files (repo root)

- `config.py` — all model/judge choices for both pipelines, plus pricing table.
- `redteam.py` — the Inspect static red-teaming task (dataset + solver + scorers).
- `run_inspect.py` — CLI convenience wrapper around `inspect eval` for `redteam.py`.
- `score.py` — judge rubrics (`build_public_prompt`, `build_cmep_prompt`, `parse_scores`). Imported by `redteam.py`; also has its own CLI for scoring legacy static-archive CSVs.
- `sync_questions.py` — parses the Google Sheet into rows (`load_rows`, imported by `redteam.py`); also has a CLI mode that snapshots the sheet to JSON for the legacy static-archive pipeline.
- `petri/` — Petri seeds, custom judge dimensions, run script.

`score.py` and `sync_questions.py` live at root (not archived) because `redteam.py` imports functions from both — they're shared infrastructure, not static-only.

## `static-archive/`

An older, standalone CSV-based static red-teaming pipeline (predates the Inspect port): fetch sheet → snapshot to `prompts/prompts.json` → call models directly → score → `view.py`/`compare.py`/`report.py` for HTML output. Kept for reference; no longer the recommended way to run static red-teaming. Don't worry about its internals unless specifically asked to work on it — treat it as archived.

## Working conventions

- Model names in this repo (e.g. `gemini-3.1-pro-preview`, `gpt-5.6-terra`, `claude-sonnet-5`) are real, current models as of this project's timeframe — don't "correct" them to older/more familiar names.
- When changing model lists in `config.py`, remember `STATIC_MODELS`/`PETRI_TARGETS`/`INSPECT_MODELS` use different naming conventions (bare name vs. `provider/model`).
