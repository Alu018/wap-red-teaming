"""Run fixed red-team prompts through a model (static red-teaming).

Usage:
    python static/run_prompts.py --limit 2 --reps 1        # default model from config.py
    python static/run_prompts.py --model gemini-3.1-flash-lite
    python static/run_prompts.py --models all              # every model in config.STATIC_MODELS
    python static/run_prompts.py --models gpt-5.6-terra,claude-sonnet-5,gemini-3.5-flash
"""

import argparse
import asyncio
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import config
import cost
DEFAULT_PROMPTS_FILE = HERE / "prompts" / "prompts.json"
RESULTS_DIR = HERE.parent / "results"
MAX_CONCURRENCY = 8
TEMPERATURE = 0.7
MAX_TOKENS = 6000
REQUEST_TIMEOUT = 120

CSV_FIELDS = [
    "id", "model", "category", "technique", "severity",
    "prompt", "response", "error",
    "latency_s", "input_tokens", "output_tokens",
]


def make_client(model: str) -> AsyncOpenAI:
    # Route by model name: gemini-* to Google's OpenAI-compatible endpoint,
    # claude-* to Anthropic's OpenAI-compatible endpoint, everything else
    # to OpenAI directly.
    if model.startswith("gemini"):
        return AsyncOpenAI(
            api_key=os.environ["GEMINI_API_KEY"],
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            timeout=REQUEST_TIMEOUT,
        )
    if model.startswith("claude"):
        return AsyncOpenAI(
            api_key=os.environ["ANTHROPIC_API_KEY"],
            base_url="https://api.anthropic.com/v1/",
            timeout=REQUEST_TIMEOUT,
        )
    return AsyncOpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        timeout=REQUEST_TIMEOUT,
    )


def load_prompts(path: Path) -> list[dict]:
    data = json.loads(path.read_text())
    return data["prompts"]


async def run_one(client: AsyncOpenAI, sem: asyncio.Semaphore, model: str,
                  prompt_obj: dict, counter: dict, writer,
                  writer_lock: asyncio.Lock, csv_file) -> dict:
    async with sem:
        start = time.time()
        row = {
            "id": prompt_obj["id"],
            "model": model,
            "category": prompt_obj.get("category", ""),
            "technique": prompt_obj.get("technique", ""),
            "severity": prompt_obj.get("severity", ""),
            "prompt": prompt_obj["prompt"],
            "response": "",
            "error": "",
            "latency_s": "",
            "input_tokens": "",
            "output_tokens": "",
        }
        try:
            kwargs = dict(
                model=model,
                messages=[{"role": "user", "content": prompt_obj["prompt"]}],
            )
            if model.startswith("gemini"):
                # Google's OpenAI-compatible endpoint takes both.
                kwargs["max_tokens"] = MAX_TOKENS
                kwargs["temperature"] = TEMPERATURE
            elif model.startswith("claude"):
                # Claude 4.7+ reject sampling params (400) — omit temperature.
                kwargs["max_tokens"] = MAX_TOKENS
            else:
                # OpenAI (gpt-5.x): needs max_completion_tokens, and reasoning
                # models only allow the default temperature — omit it.
                kwargs["max_completion_tokens"] = MAX_TOKENS
            resp = await client.chat.completions.create(**kwargs)
            row["response"] = resp.choices[0].message.content or ""
            if resp.usage:
                row["input_tokens"] = resp.usage.prompt_tokens
                row["output_tokens"] = resp.usage.completion_tokens
        except Exception as e:
            row["error"] = f"{type(e).__name__}: {e}"
        row["latency_s"] = round(time.time() - start, 2)
        async with writer_lock:
            counter["done"] += 1
            idx, total = counter["done"], counter["total"]
            writer.writerow(row)
            csv_file.flush()
        status = "OK " if not row["error"] else "ERR"
        print(f"  [{idx:>4}/{total}] [{status}] {model}  {prompt_obj['id']}  ({row['latency_s']}s)", flush=True)
        return row


async def run_all(model: str, prompts: list[dict], reps: int, writer, csv_file) -> list[dict]:
    client = make_client(model)
    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    expanded = []
    for p in prompts:
        for rep in range(1, reps + 1):
            expanded.append({**p, "id": f"{p['id']}_r{rep}"} if reps > 1 else p)
    counter = {"done": 0, "total": len(expanded)}
    writer_lock = asyncio.Lock()
    tasks = [run_one(client, sem, model, p, counter, writer, writer_lock, csv_file)
             for p in expanded]
    print(f"Dispatching {len(tasks)} requests "
          f"({len(prompts)} prompts × {reps} reps × {model}, "
          f"concurrency={MAX_CONCURRENCY})\n", flush=True)
    return await asyncio.gather(*tasks)


def run_model(model: str, prompts: list[dict], reps: int, stem: str) -> Path:
    date = datetime.now().strftime("%Y%m%d")
    slug = model.replace("/", "-")
    out_path = RESULTS_DIR / f"redteam_results_{stem}_{slug}_{date}.csv"
    # If a run already exists for this prompts file on this date, fall back to
    # including the time so the earlier run is not overwritten silently.
    if out_path.exists():
        time_suffix = datetime.now().strftime("%H%M%S")
        out_path = RESULTS_DIR / f"redteam_results_{stem}_{slug}_{date}_{time_suffix}.csv"

    t0 = time.time()
    with out_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        csv_file.flush()
        rows = asyncio.run(run_all(model, prompts, reps, writer, csv_file))
    elapsed = time.time() - t0

    errors = sum(1 for r in rows if r["error"])
    in_tok = sum(int(r["input_tokens"] or 0) for r in rows)
    out_tok = sum(int(r["output_tokens"] or 0) for r in rows)
    print(f"\nDone in {elapsed:.1f}s. Wrote {len(rows)} rows to {out_path}", flush=True)
    print(f"Errors: {errors}/{len(rows)}", flush=True)
    print(f"Tokens — input: {in_tok:,}  output: {out_tok:,}", flush=True)
    cost.log("run", model, len(rows), in_tok, out_tok, out_path.name)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run red-team prompts through one or more models.")
    parser.add_argument("prompts_file", nargs="?", type=Path, default=DEFAULT_PROMPTS_FILE,
                        help=f"Path to prompts JSON (default: {DEFAULT_PROMPTS_FILE})")
    parser.add_argument("--model", default=config.STATIC_MODEL,
                        help="Single model to test (gemini-* -> Google, claude-* -> Anthropic, else OpenAI)")
    parser.add_argument("--models", default=None,
                        help="Comma-separated list of models, or 'all' for config.STATIC_MODELS; "
                             "overrides --model and writes one CSV per model")
    parser.add_argument("--reps", type=int, default=1, help="Repetitions per prompt")
    parser.add_argument("--limit", type=int, default=None, help="Cap number of prompts")
    parser.add_argument("--id", default=None,
                        help="Only run prompts with these ids (comma-separated, e.g. 5 or 5,12,40)")
    args = parser.parse_args()

    if args.models == "all":
        models = config.STATIC_MODELS
    elif args.models:
        models = [m.strip() for m in args.models.split(",") if m.strip()]
    else:
        models = [args.model]

    prompts = load_prompts(args.prompts_file)
    if args.id:
        wanted = [i.strip() for i in args.id.split(",") if i.strip()]
        prompts = [p for p in prompts if p["id"] in wanted]
        missing = [i for i in wanted if i not in {p["id"] for p in prompts}]
        if missing:
            raise SystemExit(f"No prompt(s) with id: {', '.join(missing)}")
    if args.limit:
        prompts = prompts[: args.limit]
    RESULTS_DIR.mkdir(exist_ok=True)

    out_paths = []
    for i, model in enumerate(models, 1):
        if len(models) > 1:
            print(f"\n=== Model {i}/{len(models)}: {model} ===", flush=True)
        out_paths.append(run_model(model, prompts, args.reps, args.prompts_file.stem))

    if len(out_paths) > 1:
        print("\nAll runs complete:", flush=True)
        for p in out_paths:
            print(f"  {p}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
