"""Inspect AI task for the static animal-welfare red-team suite.

Same prompts and judges as static-archive/run_prompts.py + score.py, but run through the
Inspect framework so every run produces an eval log you can open with
`inspect view` (transcripts, scores, token usage, errors, retries).

The dataset is fetched directly from the Google Sheet in config.SHEET_URL
(same columns as sync_questions.py expects: id, category, text; optional
severity, technique, answer_key). The two judge rubrics are imported from
score.py so they stay a single source of truth — a scored run here is
comparable to a scored CSV from the static pipeline.

The judge is model-dependent by default (see _resolve_judge below): a model
is never graded by a judge from its own family, so Claude models are judged
by config.INSPECT_JUDGE_FOR_CLAUDE instead of config.INSPECT_JUDGE_DEFAULT.
Pass an explicit `judge` to override this for every model in the run.

Usage (or use run_inspect.py for the multi-model convenience wrapper):

    inspect eval redteam.py --model google/gemini-3.5-flash --limit 2
    inspect eval redteam.py --model openai/gpt-5.6-terra --epochs 3
    inspect eval redteam.py -T judge=anthropic/claude-sonnet-5
    inspect eval redteam.py -T source=path/to/local.csv
    inspect view
"""

import config
from score import build_cmep_prompt, build_public_prompt, parse_scores
from sync_questions import load_rows

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.model import GenerateConfig, ModelName, get_model
from inspect_ai.scorer import Score, Scorer, Target, mean, scorer, stderr
from inspect_ai.solver import TaskState, generate

MAX_TOKENS = 6000  # matches static-archive/run_prompts.py

EMPTY_RESPONSE = "(empty response — model returned no content)"


def sheet_dataset(source: str) -> MemoryDataset:
    """Build the dataset from a Google Sheet URL / spreadsheet ID / local CSV."""
    rows = load_rows(source)
    samples = []
    for i, r in enumerate(rows):
        # the sheet has used `text`, `question`, and `prompt` as the prompt
        # column, and `category`/`family` for the category column
        text = (r.get("text") or r.get("question") or r.get("prompt") or "").strip()
        if not text:
            continue
        samples.append(
            Sample(
                id=(r.get("id") or str(i)).strip(),
                input=text,
                # answer_key rides along as the target so scorers receive it
                target=(r.get("answer_key") or "").strip(),
                metadata={
                    "category": (r.get("category") or r.get("family") or "").strip(),
                    "technique": (r.get("technique") or "direct").strip() or "direct",
                    "severity": (r.get("severity") or "").strip(),
                },
            )
        )
    if not samples:
        raise ValueError(f"No prompts with non-empty text found in {source}")
    return MemoryDataset(samples=samples, name="wap-redteam", location=source)


def _response_text(state: TaskState) -> str:
    text = (state.output.completion or "").strip()
    return text if text else EMPTY_RESPONSE


def _resolve_judge(judge: str | None, model: ModelName) -> str:
    """Model-dependent judge: never grade a model with a judge from its own family."""
    if judge:
        return judge
    return config.INSPECT_JUDGE_FOR_CLAUDE if model == "claude" else config.INSPECT_JUDGE_DEFAULT


async def _judge_scores(judge, prompt: str, attempts: int = 3) -> dict:
    """Call the judge and parse its JSON, retrying on unparseable output."""
    last_err = ""
    for _ in range(attempts):
        result = await get_model(judge).generate(prompt)
        try:
            return parse_scores(result.completion)
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}; raw: {result.completion[:200]!r}"
    raise ValueError(f"Judge output unparseable after {attempts} attempts — {last_err}")


@scorer(metrics=[mean(), stderr()])
def public_judge(judge: str | None = None) -> Scorer:
    """Reasonable-person judge — headline `score`, 0.0 worst .. 1.0 ideal."""

    async def score(state: TaskState, target: Target) -> Score:
        annotation = target.text.strip() or None
        prompt = build_public_prompt(state.input_text, _response_text(state), annotation)
        d = await _judge_scores(_resolve_judge(judge, state.model), prompt)
        return Score(
            value=float(d["score"]),
            answer=d.get("pivotal_quote", ""),
            explanation=d.get("rationale", ""),
            metadata={
                "request_class": d.get("request_class", ""),
                "refusal_posture": d.get("refusal_posture", ""),
                "harm_identification": d.get("harm_identification", ""),
                "actionable_harm": d.get("actionable_harm", ""),
                "safe_alternative": d.get("safe_alternative", ""),
                "confidence": d.get("confidence", ""),
                "answer_key_used": "yes" if annotation else "no",
            },
        )

    return score


@scorer(metrics=[mean(), stderr()])
def cmep_judge(judge: str | None = None) -> Scorer:
    """Welfare-principles judge — `cmep_score`, 0.0 worst/violated .. 1.0 best/no violation."""

    async def score(state: TaskState, target: Target) -> Score:
        prompt = build_cmep_prompt(state.input_text, _response_text(state))
        d = await _judge_scores(_resolve_judge(judge, state.model), prompt)
        return Score(
            value=float(d["cmep_score"]),
            explanation=d.get("cmep_rationale", ""),
            metadata={"cmep_applicable": d.get("cmep_applicable", "")},
        )

    return score


@task
def wap_redteam(
    source: str = config.SHEET_URL,
    judge: str | None = None,
) -> Task:
    """Static animal-welfare red-teaming as an Inspect task.

    Args:
        source: Google Sheet URL, spreadsheet ID, or local CSV path.
        judge: Inspect model (provider/model) used by both judges. Defaults
            to None, which picks a judge per-model (see _resolve_judge) so a
            model is never graded by a judge from its own family. Pass an
            explicit model to force the same judge for every model in the run.
    """
    return Task(
        dataset=sheet_dataset(source),
        solver=generate(),
        scorer=[public_judge(judge), cmep_judge(judge)],
        # Temperature is left at provider default: Claude 4.7+ rejects
        # sampling params, and OpenAI reasoning models only allow the default.
        config=GenerateConfig(max_tokens=MAX_TOKENS),
    )
