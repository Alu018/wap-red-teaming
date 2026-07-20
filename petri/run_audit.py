"""Run a Petri animal-welfare audit.

Usage:
    python petri/run_audit.py --limit 3                    # default target: openai/gpt-5.6-terra
    python petri/run_audit.py --target anthropic/claude-haiku-4-5 --max-turns 15
    python petri/run_audit.py --sample-id backyard_slaughter_advice,humane_washing_copy
    python petri/run_audit.py --targets all                 # every model in config.PETRI_TARGETS
"""

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import config

from inspect_ai import eval
from inspect_petri import audit
from inspect_petri._judge.dimensions import load_dimensions

# Built-in dimensions to keep alongside the custom ones. The first four are
# audit-quality checks (high scores mean the audit itself is broken, not the
# target); the rest are behavior dimensions relevant to these seeds.
BUILTIN_DIMENSIONS = [
    "auditor_failure",
    "stuck_in_loops",
    "eval_awareness",
    "scenario_realism",
    "concerning",
    "unprompted_sycophancy",
    "unprompted_deception_toward_user",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default=config.PETRI_TARGET, help="e.g. openai/gpt-5.6-terra")
    parser.add_argument(
        "--targets",
        default=None,
        help="Comma-separated Inspect targets, or 'all' for config.PETRI_TARGETS; "
             "overrides --target and runs one audit per target",
    )
    parser.add_argument("--auditor", default=config.PETRI_AUDITOR)
    parser.add_argument("--judge", default=config.PETRI_JUDGE)
    parser.add_argument("--seeds", default=str(HERE / "seeds"))
    parser.add_argument("--max-turns", type=int, default=20)
    parser.add_argument("--limit", type=int, default=None, help="cap number of samples")
    parser.add_argument(
        "--sample-id",
        default=None,
        help="comma-separated seed names to run, e.g. backyard_slaughter_advice,humane_washing_copy",
    )
    args = parser.parse_args()

    builtins_by_name = {d.name: d for d in load_dimensions()}
    dimensions = load_dimensions(HERE / "dimensions") + [
        builtins_by_name[n] for n in BUILTIN_DIMENSIONS
    ]

    if args.targets == "all":
        targets = config.PETRI_TARGETS
    elif args.targets:
        targets = [t.strip() for t in args.targets.split(",") if t.strip()]
    else:
        targets = [args.target]

    for i, target in enumerate(targets, 1):
        if len(targets) > 1:
            print(f"\n=== Target {i}/{len(targets)}: {target} ===", flush=True)
        eval(
            audit(
                seed_instructions=args.seeds,
                max_turns=args.max_turns,
                judge_dimensions=dimensions,
            ),
            model_roles=dict(
                auditor=args.auditor,
                target=target,
                judge=args.judge,
            ),
            limit=args.limit,
            sample_id=args.sample_id.split(",") if args.sample_id else None,
        )


if __name__ == "__main__":
    main()
