# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from typing import ClassVar

import nmp.evaluator.app.values as app
from nmp.common.entities.client import EntityBase
from nmp.evaluator.entities.metrics import Metric
from nmp.evaluator.entities.utils import EmbeddedEntityMixin
from pydantic import Field


class Benchmark(EmbeddedEntityMixin, app.Benchmark, EntityBase):
    """Benchmark entity for grouping metrics."""

    __embedded_entity_fields__: ClassVar[dict[str, type]] = {"metrics": Metric}  # ty: ignore[invalid-assignment]
    metrics: list[Metric] = Field(min_length=1, description="List of metrics that comprise this benchmark.")
