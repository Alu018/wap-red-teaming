"""Run fixed red-team prompts through a model (static red-teaming).

Usage:
    python static/run_prompts.py --limit 2 --reps 1        # default model: gpt-5.6-terra
    python static/run_prompts.py --model gemini-3.1-flash-lite
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
    # Route by model name: gemini-* goes to Google's OpenAI-compatible
    # endpoint, everything else to OpenAI directly.
    if model.startswith("gemini"):
        return AsyncOpenAI(
            api_key=os.environ["GEMINI_API_KEY"],
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
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
            resp = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt_obj["prompt"]}],
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS,
            )
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run red-team prompts through a model.")
    parser.add_argument("prompts_file", nargs="?", type=Path, default=DEFAULT_PROMPTS_FILE,
                        help=f"Path to prompts JSON (default: {DEFAULT_PROMPTS_FILE})")
    parser.add_argument("--model", default=config.STATIC_MODEL,
                        help="Model to test (gemini-* routes to Google's endpoint, otherwise OpenAI)")
    parser.add_argument("--reps", type=int, default=2, help="Repetitions per prompt")
    parser.add_argument("--limit", type=int, default=None, help="Cap number of prompts")
    args = parser.parse_args()

    prompts = load_prompts(args.prompts_file)
    if args.limit:
        prompts = prompts[: args.limit]
    RESULTS_DIR.mkdir(exist_ok=True)
    stem = args.prompts_file.stem
    date = datetime.now().strftime("%Y%m%d")
    out_path = RESULTS_DIR / f"redteam_results_{stem}_{date}.csv"
    # If a run already exists for this prompts file on this date, fall back to
    # including the time so the earlier run is not overwritten silently.
    if out_path.exists():
        time_suffix = datetime.now().strftime("%H%M%S")
        out_path = RESULTS_DIR / f"redteam_results_{stem}_{date}_{time_suffix}.csv"

    t0 = time.time()
    with out_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        csv_file.flush()
        rows = asyncio.run(run_all(args.model, prompts, args.reps, writer, csv_file))
    elapsed = time.time() - t0

    errors = sum(1 for r in rows if r["error"])
    in_tok = sum(int(r["input_tokens"] or 0) for r in rows)
    out_tok = sum(int(r["output_tokens"] or 0) for r in rows)
    print(f"\nDone in {elapsed:.1f}s. Wrote {len(rows)} rows to {out_path}", flush=True)
    print(f"Errors: {errors}/{len(rows)}", flush=True)
    print(f"Tokens — input: {in_tok:,}  output: {out_tok:,}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
