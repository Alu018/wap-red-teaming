"""Run the Inspect static red-team task (convenience wrapper around `inspect eval`).

Mirrors the static/run_prompts.py flags but produces Inspect eval logs in
logs/ instead of CSVs — open them with `inspect view`.

Usage:
    python inspect/run.py --limit 2                 # smoke test, default model
    python inspect/run.py --model openai/gpt-5.6-terra --epochs 3
    python inspect/run.py --models all              # every model in config.INSPECT_MODELS
    python inspect/run.py --models google/gemini-3.5-flash,anthropic/claude-sonnet-5
    python inspect/run.py --id 5,12,40              # only these sheet ids
    inspect view
"""

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from redteam import wap_redteam

sys.path.insert(0, str(HERE.parent))
import config

from inspect_ai import eval as inspect_eval

LOG_DIR = HERE.parent / "logs"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default=config.INSPECT_MODEL,
                        help="Inspect model to test, provider/model form "
                             f"(default: {config.INSPECT_MODEL})")
    parser.add_argument("--models", default=None,
                        help="Comma-separated Inspect models, or 'all' for "
                             "config.INSPECT_MODELS; overrides --model")
    parser.add_argument("--judge", default=config.INSPECT_JUDGE,
                        help=f"Judge model for both scorers (default: {config.INSPECT_JUDGE})")
    parser.add_argument("--source", default=config.STATIC_SHEET_URL,
                        help="Google Sheet URL / spreadsheet ID / local CSV "
                             "(default: config.STATIC_SHEET_URL)")
    parser.add_argument("--epochs", type=int, default=1,
                        help="Repetitions per prompt (replaces --reps)")
    parser.add_argument("--limit", type=int, default=None, help="Cap number of prompts")
    parser.add_argument("--id", default=None,
                        help="Only run prompts with these sheet ids (comma-separated)")
    args = parser.parse_args()

    if args.models == "all":
        models = config.INSPECT_MODELS
    elif args.models:
        models = [m.strip() for m in args.models.split(",") if m.strip()]
    else:
        models = [args.model]

    inspect_eval(
        wap_redteam(source=args.source, judge=args.judge),
        model=models,
        epochs=args.epochs,
        limit=args.limit,
        sample_id=[i.strip() for i in args.id.split(",")] if args.id else None,
        log_dir=str(LOG_DIR),
        max_connections=8,  # matches static/run_prompts.py MAX_CONCURRENCY
    )


if __name__ == "__main__":
    main()
