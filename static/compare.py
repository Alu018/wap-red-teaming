"""Build a cross-model comparison report from scored results CSVs.

Usage:
    python static/compare.py                      # auto: latest scored CSV per model
    python static/compare.py a_scored.csv b_scored.csv ...

Writes results/comparison_<date>.html (or --out PATH) and prints the path.
Both scores: higher = better (0 worst, 1 best). Public = reasonable-person
acceptability; CMEP = adherence to the welfare principles.
"""

import argparse
import csv
import html
import re
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS_DIR = HERE.parent / "results"


def to_float(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def model_of(path: Path):
    # e.g. redteam_results_prompts_gpt-5.6-terra_20260719_scored -> "gpt-5.6-terra"
    m = re.match(r"redteam_results_prompts_(.+)_\d{8}(?:_\d{6})?_scored$", path.stem)
    return m.group(1) if m else None


def latest_scored_per_model() -> list[Path]:
    best: dict[str, Path] = {}
    for p in RESULTS_DIR.glob("redteam_results_prompts_*_scored.csv"):
        model = model_of(p)
        if not model:  # old model-less runs (no model slug in the name)
            continue
        if model not in best or p.stat().st_mtime > best[model].stat().st_mtime:
            best[model] = p
    return sorted(best.values(), key=model_of)


def load(path: Path) -> dict:
    """Return {model, per_prompt: {id: {...}}, means}."""
    rows = list(csv.DictReader(path.open()))
    per_prompt = {}
    for r in rows:
        base = r["id"].rsplit("_r", 1)[0]
        per_prompt.setdefault(base, []).append(r)
    prompts = {}
    for base, reps in per_prompt.items():
        pubs = [s for s in (to_float(r.get("score")) for r in reps) if s is not None]
        cms = [s for s in (to_float(r.get("cmep_score")) for r in reps) if s is not None]
        rep = reps[0]
        prompts[base] = {
            "category": rep.get("category", ""),
            "prompt": rep.get("prompt", ""),
            "request_class": rep.get("request_class", ""),
            "pub": statistics.mean(pubs) if pubs else None,
            "cmep": statistics.mean(cms) if cms else None,
            "reps": [{
                "response": r.get("response", ""),
                "pub": to_float(r.get("score")),
                "cmep": to_float(r.get("cmep_score")),
                "rationale": r.get("rationale", ""),
                "error": r.get("error", "") or r.get("judge_error", ""),
            } for r in reps],
        }
    errs = sum(1 for r in rows if r.get("judge_error"))
    return {"model": model_of(path), "prompts": prompts, "n": len(prompts), "errors": errs}


def cls(v, higher_bad=False):
    if v is None:
        return "na"
    hi, lo = ("bad", "good") if higher_bad else ("good", "bad")
    return hi if v >= 0.75 else ("mid" if v >= 0.4 else lo)


def render(datasets: list[dict]) -> str:
    esc = lambda s: html.escape(str(s if s is not None else ""))
    models = [d["model"] for d in datasets]

    def mean(d, key, filt=None):
        vals = [p[key] for p in d["prompts"].values()
                if p[key] is not None and (filt is None or filt(p))]
        return statistics.mean(vals) if vals else None

    def cell(v):
        t = f"{v:.2f}" if v is not None else "—"
        return f'<td class="num {cls(v)}">{t}</td>'

    # KPI cards per model
    fmt = lambda v: f"{v:.2f}" if v is not None else "—"
    kpis = ""
    for d in datasets:
        mp, mc = mean(d, "pub"), mean(d, "cmep")
        kpis += (f'<div class="kpi"><div class="mname">{esc(d["model"])}</div>'
                 f'<div class="row"><span>public</span><b class="{cls(mp)}">{fmt(mp)}</b></div>'
                 f'<div class="row"><span>CMEP</span><b class="{cls(mc)}">{fmt(mc)}</b></div>'
                 f'<div class="sub">{d["n"]} prompts · {d["errors"]} judge errors</div></div>')

    # union of prompt ids, ordered by worst avg public score first
    all_ids = sorted({i for d in datasets for i in d["prompts"]},
                     key=lambda i: statistics.mean(
                         [d["prompts"][i]["pub"] for d in datasets
                          if i in d["prompts"] and d["prompts"][i]["pub"] is not None] or [1]))

    # category means table
    cats = sorted({p["category"] for d in datasets for p in d["prompts"].values()})
    cat_head = "".join(f'<th colspan="2">{esc(m)}</th>' for m in models)
    cat_sub = "".join('<th class="num">P</th><th class="num">C</th>' for _ in models)
    cat_rows = ""
    for c in cats:
        cells = ""
        for d in datasets:
            mp = mean(d, "pub", lambda p: p["category"] == c)
            mc = mean(d, "cmep", lambda p: p["category"] == c)
            cells += cell(mp) + cell(mc)
        cat_rows += f'<tr><td>{esc(c)}</td>{cells}</tr>'

    # per-prompt table
    prompt_head = "".join(f'<th colspan="2">{esc(m)}</th>' for m in models)
    prompt_sub = "".join('<th class="num">P</th><th class="num">C</th>' for _ in models)
    prompt_rows = ""
    ncols = 2 + 2 * len(models)
    fmt = lambda v: f"{v:.2f}" if v is not None else "—"
    for i in all_ids:
        ref = next(d["prompts"][i] for d in datasets if i in d["prompts"])
        cells = ""
        for d in datasets:
            p = d["prompts"].get(i)
            cells += (cell(p["pub"]) + cell(p["cmep"])) if p else '<td class="num na">·</td><td class="num na">·</td>'
        q = esc(ref["prompt"][:110]) + ("…" if len(ref["prompt"]) > 110 else "")

        # expandable detail: full prompt + each model's response(s)
        blocks = f'<div class="prompt-box"><b>Prompt.</b> {esc(ref["prompt"])}</div>'
        for d in datasets:
            p = d["prompts"].get(i)
            if not p:
                blocks += (f'<div class="resp-block"><div class="resp-head">{esc(d["model"])}</div>'
                           f'<div class="resp na">(not run on this model)</div></div>')
                continue
            reps_html = ""
            for n, r in enumerate(p["reps"], 1):
                meta = f'rep {n} · public {fmt(r["pub"])} · CMEP {fmt(r["cmep"])}'
                if r["error"]:
                    meta += f' · ERROR: {esc(r["error"][:200])}'
                reps_html += f'<div class="rep-meta">{meta}</div>'
                reps_html += f'<div class="resp">{esc(r["response"]) or "<em>(empty response)</em>"}</div>'
                if r["rationale"]:
                    reps_html += f'<div class="rationale"><b>Judge.</b> {esc(r["rationale"])}</div>'
            blocks += (f'<div class="resp-block"><div class="resp-head">{esc(d["model"])} '
                       f'<span class="scores">public {fmt(p["pub"])} · CMEP {fmt(p["cmep"])}</span></div>'
                       f'{reps_html}</div>')

        prompt_rows += (f'<tr class="prow" onclick="tog(this)"><td class="pid">'
                        f'<span class="chev">▸</span> #{esc(i)}</td><td class="q">'
                        f'<span class="cat">{esc(ref["category"])}</span> {q}</td>{cells}</tr>'
                        f'<tr class="detail"><td colspan="{ncols}">{blocks}</td></tr>')

    date = datetime.now().strftime("%Y-%m-%d")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Model comparison · red-team</title>
<style>
  :root {{ --bg:#faf9f7; --card:#fff; --ink:#1c1b19; --muted:#6b6862; --line:#e7e4de;
    --good:#3d8b5f; --mid:#c98a2b; --bad:#c0483c; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg:#1a1917; --card:#242320; --ink:#eceae5;
    --muted:#a09c94; --line:#35332e; --good:#5fb488; --mid:#d9a94e; --bad:#e0685c; }} }}
  *{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);
    font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
  .wrap{{max-width:1100px;margin:0 auto;padding:32px 20px 80px}}
  h1{{font-size:22px;margin:0 0 4px}} h2{{font-size:14px;text-transform:uppercase;
    letter-spacing:.05em;color:var(--muted);margin:30px 0 10px}}
  .legend{{color:var(--muted);font-size:12px;margin:0 0 20px}}
  .kpis{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:8px}}
  .kpi{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;min-width:180px;flex:1}}
  .mname{{font-weight:650;margin-bottom:8px}}
  .kpi .row{{display:flex;justify-content:space-between;font-variant-numeric:tabular-nums}}
  .kpi .row b{{font-size:16px}} .kpi .sub{{color:var(--muted);font-size:11px;margin-top:8px}}
  table{{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);
    border-radius:10px;overflow:hidden;margin-bottom:8px}}
  th,td{{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;font-size:13px;vertical-align:top}}
  th{{color:var(--muted);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.03em;text-align:center}}
  th:first-child,td:first-child{{text-align:left}}
  td.num{{text-align:center;font-variant-numeric:tabular-nums;width:42px}}
  .good{{color:var(--good)}} .mid{{color:var(--mid)}} .bad{{color:var(--bad);font-weight:650}} .na{{color:var(--muted)}}
  .pid{{font-weight:600;white-space:nowrap}} .q{{color:var(--ink)}} .cat{{color:var(--muted);font-size:11px}}
  tr.prow{{cursor:pointer}} tr.prow:hover td{{background:rgba(127,127,127,.05)}}
  .chev{{display:inline-block;color:var(--muted);transition:transform .15s;font-size:11px}}
  tr.prow.open .chev{{transform:rotate(90deg)}}
  tr.detail{{display:none}} tr.detail.open{{display:table-row}}
  tr.detail>td{{background:rgba(127,127,127,.04);padding:14px 16px}}
  .prompt-box{{background:rgba(127,127,127,.08);border-radius:8px;padding:10px 12px;margin-bottom:12px;font-size:13px}}
  .resp-block{{border:1px solid var(--line);border-radius:8px;padding:10px 12px;margin-bottom:10px;background:var(--card)}}
  .resp-head{{font-weight:650;margin-bottom:6px}} .resp-head .scores{{font-weight:400;color:var(--muted);font-size:12px}}
  .rep-meta{{color:var(--muted);font-size:11px;margin:8px 0 4px;font-variant-numeric:tabular-nums}}
  .resp{{white-space:pre-wrap;font-size:13px}}
  .rationale{{color:var(--muted);font-size:12px;margin-top:6px;border-left:2px solid var(--line);padding-left:8px}}
</style></head><body><div class="wrap">
  <h1>Model comparison</h1>
  <p class="legend">Generated {date}. Both scores 0.00 (worst) → 1.00 (ideal); <b>higher = better</b>.
  <b>P</b> = public (reasonable-person acceptability) · <b>C</b> = CMEP (welfare-principle adherence).
  Green ≥ 0.75, amber ≥ 0.40, red &lt; 0.40. Per-prompt table sorted worst public score first.</p>
  <h2>Overall</h2>
  <div class="kpis">{kpis}</div>
  <h2>Mean score by category</h2>
  <table><thead><tr><th>Category</th>{cat_head}</tr><tr><th></th>{cat_sub}</tr></thead>
  <tbody>{cat_rows}</tbody></table>
  <h2>Per prompt (worst first)</h2>
  <table><thead><tr><th>ID</th><th>Prompt</th>{prompt_head}</tr>
  <tr><th></th><th></th>{prompt_sub}</tr></thead><tbody>{prompt_rows}</tbody></table>
</div>
<script>
function tog(row) {{
  row.classList.toggle('open');
  row.nextElementSibling.classList.toggle('open');
}}
</script>
</body></html>"""


def main():
    ap = argparse.ArgumentParser(description="Cross-model comparison report.")
    ap.add_argument("scored_csvs", nargs="*", type=Path,
                    help="Scored CSVs (default: latest scored per model in results/)")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    paths = args.scored_csvs or latest_scored_per_model()
    if len(paths) < 2:
        raise SystemExit("Need at least 2 scored CSVs to compare. "
                         "Score more models first, or pass files explicitly.")
    datasets = [load(p) for p in paths]
    out = args.out or (RESULTS_DIR / f"comparison_{datetime.now().strftime('%Y%m%d')}.html")
    out.write_text(render(datasets), encoding="utf-8")
    print(f"Compared {len(datasets)} models: {', '.join(d['model'] for d in datasets)}")
    print(f"Wrote {out}\nOpen with:  open {out}")


if __name__ == "__main__":
    main()
