"""Run a Petri animal-welfare audit.

Usage:
    python petri/run_audit.py --target openai/gpt-5-mini --limit 3
    python petri/run_audit.py --target anthropic/claude-haiku-4-5 --max-turns 15
"""

import argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent

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
    parser.add_argument("--target", required=True, help="e.g. openai/gpt-5-mini")
    parser.add_argument("--auditor", default="anthropic/claude-sonnet-4-6")
    parser.add_argument("--judge", default="anthropic/claude-opus-4-6")
    parser.add_argument("--seeds", default=str(HERE / "seeds"))
    parser.add_argument("--max-turns", type=int, default=20)
    parser.add_argument("--limit", type=int, default=None, help="cap number of samples")
    args = parser.parse_args()

    builtins_by_name = {d.name: d for d in load_dimensions()}
    dimensions = load_dimensions(HERE / "dimensions") + [
        builtins_by_name[n] for n in BUILTIN_DIMENSIONS
    ]

    eval(
        audit(
            seed_instructions=args.seeds,
            max_turns=args.max_turns,
            judge_dimensions=dimensions,
        ),
        model_roles=dict(
            auditor=args.auditor,
            target=args.target,
            judge=args.judge,
        ),
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
