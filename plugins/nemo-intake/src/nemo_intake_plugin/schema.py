# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Intake-specific schema helpers not provided by the plugin API."""

from __future__ import annotations

from typing import ClassVar, Generic, TypeVar

from nemo_platform_plugin.api.parsed_filter import ENTITY_BASE_FIELDS
from nemo_platform_plugin.filter_ops import ComparisonOperation, FilterOperation, LogicalOperation
from nemo_platform_plugin.schema import Filter as PluginFilter
from nemo_platform_plugin.schema import PaginationData
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class PaginatedResult(BaseModel, Generic[T]):
    """Repository-layer result before API filter and sort context is added."""

    data: list[T]
    pagination: PaginationData


class EntityFieldMapping:
    def __init__(self, entity_path: str, *, namespace: bool = False) -> None:
        self.entity_path = entity_path
        self.namespace = namespace


def map_entity_field(entity_path: str, *, namespace: bool = False) -> EntityFieldMapping:
    """Map a public filter field or namespace to its entity-store path."""

    return EntityFieldMapping(entity_path=entity_path, namespace=namespace)


def _translate_operation(
    operation: FilterOperation,
    field_map: dict[str, str],
    namespace_map: dict[str, str],
) -> FilterOperation:
    if isinstance(operation, ComparisonOperation):
        mapped_field = field_map.get(operation.field)
        if mapped_field is None:
            for prefix, entity_prefix in namespace_map.items():
                if operation.field == prefix or operation.field.startswith(f"{prefix}."):
                    mapped_field = entity_prefix + operation.field[len(prefix) :]
                    break
        if mapped_field is None or mapped_field == operation.field:
            return operation
        return ComparisonOperation(operator=operation.operator, field=mapped_field, value=operation.value)

    if isinstance(operation, LogicalOperation):
        return LogicalOperation(
            operator=operation.operator,
            operations=[_translate_operation(child, field_map, namespace_map) for child in operation.operations],
        )
    return operation


class EntityFilter(PluginFilter):
    """Filter that translates public fields to entity-store data paths."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    _entity_field_map_cache: ClassVar[dict[str, str] | None] = None
    _entity_namespace_map_cache: ClassVar[dict[str, str] | None] = None

    @classmethod
    def _get_entity_field_map(cls) -> dict[str, str]:
        cached = cls.__dict__.get("_entity_field_map_cache")
        if cached is not None:
            return cached

        field_map: dict[str, str] = {}
        for field_name, field_info in cls.model_fields.items():
            mapping = next(
                (item for item in field_info.metadata if isinstance(item, EntityFieldMapping)),
                None,
            )
            if mapping is not None:
                if not mapping.namespace:
                    field_map[field_name] = mapping.entity_path
            elif field_name not in ENTITY_BASE_FIELDS:
                field_map[field_name] = f"data.{field_name}"

        cls._entity_field_map_cache = field_map
        return field_map

    @classmethod
    def _get_entity_namespace_map(cls) -> dict[str, str]:
        cached = cls.__dict__.get("_entity_namespace_map_cache")
        if cached is not None:
            return cached

        namespace_map: dict[str, str] = {}
        for field_name, field_info in cls.model_fields.items():
            mapping = next(
                (item for item in field_info.metadata if isinstance(item, EntityFieldMapping) and item.namespace),
                None,
            )
            if mapping is not None:
                namespace_map[field_name] = mapping.entity_path

        cls._entity_namespace_map_cache = namespace_map
        return namespace_map

    @classmethod
    def translate_operation(cls, operation: FilterOperation) -> FilterOperation:
        return _translate_operation(
            operation,
            cls._get_entity_field_map(),
            cls._get_entity_namespace_map(),
        )


class NumberFilter(PluginFilter):
    gte: float | None = Field(
        None,
        alias="$gte",
        serialization_alias="$gte",
        description="Filter for results greater than or equal to this value.",
    )
    lte: float | None = Field(
        None,
        alias="$lte",
        serialization_alias="$lte",
        description="Filter for results less than or equal to this value.",
    )
    gt: float | None = Field(
        None,
        alias="$gt",
        serialization_alias="$gt",
        description="Filter for results greater than this value.",
    )
    lt: float | None = Field(
        None,
        alias="$lt",
        serialization_alias="$lt",
        description="Filter for results less than this value.",
    )
    eq: float | None = Field(
        None,
        alias="$eq",
        serialization_alias="$eq",
        description="Filter for results equal to this value.",
    )

    model_config = ConfigDict(
        extra="forbid",
        protected_namespaces=(),
        populate_by_name=True,
        json_schema_extra={"minProperties": 1},
    )
