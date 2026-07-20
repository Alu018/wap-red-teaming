"""Cost estimates + a persistent run cost log.

Prices come from config.PRICING (USD per 1M tokens). Model names are
normalized by stripping any 'provider/' prefix, so 'anthropic/claude-sonnet-5'
and 'claude-sonnet-5' share pricing. Unlisted models report cost as unknown.
All reported costs are ESTIMATES based on the (editable) config prices.

Every run is appended to results/cost_log.csv so you get a running ledger.
"""

import csv
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import config

RESULTS_DIR = HERE.parent / "results"
COST_LOG = RESULTS_DIR / "cost_log.csv"
LOG_FIELDS = ["timestamp", "stage", "model", "n_items", "input_tokens",
              "output_tokens", "cost_usd", "source"]


def price_for(model: str):
    """Return {'in':.., 'out':..} per 1M tokens, or None if unlisted."""
    name = model.split("/", 1)[-1]  # strip provider prefix
    return config.PRICING.get(name) or config.PRICING.get(model)


def estimate(model: str, in_tok: int, out_tok: int):
    """USD estimate, or None if the model has no pricing."""
    p = price_for(model)
    if not p:
        return None
    return (in_tok / 1_000_000) * p["in"] + (out_tok / 1_000_000) * p["out"]


def fmt(usd) -> str:
    if usd is None:
        return "unknown (no pricing in config.PRICING)"
    return f"${usd:,.4f} (est.)"


def log(stage: str, model: str, n_items: int, in_tok: int, out_tok: int, source: str) -> float | None:
    """Print a cost line and append it to results/cost_log.csv. Returns the estimate."""
    usd = estimate(model, in_tok, out_tok)
    print(f"Cost [{stage}] {model}: {fmt(usd)}  "
          f"({in_tok:,} in + {out_tok:,} out tokens over {n_items} items)", flush=True)
    RESULTS_DIR.mkdir(exist_ok=True)
    new = not COST_LOG.exists()
    with COST_LOG.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if new:
            w.writeheader()
        w.writerow({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "stage": stage,
            "model": model,
            "n_items": n_items,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "cost_usd": f"{usd:.6f}" if usd is not None else "",
            "source": source,
        })
    return usd
