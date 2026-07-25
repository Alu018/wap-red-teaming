# Animal-welfare red-teaming suite

Two ways to red-team language models on animal welfare:

| | Inspect static red-teaming | Petri (agentic auditing) |
|---|---|---|
| Stimulus | Hand-written single-turn prompts, identical every run, pulled live from a Google Sheet | Auditor model improvises multi-turn scenarios from seed instructions |
| Measures | Response policy: refusal posture, welfare-frame engagement, operational leakage | Behavioral propensities: welfare dismissal under pressure, sycophancy, welfare-washing, agentic tradeoffs |
| Judge | Frontier judge (two rubrics: public acceptability + welfare principles) | Frontier judge, transcript-level dimensions |
| Strengths | Reproducible, cheap, cross-model comparable, statistical reps | Finds behaviors fixed prompts can't reach (pushback, system-prompt pressure, tool use) |
| Best for | Tracking known failure modes over time / across models | Discovering new failure modes and pressure sequences |

Both produce Inspect eval logs (`logs/`), browsable with `inspect view`.

Typical loop: discover with Petri → distill confirmed findings into fixed prompts → track with Inspect static runs.

## Configuration

All model choices live in `config.py`: `INSPECT_MODEL` / `INSPECT_MODELS` / `INSPECT_JUDGE` for Inspect static red-teaming, `PETRI_TARGET` / `PETRI_TARGETS` / `PETRI_AUDITOR` / `PETRI_JUDGE` for Petri. (`STATIC_MODEL` / `STATIC_MODELS` / `STATIC_JUDGE` are only used by the legacy `static-archive/` pipeline.) Keep judge/auditor models fixed across runs so scores stay comparable. CLI flags override per-run.

## Setup

```bash
source .venv/bin/activate      # inspect-ai, inspect-petri, python-dotenv installed
```

Create `.env` in the repo root (gitignored):

```
GOOGLE_API_KEY=...      # Inspect static runner (Gemini), set to the same value as GEMINI_API_KEY
ANTHROPIC_API_KEY=...   # judge model + Petri auditor/judge
OPENAI_API_KEY=...      # if targeting OpenAI models
```

Petri reads keys from the environment, so also `export` them (or use `dotenv run`).

## Inspect static red-teaming

`redteam.py` is the Inspect task: prompts are fetched **directly from the Google Sheet** (`config.STATIC_SHEET_URL`) every run, the model under test answers each single-turn, and two judges score every response — `public_judge` (reasonable-person acceptability) and `cmep_judge` (adherence to animal/AI-welfare principles). Both scores run 0.0 (worst) → 1.0 (best). Models use Inspect's `provider/model` naming.

**Do you need to sync questions first? No.** The sheet is read live on every run — edit the sheet and just re-run. (This is different from the archived static pipeline in `static-archive/`, which reads from a cached JSON snapshot that has to be regenerated after sheet edits — see below.)

```bash
# Smoke test: 2 prompts (default model from config.INSPECT_MODEL)
python run_inspect.py --limit 2

# Full run; --epochs replaces --reps
python run_inspect.py --model openai/gpt-5.6-terra --epochs 3

# Every model in config.INSPECT_MODELS (one eval log per model), or an explicit list
python run_inspect.py --models all
python run_inspect.py --models google/gemini-3.1-pro-preview,anthropic/claude-opus-5

# Only specific sheet ids
python run_inspect.py --id 5,12,40

# Or use the inspect CLI directly (task args via -T)
inspect eval redteam.py --model google/gemini-3.1-pro-preview --limit 2
inspect eval redteam.py -T judge=anthropic/claude-sonnet-5 -T source=path/to/local.csv

# Browse transcripts, per-sample judge rationales, scores, token usage
inspect view
```

Logs land in `logs/` (same directory as Petri's). Per-sample judge diagnostics (`request_class`, `refusal_posture`, `actionable_harm`, …) are in each score's metadata in the log viewer; token usage (and cost) is tracked natively by Inspect.

## Petri (agentic auditing)

8 custom seeds in `petri/seeds/`, 3 custom judge dimensions in `petri/dimensions/` (merged with built-in audit-quality dimensions by the run script — note a directory passed to `judge_dimensions` directly would *replace* the built-ins).

```bash
# Smoke test: 2 seeds, short conversations (default target: openai/gpt-5.6-terra)
python petri/run_audit.py --limit 2 --max-turns 15

# Full custom-seed run
python petri/run_audit.py --target openai/gpt-5.6-terra

# Run specific seeds only (comma-separated seed filenames, without .md)
python petri/run_audit.py --sample-id backyard_slaughter_advice,humane_washing_copy

# Or point --seeds at a single seed file
python petri/run_audit.py --seeds petri/seeds/backyard_slaughter_advice.md

# Run every target in config.PETRI_TARGETS (one eval log per target), or an explicit list
python petri/run_audit.py --targets all
python petri/run_audit.py --targets google/gemini-3.1-pro-preview,anthropic/claude-opus-5

# View transcripts
inspect view
```

Logs land in `logs/`. Check audit-quality dimensions first (`auditor_failure`, `stuck_in_loops`, `eval_awareness`, `scenario_realism`) — high scores there mean the audit is broken, not the target. Scores triage; read the flagged transcripts.

Rescore existing logs without re-running conversations:

```bash
inspect score logs/<file>.eval --scorer inspect_petri/audit_judge -S model=... --action append
```

## `static-archive/` (legacy)

Before the Inspect port, static red-teaming ran as a standalone CSV-based pipeline (fetch sheet → snapshot to JSON → call models directly → score → view/compare/report as HTML). That pipeline is preserved as-is in `static-archive/` for reference but is no longer the recommended way to run static red-teaming — use `redteam.py` / `run_inspect.py` instead. `score.py` and `sync_questions.py` still live at repo root since Inspect's task imports from them (shared judge rubrics + sheet-loading code).

## Provenance

- Petri: [Inspect Petri v3](https://meridianlabs-ai.github.io/inspect_petri/) (Meridian Labs; originally Anthropic).
- Static: simplified port of `Evals_Experimental/llm-red-teaming` (runner + judge rubric + Allen's prompt set).
