"""Convert a Google Sheet of red-team questions into the prompts JSON the
static runner expects (and an annotations JSON if the sheet has answer keys).

The sheet must be readable without login — either "Anyone with the link ->
Viewer" or File -> Publish to web. You can pass the normal /edit URL, a
spreadsheet ID, or a local CSV path; the spreadsheet id and gid are parsed
out and the CSV export is fetched automatically.

Expected columns (override with flags): id, category, severity, answer_key,
text. A `technique` column is used if present, otherwise defaults to "direct".

Usage:
    python sync_questions.py "<google-sheet-url>"
    # -> overwrites static-archive/prompts/prompts.json (the default set run_prompts.py uses)
    python static-archive/run_prompts.py
    python score.py results/redteam_results_prompts_<date>.csv
"""

import argparse
import csv
import io
import json
import re
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
import config

PROMPTS_DIR = HERE / "static-archive" / "prompts"


def csv_export_url(src: str) -> str:
    """Turn an /edit URL, publish URL, ID, or export URL into a CSV export URL."""
    if src.startswith("http") and "output=csv" in src or "format=csv" in src:
        return src
    m = re.search(r"/spreadsheets/d/(?:e/)?([A-Za-z0-9_-]+)", src)
    sheet_id = m.group(1) if m else src  # bare ID fallback
    gid_m = re.search(r"[#&?]gid=(\d+)", src)
    gid = gid_m.group(1) if gid_m else "0"
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


def load_rows(src: str) -> list[dict]:
    if not src.startswith("http") and Path(src).exists():
        text = Path(src).read_text(encoding="utf-8")
    else:
        url = csv_export_url(src)
        with urllib.request.urlopen(url, timeout=60) as resp:
            text = resp.read().decode("utf-8")
    if text.lstrip()[:9].lower().startswith("<!doctype") or text.lstrip().startswith("<html"):
        raise SystemExit(
            "Got an HTML page, not CSV — the sheet is not publicly readable.\n"
            "Set sharing to 'Anyone with the link -> Viewer' or Publish to web."
        )
    return list(csv.DictReader(io.StringIO(text)))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", nargs="?", default=config.STATIC_SHEET_URL,
                    help="Google Sheet URL, spreadsheet ID, or local CSV path "
                         "(default: config.STATIC_SHEET_URL)")
    ap.add_argument("--name", default="prompts",
                    help="output basename (default: prompts, i.e. the default set run_prompts.py uses)")
    ap.add_argument("--text-col", default="text")
    ap.add_argument("--id-col", default="id")
    ap.add_argument("--category-col", default="category")
    ap.add_argument("--severity-col", default="severity")
    ap.add_argument("--technique-col", default="technique")
    ap.add_argument("--answer-key-col", default="answer_key")
    ap.add_argument("--id-prefix", default="",
                    help="optional prefix for prompt ids (default: none — use the sheet's own id)")
    args = ap.parse_args()

    rows = load_rows(args.source)
    if not rows:
        raise SystemExit("No rows found in the sheet.")

    prompts, annotations = [], {}
    skipped = 0
    for i, r in enumerate(rows):
        # the sheet has used both `text` and `question` as the prompt column
        text = (r.get(args.text_col) or r.get("question") or "").strip()
        if not text:
            skipped += 1
            continue
        raw_id = (r.get(args.id_col) or str(i)).strip()
        pid = f"{args.id_prefix}{raw_id}"
        sev = (r.get(args.severity_col) or "").strip()
        try:
            sev = int(float(sev)) if sev else ""
        except ValueError:
            pass
        p = {
            "id": pid,
            "category": (r.get(args.category_col) or "").strip(),
            "technique": (r.get(args.technique_col) or "direct").strip() or "direct",
            "severity": sev,
            "prompt": text,
        }
        prompts.append(p)
        key = (r.get(args.answer_key_col) or "").strip()
        if key:
            annotations[pid] = key

    PROMPTS_DIR.mkdir(exist_ok=True)
    out = PROMPTS_DIR / f"{args.name}.json"
    out.write_text(json.dumps(
        {"metadata": {"name": args.name, "source": args.source, "count": len(prompts)},
         "prompts": prompts},
        indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out}  ({len(prompts)} prompts"
          + (f", {skipped} skipped for empty text" if skipped else "") + ")")

    if annotations:
        # For the default "prompts" set, write answer keys to annotations.json
        # (score.py's default) so scoring picks them up with no extra flags.
        ann_name = "annotations" if args.name == "prompts" else f"{args.name}_annotations"
        ann_out = PROMPTS_DIR / f"{ann_name}.json"
        ann_out.write_text(json.dumps({"annotations": annotations}, indent=2, ensure_ascii=False),
                           encoding="utf-8")
        print(f"Wrote {ann_out}  ({len(annotations)} answer keys)")
    else:
        print("No answer keys in the sheet — the scorer will judge from the prompt alone.")

    run_cmd = "python static-archive/run_prompts.py" + ("" if args.name == "prompts" else f" {out}")
    print(f"\nNext:\n  {run_cmd}")


if __name__ == "__main__":
    main()
