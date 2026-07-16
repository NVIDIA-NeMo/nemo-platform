# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Built-in metric type catalog (`MetricVariants`), shared by the CLI and the REST routes."""

from __future__ import annotations

import inspect
from enum import Enum
from types import UnionType
from typing import Annotated, Any, Union, get_args, get_origin

from nemo_evaluator_sdk.metrics.types import MetricVariants
from nemo_evaluator_sdk.values.metrics import _RAGASBase
from pydantic import BaseModel


def _unwrap_metric_model_classes(type_hint: object) -> list[type[BaseModel]]:
    """Return Pydantic model classes from an annotated metric union."""
    origin = get_origin(type_hint)
    if origin is Annotated:
        return _unwrap_metric_model_classes(get_args(type_hint)[0])
    if origin in {Union, UnionType}:
        model_classes: list[type[BaseModel]] = []
        for union_member in get_args(type_hint):
            model_classes.extend(_unwrap_metric_model_classes(union_member))
        return model_classes
    if isinstance(type_hint, type) and issubclass(type_hint, BaseModel):
        return [type_hint]
    return []


def _json_value(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    return value


def _metric_type_values(model_cls: type[BaseModel]) -> list[str]:
    type_field = model_cls.model_fields["type"]
    annotation_args = get_args(type_field.annotation)
    if annotation_args:
        return [str(_json_value(value)) for value in annotation_args]
    return [str(_json_value(type_field.default))]


def _is_ragas_metric(model_cls: type[BaseModel]) -> bool:
    return issubclass(model_cls, _RAGASBase)


def metric_type_models() -> dict[str, type[BaseModel]]:
    """Map each built-in metric type name to its Pydantic config model class."""
    metric_types: dict[str, type[BaseModel]] = {}
    for model_cls in _unwrap_metric_model_classes(MetricVariants):
        for metric_type in _metric_type_values(model_cls):
            existing = metric_types.get(metric_type)
            if existing is not None and existing is not model_cls:
                raise ValueError(
                    f"Duplicate metric type '{metric_type}' mapped to both {existing.__name__} and {model_cls.__name__}"
                )
            metric_types[metric_type] = model_cls
    return dict(sorted(metric_types.items()))


def metric_type_entries() -> list[dict[str, str]]:
    """List `{name, description}` for every built-in metric type (RAGAS sorted last)."""
    return [
        {
            "name": metric_type,
            "description": inspect.getdoc(model_cls) or "",
        }
        for metric_type, model_cls in sorted(
            metric_type_models().items(),
            key=lambda item: (_is_ragas_metric(item[1]), item[0]),
        )
    ]


def metric_type_schema(metric_type: str) -> dict[str, Any] | None:
    """Return the JSON schema for a metric type, or None if the type is unknown."""
    model_cls = metric_type_models().get(metric_type)
    if model_cls is None:
        return None
    return model_cls.model_json_schema()
