# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ProfBench loading, rubric scoring, and judging helpers."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

import nemo_evaluator_sdk.inference as inference
from nemo_evaluator_sdk.agent_eval import AgentEvalAttempt, AgentEvalRunResult, AgentEvalTask, AgentOutput
from nemo_evaluator_sdk.agent_eval.benchmarks import (
    AgentEvalBenchmarkBundle,
    AgentEvalBenchmarkEvaluationKind,
    AgentEvalBenchmarkLoadConfig,
    AgentEvalBenchmarkReports,
    UnsupportedBenchmarkModeError,
)
from nemo_evaluator_sdk.execution.metric_execution import generate_online_sample
from nemo_evaluator_sdk.metrics.protocol import MetricInput, MetricOutput, MetricOutputSpec, MetricResult
from nemo_evaluator_sdk.values import InferenceParams, Model, RunConfigOnlineModel
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

    def href(self, *, base_dir: str | Path | None = None) -> str:
        """Return a browser-usable evidence link."""
        href, supports_line_fragment = self._href_base(base_dir=base_dir)
        if self.line is None or not supports_line_fragment:
            return href
        separator = "&" if "#" in href else "#"
        return f"{href}{separator}L{self.line}"

    def _href_base(self, *, base_dir: str | Path | None) -> tuple[str, bool]:
        if self.uri.startswith(("http://", "https://", "atif://")):
            href = self.uri
            return href, True

        local_path = _local_evidence_path(self.uri)
        if local_path is not None:
            if base_dir is not None:
                base_path = Path(base_dir).expanduser().resolve()
                resolved_path = local_path if local_path.is_absolute() else (base_path / local_path).resolve()
                return quote(Path(os.path.relpath(resolved_path, base_path)).as_posix(), safe="/"), False
            return local_path.expanduser().resolve().as_uri(), False

        return quote(self.uri), False


def _local_evidence_path(uri: str) -> Path | None:
    parsed = urlparse(uri)
    if parsed.scheme == "file":
        return Path(parsed.path)
    if parsed.scheme:
        return None
    return Path(uri)


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


class ProfBenchAgentEvalBenchmark:
    """Adapter that exposes ProfBench through the generic agent-eval benchmark protocol."""

    name = "profbench"
    default_source = PROFBENCH_DATASET_URL

    def __init__(
        self,
        *,
        judge_factory: Callable[[], ProfBenchJudge] | None = None,
        include_cached_fulfilments: bool = True,
        score_source: str | None = None,
    ) -> None:
        self._judge_factory = judge_factory
        self._include_cached_fulfilments = include_cached_fulfilments
        self._score_source = score_source

    def load(self, config: AgentEvalBenchmarkLoadConfig) -> AgentEvalBenchmarkBundle:
        source = config.source or self.default_source
        if config.evaluation_kind == AgentEvalBenchmarkEvaluationKind.STORED_ATTEMPTS:
            benchmark = load_profbench(
                source,
                limit=config.limit,
                judge=self._judge(),
                evidence_dir=config.evidence_dir,
                include_cached_fulfilments=self._include_cached_fulfilments,
            )
            return AgentEvalBenchmarkBundle(
                evaluation_kind=config.evaluation_kind,
                tasks=benchmark.tasks,
                attempts=benchmark.attempts,
                metadata=self._metadata(benchmark.metadata),
            )

        if config.evaluation_kind == AgentEvalBenchmarkEvaluationKind.LIVE_TARGET:
            if self._judge_factory is None:
                raise UnsupportedBenchmarkModeError("ProfBench live_target mode requires a judge factory")
            benchmark = load_profbench(
                source,
                limit=config.limit,
                judge=self._judge(),
                evidence_dir=config.evidence_dir,
                include_cached_fulfilments=False,
            )
            return AgentEvalBenchmarkBundle(
                evaluation_kind=config.evaluation_kind,
                tasks=benchmark.tasks,
                attempts=None,
                metadata=self._metadata(benchmark.metadata, default_score_source="live_target_and_live_judge"),
            )

        raise UnsupportedBenchmarkModeError(f"unsupported ProfBench evaluation kind {config.evaluation_kind!r}")

    def write_reports(self, result: AgentEvalRunResult, output_dir: Path) -> AgentEvalBenchmarkReports:
        from .dashboard import write_example_dashboards

        return AgentEvalBenchmarkReports(paths=list(write_example_dashboards(result, output_dir)))

    def _judge(self) -> ProfBenchJudge | None:
        if self._judge_factory is None:
            return None
        return self._judge_factory()

    def _metadata(self, metadata: dict[str, Any], *, default_score_source: str | None = None) -> dict[str, Any]:
        score_source = self._score_source or default_score_source
        if score_source is None:
            return metadata
        return {**metadata, "score_source": score_source}


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
        return EvidenceLocator(kind="judge", uri=str(path.resolve()), line=1, json_path="$.decision", excerpt=decision.reason)


def load_profbench(
    source: str | Path = PROFBENCH_DATASET_URL,
    *,
    limit: int | None = None,
    judge: ProfBenchJudge | None = None,
    evidence_dir: Path | None = None,
    include_cached_fulfilments: bool = True,
) -> ProfBenchBenchmark:
    """Load ProfBench from local JSONL or the Hugging Face raw URL."""
    source_uri, lines, metadata = _read_jsonl_source(source, evidence_dir=evidence_dir)
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

def _baseline_fulfilments(metadata: dict[str, Any]) -> dict[str, bool]:
    raw = metadata.get("profbench_fulfilments")
    if not isinstance(raw, dict):
        return {}
    return {str(key): _coerce_bool(value) for key, value in raw.items()}


def _read_jsonl_source(source: str | Path, *, evidence_dir: Path | None = None) -> tuple[str, list[tuple[int, str]], dict[str, Any]]:
    source_text = str(source)
    if source_text.startswith(("http://", "https://")):
        request = Request(source_text, headers={"User-Agent": "nemo-evaluator-sdk"})
        with urlopen(request, timeout=60) as response:
            body = response.read().decode("utf-8")
            headers = dict(response.headers.items())
        metadata = {
            "etag": headers.get("ETag"),
            "resolved_commit": headers.get("x-repo-commit"),
            "remote_source": source_text,
        }
        source_uri = source_text
        if evidence_dir is not None:
            evidence_dir.mkdir(parents=True, exist_ok=True)
            dataset_path = evidence_dir / "profbench-dataset.jsonl"
            dataset_path.write_text(body, encoding="utf-8")
            source_uri = str(dataset_path.resolve())
            metadata["source_file"] = source_uri
        lines = [(index, line) for index, line in enumerate(body.splitlines(), start=1) if line.strip()]
        return source_uri, lines, metadata

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
