"""Single place to set which models the suite uses.

The two you'll usually change — the model under test:

    STATIC_MODEL  — static red-teaming (gemini-* routes to Google's
                    OpenAI-compatible endpoint, everything else to OpenAI)
    PETRI_TARGET  — petri audits (Inspect format: provider/model)

CLI flags on the individual scripts still override these.
"""

# Model under test
STATIC_MODEL = "gemini-3.5-flash"
PETRI_TARGET = "google/gemini-3.5-flash"

# Graders / audit machinery — keep these fixed across runs so scores stay
# comparable between tested models.
STATIC_JUDGE = "claude-sonnet-5"
PETRI_AUDITOR = "anthropic/claude-sonnet-5"
PETRI_JUDGE = "anthropic/claude-opus-4-7"
