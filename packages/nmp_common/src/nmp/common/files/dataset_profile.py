# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed contract for the NMP dataset profile (schema_version 2.1).

The Pydantic models a profiler writes and consumers (Customizer's backend
chooser, Studio, validation steps) read, plus the bridge onto
``DatasetMetadataContent``'s JSON-Schema fields.

Produced by the files-service profiler; the profile lives at
``Fileset.metadata.dataset.profile``.

Design invariants the models enforce:
  - task/format vocabularies are closed enums (consumers can exhaustively
    match; NO backend names — task→backend mapping is consumer policy);
  - each group's ``row_schema`` is valid JSON Schema (same check as
    ``DatasetMetadataContent``);
  - ``primary`` names an existing group;
  - confidences are ordinal rankings in [0, 1], not calibrated probabilities.
"""

from enum import Enum
from typing import Any, Literal, Optional

from jsonschema.exceptions import SchemaError
from jsonschema.validators import validator_for
from pydantic import BaseModel, Field, model_validator


class TrainingTask(str, Enum):
    """Generic training-task vocabulary — deliberately backend-free."""

    SFT = "sft"
    DPO = "dpo"
    KTO = "kto"
    REWARD_MODEL = "reward_model"
    GRPO = "grpo"
    RLVR = "rlvr"
    EMBEDDING = "embedding"
    SEQ_CLS = "seq_cls"
    CONTINUED_PRETRAIN = "continued_pretrain"
    OFFLINE_LOGIT_KD = "offline_logit_kd"


class DetectedFormat(str, Enum):
    """Objective data shapes (vs. TrainingTask, which is interpretive).

    Names align with the RL backend's own detector where they overlap
    (``preference_binary`` ↔ its BinaryPreferenceDataset).
    """

    PREFERENCE_BINARY = "preference_binary"
    UNPAIRED_PREFERENCE = "unpaired_preference"
    CHAT_MESSAGES = "chat_messages"
    PROMPT_COMPLETION = "prompt_completion"
    TEXT_CORPUS = "text_corpus"
    TEXT_CLASSIFICATION = "text_classification"
    EMBEDDING_TRIPLET = "embedding_triplet"
    EMBEDDING_PAIR = "embedding_pair"
    EMBEDDING_PAIR_SCORED = "embedding_pair_scored"
    PROMPT_ONLY = "prompt_only"
    PROMPT_WITH_GROUND_TRUTH = "prompt_with_ground_truth"
    UNKNOWN = "unknown"


class ColumnType(str, Enum):
    """HF datasets-server /statistics column taxonomy (+ ``dict`` for nested
    structs, which HF flattens but we keep)."""

    STRING_LABEL = "string_label"
    STRING_TEXT = "string_text"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    LIST = "list"
    CLASS_LABEL = "class_label"
    DICT = "dict"


class TaskCandidate(BaseModel):
    task: TrainingTask
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Ordinal ranking weight, not a calibrated probability.",
    )
    reason: str


class GroupSemantics(BaseModel):
    canonical_roles: dict[str, str] = Field(
        default_factory=dict,
        description="Column name → canonical role (e.g. 'instruction' → 'prompt').",
    )
    detected_format: DetectedFormat
    task_candidates: list[TaskCandidate] = Field(default_factory=list)
    ambiguities: list[str] = Field(
        default_factory=list,
        description="Data facts the shape alone cannot resolve (e.g. DPO vs "
        "reward-model); what to do about them is consumer policy.",
    )


class ColumnStatistics(BaseModel):
    column_name: str
    column_type: ColumnType
    column_statistics: dict[str, Any] = Field(
        default_factory=dict,
        description="nan_count/nan_proportion always; n_unique for label-ish "
        "columns; min/max/mean for numeric, text-length and list-length stats.",
    )


class GroupSampling(BaseModel):
    strategy: Literal["head", "stratified", "even"]
    strata: Optional[int] = None
    rows_sampled: int = Field(ge=0)


class GroupStructure(BaseModel):
    row_schema: dict = Field(
        description="JSON Schema (draft 2020-12) for one row — the platform-"
        "native serialization, feedable to DatasetMetadataContent.schema / "
        "schemas_by_path. Sample-derived and advisory."
    )
    features: Optional[dict[str, Any]] = Field(
        default=None,
        description="The same shape serialized as a datasets.Features mapping "
        "(HF `_type` discriminated form) for HF-tooling interop.",
    )
    num_rows: Optional[int] = Field(
        default=None,
        description="Filled only when exact (parquet metadata / fully-read "
        "files); else the controller fills it from FileSet accounting.",
    )
    num_bytes: Optional[int] = None

    @model_validator(mode="after")
    def validate_row_schema(self) -> "GroupStructure":
        validator = validator_for(self.row_schema)
        try:
            validator.check_schema(self.row_schema)
        except SchemaError as e:
            raise ValueError(
                f"structure.row_schema is not valid JSON Schema: {e.message}"
            ) from e
        return self


class ProfileGroup(BaseModel):
    """One profile per column-set signature; a FileSet with heterogeneous
    shards (e.g. an SFT shard + a preference shard) yields multiple groups."""

    name: str
    files: list[str] = Field(description="Relative paths of the member files.")
    columns: list[str]
    sampling: GroupSampling
    structure: GroupStructure
    statistics: list[ColumnStatistics] = Field(default_factory=list)
    semantics: GroupSemantics


class SkippedFile(BaseModel):
    path: str
    reason: str


class ProfileSource(BaseModel):
    kind: str = Field(description="How the files arrived, e.g. 'upload'.")
    path: str
    files_hash: str = Field(
        description="sha256 over (relative path, size) of every resolved file; "
        "the controller compares this to decide whether to re-profile."
    )
    files_skipped: list[SkippedFile] = Field(default_factory=list)
    files_truncated: int = Field(
        default=0,
        ge=0,
        description="Files beyond the profiler's hard cap, not sampled.",
    )


class ProfilerInfo(BaseModel):
    name: str
    version: str
    method: Literal["sampled"] = "sampled"
    sampled_rows: int = Field(ge=0)


class DatasetProfile(BaseModel):
    """The full profile written to FileSet metadata.

    Idempotent by construction: no timestamps, deterministic sampling and
    group ordering — identical files must yield an identical profile so
    metadata writes never churn or re-trigger the controller.
    """

    schema_version: str
    profiler: ProfilerInfo
    source: ProfileSource
    groups: list[ProfileGroup] = Field(default_factory=list)
    primary: Optional[str] = Field(
        default=None,
        description="Name of the largest group by bytes — where simple "
        "consumers look first.",
    )

    @model_validator(mode="after")
    def validate_primary(self) -> "DatasetProfile":
        names = {g.name for g in self.groups}
        if self.primary is not None and self.primary not in names:
            raise ValueError(f"primary '{self.primary}' does not name a group")
        if self.primary is None and self.groups:
            raise ValueError("primary must be set when groups are present")
        return self

    def primary_group(self) -> Optional[ProfileGroup]:
        return next((g for g in self.groups if g.name == self.primary), None)


def to_dataset_metadata_content(profile: DatasetProfile) -> dict:
    """Bridge a profile onto ``DatasetMetadataContent``'s JSON-Schema fields.

    Returns the dict form (``schema`` / ``schema_defs`` / ``schemas_by_path``)
    so existing consumers (DatasetValidator et al.) work without knowing the
    profile exists: each group's row_schema becomes a schema_def keyed by
    group name, every member file points at it, and the fileset-level default
    is the primary group's schema. Feed the result to
    ``DatasetMetadataContent(**bridge, ...)`` (kept as a dict here to avoid a
    circular import: metadata.py imports this module for the profile field).
    """
    return {
        "schema": profile.primary,
        "schema_defs": {g.name: g.structure.row_schema for g in profile.groups},
        "schemas_by_path": {
            path: g.name for g in profile.groups for path in g.files
        },
    }
