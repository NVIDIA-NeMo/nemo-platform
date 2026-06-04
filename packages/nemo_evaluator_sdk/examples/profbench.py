# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ProfBench loading, rubric scoring, and runnable agent-eval example."""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import logging
import os
import re
from collections.abc import Awaitable
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote
from urllib.request import Request, urlopen

import nemo_evaluator_sdk.inference as inference
from nemo_evaluator_sdk.agent_eval import (
    AgentEvalAttempt,
    AgentEvalRunConfig,
    AgentEvalRunResult,
    AgentEvalTask,
    AgentEvalTaskResult,
    AgentEvaluator,
    AgentOutput,
)
from nemo_evaluator_sdk.agent_eval.dashboard import write_dashboard as write_sdk_dashboard
from nemo_evaluator_sdk.execution.metric_execution import generate_online_sample
from nemo_evaluator_sdk.metrics.protocol import MetricInput, MetricOutput, MetricOutputSpec, MetricResult
from nemo_evaluator_sdk.values import InferenceParams, Model, RunConfigOnlineModel, SecretRef
from nemo_evaluator_sdk.values.evidence import CandidateEvidence, EvidenceDescriptor
from pydantic import BaseModel, ConfigDict, Field, model_validator

PROFBENCH_DATASET_URL = "https://huggingface.co/datasets/nvidia/ProfBench/resolve/main/test.jsonl"
PROFBENCH_METRIC_TYPE = "profbench_rubric"
PROFBENCH_METRIC_ID = "profbench"
PROFBENCH_DETAILS_OUTPUT = "profbench_details"
PROFBENCH_WEIGHT_POINTS = {
    "Critical": 4.0,
    "Major": 3.0,
    "Minor": 2.0,
    "Additional": 1.0,
}
PROFBENCH_BASELINE_RESPONSES = {
    "o3": "o3_response",
    "r1-0528": "r1-0528_response",
    "grok4": "grok4_response",
}
FULFILLED_PATTERN = re.compile(r"\bfulfilled\s*[:=]\s*(true|false)\b", re.IGNORECASE)
REASON_PATTERN = re.compile(r"\breason\s*[:=]\s*(?P<reason>.*?)(?:\}+\s*)?$", re.IGNORECASE | re.DOTALL)
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "profbench-agent-eval-output"
DEFAULT_MODEL_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
DEFAULT_MODEL_NAME = "nvidia/nemotron-3-nano-30b-a3b"
DEFAULT_API_KEY_SECRET = os.getenv("NMP_EVALUATOR_DEFAULT_API_KEY_SECRET", "NVIDIA_API_KEY")
MAX_JUDGE_REASON_EXCERPT_CHARS = 320
PROFBENCH_JUDGE_STRUCTURED_OUTPUT = {
    "schema": {
        "type": "object",
        "properties": {
            "fulfilled": {"type": "boolean"},
            "reason": {"type": "string"},
        },
        "required": ["fulfilled", "reason"],
        "additionalProperties": False,
    }
}

CriterionType = str | list[str]


class EvidenceLocator(BaseModel):
    """Concrete link to evidence for a score deduction."""

    model_config = ConfigDict(extra="forbid")

    kind: str
    uri: str
    line: int | None = Field(default=None, ge=1)
    json_path: str | None = None
    excerpt: str | None = None
    label: str | None = None

    @model_validator(mode="after")
    def _atif_requires_line(self) -> "EvidenceLocator":
        if self.kind.lower() == "atif" and self.line is None:
            raise ValueError("ATIF evidence locators require a line number")
        return self

    def href(self) -> str:
        """Return a browser-usable evidence link."""
        if self.uri.startswith(("http://", "https://", "atif://")):
            href = self.uri
        elif self.uri.startswith("/"):
            href = Path(self.uri).as_uri()
        else:
            href = quote(self.uri)

        if self.line is None:
            return href
        separator = "&" if "#" in href else "#"
        return f"{href}{separator}L{self.line}"


class ScoreDeduction(BaseModel):
    """Lost points for one failed criterion, with traceable evidence."""

    model_config = ConfigDict(extra="forbid")

    raw_points: float = Field(gt=0)
    normalized_impact: float = Field(ge=0)
    criterion_id: str
    reason: str
    evidence: list[EvidenceLocator] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_evidence(self) -> "ScoreDeduction":
        for locator in self.evidence:
            if locator.kind.lower() == "atif" and locator.line is None:
                raise ValueError("ATIF score deductions require line-resolvable evidence")
        return self


class CriterionScore(BaseModel):
    """Per-criterion scoring result."""

    model_config = ConfigDict(extra="forbid")

    criterion_id: str
    description: str
    criterion_type: CriterionType | None = None
    weight_name: str
    points: float
    fulfilled: bool
    evidence: list[EvidenceLocator] = Field(default_factory=list)
    judge_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProfBenchRubricDetails(BaseModel):
    """ProfBench-specific rubric diagnostics emitted by the example metric."""

    model_config = ConfigDict(extra="forbid")

    score: float = Field(ge=0, le=1)
    earned_points: float = Field(ge=0)
    max_points: float = Field(gt=0)
    model_id: str
    domain: str | None = None
    criterion_scores: list[CriterionScore]
    deductions: list[ScoreDeduction] = Field(default_factory=list)


class ProfBenchCriterion(BaseModel):
    """One ProfBench rubric criterion with source location metadata."""

    model_config = ConfigDict(extra="forbid")

    id: str
    description: str
    weight_name: str
    points: float
    criterion_type: CriterionType | None = None
    source_uri: str
    line_number: int
    json_path: str

    @classmethod
    def from_raw(
        cls,
        *,
        task_id: str,
        index: int,
        raw: dict[str, Any],
        source_uri: str,
        line_number: int,
    ) -> "ProfBenchCriterion":
        weight_name = str(raw.get("criterion_weight", "Minor"))
        return cls(
            id=f"{task_id}:criterion-{index + 1}",
            description=str(raw["criterion_description"]),
            weight_name=weight_name,
            points=PROFBENCH_WEIGHT_POINTS.get(weight_name, 1.0),
            criterion_type=raw.get("criterion_type"),
            source_uri=source_uri,
            line_number=line_number,
            json_path=f"$.rubrics[{index}]",
        )

    def source_locator(self) -> EvidenceLocator:
        return EvidenceLocator(
            kind="profbench",
            uri=self.source_uri,
            line=self.line_number,
            json_path=self.json_path,
            excerpt=self.description,
            label=self.id,
        )


class ProfBenchJudgeRequest(BaseModel):
    """Prompt material passed to a ProfBench rubric judge."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    prompt: str
    response: str
    criterion_id: str
    criterion_description: str
    criterion_type: CriterionType | None = None
    weight_name: str


class ProfBenchJudgeDecision(BaseModel):
    """Yes/No rubric judge decision."""

    model_config = ConfigDict(extra="forbid")

    fulfilled: bool
    reason: str
    raw_response: dict[str, Any] | None = None


class ProfBenchJudge(Protocol):
    """Async rubric judge protocol used by the example metric."""

    def judge(self, request: ProfBenchJudgeRequest) -> Awaitable[ProfBenchJudgeDecision]: ...


class ProfBenchBenchmark(BaseModel):
    """Loaded ProfBench tasks and provided baseline attempts."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    tasks: list[AgentEvalTask]
    attempts: list[AgentEvalAttempt]
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProfBenchModelJudge:
    """Minimal Yes/No LLM judge for ProfBench criteria."""

    def __init__(
        self,
        *,
        model: Model,
        params: RunConfigOnlineModel | None = None,
        inference_fn: inference.InferenceFn | None = None,
        client: Any | None = None,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        self.model = model
        self.params = params or _default_judge_params()
        self.inference_fn = inference_fn or inference.make_inference_request
        self.client = client
        self.default_headers = default_headers

    async def judge(self, request: ProfBenchJudgeRequest) -> ProfBenchJudgeDecision:
        preprocess_hooks, postprocess_hooks = inference.new_hooks(self.params, model_format=self.model.format)
        sample = await generate_online_sample(
            target=self.model,
            row={"prompt": _render_judge_prompt(request)},
            index=0,
            prompt_template={
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a JSON-only evaluator. Return the requested JSON object and no reasoning text.",
                    },
                    {"role": "user", "content": "{{item.prompt}}"},
                ]
            },
            params=self.params,
            inference_fn=self.inference_fn,
            client=self.client,
            preprocess_hooks=preprocess_hooks,
            postprocess_hooks=postprocess_hooks,
            default_headers=self.default_headers,
        )
        text = sample.get("output_text") or ""
        raw_response = sample.get("response")
        return _parse_yes_no_decision(text, raw_response=raw_response if isinstance(raw_response, dict) else None)


class ProfBenchRubricMetric:
    """Score ProfBench attempts and emit evidence-backed point deductions."""

    def __init__(
        self,
        *,
        criteria: list[ProfBenchCriterion],
        judge: ProfBenchJudge | None = None,
        evidence_dir: Path | None = None,
    ) -> None:
        self.criteria = criteria
        self.judge = judge
        self.evidence_dir = evidence_dir

    @property
    def type(self) -> str:
        return PROFBENCH_METRIC_TYPE

    def output_spec(self) -> list[MetricOutputSpec]:
        return [
            MetricOutputSpec.continuous_score(PROFBENCH_METRIC_ID),
            MetricOutputSpec.model(PROFBENCH_DETAILS_OUTPUT, ProfBenchRubricDetails),
        ]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        details = await self._score(input)
        return MetricResult(
            outputs=[
                MetricOutput(name=PROFBENCH_METRIC_ID, value=details.score),
                MetricOutput(name=PROFBENCH_DETAILS_OUTPUT, value=details),
            ]
        )

    async def _score(self, input: MetricInput) -> ProfBenchRubricDetails:
        if not self.criteria:
            raise ValueError("ProfBench metric requires at least one criterion")

        fulfilments = _baseline_fulfilments(input.candidate.metadata)
        output_text = input.candidate.output_text
        if output_text is None:
            raise ValueError("ProfBench attempt has no output_text to score")

        earned_points = 0.0
        max_points = sum(criterion.points for criterion in self.criteria)
        criterion_scores: list[CriterionScore] = []
        deductions: list[ScoreDeduction] = []

        for criterion in self.criteria:
            source_locator = criterion.source_locator()
            judge_locator: EvidenceLocator | None = None
            judge_reason: str | None = None
            score_source = "dataset_label"

            if criterion.id in fulfilments:
                fulfilled = fulfilments[criterion.id]
            else:
                if self.judge is None:
                    raise ValueError("ProfBench candidate scoring requires a judge when dataset labels are absent")
                score_source = "judge"
                inputs = input.row.data.get("inputs", {})
                task = input.row.data.get("task", {})
                judge_request = ProfBenchJudgeRequest(
                    task_id=str(task.get("id", "")) if isinstance(task, dict) else "",
                    prompt=str(inputs.get("prompt", "")) if isinstance(inputs, dict) else "",
                    response=output_text,
                    criterion_id=criterion.id,
                    criterion_description=criterion.description,
                    criterion_type=criterion.criterion_type,
                    weight_name=criterion.weight_name,
                )
                decision = await self.judge.judge(judge_request)
                fulfilled = decision.fulfilled
                judge_reason = decision.reason
                judge_locator = self._write_judge_artifact(
                    task_id=str(task.get("id", "")) if isinstance(task, dict) else "",
                    attempt_id=str(input.candidate.metadata.get("attempt_id", "attempt")),
                    criterion_id=criterion.id,
                    request=judge_request,
                    decision=decision,
                )

            evidence = [source_locator]
            if judge_locator is not None:
                evidence.append(judge_locator)

            if fulfilled:
                earned_points += criterion.points
            else:
                deductions.append(
                    ScoreDeduction(
                        raw_points=criterion.points,
                        normalized_impact=criterion.points / max_points,
                        criterion_id=criterion.id,
                        reason=f"Criterion was not fulfilled: {criterion.description}",
                        evidence=evidence,
                        metadata={
                            "weight_name": criterion.weight_name,
                            "criterion_type": criterion.criterion_type,
                            "score_source": score_source,
                        },
                    )
                )

            criterion_scores.append(
                CriterionScore(
                    criterion_id=criterion.id,
                    description=criterion.description,
                    criterion_type=criterion.criterion_type,
                    weight_name=criterion.weight_name,
                    points=criterion.points,
                    fulfilled=fulfilled,
                    evidence=evidence,
                    judge_reason=judge_reason,
                    metadata={"score_source": score_source},
                )
            )

        model_id = str(
            input.candidate.metadata.get("model_id") or input.candidate.metadata.get("target_name") or "candidate"
        )
        inputs = input.row.data.get("inputs", {})
        domain = inputs.get("domain") if isinstance(inputs, dict) else None
        return ProfBenchRubricDetails(
            score=earned_points / max_points,
            earned_points=earned_points,
            max_points=max_points,
            model_id=model_id,
            domain=domain if isinstance(domain, str) else None,
            criterion_scores=criterion_scores,
            deductions=deductions,
        )

    def _write_judge_artifact(
        self,
        *,
        task_id: str,
        attempt_id: str,
        criterion_id: str,
        request: ProfBenchJudgeRequest,
        decision: ProfBenchJudgeDecision,
    ) -> EvidenceLocator | None:
        if self.evidence_dir is None:
            return None

        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        file_name = _safe_artifact_name(f"judge-{task_id}-{attempt_id}-{criterion_id}.json")
        path = self.evidence_dir / file_name
        path.write_text(
            json.dumps(
                {
                    "request": request.model_dump(mode="json"),
                    "decision": decision.model_dump(mode="json"),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return EvidenceLocator(kind="judge", uri=str(path), line=1, json_path="$.decision", excerpt=decision.reason)


def load_profbench(
    source: str | Path = PROFBENCH_DATASET_URL,
    *,
    limit: int | None = None,
    judge: ProfBenchJudge | None = None,
    evidence_dir: Path | None = None,
    include_cached_fulfilments: bool = True,
) -> ProfBenchBenchmark:
    """Load ProfBench from local JSONL or the Hugging Face raw URL."""
    source_uri, lines, metadata = _read_jsonl_source(source)
    tasks: list[AgentEvalTask] = []
    attempts: list[AgentEvalAttempt] = []

    for line_number, line in lines[:limit]:
        row = json.loads(line)
        task_id = str(row["task_id"])
        criteria = [
            ProfBenchCriterion.from_raw(
                task_id=task_id,
                index=index,
                raw=raw_rubric,
                source_uri=source_uri,
                line_number=line_number,
            )
            for index, raw_rubric in enumerate(row["rubrics"])
        ]
        task = AgentEvalTask(
            id=task_id,
            intent=str(row["prompt"]),
            inputs={"prompt": row["prompt"], "domain": row.get("domain")},
            metrics=[ProfBenchRubricMetric(criteria=criteria, judge=judge, evidence_dir=evidence_dir)],
            metadata={
                "benchmark": "ProfBench",
                "domain": row.get("domain"),
                "profbench_task_id": task_id,
                "source_uri": source_uri,
                "line_number": line_number,
            },
        )
        tasks.append(task)
        attempts.extend(
            _recorded_attempts(
                row=row,
                task_id=task_id,
                criteria=criteria,
                source_uri=source_uri,
                include_cached_fulfilments=include_cached_fulfilments,
            )
        )

    metadata.update(
        {
            "benchmark": "ProfBench",
            "dataset_url": PROFBENCH_DATASET_URL,
            "source": source_uri,
            "record_count": len(tasks),
            "baseline_models": sorted(PROFBENCH_BASELINE_RESPONSES),
        }
    )
    return ProfBenchBenchmark(tasks=tasks, attempts=attempts, metadata=metadata)


def profbench_details(output: MetricOutput) -> ProfBenchRubricDetails | None:
    """Return ProfBench details for a metric output, if present."""
    if output.name != PROFBENCH_DETAILS_OUTPUT:
        return None
    if isinstance(output.value, ProfBenchRubricDetails):
        return output.value
    return ProfBenchRubricDetails.model_validate(output.value)


def write_profbench_dashboard(result: AgentEvalRunResult, output_path: str | Path) -> Path:
    """Write the ProfBench-specific HTML report for an example run."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_profbench_dashboard(result), encoding="utf-8")
    return path


def write_example_dashboards(result: AgentEvalRunResult, output_dir: str | Path) -> tuple[Path, Path, Path]:
    """Write generic SDK and ProfBench-specific dashboards for this example."""
    path = Path(output_dir)
    sdk_dashboard_path = write_sdk_dashboard(result, path / "sdk-report.html")
    profbench_dashboard_path = write_profbench_dashboard(result, path / "profbench-report.html")
    default_dashboard_path = write_profbench_dashboard(result, path / "report.html")
    return sdk_dashboard_path, profbench_dashboard_path, default_dashboard_path


def render_profbench_dashboard(result: AgentEvalRunResult) -> str:
    """Render a ProfBench-aware HTML report from generic agent-eval results."""
    rows = _profbench_result_rows(result.results)
    data_json = json.dumps(result.model_dump(mode="json"), sort_keys=True)
    overall = _format_percent(result.summary.overall_score)
    top_deductions = sorted(
        ((task_result, details, deduction) for task_result, details in rows for deduction in details.deductions),
        key=lambda item: item[2].normalized_impact,
        reverse=True,
    )[:25]

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_e(result.run_id)} ProfBench Report</title>
  <style>
    :root {{ color-scheme: light dark; --bg:#f7f8fa; --fg:#15171a; --muted:#667085; --line:#d0d5dd; --panel:#fff; --accent:#0f766e; --bad:#b42318; --soft:#f8fafc; }}
    @media (prefers-color-scheme: dark) {{ :root {{ --bg:#111418; --fg:#f3f4f6; --muted:#a4aebc; --line:#30363d; --panel:#1b2027; --accent:#5eead4; --bad:#ff8a80; --soft:#151a21; }} }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--fg); font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
    header {{ padding:28px 32px 20px; border-bottom:1px solid var(--line); background:var(--panel); }}
    h1 {{ margin:0 0 8px; font-size:28px; letter-spacing:0; }}
    h2 {{ margin:28px 0 12px; font-size:18px; letter-spacing:0; }}
    main {{ max-width:1280px; margin:0 auto; padding:24px 32px 48px; }}
    .hero {{ display:flex; gap:24px; align-items:flex-end; flex-wrap:wrap; }}
    .score {{ font-size:54px; font-weight:700; line-height:1; color:var(--accent); }}
    .muted {{ color:var(--muted); }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:12px; }}
    .card {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:14px; }}
    .card strong {{ display:block; font-size:22px; margin-top:6px; }}
    table {{ width:100%; border-collapse:collapse; background:var(--panel); border:1px solid var(--line); }}
    th, td {{ padding:9px 10px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
    th {{ font-size:12px; text-transform:uppercase; color:var(--muted); background:var(--soft); }}
    tr:last-child td {{ border-bottom:0; }}
    .deduction {{ color:var(--bad); font-weight:600; }}
    .pass {{ color:var(--accent); font-weight:600; }}
    .fail {{ color:var(--bad); font-weight:600; }}
    .toolbar {{ display:flex; gap:8px; margin:16px 0; flex-wrap:wrap; }}
    input, select, button {{ border:1px solid var(--line); border-radius:6px; padding:8px 10px; background:var(--panel); color:var(--fg); }}
    button {{ cursor:pointer; }}
    details {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; margin:10px 0; }}
    summary {{ padding:12px 14px; cursor:pointer; }}
    details table {{ border:0; border-top:1px solid var(--line); }}
    a {{ color:var(--accent); }}
    code {{ background:var(--soft); border-radius:4px; padding:1px 4px; }}
    .chips {{ display:flex; flex-wrap:wrap; gap:6px; }}
    .chip {{ border:1px solid var(--line); border-radius:999px; padding:2px 8px; color:var(--muted); text-decoration:none; }}
  </style>
</head>
<body>
<header>
  <div class="hero">
    <div>
      <h1>ProfBench Agent Eval Report</h1>
      <div class="muted">Run {_e(result.run_id)} · {_e(result.summary.task_count)} tasks · {_e(result.summary.attempt_count)} attempts</div>
    </div>
    <div class="score">{overall}</div>
  </div>
</header>
<main>
  <section>
    <div class="grid">
      {_cards("Model Scores", _scores_by_model(rows))}
      {_cards("Domain Scores", _scores_by_domain(rows))}
      {_cards("Criterion Fulfilment", _criterion_fulfilment(rows))}
      <div class="card"><span class="muted">Deductions</span><strong>{_e(_deduction_count(rows))}</strong></div>
    </div>
  </section>
  <section>
    <h2>Highest-Impact Failures</h2>
    <div class="toolbar">
      <input id="filter" placeholder="Filter task, model, reason">
      <select id="modelFilter"><option value="">All models</option>{_model_options(rows)}</select>
      <button id="exportJson">Export JSON</button>
    </div>
    <table id="deductions">
      <thead><tr><th>Task</th><th>Model</th><th>Lost</th><th>Criterion</th><th>Reason</th><th>Evidence</th></tr></thead>
      <tbody>{_deduction_rows(top_deductions)}</tbody>
    </table>
  </section>
  <section>
    <h2>Task Details</h2>
    {_task_details(rows)}
  </section>
</main>
<script id="run-data" type="application/json">{html.escape(data_json)}</script>
<script>
const data = JSON.parse(document.getElementById("run-data").textContent);
const filter = document.getElementById("filter");
const modelFilter = document.getElementById("modelFilter");
function applyFilters() {{
  const query = filter.value.toLowerCase();
  const model = modelFilter.value;
  for (const row of document.querySelectorAll("#deductions tbody tr")) {{
    const matchesQuery = !query || row.textContent.toLowerCase().includes(query);
    const matchesModel = !model || row.dataset.model === model;
    row.style.display = matchesQuery && matchesModel ? "" : "none";
  }}
}}
filter.addEventListener("input", applyFilters);
modelFilter.addEventListener("change", applyFilters);
document.getElementById("exportJson").addEventListener("click", () => {{
  const blob = new Blob([JSON.stringify(data, null, 2)], {{type: "application/json"}});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${{data.run_id}}.json`;
  link.click();
  URL.revokeObjectURL(url);
}});
</script>
</body>
</html>
"""


def _profbench_result_rows(
    results: list[AgentEvalTaskResult],
) -> list[tuple[AgentEvalTaskResult, ProfBenchRubricDetails]]:
    rows: list[tuple[AgentEvalTaskResult, ProfBenchRubricDetails]] = []
    for task_result in results:
        for output in task_result.outputs:
            details = profbench_details(output)
            if details is not None:
                rows.append((task_result, details))
    return rows


def _cards(title: str, values: dict[str, float]) -> str:
    if not values:
        return f'<div class="card"><span class="muted">{_e(title)}</span><strong>n/a</strong></div>'
    return "".join(
        f'<div class="card"><span class="muted">{_e(title)} · {_e(name)}</span><strong>{_format_percent(score)}</strong></div>'
        for name, score in sorted(values.items())
    )


def _scores_by_model(rows: list[tuple[AgentEvalTaskResult, ProfBenchRubricDetails]]) -> dict[str, float]:
    values: dict[str, list[float]] = {}
    for _, details in rows:
        values.setdefault(details.model_id, []).append(details.score)
    return _mean_by_key(values)


def _scores_by_domain(rows: list[tuple[AgentEvalTaskResult, ProfBenchRubricDetails]]) -> dict[str, float]:
    values: dict[str, list[float]] = {}
    for _, details in rows:
        values.setdefault(details.domain or "unknown", []).append(details.score)
    return _mean_by_key(values)


def _criterion_fulfilment(rows: list[tuple[AgentEvalTaskResult, ProfBenchRubricDetails]]) -> dict[str, float]:
    values: dict[str, list[float]] = {}
    for _, details in rows:
        for criterion in details.criterion_scores:
            for criterion_type in _criterion_type_labels(criterion.criterion_type):
                values.setdefault(criterion_type, []).append(1.0 if criterion.fulfilled else 0.0)
    return _mean_by_key(values)


def _deduction_count(rows: list[tuple[AgentEvalTaskResult, ProfBenchRubricDetails]]) -> int:
    return sum(len(details.deductions) for _, details in rows)


def _model_options(rows: list[tuple[AgentEvalTaskResult, ProfBenchRubricDetails]]) -> str:
    models = sorted({details.model_id for _, details in rows})
    return "".join(f'<option value="{_e(model)}">{_e(model)}</option>' for model in models)


def _deduction_rows(
    rows: list[tuple[AgentEvalTaskResult, ProfBenchRubricDetails, ScoreDeduction]],
) -> str:
    rendered = []
    for task_result, details, deduction in rows:
        rendered.append(
            "<tr "
            f'data-model="{_e(details.model_id)}">'
            f"<td>{_e(task_result.task_id)}</td>"
            f"<td>{_e(details.model_id)}</td>"
            f'<td class="deduction">{deduction.raw_points:g}</td>'
            f"<td>{_e(deduction.criterion_id)}</td>"
            f"<td>{_e(deduction.reason)}</td>"
            f"<td>{_evidence_links(deduction.evidence)}</td>"
            "</tr>"
        )
    return "".join(rendered)


def _task_details(rows: list[tuple[AgentEvalTaskResult, ProfBenchRubricDetails]]) -> str:
    rendered = []
    for task_result, details in rows:
        criterion_rows = "".join(
            "<tr>"
            f"<td>{_e(criterion.criterion_id)}</td>"
            f"<td>{_e(criterion.weight_name)}</td>"
            f"<td>{_e(_criterion_type_label(criterion.criterion_type))}</td>"
            f"<td>{criterion.points:g}</td>"
            f'<td class="{"pass" if criterion.fulfilled else "fail"}">{"yes" if criterion.fulfilled else "no"}</td>'
            f"<td>{_e(criterion.description)}</td>"
            f"<td>{_e(criterion.metadata.get('score_source', ''))}</td>"
            f"<td>{_e(criterion.judge_reason or '')}</td>"
            f"<td>{_evidence_links(criterion.evidence)}</td>"
            "</tr>"
            for criterion in details.criterion_scores
        )
        rendered.append(
            "<details>"
            f"<summary>{_e(task_result.task_id)} · {_e(details.model_id)} · {_format_percent(details.score)}</summary>"
            "<table><thead><tr><th>Criterion</th><th>Weight</th><th>Type</th><th>Points</th>"
            "<th>Fulfilled</th><th>Description</th><th>Source</th><th>Reason</th><th>Evidence</th></tr></thead>"
            f"<tbody>{criterion_rows}</tbody></table>"
            "</details>"
        )
    return "".join(rendered)


def _evidence_links(locators: list[EvidenceLocator]) -> str:
    if not locators:
        return ""
    return '<div class="chips">' + "".join(_evidence_link(locator) for locator in locators) + "</div>"


def _evidence_link(locator: EvidenceLocator) -> str:
    label = locator.label or locator.kind
    if locator.line is not None:
        label = f"{label}:L{locator.line}"
    if locator.json_path:
        label = f"{label} {locator.json_path}"
    return f'<a class="chip" href="{_e(locator.href())}">{_e(label)}</a>'


def _mean_by_key(values: dict[str, list[float]]) -> dict[str, float]:
    return {key: _mean(scores) for key, scores in values.items()}


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _format_percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def _criterion_type_label(value: CriterionType | None) -> str:
    return ", ".join(_criterion_type_labels(value))


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def configure_example_logging() -> None:
    """Enable SDK progress logs when this example file is executed directly."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("nemo_evaluator_sdk.inference").setLevel(logging.WARNING)


async def run_profbench_baseline_example(*, limit: int | None) -> None:
    """Score the ProfBench baseline model responses bundled in the dataset."""
    _print_example_separator(run_profbench_baseline_example.__name__)

    output_dir = _profbench_output_dir("baseline")
    benchmark = load_profbench(_profbench_source(), limit=limit, evidence_dir=output_dir / "evidence")
    result = await AgentEvaluator().run(
        tasks=benchmark.tasks,
        attempts=benchmark.attempts,
        config=AgentEvalRunConfig(
            output_dir=output_dir,
            benchmark=benchmark.metadata,
            write_dashboard=False,
        ),
    )
    sdk_dashboard_path, profbench_dashboard_path, default_dashboard_path = write_example_dashboards(result, output_dir)

    print(f"ProfBench tasks: {result.summary.task_count}")
    print(f"ProfBench attempts: {result.summary.attempt_count}")
    print(f"Overall score: {result.summary.overall_score:.3f}" if result.summary.overall_score is not None else "n/a")
    print(f"Metric scores: {result.summary.metric_scores}")
    print(f"SDK dashboard: {sdk_dashboard_path}")
    print(f"ProfBench dashboard: {profbench_dashboard_path}")
    print(f"Default dashboard: {default_dashboard_path}")


async def run_profbench_live_judge_example(*, limit: int | None) -> None:
    """Score the recorded ProfBench responses with a live LLM judge."""
    _print_example_separator(run_profbench_live_judge_example.__name__)

    model = _example_model()
    output_dir = _profbench_output_dir("live-judge")
    benchmark = load_profbench(
        _profbench_source(),
        limit=limit,
        judge=ProfBenchModelJudge(model=model),
        evidence_dir=output_dir / "evidence",
        include_cached_fulfilments=False,
    )

    result = await AgentEvaluator().run(
        tasks=benchmark.tasks,
        attempts=benchmark.attempts,
        config=AgentEvalRunConfig(
            output_dir=output_dir,
            benchmark={**benchmark.metadata, "score_source": "live_judge"},
            write_dashboard=False,
        ),
    )
    sdk_dashboard_path, profbench_dashboard_path, default_dashboard_path = write_example_dashboards(result, output_dir)

    print(f"ProfBench tasks: {result.summary.task_count}")
    print(f"Recorded attempts judged: {result.summary.attempt_count}")
    print(f"Live judge score: {result.summary.metric_scores}")
    print(f"SDK dashboard: {sdk_dashboard_path}")
    print(f"ProfBench dashboard: {profbench_dashboard_path}")
    print(f"Default dashboard: {default_dashboard_path}")


async def run_profbench_live_candidate_example(*, limit: int | None) -> None:
    """Generate fresh ProfBench responses from a model and score them with a judge."""
    _print_example_separator(run_profbench_live_candidate_example.__name__)

    model = _example_model()
    output_dir = _profbench_output_dir("live-candidate")
    params = RunConfigOnlineModel(
        parallelism=2,
        inference=InferenceParams(temperature=0.0, max_tokens=4096),
    )
    benchmark = load_profbench(
        _profbench_source(),
        limit=limit,
        judge=ProfBenchModelJudge(model=model),
        evidence_dir=output_dir / "evidence",
        include_cached_fulfilments=False,
    )

    result = await AgentEvaluator().run(
        tasks=benchmark.tasks,
        target=model,
        config=AgentEvalRunConfig(
            output_dir=output_dir,
            params=params,
            benchmark={**benchmark.metadata, "score_source": "fresh_candidate_and_live_judge"},
            write_dashboard=False,
        ),
    )
    sdk_dashboard_path, profbench_dashboard_path, default_dashboard_path = write_example_dashboards(result, output_dir)

    print(f"ProfBench tasks: {result.summary.task_count}")
    print(f"Live model score: {result.summary.metric_scores}")
    print(f"SDK dashboard: {sdk_dashboard_path}")
    print(f"ProfBench dashboard: {profbench_dashboard_path}")
    print(f"Default dashboard: {default_dashboard_path}")


async def run_examples(*, limit: int | None, run_live_judge: bool, run_live_candidate: bool) -> None:
    """Execute the ProfBench agent-eval examples."""
    await run_profbench_baseline_example(limit=limit)

    if run_live_judge:
        await run_profbench_live_judge_example(limit=limit)
    else:
        print("Skipping live ProfBench judge example. Pass --run-live-judge to run it.")

    if run_live_candidate:
        await run_profbench_live_candidate_example(limit=limit)
    else:
        print("Skipping live ProfBench candidate example. Pass --run-live-candidate to run it.")


def _recorded_attempts(
    *,
    row: dict[str, Any],
    task_id: str,
    criteria: list[ProfBenchCriterion],
    source_uri: str,
    include_cached_fulfilments: bool,
) -> list[AgentEvalAttempt]:
    attempts: list[AgentEvalAttempt] = []
    for model_id, response_field in PROFBENCH_BASELINE_RESPONSES.items():
        response_text = row.get(response_field)
        if not isinstance(response_text, str):
            continue

        metadata: dict[str, Any] = {
            "attempt_id": f"{task_id}:{model_id}",
            "model_id": model_id,
            "profbench_response_field": response_field,
        }
        if include_cached_fulfilments:
            metadata["profbench_fulfilments"] = {
                criterion.id: _coerce_bool(row["rubrics"][index].get(f"{model_id}_fulfilment"))
                for index, criterion in enumerate(criteria)
            }

        attempts.append(
            AgentEvalAttempt(
                id=f"{task_id}:{model_id}",
                task_id=task_id,
                output=AgentOutput(text=response_text),
                evidence=CandidateEvidence(
                    descriptors={
                        "source": EvidenceDescriptor(
                            kind="profbench",
                            ref=source_uri,
                            format="jsonl",
                            metadata={"task_id": task_id, "response_field": response_field},
                        )
                    }
                ),
                metadata=metadata,
            )
        )
    return attempts


def _profbench_source() -> str:
    return os.getenv("NEMO_EVALUATOR_PROFBENCH_SOURCE", PROFBENCH_DATASET_URL)


def _profbench_limit_from_args(limit: int) -> int | None:
    return None if limit == 0 else limit


def _profbench_output_dir(suffix: str) -> Path:
    root = Path(os.getenv("NEMO_EVALUATOR_PROFBENCH_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR)))
    return root / suffix


def _example_model() -> Model:
    return Model(
        url=os.getenv("NEMO_EVALUATOR_PROFBENCH_MODEL_URL", DEFAULT_MODEL_URL),
        name=os.getenv("NEMO_EVALUATOR_PROFBENCH_MODEL", DEFAULT_MODEL_NAME),
        api_key_secret=SecretRef(root=DEFAULT_API_KEY_SECRET),
    )


def _print_example_separator(name: str) -> None:
    edge = "====="
    middle_line = f"{edge} {name} {edge}"
    rule = "=" * len(middle_line)
    print(f"\n{rule}\n{middle_line}\n{rule}\n")


def _baseline_fulfilments(metadata: dict[str, Any]) -> dict[str, bool]:
    raw = metadata.get("profbench_fulfilments")
    if not isinstance(raw, dict):
        return {}
    return {str(key): _coerce_bool(value) for key, value in raw.items()}


def _read_jsonl_source(source: str | Path) -> tuple[str, list[tuple[int, str]], dict[str, Any]]:
    source_text = str(source)
    if source_text.startswith(("http://", "https://")):
        request = Request(source_text, headers={"User-Agent": "nemo-evaluator-sdk"})
        with urlopen(request, timeout=60) as response:
            body = response.read().decode("utf-8")
            headers = dict(response.headers.items())
        metadata = {
            "etag": headers.get("ETag"),
            "resolved_commit": headers.get("x-repo-commit"),
        }
        lines = [(index, line) for index, line in enumerate(body.splitlines(), start=1) if line.strip()]
        return source_text, lines, metadata

    path = Path(source).expanduser().resolve()
    raw_lines = path.read_text(encoding="utf-8").splitlines()
    lines = [(index, line) for index, line in enumerate(raw_lines, start=1) if line.strip()]
    return str(path), lines, {"source_file": str(path)}


def _render_judge_prompt(request: ProfBenchJudgeRequest) -> str:
    criterion_type = request.criterion_type
    if isinstance(criterion_type, list):
        criterion_type_text = ", ".join(str(value) for value in criterion_type)
    else:
        criterion_type_text = str(criterion_type or "unspecified")

    return (
        "You are judging whether a professional benchmark response satisfies one rubric criterion.\n"
        "Return only a compact JSON object with keys `fulfilled` (boolean) and `reason` (string). "
        "Do not include markdown, analysis, or explanatory text outside the JSON object.\n\n"
        f"Task prompt:\n{request.prompt}\n\n"
        f"Candidate response:\n{request.response}\n\n"
        f"Criterion id: {request.criterion_id}\n"
        f"Criterion type: {criterion_type_text}\n"
        f"Criterion weight: {request.weight_name}\n"
        f"Criterion:\n{request.criterion_description}\n"
    )


def _parse_yes_no_decision(text: str, *, raw_response: dict[str, Any] | None = None) -> ProfBenchJudgeDecision:
    stripped = text.strip()
    parsed = _parse_json_object(stripped)
    if parsed is None:
        lowered = stripped.lower()
        if lowered.startswith("yes") or '"fulfilled": true' in lowered or "'fulfilled': true" in lowered:
            return ProfBenchJudgeDecision(fulfilled=True, reason=stripped, raw_response=raw_response)
        if lowered.startswith("no") or '"fulfilled": false' in lowered or "'fulfilled': false" in lowered:
            return ProfBenchJudgeDecision(fulfilled=False, reason=stripped, raw_response=raw_response)
        loose_match = FULFILLED_PATTERN.search(stripped)
        if loose_match is not None:
            reason_match = REASON_PATTERN.search(stripped)
            reason = reason_match.group("reason").strip() if reason_match is not None else stripped
            return ProfBenchJudgeDecision(
                fulfilled=loose_match.group(1).lower() == "true",
                reason=reason,
                raw_response=raw_response,
            )
        return _unparseable_judge_decision(
            "Judge response was not parseable as JSON or Yes/No",
            stripped,
            raw_response=raw_response,
        )

    fulfilled = parsed.get("fulfilled")
    if not isinstance(fulfilled, bool):
        return _unparseable_judge_decision(
            "Judge JSON did not contain a boolean 'fulfilled' field",
            json.dumps(parsed, sort_keys=True),
            raw_response=raw_response,
        )
    reason = parsed.get("reason")
    if not isinstance(reason, str):
        reason = json.dumps(parsed, sort_keys=True)
    return ProfBenchJudgeDecision(fulfilled=fulfilled, reason=reason, raw_response=raw_response)


def _unparseable_judge_decision(
    prefix: str,
    text: str,
    *,
    raw_response: dict[str, Any] | None,
) -> ProfBenchJudgeDecision:
    excerpt = _shorten_one_line(text, MAX_JUDGE_REASON_EXCERPT_CHARS)
    reason = f"{prefix}; treating criterion as unfulfilled."
    if excerpt:
        reason = f"{reason} Raw judge text: {excerpt}"
    return ProfBenchJudgeDecision(fulfilled=False, reason=reason, raw_response=raw_response)


def _shorten_one_line(text: str, max_chars: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    return f"{normalized[: max_chars - 3]}..."


def _parse_json_object(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def _default_judge_params() -> RunConfigOnlineModel:
    return RunConfigOnlineModel(
        parallelism=1,
        inference=InferenceParams.model_validate(
            {
                "temperature": 0.0,
                "max_tokens": 256,
                "extra_body": {
                    "chat_template_kwargs": {"enable_thinking": False},
                    "reasoning_budget": 0,
                },
            }
        ),
        structured_output=PROFBENCH_JUDGE_STRUCTURED_OUTPUT,
    )


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
    return bool(value)


def _criterion_type_labels(value: CriterionType | None) -> list[str]:
    if value is None:
        return ["unknown"]
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _safe_artifact_name(value: str) -> str:
    return "".join(character if character.isalnum() or character in {"-", "_", "."} else "_" for character in value)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run ProfBench agent-eval examples.")
    parser.add_argument(
        "--limit",
        type=int,
        default=1,
        help="Maximum number of ProfBench tasks to evaluate (0 = no limit). Default: 1.",
    )
    parser.add_argument(
        "--run-live",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Alias for --run-live-judge.",
    )
    parser.add_argument(
        "--run-live-judge",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Score the recorded ProfBench responses with a live LLM judge after the baseline example.",
    )
    parser.add_argument(
        "--run-live-candidate",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Generate fresh candidate responses from the configured model, then score them with a live LLM judge.",
    )
    args = parser.parse_args()

    configure_example_logging()
    asyncio.run(
        run_examples(
            limit=_profbench_limit_from_args(args.limit),
            run_live_judge=args.run_live or args.run_live_judge,
            run_live_candidate=args.run_live_candidate,
        )
    )
