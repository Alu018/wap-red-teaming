"""Single place to set which models the suite uses.

The two you'll usually change — the model under test:

    STATIC_MODEL  — static red-teaming (gemini-* routes to Google's
                    OpenAI-compatible endpoint, everything else to OpenAI)
    PETRI_TARGET  — petri audits (Inspect format: provider/model)

CLI flags on the individual scripts still override these.
"""

# Google Sheet that backs the static prompt set. Must be readable without
# login (Share -> Anyone with the link -> Viewer, or Publish to web).
# `sync_questions.py` uses this when no source is passed on the CLI.
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQiLkfC6myL0psYWwbaEUNSj04kmnyo-vLgq9oH-zLZf2AjN9g0P25GQMfsB0xqKoVnRZ3CiLiMqSJt/pub?output=csv"

# Model under test
STATIC_MODEL = "gemini-3.5-flash"
PETRI_TARGET = "google/gemini-3.5-flash"

# Model suites for multi-model runs (static-archive/run_prompts.py --models all,
# petri/run_audit.py --targets all). Static names route by prefix:
# gemini-* -> Google, claude-* -> Anthropic (OpenAI-compatible endpoint),
# everything else -> OpenAI. Petri targets use Inspect's provider/model form.
STATIC_MODELS = [
    "gemini-3.1-pro-preview",
    "gpt-5.6-terra",
    "claude-sonnet-5",
]
PETRI_TARGETS = [
    "google/gemini-3.1-pro-preview",
    "openai/gpt-5.6-terra",
    "anthropic/claude-sonnet-5",
]

# Inspect port of the static suite (redteam.py / run_inspect.py). Same
# provider/model format as petri targets; prompts come straight from
# SHEET_URL.
INSPECT_MODEL = "google/gemini-3.1-pro-preview"
INSPECT_MODELS = [
    "google/gemini-3.1-pro-preview",
    "openai/gpt-5.6-terra",
    "anthropic/claude-sonnet-5",
]

# Graders / audit machinery — keep these fixed across runs so scores stay
# comparable between tested models.
STATIC_JUDGE = "claude-sonnet-5"

# Inspect judge is model-dependent so it's never grading its own family:
# claude-sonnet-5 judges everything EXCEPT Claude models, which gpt-5.6-terra
# judges instead. redteam.py picks between these per-sample based on the
# model under test (see _resolve_judge / ModelName matching there).
INSPECT_JUDGE_DEFAULT = "anthropic/claude-sonnet-5"
INSPECT_JUDGE_FOR_CLAUDE = "openai/gpt-5.6-terra"

PETRI_AUDITOR = "anthropic/claude-sonnet-5"
PETRI_JUDGE = "anthropic/claude-opus-4-7"

# Pricing for cost estimates, USD per 1,000,000 tokens as (input, output).
# Any provider/model prefix (e.g. "anthropic/") is stripped before lookup; an
# unlisted model reports cost as unknown. Reported costs are estimates.
# Rates verified 2026-07-19 (sources in comments); confirm before relying on them.
PRICING = {
    "gemini-3.5-flash": {"in": 1.50, "out": 9.00},    # Google, per pricepertoken/devtk (May 2026)
    "gpt-5.6-terra":    {"in": 2.50, "out": 15.00},   # OpenAI GPT-5.6 Terra tier (GA 2026-07-09)
    "claude-sonnet-5":  {"in": 3.00, "out": 15.00},   # Anthropic (intro $2/$10 through 2026-08-31)
    "claude-opus-4-7":  {"in": 5.00, "out": 25.00},   # Anthropic Opus 4.x
    "claude-opus-4-8":  {"in": 5.00, "out": 25.00},   # Anthropic Opus 4.x
}
