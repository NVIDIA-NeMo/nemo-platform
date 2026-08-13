# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Materialize reviewable evaluation datasets from Intake traces or existing datasets."""

from __future__ import annotations

import hashlib
import io
import json
import logging
from typing import Annotated, Any, ClassVar, Literal, cast

import pandas as pd
from nemo_platform import NeMoPlatform
from nemo_platform.filesets import parse_fileset_ref
from nemo_platform_plugin.files.metadata import (
    DatasetLineage,
    DatasetLineageSource,
    DatasetMetadataContent,
    FilesetMetadata,
)
from nemo_platform_plugin.files.types import CreateFilesetRequest, FilesetPurpose
from nemo_platform_plugin.job import NemoJob
from nemo_platform_plugin.job_context import JobContext
from nemo_platform_plugin.jobs.api_factory import (
    ContainerSpec,
    CPUExecutionProviderSpec,
    PlatformJobSpec,
    PlatformJobStep,
)
from nemo_platform_plugin.jobs.image import get_qualified_image
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

DATASET_CONTRACT = "nemo.agent-eval-dataset.v1"
DATASET_DATA_PATH = "data/data.parquet"
DATASET_PRODUCER = "nemo-data-designer.build-dataset/v1"


class DatasetDestination(BaseModel):
    """The immutable Fileset snapshot produced by a build-dataset job."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Name of the destination dataset Fileset.")
    description: str | None = Field(default=None, max_length=255)
    project: str | None = None


class IntakeTraceSelection(BaseModel):
    """A user-selected set of normalized Intake traces for one agent."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["intake-traces"] = "intake-traces"
    agent_name: str = Field(min_length=1, description="Expected agent identity for every selected root trace.")
    trace_ids: list[str] = Field(min_length=1, max_length=10_000)
    grader_refs: list[str] = Field(
        default_factory=list,
        description="Platform metric references to bind to every generated dataset row.",
    )

    @field_validator("trace_ids")
    @classmethod
    def _unique_trace_ids(cls, value: list[str]) -> list[str]:
        if any(not trace_id.strip() for trace_id in value):
            raise ValueError("trace_ids must not contain empty values")
        if len(set(value)) != len(value):
            raise ValueError("trace_ids must be unique")
        return value

    @field_validator("grader_refs")
    @classmethod
    def _unique_grader_refs(cls, value: list[str]) -> list[str]:
        if any(not ref.strip() for ref in value):
            raise ValueError("grader_refs must not contain empty values")
        return list(dict.fromkeys(value))


class DatasetComposition(BaseModel):
    """A catalog-level union of already-materialized agent datasets."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["datasets"] = "datasets"
    datasets: list[str] = Field(
        min_length=1,
        max_length=1_000,
        description="Dataset Fileset references (workspace/name or name in the job workspace).",
    )

    @field_validator("datasets")
    @classmethod
    def _unique_datasets(cls, value: list[str]) -> list[str]:
        if any(not ref.strip() for ref in value):
            raise ValueError("datasets must not contain empty values")
        if len(set(value)) != len(value):
            raise ValueError("datasets must be unique")
        return value


DatasetSource = Annotated[IntakeTraceSelection | DatasetComposition, Field(discriminator="kind")]


class BuildDatasetConfig(BaseModel):
    """User-facing and canonical config for a dataset materialization job."""

    model_config = ConfigDict(extra="forbid")

    destination: DatasetDestination
    source: DatasetSource

    @model_validator(mode="after")
    def _destination_must_not_be_a_source(self) -> BuildDatasetConfig:
        if not isinstance(self.source, DatasetComposition):
            return self
        source_names = {ref.split("#", 1)[0].split("/")[-1] for ref in self.source.datasets}
        if self.destination.name in source_names:
            raise ValueError("destination dataset must not also be a source dataset")
        return self


class AgentEvalDatasetRow(BaseModel):
    """Stable, review-oriented row contract shared by trace and composed datasets.

    Complex grader/reference/provenance values are canonical JSON strings so heterogeneous
    agent-specific oracles remain representable in one Parquet schema and Data Designer can use
    the file directly as a seed dataset.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    instruction: str
    observed_output: str | None = None
    reference: str = "{}"
    grader_refs: str = "[]"
    grader_results: str = "[]"
    agent_name: str
    trace_id: str
    session_id: str
    evaluation_id: str | None = None
    test_case_id: str | None = None
    trace_status: str
    trace_started_at: str
    lineage: str


class BuildDatasetJob(NemoJob):
    name: ClassVar[str] = "build-dataset"
    description: ClassVar[str] = "Build a lineage-aware evaluation dataset from Intake traces or datasets"
    container: ClassVar[str] = "cpu-tasks"

    spec_schema = BuildDatasetConfig

    @classmethod
    async def compile(
        cls,
        *,
        workspace: str,
        spec: BaseModel,
        entity_client: object,
        job_name: str | None,
        async_sdk: object,
        profile: str | None = None,
        options: dict | None = None,
    ) -> PlatformJobSpec:
        return PlatformJobSpec(
            steps=[
                PlatformJobStep(
                    name="build-dataset",
                    executor=CPUExecutionProviderSpec(
                        profile=profile or "default",
                        provider="cpu",
                        container=ContainerSpec(
                            image=get_qualified_image("nmp-cpu-tasks"),
                            entrypoint=["python", "-m"],
                            command=["nemo_data_designer_plugin.jobs.build_dataset_bridge"],
                        ),
                    ),
                    config=spec.model_dump(),
                    environment=[],
                )
            ],
        )

    def run(self, config: dict, *, ctx: JobContext, sdk: NeMoPlatform, is_local: bool = False) -> dict:
        return run_build_dataset(BuildDatasetConfig.model_validate(config), ctx=ctx, sdk=sdk)


def run_build_dataset(config: BuildDatasetConfig, *, ctx: JobContext, sdk: NeMoPlatform) -> dict[str, object]:
    """Build and publish one immutable dataset Fileset, rolling it back on partial upload."""

    try:
        rows, sources = _resolve_rows(config.source, workspace=ctx.workspace, sdk=sdk)
        frame = pd.DataFrame([row.model_dump() for row in rows])
        parquet = io.BytesIO()
        frame.to_parquet(parquet, index=False)

        grader_refs = sorted(
            {ref for row in rows for ref in _json_string_list(row.grader_refs, field_name=f"row {row.id} grader_refs")}
        )
        lineage = DatasetLineage(producer=DATASET_PRODUCER, sources=sources)
        dataset_metadata = DatasetMetadataContent(
            schema=AgentEvalDatasetRow.model_json_schema(),
            schemas_by_path={DATASET_DATA_PATH: AgentEvalDatasetRow.model_json_schema()},
            data_path=DATASET_DATA_PATH,
            record_count=len(rows),
            grader_refs=grader_refs,
            lineage=lineage,
        )
        _publish_dataset(
            config=config,
            workspace=ctx.workspace,
            sdk=sdk,
            parquet=parquet.getvalue(),
            metadata=dataset_metadata,
            rows=rows,
        )
        return {
            "exit_code": 0,
            "workspace": ctx.workspace,
            "dataset_ref": f"{ctx.workspace}/{config.destination.name}",
            "data_path": DATASET_DATA_PATH,
            "record_count": len(rows),
            "grader_refs": grader_refs,
        }
    except Exception as exc:
        logger.exception("Dataset build failed: %s", exc)
        return {
            "exit_code": 1,
            "workspace": ctx.workspace,
            "dataset_ref": f"{ctx.workspace}/{config.destination.name}",
            "error": str(exc),
        }


def _resolve_rows(
    source: DatasetSource,
    *,
    workspace: str,
    sdk: NeMoPlatform,
) -> tuple[list[AgentEvalDatasetRow], list[DatasetLineageSource]]:
    if isinstance(source, IntakeTraceSelection):
        return _rows_from_traces(source, workspace=workspace, sdk=sdk)
    return _rows_from_datasets(source, workspace=workspace, sdk=sdk)


def _rows_from_traces(
    source: IntakeTraceSelection,
    *,
    workspace: str,
    sdk: NeMoPlatform,
) -> tuple[list[AgentEvalDatasetRow], list[DatasetLineageSource]]:
    rows: list[AgentEvalDatasetRow] = []
    for trace_id in source.trace_ids:
        trace = sdk.intake.traces.retrieve(trace_id, workspace=workspace, mode="detailed")
        root_span_id = getattr(trace, "root_span_id", None)
        if not root_span_id:
            raise ValueError(f"trace {trace_id!r} has no root_span_id")
        root_span = sdk.intake.spans.retrieve(root_span_id, workspace=workspace)
        observed_agent = getattr(trace, "agent_name", None) or getattr(root_span, "agent_name", None)
        if observed_agent != source.agent_name:
            raise ValueError(f"trace {trace_id!r} belongs to agent {observed_agent!r}, expected {source.agent_name!r}")
        raw_attributes = getattr(root_span, "raw_attributes", None)
        atif_instruction, atif_output = _messages_from_raw_attributes(raw_attributes)
        instruction = getattr(trace, "input", None) or atif_instruction
        if not isinstance(instruction, str) or not instruction.strip():
            raise ValueError(f"trace {trace_id!r} has no non-empty root input")
        observed_output = atif_output or getattr(trace, "output", None)

        evaluator_results = sdk.intake.spans.evaluator_results.list(root_span_id, workspace=workspace)
        evaluation_context = getattr(trace, "evaluation_context", None)
        lineage = [
            {
                "kind": "intake-trace",
                "ref": f"{workspace}/{trace_id}",
                "root_span_id": root_span_id,
                "session_id": trace.session_id,
            }
        ]
        rows.append(
            AgentEvalDatasetRow(
                id=_trace_record_id(workspace, trace_id),
                instruction=instruction,
                observed_output=observed_output,
                reference=_canonical_json(_reference_from_raw_attributes(raw_attributes)),
                grader_refs=_canonical_json(source.grader_refs),
                grader_results=_canonical_json([_as_dict(result) for result in evaluator_results]),
                agent_name=source.agent_name,
                trace_id=trace_id,
                session_id=trace.session_id,
                evaluation_id=getattr(evaluation_context, "evaluation_id", None),
                test_case_id=getattr(evaluation_context, "test_case_id", None),
                trace_status=str(trace.status),
                trace_started_at=trace.started_at.isoformat(),
                lineage=_canonical_json(lineage),
            )
        )

    selection_digest = hashlib.sha256("\n".join(sorted(source.trace_ids)).encode()).hexdigest()
    return rows, [
        DatasetLineageSource(
            kind="intake-traces",
            ref=f"{workspace}/agents/{source.agent_name}",
            record_count=len(rows),
            digest=selection_digest,
            attributes={"agent_name": source.agent_name},
        )
    ]


def _rows_from_datasets(
    source: DatasetComposition,
    *,
    workspace: str,
    sdk: NeMoPlatform,
) -> tuple[list[AgentEvalDatasetRow], list[DatasetLineageSource]]:
    rows_by_id: dict[str, AgentEvalDatasetRow] = {}
    lineage_sources: list[DatasetLineageSource] = []
    for ref in source.datasets:
        source_workspace, fileset_name, fragment = parse_fileset_ref(ref, workspace_fallback=workspace)
        if fragment:
            raise ValueError(f"dataset source {ref!r} must reference a Fileset, not an individual file")
        fileset = sdk.files.client.get_fileset(workspace=source_workspace, name=fileset_name).data()
        if str(fileset.purpose) != FilesetPurpose.DATASET.value:
            raise ValueError(f"source {source_workspace}/{fileset_name} is not a dataset Fileset")
        if fileset.custom_fields.get("dataset.contract") != DATASET_CONTRACT:
            raise ValueError(f"source {source_workspace}/{fileset_name} does not implement {DATASET_CONTRACT}")
        metadata = fileset.metadata.dataset
        if metadata is None or not metadata.data_path:
            raise ValueError(f"source {source_workspace}/{fileset_name} has no canonical dataset data_path")
        content = sdk.files.download_content(
            workspace=source_workspace,
            fileset=fileset_name,
            remote_path=metadata.data_path,
        )
        frame = pd.read_parquet(io.BytesIO(content))
        source_ref = f"{source_workspace}/{fileset_name}"
        contributed = 0
        for raw_row in frame.to_dict(orient="records"):
            row = AgentEvalDatasetRow.model_validate(raw_row)
            lineage = _json_object_list(row.lineage, field_name=f"row {row.id} lineage")
            if not any(item.get("kind") == "dataset" and item.get("ref") == source_ref for item in lineage):
                lineage.append({"kind": "dataset", "ref": source_ref})
            row = row.model_copy(update={"lineage": _canonical_json(lineage)})
            existing = rows_by_id.get(row.id)
            if existing is not None:
                if existing.model_dump(exclude={"lineage"}) != row.model_dump(exclude={"lineage"}):
                    raise ValueError(f"dataset sources contain conflicting rows with id {row.id!r}")
                merged_lineage = _json_object_list(existing.lineage, field_name=f"row {row.id} lineage")
                for item in lineage:
                    if item not in merged_lineage:
                        merged_lineage.append(item)
                rows_by_id[row.id] = existing.model_copy(update={"lineage": _canonical_json(merged_lineage)})
            else:
                rows_by_id[row.id] = row
                contributed += 1
        lineage_sources.append(DatasetLineageSource(kind="dataset", ref=source_ref, record_count=contributed))
    return list(rows_by_id.values()), lineage_sources


def _publish_dataset(
    *,
    config: BuildDatasetConfig,
    workspace: str,
    sdk: NeMoPlatform,
    parquet: bytes,
    metadata: DatasetMetadataContent,
    rows: list[AgentEvalDatasetRow],
) -> None:
    destination = config.destination
    created = False
    try:
        sdk.files.client.create_fileset(
            workspace=workspace,
            body=CreateFilesetRequest(
                name=destination.name,
                description=destination.description,
                project=destination.project,
                purpose=FilesetPurpose.DATASET,
                metadata=FilesetMetadata(dataset=metadata),
                custom_fields={
                    "dataset.contract": DATASET_CONTRACT,
                    "dataset.source_kind": config.source.kind,
                },
            ),
        )
        created = True
        sdk.files.upload_content(
            content=parquet,
            remote_path=DATASET_DATA_PATH,
            fileset=destination.name,
            workspace=workspace,
        )
    except Exception:
        if created:
            try:
                sdk.files.client.delete_fileset(workspace=workspace, name=destination.name)
            except Exception:
                logger.exception("Failed to roll back partial dataset Fileset %s/%s", workspace, destination.name)
        raise


def _trace_record_id(workspace: str, trace_id: str) -> str:
    return hashlib.sha256(f"{workspace}\0{trace_id}".encode()).hexdigest()


def _reference_from_raw_attributes(raw_attributes: object) -> dict[str, Any]:
    raw = _json_object(raw_attributes)
    raw_extra = raw.get("extra")
    extra = cast(dict[str, Any], raw_extra) if isinstance(raw_extra, dict) else {}
    for candidate in (raw.get("reference"), extra.get("reference")):
        if isinstance(candidate, dict):
            return candidate
    for candidate in (raw.get("oracle"), extra.get("oracle")):
        if candidate is not None:
            return {"oracle": candidate}
    return {}


def _messages_from_raw_attributes(raw_attributes: object) -> tuple[str | None, str | None]:
    """Recover reviewable input/output from raw ATIF or ATOF evidence.

    Fabric trajectories can leave the normalized root ``input`` empty and the root ``output``
    pointing at an orchestration event. The raw evidence still contains repeated user/assistant
    messages. Selecting the first user message and final assistant message yields the stable task
    boundary while avoiding system prompts and tool payloads.
    """

    raw = _json_object(raw_attributes)
    messages: list[tuple[str, str]] = []

    def collect(value: object) -> None:
        if isinstance(value, dict):
            role = value.get("role") or value.get("type")
            content = _text_content(value.get("content"))
            normalized_role = {
                "user": "user",
                "human": "user",
                "assistant": "assistant",
                "ai": "assistant",
            }.get(role)
            if normalized_role and content:
                message = (normalized_role, content)
                if not messages or messages[-1] != message:
                    messages.append(message)
            for nested in value.values():
                collect(nested)
        elif isinstance(value, list):
            for nested in value:
                collect(nested)

    collect(raw)
    user_inputs = [content for role, content in messages if role == "user"]
    assistant_outputs = [content for role, content in messages if role == "assistant"]
    return (user_inputs[0] if user_inputs else None, assistant_outputs[-1] if assistant_outputs else None)


def _text_content(value: object) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if not isinstance(value, list):
        return None
    blocks: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            blocks.append(item.strip())
        elif isinstance(item, dict):
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                blocks.append(text.strip())
    return "\n".join(blocks) or None


def _json_object(value: object) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return cast(dict[str, Any], value)
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    return {}


def _json_string_list(value: str, *, field_name: str) -> list[str]:
    parsed = json.loads(value)
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise ValueError(f"{field_name} must be a JSON string array")
    return parsed


def _json_object_list(value: str, *, field_name: str) -> list[dict[str, Any]]:
    parsed = json.loads(value)
    if not isinstance(parsed, list) or not all(isinstance(item, dict) for item in parsed):
        raise ValueError(f"{field_name} must be a JSON object array")
    return parsed


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _as_dict(value: object) -> dict[str, Any]:
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_dict(mode="json")
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    if isinstance(value, dict):
        return cast(dict[str, Any], value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


__all__ = [
    "AgentEvalDatasetRow",
    "BuildDatasetConfig",
    "BuildDatasetJob",
    "DATASET_CONTRACT",
    "DATASET_DATA_PATH",
    "DatasetComposition",
    "DatasetDestination",
    "IntakeTraceSelection",
    "run_build_dataset",
]
