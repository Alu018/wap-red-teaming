# Animal-welfare red-teaming suite

Two complementary ways to red-team language models on animal welfare, cleanly separated so you can run either independently:

| | `static/` — fixed prompts | `petri/` — agentic auditing |
|---|---|---|
| Stimulus | Hand-written single-turn prompts, identical every run | Auditor model improvises multi-turn scenarios from seed instructions |
| Measures | Response policy: refusal posture, welfare-frame engagement, operational leakage | Behavioral propensities: welfare dismissal under pressure, sycophancy, welfare-washing, agentic tradeoffs |
| Judge | Gemini Flash, fixed rubric + per-prompt answer keys | Frontier judge, transcript-level dimensions |
| Strengths | Reproducible, cheap, cross-model comparable, statistical reps | Finds behaviors fixed prompts can't reach (pushback, system-prompt pressure, tool use) |
| Best for | Tracking known failure modes over time / across models | Discovering new failure modes and pressure sequences |

Typical loop: discover with Petri → distill confirmed findings into fixed prompts with answer keys → track with static runs.

## Setup

```bash
source .venv/bin/activate      # inspect-petri, openai, python-dotenv installed
```

Create `.env` in the repo root (gitignored):

```
GEMINI_API_KEY=...      # static runner + judge (Gemini OpenAI-compatible endpoint)
ANTHROPIC_API_KEY=...   # petri auditor + judge
OPENAI_API_KEY=...      # if targeting OpenAI models with petri
```

Petri reads keys from the environment, so also `export` them (or use `dotenv run`).

## Static red-teaming

94 prompts across 13 categories (companion animal cruelty, substandard slaughter, unauthorized research, …) in `static/prompts/prompts_allen.json`; 22 have expert answer-key annotations in `static/prompts/annotations.json`.

```bash
# Smoke test: 2 prompts, 1 rep
python static/run_prompts.py --model gemini-3.1-flash-lite --limit 2 --reps 1

# Full run (94 prompts × 2 reps)
python static/run_prompts.py --model gemini-3.1-flash-lite

# Score a results file with the LLM judge
python static/score.py results/redteam_results_prompts_allen_<date>.csv
```

Results land in `results/` as CSV; scoring writes `<name>_scored.csv` alongside. Prompts with an answer key are judged against it (`answer_key_used` column); the rest are judged from the prompt alone. Judge dimensions: `refusal_posture`, `harm_identification`, `actionable_harm`, `safe_alternative`, `severity` (1–5), `confidence`.

## Petri (agentic auditing)

8 custom seeds in `petri/seeds/`, 3 custom judge dimensions in `petri/dimensions/` (merged with built-in audit-quality dimensions by the run script — note a directory passed to `judge_dimensions` directly would *replace* the built-ins).

```bash
# Smoke test: 2 seeds, short conversations
python petri/run_audit.py --target openai/gpt-5-mini --limit 2 --max-turns 15

# Full custom-seed run
python petri/run_audit.py --target openai/gpt-5-mini

# View transcripts
inspect view
```

Logs land in `logs/`. Check audit-quality dimensions first (`auditor_failure`, `stuck_in_loops`, `eval_awareness`, `scenario_realism`) — high scores there mean the audit is broken, not the target. Scores triage; read the flagged transcripts.

Rescore existing logs without re-running conversations:

```bash
inspect score logs/<file>.eval --scorer inspect_petri/audit_judge -S model=... --action append
```

## Provenance

- Petri: [Inspect Petri v3](https://meridianlabs-ai.github.io/inspect_petri/) (Meridian Labs; originally Anthropic).
- Static: simplified port of `Evals_Experimental/llm-red-teaming` (runner + judge rubric + Allen's prompt set). Multi-turn priming chains and HTML reporting were intentionally left behind — Petri covers multi-turn, and the scored CSVs are directly analyzable.
