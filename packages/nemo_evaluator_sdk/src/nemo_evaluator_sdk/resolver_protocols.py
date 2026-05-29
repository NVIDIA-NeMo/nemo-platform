# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Resolver protocols for evaluator SDK references."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from nemo_evaluator_sdk.values.common import SecretRef
from nemo_evaluator_sdk.values.models import Model, ModelRef


@runtime_checkable
class SecretResolver(Protocol):
    """Resolve evaluator secret references to secret values."""

    async def resolve_secret(self, secret_ref: SecretRef) -> str | None:
        """Return the secret value for ``secret_ref`` when available."""
        ...


@runtime_checkable
class ModelResolver(Protocol):
    """Resolve evaluator model references to concrete SDK model bindings."""

    async def resolve_model(self, model_ref: ModelRef) -> Model:
        """Return the concrete model binding for ``model_ref``."""
        ...
