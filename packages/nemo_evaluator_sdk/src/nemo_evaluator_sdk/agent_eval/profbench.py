# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ProfBench loading and rubric scoring for standalone agent evaluation."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Awaitable, Iterable
from pathlib import Path
from typing import Any, Protocol
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field

import nemo_evaluator_sdk.inference as inference
from nemo_evaluator_sdk.agent_eval.types import (
    AgentEvalAttempt,
    AgentEvalMetricSpec,
    AgentEvalSummary,
    AgentEvalTask,
    AgentEvalTaskResult,
    AgentOutput,
    CriterionScore,
    CriterionType,
    EvidenceLocator,
    ScoreDeduction,
)
from nemo_evaluator_sdk.values import Model, RunConfigOnlineModel
from nemo_evaluator_sdk.values.evidence import CandidateEvidence, EvidenceDescriptor

PROFBENCH_DATASET_URL = "https://huggingface.co/datasets/nvidia/ProfBench/resolve/main/test.jsonl"
PROFBENCH_METRIC_TYPE = "profbench_rubric"
PROFBENCH_METRIC_ID = "profbench"
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
        weight_name = str(raw.get("criterion_weight", "")).strip()
        if weight_name not in PROFBENCH_WEIGHT_POINTS:
            raise ValueError(f"Unsupported ProfBench criterion weight: {weight_name!r}")

        return cls(
            id=f"{task_id}:criterion-{index + 1}",
            description=str(raw.get("criterion_description", "")).strip(),
            weight_name=weight_name,
            points=PROFBENCH_WEIGHT_POINTS[weight_name],
            criterion_type=_criterion_type(raw.get("criterion_type")),
            source_uri=source_uri,
            line_number=line_number,
            json_path=f"$.rubrics[{index}]",
        )

    def source_locator(self) -> EvidenceLocator:
        """Return the JSONL source evidence for this criterion."""
        return EvidenceLocator(
            kind="profbench",
            uri=self.source_uri,
            line=self.line_number,
            json_path=self.json_path,
            excerpt=self.description,
            label=self.id,
        )


class ProfBenchBenchmark(BaseModel):
    """Loaded ProfBench task/attempt bundle."""

    model_config = ConfigDict(extra="forbid")

    tasks: list[AgentEvalTask]
    attempts: list[AgentEvalAttempt]
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProfBenchJudgeRequest(BaseModel):
    """Single criterion judgement request."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    prompt: str
    response: str
    criterion_id: str
    criterion_description: str
    criterion_type: CriterionType | None = None
    weight_name: str


class ProfBenchJudgeDecision(BaseModel):
    """Parsed ProfBench judge decision."""

    model_config = ConfigDict(extra="forbid")

    fulfilled: bool
    reason: str = ""
    raw_response: Any | None = None


class ProfBenchJudge(Protocol):
    """Callable protocol for injected ProfBench judges."""

    def judge(self, request: ProfBenchJudgeRequest) -> Awaitable[ProfBenchJudgeDecision]: ...


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
        self.params = params or RunConfigOnlineModel(parallelism=1)
        self.inference_fn = inference_fn or inference.make_inference_request
        self.client = client
        self.default_headers = default_headers

    async def judge(self, request: ProfBenchJudgeRequest) -> ProfBenchJudgeDecision:
        prompt = _render_judge_prompt(request)
        response = await self.inference_fn(
            self.model,
            {"messages": [{"role": "user", "content": prompt}]},
            self.params.max_retries,
            client=self.client,
            default_headers=self.default_headers,
            timeout=self.params.request_timeout,
        )
        text = inference.process_output(response, hooks=[], id=request.criterion_id) or ""
        return _parse_yes_no_decision(text, raw_response=response)


class ProfBenchRubricMetric:
    """Score ProfBench attempts and emit evidence-backed point deductions."""

    def __init__(self, *, judge: ProfBenchJudge | None = None, evidence_dir: Path | None = None) -> None:
        self.judge = judge
        self.evidence_dir = evidence_dir

    async def score_attempt(self, task: AgentEvalTask, attempt: AgentEvalAttempt) -> AgentEvalTaskResult:
        criteria = criteria_from_task(task)
        if not criteria:
            raise ValueError(f"task {task.id!r} does not include ProfBench rubrics")

        fulfilments = _baseline_fulfilments(attempt)
        output_text = attempt.output.output_text if attempt.output is not None else None
        if output_text is None:
            raise ValueError(f"attempt {attempt.id!r} has no output_text to score")

        earned_points = 0.0
        max_points = sum(criterion.points for criterion in criteria)
        criterion_scores: list[CriterionScore] = []
        deductions: list[ScoreDeduction] = []

        for criterion in criteria:
            source_locator = criterion.source_locator()
            judge_locator: EvidenceLocator | None = None
            judge_reason: str | None = None

            if criterion.id in fulfilments:
                fulfilled = fulfilments[criterion.id]
                judge_reason = "Dataset fulfilment label"
            else:
                if self.judge is None:
                    raise ValueError(
                        "ProfBench candidate scoring requires a judge when dataset fulfilment labels are absent"
                    )
                judge_request = ProfBenchJudgeRequest(
                    task_id=task.id,
                    prompt=str(task.inputs.get("prompt", "")),
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
                    task_id=task.id,
                    attempt_id=attempt.id,
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
                )
            )

        model_id = str(attempt.metadata.get("model_id") or attempt.metadata.get("target_name") or "candidate")
        return AgentEvalTaskResult(
            task_id=task.id,
            attempt_id=attempt.id,
            model_id=model_id,
            metric_id=PROFBENCH_METRIC_ID,
            score=earned_points / max_points,
            earned_points=earned_points,
            max_points=max_points,
            domain=task.metadata.get("domain"),
            criterion_scores=criterion_scores,
            deductions=deductions,
            metadata={
                "benchmark": "ProfBench",
                "source_task_id": task.metadata.get("profbench_task_id", task.id),
            },
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


def load_profbench(source: str | Path = PROFBENCH_DATASET_URL, *, limit: int | None = None) -> ProfBenchBenchmark:
    """Load ProfBench from local JSONL or the Hugging Face raw URL."""
    source_uri, lines, metadata = _read_jsonl_source(source)
    tasks: list[AgentEvalTask] = []
    attempts: list[AgentEvalAttempt] = []

    for line_number, line in lines[:limit]:
        row = json.loads(line)
        task_id = str(row["task_id"])
        rubrics = [
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
            metrics=[
                AgentEvalMetricSpec(
                    id=PROFBENCH_METRIC_ID,
                    type=PROFBENCH_METRIC_TYPE,
                    config={"rubrics": [rubric.model_dump(mode="json") for rubric in rubrics]},
                )
            ],
            metadata={
                "benchmark": "ProfBench",
                "domain": row.get("domain"),
                "profbench_task_id": task_id,
                "source_uri": source_uri,
                "line_number": line_number,
            },
        )
        tasks.append(task)
        attempts.extend(_baseline_attempts(row=row, task_id=task_id, rubrics=rubrics, source_uri=source_uri))

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


def criteria_from_task(task: AgentEvalTask) -> list[ProfBenchCriterion]:
    """Extract ProfBench criteria from an agent-eval task."""
    for metric in task.metrics:
        if metric.type == PROFBENCH_METRIC_TYPE:
            raw_rubrics = metric.config.get("rubrics", [])
            return [ProfBenchCriterion.model_validate(rubric) for rubric in raw_rubrics]
    return []


def summarize_results(results: Iterable[AgentEvalTaskResult]) -> AgentEvalSummary:
    """Aggregate task-attempt results using ProfBench-style means."""
    results_list = list(results)
    scores_by_domain: dict[str, list[float]] = defaultdict(list)
    scores_by_model_domain: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    fulfilment_by_type: dict[str, list[float]] = defaultdict(list)

    for result in results_list:
        domain = result.domain or "unknown"
        scores_by_domain[domain].append(result.score)
        scores_by_model_domain[result.model_id][domain].append(result.score)
        for criterion in result.criterion_scores:
            for criterion_type in _criterion_type_labels(criterion.criterion_type):
                fulfilment_by_type[criterion_type].append(1.0 if criterion.fulfilled else 0.0)

    domain_scores = {domain: _mean(scores) for domain, scores in sorted(scores_by_domain.items())}
    model_domain_scores = {
        model_id: {domain: _mean(scores) for domain, scores in sorted(domain_scores.items())}
        for model_id, domain_scores in sorted(scores_by_model_domain.items())
    }
    model_scores = {
        model_id: _mean(domain_scores.values()) for model_id, domain_scores in sorted(model_domain_scores.items())
    }

    return AgentEvalSummary(
        overall_score=_mean(model_scores.values()) if model_scores else None,
        domain_scores=domain_scores,
        model_scores=model_scores,
        model_domain_scores=model_domain_scores,
        criterion_type_fulfilment={
            criterion_type: _mean(scores) for criterion_type, scores in sorted(fulfilment_by_type.items())
        },
        task_count=len({result.task_id for result in results_list}),
        attempt_count=len({result.attempt_id for result in results_list}),
        deduction_count=sum(len(result.deductions) for result in results_list),
    )


def _baseline_attempts(
    *,
    row: dict[str, Any],
    task_id: str,
    rubrics: list[ProfBenchCriterion],
    source_uri: str,
) -> list[AgentEvalAttempt]:
    attempts: list[AgentEvalAttempt] = []
    for model_id, response_field in PROFBENCH_BASELINE_RESPONSES.items():
        response_text = row.get(response_field)
        if not isinstance(response_text, str):
            continue

        fulfilments = {
            rubric.id: _coerce_bool(row["rubrics"][index].get(f"{model_id}_fulfilment"))
            for index, rubric in enumerate(rubrics)
        }
        attempts.append(
            AgentEvalAttempt(
                id=f"{task_id}:{model_id}",
                task_id=task_id,
                output=AgentOutput(
                    output_text=response_text,
                    evidence=CandidateEvidence(
                        sources=[
                            EvidenceDescriptor(
                                kind="profbench",
                                ref=source_uri,
                                format="jsonl",
                                metadata={"task_id": task_id, "response_field": response_field},
                            )
                        ]
                    ),
                ),
                metadata={
                    "model_id": model_id,
                    "profbench_response_field": response_field,
                    "profbench_fulfilments": fulfilments,
                },
            )
        )
    return attempts


def _baseline_fulfilments(attempt: AgentEvalAttempt) -> dict[str, bool]:
    raw = attempt.metadata.get("profbench_fulfilments")
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
    return str(path), lines, {}


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "y", "1", "fulfilled", "pass"}:
            return True
        if normalized in {"false", "no", "n", "0", "unfulfilled", "fail"}:
            return False
    raise ValueError(f"Unable to coerce ProfBench fulfilment value to bool: {value!r}")


def _criterion_type(value: Any) -> CriterionType | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    raise ValueError(f"Unsupported ProfBench criterion_type value: {value!r}")


def _criterion_type_labels(value: CriterionType | None) -> list[str]:
    if value is None:
        return ["unknown"]
    if isinstance(value, str):
        return [value]
    return value or ["unknown"]


def _mean(values: Iterable[float]) -> float:
    values_list = list(values)
    if not values_list:
        return 0.0
    return sum(values_list) / len(values_list)


def _render_judge_prompt(request: ProfBenchJudgeRequest) -> str:
    return "\n\n".join(
        [
            "You are evaluating whether an answer fulfils one ProfBench rubric criterion.",
            f"Prompt:\n{request.prompt}",
            f"Answer:\n{request.response}",
            f"Criterion ({request.weight_name}):\n{request.criterion_description}",
            'Respond with JSON only: {"fulfilled": true|false, "reason": "<brief evidence-based reason>"}',
        ]
    )


def _parse_yes_no_decision(text: str, *, raw_response: Any | None = None) -> ProfBenchJudgeDecision:
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict) and isinstance(payload.get("fulfilled"), bool):
            return ProfBenchJudgeDecision(
                fulfilled=payload["fulfilled"],
                reason=str(payload.get("reason") or ""),
                raw_response=raw_response,
            )

    lowered = stripped.lower()
    fulfilled = lowered.startswith("yes") or '"fulfilled": true' in lowered or "'fulfilled': true" in lowered
    if not fulfilled and not (lowered.startswith("no") or '"fulfilled": false' in lowered or "'fulfilled': false" in lowered):
        raise ValueError(f"Unable to parse ProfBench judge response as yes/no: {text!r}")
    return ProfBenchJudgeDecision(fulfilled=fulfilled, reason=stripped, raw_response=raw_response)


def _safe_artifact_name(value: str) -> str:
    return "".join(character if character.isalnum() or character in "._-" else "-" for character in value)
