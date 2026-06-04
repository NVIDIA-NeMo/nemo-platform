# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Runtime context for service-backed Anonymizer execution."""

from __future__ import annotations

from typing import Protocol

import data_designer.config as dd
from data_designer.config.models import ModelProvider as DDModelProvider
from data_designer_nemo.model_provider import (
    make_model_provider_registry,
)
from data_designer_nemo.sdk_translation import sync_to_async_sdk
from nemo_anonymizer_plugin.app.errors import AnonymizerInvalidConfigError
from nemo_anonymizer_plugin.app.input import (
    AnonymizerInputSpec,
    PreparedAnonymizerInput,
    prepare_anonymizer_input_async,
    validate_anonymizer_input_source,
)
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform


class AnonymizerContext(Protocol):
    async def make_model_providers(
        self,
        model_configs: list[dd.ModelConfig] | None,
        *,
        require_model_configs: bool,
    ) -> list[DDModelProvider] | None: ...

    async def prepare_input(self, data: AnonymizerInputSpec) -> PreparedAnonymizerInput: ...

    def validate_input_reference(self, data: AnonymizerInputSpec) -> None: ...


class ServiceAnonymizerContext:
    def __init__(self, sdk: AsyncNeMoPlatform | NeMoPlatform, workspace: str):
        self._sdk = sdk
        self._workspace = workspace

    async def make_model_providers(
        self,
        model_configs: list[dd.ModelConfig] | None,
        *,
        require_model_configs: bool,
    ) -> list[DDModelProvider] | None:
        if not model_configs:
            if require_model_configs:
                raise AnonymizerInvalidConfigError(
                    "model_configs are required for anonymizer execution so requests route through NeMo Platform "
                    "Inference Gateway instead of Anonymizer library defaults."
                )
            return None
        async_sdk = sync_to_async_sdk(self._sdk) if isinstance(self._sdk, NeMoPlatform) else self._sdk
        registry = await make_model_provider_registry(
            model_configs,
            sdk=async_sdk,
            default_workspace=self._workspace,
        )
        if registry is None:
            return None
        return registry.providers

    async def prepare_input(self, data: AnonymizerInputSpec) -> PreparedAnonymizerInput:
        return await prepare_anonymizer_input_async(
            data,
            sdk=self._sdk,
            workspace=self._workspace,
            allow_local_paths=False,
        )

    def validate_input_reference(self, data: AnonymizerInputSpec) -> None:
        validate_anonymizer_input_source(data, workspace=self._workspace, allow_local_paths=False)


def create_anonymizer_context(
    sdk: AsyncNeMoPlatform | NeMoPlatform,
    workspace: str,
) -> AnonymizerContext:
    return ServiceAnonymizerContext(sdk, workspace)
