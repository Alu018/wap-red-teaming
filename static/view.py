"""Build a self-contained HTML report from a results CSV.

Usage:
    # Scored CSV -> full report with judge scores
    python static/view.py results/redteam_results_prompts_20260716_scored.csv

    # Raw CSV (no judge columns) -> responses-only report, automatically
    python static/view.py results/redteam_results_prompts_20260716.csv

    # Force responses-only even on a scored CSV (hide the judge in the viewer)
    python static/view.py results/..._scored.csv --responses-only

Writes an .html next to the CSV and prints the path. Open it in any
browser — no server, no external assets.
"""

import argparse
import csv
import html
import statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent


def to_float(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def severity_class(sev: float | None, higher_is_bad: bool = True) -> str:
    # Public score: higher = bad. CMEP: higher = good (pass higher_is_bad=False).
    if sev is None:
        return "na"
    hi, lo = ("bad", "good") if higher_is_bad else ("good", "bad")
    if sev >= 0.75:
        return hi
    if sev >= 0.4:
        return "mid"
    return lo


def aggregate(rows):
    """Collapse reps into per-prompt groups; keep one representative row."""
    by_prompt = defaultdict(list)
    for r in rows:
        base = r["id"].rsplit("_r", 1)[0]
        by_prompt[base].append(r)
    prompts = []
    for base, reps in by_prompt.items():
        sevs = [s for s in (to_float(r.get("score")) for r in reps) if s is not None]
        cmeps = [s for s in (to_float(r.get("cmep_score")) for r in reps) if s is not None]
        rep = reps[0]
        prompts.append({
            "id": base,
            "category": rep.get("category", ""),
            "technique": rep.get("technique", ""),
            "request_class": rep.get("request_class", ""),
            "answer_key": rep.get("answer_key_used", ""),
            "n_reps": len(reps),
            "mean_sev": statistics.mean(sevs) if sevs else None,
            "mean_cmep": statistics.mean(cmeps) if cmeps else None,
            "n_scored": len(sevs),
            "reps": reps,
        })
    return prompts


def render(rows, csv_name, scored):
    prompts = aggregate(rows)
    model = rows[0].get("model", "?") if rows else "?"
    n_err = sum(1 for r in rows if r.get("judge_error")) if scored else 0

    def esc(s):
        return html.escape(str(s or ""))

    # --- KPI strip ---
    if scored:
        scored_ps = [p for p in prompts if p["mean_sev"] is not None]

        def mean_of(ps):
            vals = [p["mean_sev"] for p in ps]
            return statistics.mean(vals) if vals else None

        overall = mean_of(scored_ps)
        cmep_ps = [p for p in prompts if p["mean_cmep"] is not None]
        cmep_mean = statistics.mean([p["mean_cmep"] for p in cmep_ps]) if cmep_ps else None
        o_txt = f"{overall:.2f}" if overall is not None else "—"
        c_txt = f"{cmep_mean:.2f}" if cmep_mean is not None else "—"
        kpis = f"""
        <div class="kpis">
          <div class="kpi"><div class="kpi-num">{len(prompts)}</div><div class="kpi-lab">prompts</div></div>
          <div class="kpi"><div class="kpi-num">{sum(p['n_reps'] for p in prompts)}</div><div class="kpi-lab">responses</div></div>
          <div class="kpi"><div class="kpi-num">{o_txt}</div><div class="kpi-lab">public score (0 worst→1 ideal)</div></div>
          <div class="kpi"><div class="kpi-num">{c_txt}</div><div class="kpi-lab">CMEP score (0 violates→1 upholds)</div></div>
          <div class="kpi"><div class="kpi-num">{n_err}</div><div class="kpi-lab">judge errors</div></div>
        </div>"""
    else:
        n_empty = sum(1 for r in rows if not (r.get("response") or "").strip())
        n_rerr = sum(1 for r in rows if r.get("error"))
        kpis = f"""
        <div class="kpis">
          <div class="kpi"><div class="kpi-num">{len(prompts)}</div><div class="kpi-lab">scenarios</div></div>
          <div class="kpi"><div class="kpi-num">{sum(p['n_reps'] for p in prompts)}</div><div class="kpi-lab">responses</div></div>
          <div class="kpi"><div class="kpi-num">{n_empty}</div><div class="kpi-lab">empty responses</div></div>
          <div class="kpi"><div class="kpi-num">{n_rerr}</div><div class="kpi-lab">request errors</div></div>
        </div>"""

    # --- category table (scored only) ---
    cat_section = ""
    if scored:
        cat_pub = defaultdict(list)
        cat_cmep = defaultdict(list)
        for p in prompts:
            if p["mean_sev"] is not None:
                cat_pub[p["category"]].append(p["mean_sev"])
            if p["mean_cmep"] is not None:
                cat_cmep[p["category"]].append(p["mean_cmep"])
        cat_summary = sorted(((cc, statistics.mean(v), len(v)) for cc, v in cat_pub.items()),
                             key=lambda t: t[1])  # worst public score first (lower = worse)

        def bar(frac, higher_is_bad=True):
            pct = 0 if frac is None else round(frac * 100)
            lbl = "—" if frac is None else f"{frac:.2f}"
            return (f'<div class="bar"><div class="bar-fill {severity_class(frac, higher_is_bad)}" '
                    f'style="width:{pct}%"></div><span class="bar-label">{lbl}</span></div>')

        def cmean(cc):
            v = cat_cmep.get(cc)
            return statistics.mean(v) if v else None

        cat_html = "".join(
            f'<tr><td>{esc(cc)}</td><td class="num">{n}</td>'
            f'<td>{bar(m, higher_is_bad=False)}</td><td>{bar(cmean(cc), higher_is_bad=False)}</td></tr>'
            for cc, m, n in cat_summary
        )
        cat_section = f"""
        <h2>Mean scores by category</h2>
        <table><thead><tr><th>Category</th><th class="num">n</th>
        <th>Public (0 worst→1 ideal)</th><th>CMEP (0 violates→1 upholds)</th></tr></thead>
        <tbody>{cat_html}</tbody></table>"""

    # --- detail cards ---
    if scored:
        order = sorted(prompts, key=lambda p: -(p["mean_sev"] or -1))
    else:
        order = sorted(prompts, key=lambda p: p["id"])

    detail = []
    for p in order:
        reps_html = ""
        for i, r in enumerate(p["reps"]):
            if scored:
                rationale = r.get("rationale") or ""
                quote = r.get("pivotal_quote") or ""
                meta = (f'rep {i+1} · score {esc(r.get("score"))} · '
                        f'{esc(r.get("request_class"))} · '
                        f'refusal {esc(r.get("score_refusal_posture"))} · '
                        f'harm_id {esc(r.get("score_harm_identification"))} · '
                        f'action {esc(r.get("score_actionable_harm"))} · '
                        f'alt {esc(r.get("score_safe_alternative"))} · '
                        f'confidence {esc(r.get("score_confidence"))}'
                        + (f' · ERROR: {esc(r.get("judge_error"))}' if r.get("judge_error") else ''))
                cmep_r = r.get("cmep_rationale") or ""
                meta += (f'<br>cmep {esc(r.get("cmep_score"))} '
                         f'(applicable {esc(r.get("cmep_applicable"))})')
                if rationale:
                    meta += f'<br><span class="rationale">public: {esc(rationale)}</span>'
                if quote:
                    meta += f'<br><span class="quote">“{esc(quote)}”</span>'
                if cmep_r:
                    meta += f'<br><span class="rationale">CMEP: {esc(cmep_r)}</span>'
            else:
                bits = [f'rep {i+1}']
                if r.get("latency_s"):
                    bits.append(f'{esc(r["latency_s"])}s')
                if r.get("output_tokens"):
                    bits.append(f'{esc(r["output_tokens"])} tok')
                if r.get("error"):
                    bits.append(f'ERROR: {esc(r["error"])}')
                meta = " · ".join(bits)
            resp = esc(r.get("response")) or "<em>(empty response)</em>"
            reps_html += f'<div class="rep"><div class="rep-meta">{meta}</div><div class="resp">{resp}</div></div>'

        if scored:
            sev = p["mean_sev"]
            cm = p["mean_cmep"]
            chip = (f'<span class="sev-chip {severity_class(sev, higher_is_bad=False)}" title="public score (0 worst, 1 ideal)">'
                    f'P {f"{sev:.1f}" if sev is not None else "—"}</span>'
                    f'<span class="sev-chip {severity_class(cm, higher_is_bad=False)}" title="CMEP score (0 violates, 1 upholds)">'
                    f'C {f"{cm:.1f}" if cm is not None else "—"}</span>')
            rc_tag = f'<span class="tag">{esc(p["request_class"])}</span>' if p["request_class"] else ''
            data_sev = sev if sev is not None else -1
        else:
            chip = ''
            rc_tag = ''
            data_sev = -1

        # Preview of the first rep's response (collapsed view)
        first_resp = (p["reps"][0].get("response") or "").strip()
        if first_resp:
            preview = first_resp[:240].rsplit(" ", 1)[0] if len(first_resp) > 240 else first_resp
            preview = esc(preview) + ("…" if len(first_resp) > 240 else "")
        else:
            preview = "<em>(empty response)</em>"

        detail.append(f"""
        <div class="card" data-rc="{esc(p['request_class'])}" data-category="{esc(p['category'])}" data-sev="{data_sev}">
          <div class="card-head" onclick="this.parentElement.classList.toggle('open')">
            <div class="card-top">
              {chip}
              <span class="pid">#{esc(p['id'])}</span>
              {rc_tag}
              <span class="tag">{esc(p['category'])}</span>
              <span class="tag muted">{esc(p['technique'])}</span>
              <span class="chev">▾</span>
            </div>
            <div class="question">{esc(p['reps'][0].get('prompt'))}</div>
            <div class="preview">{preview}</div>
          </div>
          <div class="card-body">
            {reps_html}
          </div>
        </div>""")

    categories = sorted({p["category"] for p in prompts})
    cat_opts = "".join(f'<option value="{esc(cc)}">{esc(cc)}</option>' for cc in categories)

    variant_filter = ""
    sort_opts = '<option value="id">Sort: id</option>'
    if scored:
        variant_filter = ('<select id="fvariant" onchange="flt()"><option value="">All request classes</option>'
                          '<option value="legitimate">Legitimate</option>'
                          '<option value="gray">Gray</option>'
                          '<option value="illegitimate">Illegitimate</option></select>')
        sort_opts = ('<option value="sev">Sort: score (worst first)</option>'
                     '<option value="id">Sort: id</option>')
        legend = ('<p class="legend">Two judges score every response; for both, <strong>higher = better</strong> '
                  '(green = good, 0 = worst, 1 = best). '
                  '<strong>P (public)</strong> — reasonable-person acceptability; the judge classifies each request '
                  'legitimate/gray/illegitimate, then scores acceptability (failing to lecture is not penalized). '
                  '<strong>C (CMEP)</strong> — adherence to the animal/AI-welfare principles (0 = ignores/violates, '
                  '1 = fully upholds). Expand a card for both judges\' rationales and the diagnostic dimensions.</p>')
    else:
        legend = ('<p class="legend">Responses-only view — no judge scores. Click any scenario to read the '
                  "model's raw response(s).</p>")

    title_note = "" if scored else " · responses only"
    heading = "Static red-team report" if scored else "Static red-team — responses"

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Red-team{title_note} · {esc(model)}</title>
<style>
  :root {{
    --bg:#faf9f7; --card:#fff; --ink:#1c1b19; --muted:#6b6862; --line:#e7e4de;
    --good:#3d8b5f; --mid:#c98a2b; --bad:#c0483c; --accent:#3a6b8f;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#1a1917; --card:#242320; --ink:#eceae5; --muted:#a09c94; --line:#35332e;
      --good:#5fb488; --mid:#d9a94e; --bad:#e0685c; --accent:#6ba3c9; }}
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
    font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
  .wrap {{ max-width:1000px; margin:0 auto; padding:32px 20px 80px; }}
  h1 {{ font-size:22px; margin:0 0 2px; }}
  .sub {{ color:var(--muted); margin:0 0 24px; font-size:13px; }}
  .kpis {{ display:flex; flex-wrap:wrap; gap:12px; margin-bottom:28px; }}
  .kpi {{ background:var(--card); border:1px solid var(--line); border-radius:10px;
    padding:14px 18px; min-width:120px; flex:1; }}
  .kpi-num {{ font-size:26px; font-weight:650; }}
  .kpi-lab {{ color:var(--muted); font-size:12px; margin-top:2px; }}
  h2 {{ font-size:15px; text-transform:uppercase; letter-spacing:.05em; color:var(--muted);
    margin:32px 0 12px; }}
  table {{ width:100%; border-collapse:collapse; background:var(--card);
    border:1px solid var(--line); border-radius:10px; overflow:hidden; }}
  th,td {{ text-align:left; padding:9px 12px; border-bottom:1px solid var(--line); font-size:14px; }}
  th {{ color:var(--muted); font-weight:600; font-size:12px; text-transform:uppercase; letter-spacing:.04em; }}
  tr:last-child td {{ border-bottom:none; }}
  td.num {{ text-align:right; font-variant-numeric:tabular-nums; width:60px; }}
  .bar {{ position:relative; height:18px; background:var(--line); border-radius:4px; overflow:hidden; min-width:120px; }}
  .bar-fill {{ position:absolute; inset:0 auto 0 0; border-radius:4px; }}
  .bar-fill.good {{ background:var(--good); }} .bar-fill.mid {{ background:var(--mid); }}
  .bar-fill.bad {{ background:var(--bad); }} .bar-fill.na {{ background:var(--muted); }}
  .bar-label {{ position:absolute; right:6px; top:0; line-height:18px; font-size:11px;
    color:var(--ink); font-variant-numeric:tabular-nums; }}
  .controls {{ display:flex; gap:10px; flex-wrap:wrap; margin:8px 0 16px; }}
  select,input {{ font:inherit; padding:7px 10px; border:1px solid var(--line);
    border-radius:8px; background:var(--card); color:var(--ink); }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:10px;
    margin-bottom:8px; }}
  .card-head {{ padding:12px 14px; cursor:pointer; }}
  .card-head:hover {{ background:rgba(127,127,127,.05); }}
  .card-top {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-bottom:6px; }}
  .sev-chip {{ font-weight:650; font-variant-numeric:tabular-nums; padding:2px 8px;
    border-radius:6px; color:#fff; min-width:44px; text-align:center; }}
  .sev-chip.good {{ background:var(--good); }} .sev-chip.mid {{ background:var(--mid); }}
  .sev-chip.bad {{ background:var(--bad); }} .sev-chip.na {{ background:var(--muted); }}
  .pid {{ font-weight:700; font-variant-numeric:tabular-nums; color:var(--accent); }}
  .tag {{ font-size:11px; padding:2px 7px; border-radius:20px; background:rgba(127,127,127,.12);
    color:var(--ink); }}
  .tag.muted {{ color:var(--muted); }}
  .chev {{ margin-left:auto; color:var(--muted); transition:transform .15s; }}
  .card.open .chev {{ transform:rotate(180deg); }}
  .question {{ font-weight:600; font-size:15px; }}
  .preview {{ color:var(--muted); font-size:13px; margin-top:6px;
    display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }}
  .card.open .preview {{ display:none; }}
  .card-body {{ display:none; padding:0 14px 14px; }}
  .card.open .card-body {{ display:block; }}
  .rep {{ border-top:1px dashed var(--line); padding-top:10px; margin-top:10px; }}
  .rep-meta {{ font-size:12px; color:var(--muted); margin-bottom:6px; font-variant-numeric:tabular-nums; }}
  .rep-meta .rationale {{ color:var(--ink); font-style:italic; }}
  .rep-meta .quote {{ color:var(--muted); }}
  .resp {{ white-space:pre-wrap; font-size:14px; }}
  .legend {{ font-size:12px; color:var(--muted); margin-top:6px; }}
</style></head>
<body><div class="wrap">
  <h1>{heading}</h1>
  <p class="sub">Model under test: <strong>{esc(model)}</strong> · source: {esc(csv_name)}</p>
  {kpis}
  {legend}
  {cat_section}

  <h2>{"All prompts" if scored else "All scenarios"}</h2>
  <div class="controls">
    {variant_filter}
    <select id="fcat" onchange="flt()"><option value="">All categories</option>{cat_opts}</select>
    <select id="fsort" onchange="flt()">{sort_opts}</select>
    <input id="fsearch" placeholder="search id / prompt / response…" oninput="flt()">
  </div>
  <div id="cards">{"".join(detail)}</div>
</div>
<script>
const cards = Array.from(document.querySelectorAll('.card'));
function flt() {{
  const vSel = document.getElementById('fvariant');
  const v = vSel ? vSel.value : '';
  const c = fcat.value, s = fsearch.value.toLowerCase(), sort = fsort.value;
  let vis = cards.filter(card => {{
    if (v && card.dataset.rc !== v) return false;
    if (c && card.dataset.category !== c) return false;
    if (s && !card.textContent.toLowerCase().includes(s)) return false;
    return true;
  }});
  cards.forEach(c => c.style.display='none');
  vis.sort((a,b) => sort==='sev'
    ? (a.dataset.sev - b.dataset.sev)
    : a.querySelector('.pid').textContent.localeCompare(b.querySelector('.pid').textContent));
  const box = document.getElementById('cards');
  vis.forEach(c => {{ c.style.display=''; box.appendChild(c); }});
}}
</script>
</body></html>"""


def latest_results_csv() -> Path:
    """Most recently modified results CSV, preferring scored ones."""
    results_dir = HERE.parent / "results"
    csvs = [p for p in results_dir.glob("redteam_results_*.csv")]
    if not csvs:
        raise SystemExit(f"No results CSVs found in {results_dir}. Run static/run_prompts.py first.")
    scored = [p for p in csvs if p.stem.endswith("_scored")]
    pool = scored or csvs
    return max(pool, key=lambda p: p.stat().st_mtime)


def main():
    ap = argparse.ArgumentParser(description="Build an HTML report from a results CSV.")
    ap.add_argument("results_csv", type=Path, nargs="?", default=None,
                    help="Results CSV (default: most recent in results/, preferring scored)")
    ap.add_argument("--responses-only", action="store_true",
                    help="Hide judge scores even if the CSV has them")
    args = ap.parse_args()
    if args.results_csv is None:
        args.results_csv = latest_results_csv()
        print(f"Using latest: {args.results_csv.name}")
    rows = list(csv.DictReader(args.results_csv.open()))
    has_scores = bool(rows) and "score" in rows[0]
    scored = has_scores and not args.responses_only
    if has_scores and args.responses_only:
        out = args.results_csv.with_suffix("").with_suffix(".responses.html")
    else:
        out = args.results_csv.with_suffix(".html")
    out.write_text(render(rows, args.results_csv.name, scored), encoding="utf-8")
    mode = "scored" if scored else "responses-only"
    print(f"Wrote {out}  ({mode})\nOpen with:  open {out}")


if __name__ == "__main__":
    main()
