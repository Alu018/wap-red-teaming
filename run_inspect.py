"""Run the Inspect static red-team task (convenience wrapper around `inspect eval`).

Mirrors the static-archive/run_prompts.py flags but produces Inspect eval logs
instead of CSVs — open them with `inspect view`. Each model gets its own
logs/<model-name>/ subfolder (provider prefix dropped) so multi-model runs
don't mix into one flat directory.

Usage:
    python run_inspect.py --limit 2                 # smoke test, default model
    python run_inspect.py --model openai/gpt-5.6-terra --epochs 3
    python run_inspect.py --models all              # every model in config.INSPECT_MODELS
    python run_inspect.py --models google/gemini-3.5-flash,anthropic/claude-sonnet-5
    python run_inspect.py --id 5,12,40              # only these sheet ids
    inspect view
"""

import argparse
import shutil
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

HERE = Path(__file__).resolve().parent
from redteam import wap_redteam

import config

from inspect_ai import eval as inspect_eval

LOG_DIR = HERE / "logs"


def _sort_logs_by_model(results) -> None:
    # eval() runs all models as parallel tasks sharing one log_dir (there's no
    # per-model log_dir option on a single call, and eval_async forbids
    # concurrent calls, which rules out one call per model). So: run into a
    # staging dir, then move each file into logs/<model-name>/ (provider
    # prefix dropped) using the model recorded in the returned EvalLog.
    for log in results:
        model_name = log.eval.model.split("/", 1)[-1]
        dest_dir = LOG_DIR / model_name
        dest_dir.mkdir(parents=True, exist_ok=True)
        src = Path(log.location)
        shutil.move(str(src), str(dest_dir / src.name))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default=config.INSPECT_MODEL,
                        help="Inspect model to test, provider/model form "
                             f"(default: {config.INSPECT_MODEL})")
    parser.add_argument("--models", default=None,
                        help="Comma-separated Inspect models, or 'all' for "
                             "config.INSPECT_MODELS; overrides --model")
    parser.add_argument("--judge", default=None,
                        help="Judge model for both scorers. Default: model-dependent — "
                             f"{config.INSPECT_JUDGE_DEFAULT} judges everything except Claude "
                             f"models, which {config.INSPECT_JUDGE_FOR_CLAUDE} judges instead. "
                             "Pass a value here to force the same judge for every model.")
    parser.add_argument("--source", default=config.SHEET_URL,
                        help="Google Sheet URL / spreadsheet ID / local CSV "
                             "(default: config.SHEET_URL)")
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

    LOG_DIR.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=LOG_DIR) as staging:
        results = inspect_eval(
            wap_redteam(source=args.source, judge=args.judge),
            model=models,
            epochs=args.epochs,
            limit=args.limit,
            sample_id=[i.strip() for i in args.id.split(",")] if args.id else None,
            log_dir=staging,
            max_connections=8,  # matches static-archive/run_prompts.py MAX_CONCURRENCY
        )
        _sort_logs_by_model(results)


if __name__ == "__main__":
    main()
