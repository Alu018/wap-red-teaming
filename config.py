"""Single place to set which models the suite uses.

The two you'll usually change — the model under test:

    STATIC_MODEL  — static red-teaming (gemini-* routes to Google's
                    OpenAI-compatible endpoint, everything else to OpenAI)
    PETRI_TARGET  — petri audits (Inspect format: provider/model)

CLI flags on the individual scripts still override these.
"""

# Google Sheet that backs the static prompt set. Must be readable without
# login (Share -> Anyone with the link -> Viewer, or Publish to web).
# `sheet_to_prompts.py` uses this when no source is passed on the CLI.
STATIC_SHEET_URL = "https://docs.google.com/spreadsheets/d/1aTMogx-M1kbr0HxwowcMqid-ore2cVq2sUg04YyPaAk/edit?gid=0#gid=0"

# Model under test
STATIC_MODEL = "gemini-3.5-flash"
PETRI_TARGET = "google/gemini-3.5-flash"

# Model suites for multi-model runs (static/run_prompts.py --models all,
# petri/run_audit.py --targets all). Static names route by prefix:
# gemini-* -> Google, claude-* -> Anthropic (OpenAI-compatible endpoint),
# everything else -> OpenAI. Petri targets use Inspect's provider/model form.
STATIC_MODELS = [
    "gemini-3.5-flash",
    "gpt-5.6-terra",
    "claude-sonnet-5"
]
PETRI_TARGETS = [
    "google/gemini-3.5-flash",
    "openai/gpt-5.6-terra",
    "anthropic/claude-sonnet-5",
]

# Graders / audit machinery — keep these fixed across runs so scores stay
# comparable between tested models.
STATIC_JUDGE = "claude-sonnet-5"
PETRI_AUDITOR = "anthropic/claude-sonnet-5"
PETRI_JUDGE = "anthropic/claude-opus-4-7"
