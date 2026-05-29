# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Local resolver implementations for evaluator SDK refs."""

from __future__ import annotations

import os

from nemo_evaluator_sdk.values.common import SecretRef
from nemo_evaluator_sdk.values.models import Model, ModelRef


def _candidate_env_names(secret_name: str) -> list[str]:
    """Generate environment variable names that may contain one secret."""
    names = [secret_name, secret_name.upper()]
    normalized = secret_name.replace("-", "_").replace("/", "_")
    names.extend([normalized, normalized.upper()])
    if normalized and normalized[0].isdigit():
        prefixed = f"_{normalized}"
        names.extend([prefixed, prefixed.upper()])
    return list(dict.fromkeys(names))


class LocalSecretResolver:
    """Resolve secrets from local environment variables."""

    async def resolve_secret(self, secret_ref: SecretRef) -> str | None:
        """Resolve one secret value from environment variables."""
        for candidate in _candidate_env_names(secret_ref.root):
            value = os.getenv(candidate)
            if value:
                return value
        return None


class LocalModelResolver:
    """Resolve model references from an in-process registry."""

    def __init__(self) -> None:
        """Create a resolver with an empty local model registry."""
        self._models: dict[str, Model] = {}

    def register_model(self, model_ref: ModelRef, model: Model, *, replace: bool = False) -> None:
        """Register a local model binding for a model reference."""
        if not replace and model_ref.root in self._models:
            raise ValueError(f"Model reference '{model_ref.root}' is already registered.")
        self._models[model_ref.root] = model

    def get_model(self, model_ref: ModelRef) -> Model:
        """Return the registered model binding for a model reference."""
        try:
            return self._models[model_ref.root]
        except KeyError as exc:
            raise ValueError(
                f"Model reference '{model_ref.root}' is not registered. "
                "Register it with LocalBackend.model_resolver.register_model() before local execution."
            ) from exc

    def unregister_model(self, model_ref: ModelRef) -> Model:
        """Remove and return a registered local model binding."""
        try:
            return self._models.pop(model_ref.root)
        except KeyError as exc:
            raise ValueError(f"Model reference '{model_ref.root}' is not registered.") from exc

    async def resolve_model(self, model_ref: ModelRef) -> Model:
        """Resolve one model reference from the local registry."""
        return self.get_model(model_ref)
