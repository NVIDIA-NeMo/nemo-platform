# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Metadata types for filesets.

The metadata uses a tagged/keyed structure where the key indicates the type:
    metadata: {dataset: {schema: {...}}}

The key in metadata should match the fileset's purpose field.
"""

from jsonschema.exceptions import SchemaError
from jsonschema.validators import validator_for
from pydantic import BaseModel, ConfigDict, Field, model_validator


class DatasetLineageSource(BaseModel):
    """One upstream source used to materialize a dataset snapshot.

    ``kind`` and ``ref`` deliberately stay open strings. Dataset producers can add new source
    systems without changing the Files API, while consumers still get a common lineage envelope.
    Exact row-level provenance belongs in the dataset rows; this object describes the snapshot as
    a whole and carries a digest for the selected source set.
    """

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(description="Source kind, for example intake-traces or dataset.")
    ref: str = Field(description="Stable source reference understood by the producer.")
    record_count: int | None = Field(default=None, ge=0, description="Rows contributed by this source.")
    digest: str | None = Field(default=None, description="Optional digest of the exact selected source identities.")
    attributes: dict[str, str] = Field(
        default_factory=dict,
        description="Small producer-supplied source attributes; row-level provenance belongs in the dataset.",
    )


class DatasetLineage(BaseModel):
    """Dataset-level provenance shared by Files, Data Designer, and evaluation consumers."""

    model_config = ConfigDict(extra="forbid")

    producer: str = Field(description="Component and contract version that materialized the dataset.")
    sources: list[DatasetLineageSource] = Field(
        min_length=1,
        description="Upstream trace selections or dataset snapshots used to build this dataset.",
    )


class DatasetMetadataContent(BaseModel):
    """Content for dataset-type filesets."""

    # Use `schema_` because `schema` is a BaseModel method.
    model_config = ConfigDict(serialize_by_alias=True)

    schema_: dict | str | None = Field(
        default=None,
        alias="schema",
        description="Default row schema for files in this fileset, either inline JSON Schema or a schema_defs key.",
    )
    schema_defs: dict[str, dict] = Field(
        default_factory=dict,
        description="Reusable JSON Schema definitions keyed by name for deduplicating per-file dataset schemas.",
    )
    schemas_by_path: dict[str, dict | str] = Field(
        default_factory=dict,
        description=(
            "Optional per-file row schemas keyed by relative path within the fileset. "
            "Each value may be inline JSON Schema or a schema_defs key."
        ),
    )
    data_path: str | None = Field(
        default=None,
        description="Canonical file within the fileset that contains dataset rows.",
    )
    record_count: int | None = Field(default=None, ge=0, description="Number of rows in the dataset snapshot.")
    grader_refs: list[str] = Field(
        default_factory=list,
        description="Distinct Platform metric references bound to rows in this dataset.",
    )
    lineage: DatasetLineage | None = Field(
        default=None,
        description="Dataset-level provenance. Exact per-row provenance is stored in the dataset itself.",
    )

    @model_validator(mode="after")
    def validate_schema_refs(self) -> "DatasetMetadataContent":
        for ref_name, ref_value in [("schema", self.schema_), *self.schemas_by_path.items()]:
            if isinstance(ref_value, str) and ref_value not in self.schema_defs:
                raise ValueError(f"dataset metadata reference '{ref_name}' points to unknown schema_def '{ref_value}'")
        return self

    @model_validator(mode="after")
    def validate_json_schemas(self) -> "DatasetMetadataContent":
        def _validate_schema_document(schema: dict, ref_name: str) -> None:
            validator = validator_for(schema)
            try:
                validator.check_schema(schema)
            except SchemaError as e:
                raise ValueError(
                    f"dataset metadata field '{ref_name}' contains invalid JSON Schema: {e.message}"
                ) from e

        if isinstance(self.schema_, dict):
            _validate_schema_document(self.schema_, "schema")

        for schema_name, schema in self.schema_defs.items():
            _validate_schema_document(schema, f"schema_defs.{schema_name}")

        for path, schema in self.schemas_by_path.items():
            if isinstance(schema, dict):
                _validate_schema_document(schema, f"schemas_by_path.{path}")

        return self


class ToolCallingMetadataContent(BaseModel):
    """Content for tool-calling configuration on model filesets.

    Stores chat template and tool calling settings that are merged into
    the ModelSpec during checkpoint analysis.
    """

    chat_template: str | None = Field(
        default=None,
        description="Jinja2 chat template for the model.",
    )
    tool_call_parser: str | None = Field(
        default=None,
        description="Name of the tool call parser (e.g., 'openai', 'hermes', 'pythonic', 'llama3_json', 'mistral').",
    )
    tool_call_plugin: str | None = Field(
        default=None,
        description="Reference to a fileset containing a custom tool call plugin Python file. "
        "Expected format: '{workspace}/{fileset_name}'.",
    )
    auto_tool_choice: bool | None = Field(
        default=None,
        description="Whether to enable automatic tool choice.",
    )


class ModelMetadataContent(BaseModel):
    """Content for model-type filesets.

    Contains tool calling configuration that is merged into the ModelSpec
    during checkpoint analysis.
    """

    tool_calling: ToolCallingMetadataContent | None = None


class FilesetMetadata(BaseModel):
    """Tagged metadata container - the key indicates the type.

    Example:
        metadata = FilesetMetadata(
            dataset=DatasetMetadataContent(
                schema={"columns": ["id", "name"]},
            )
        )
    """

    dataset: DatasetMetadataContent | None = None
    model: ModelMetadataContent | None = None
