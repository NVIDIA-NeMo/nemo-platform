# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from typing import Protocol

import data_designer.config as dd
from data_designer.config.utils.constants import MANAGED_ASSETS_PATH
from data_designer.engine.resources.person_reader import PersonReader, create_person_reader
from data_designer.engine.resources.seed_reader import (
    AgentRolloutSeedReader,
    DataFrameSeedReader,
    DirectorySeedReader,
    FileContentsSeedReader,
    HuggingFaceSeedReader,
    LocalFileSeedReader,
    SeedReader,
)
from data_designer.engine.secret_resolver import (
    CompositeResolver,
    EnvironmentResolver,
    PlaintextResolver,
    SecretResolver,
)
from data_designer_nemo.errors import NDDError
from data_designer_nemo.fileset_file_seed_reader import FilesetFileSeedReader
from data_designer_nemo.model_provider import (
    make_local_first_model_provider_registry,
    make_model_provider_registry,
    make_noop_provider,
)
from data_designer_nemo.person_reader import FilesetsPersonReader
from data_designer_nemo.person_sampling import ensure_nemotron_personas_filesets
from data_designer_nemo.sdk_translation import sync_to_async_sdk
from data_designer_nemo.secret_resolver import NMPSecretResolver
from data_designer_nemo.seed import validate_seed
from data_designer_nemo.unsupported_features import (
    validate_no_tool_configs,
    validate_seed_config_for_execution_context,
)
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform


class DataDesignerContext(Protocol):
    async def validate(self, config: dd.DataDesignerConfig) -> list[NDDError]:
        """Run validators and return all collected errors (empty if config is valid).

        Implementations should run every sub-check, accumulating ``NDDError`` (config
        and internal) results into the returned list rather than raising on the
        first failure. Truly unexpected errors (programmer error, transport-layer
        failures outside the validators themselves) still propagate as exceptions.
        """
        ...

    def get_secret_resolver(self) -> SecretResolver: ...

    def get_seed_readers(self) -> list[SeedReader]: ...

    def get_person_reader(self) -> PersonReader: ...

    async def get_model_providers(self, model_configs: list[dd.ModelConfig]) -> list[dd.ModelProvider]: ...


class LocalDataDesignerContext:
    def __init__(self, sdk: AsyncNeMoPlatform | NeMoPlatform, workspace: str):
        self._sdk = sdk
        self._workspace = workspace

    def get_secret_resolver(self) -> SecretResolver:
        return CompositeResolver(
            resolvers=[
                EnvironmentResolver(),
                NMPSecretResolver(self._sdk, self._workspace),
                PlaintextResolver(),
            ]
        )

    async def validate(self, config: dd.DataDesignerConfig) -> list[NDDError]:
        errors: list[NDDError] = []
        try:
            validate_seed_config_for_execution_context(config, is_local=True)
        except NDDError as e:
            errors.append(e)
        return errors

    def get_seed_readers(self) -> list[SeedReader]:
        return [
            HuggingFaceSeedReader(),
            LocalFileSeedReader(),
            DataFrameSeedReader(),
            DirectorySeedReader(),
            FileContentsSeedReader(),
            AgentRolloutSeedReader(),
            FilesetFileSeedReader(self._sdk),
        ]

    def get_person_reader(self) -> PersonReader:
        return create_person_reader(str(MANAGED_ASSETS_PATH))

    async def get_model_providers(self, model_configs: list[dd.ModelConfig]) -> list[dd.ModelProvider]:
        if (
            local_first_registry := await make_local_first_model_provider_registry(
                model_configs,
                sdk=self._sdk,
                default_workspace=self._workspace,
            )
        ) is not None:
            return local_first_registry.providers

        return [make_noop_provider()]


class RemoteDataDesignerContext:
    def __init__(self, sdk: AsyncNeMoPlatform | NeMoPlatform, workspace: str):
        self._sdk = sdk
        self._workspace = workspace

    def get_secret_resolver(self) -> SecretResolver:
        return NMPSecretResolver(self._sdk, self._workspace)

    async def validate(self, config: dd.DataDesignerConfig) -> list[NDDError]:
        sdk = self._async_sdk()
        errors: list[NDDError] = []

        try:
            validate_no_tool_configs(config)
        except NDDError as e:
            errors.append(e)
        try:
            validate_seed_config_for_execution_context(config, is_local=False)
        except NDDError as e:
            errors.append(e)
        try:
            await validate_seed(config, self._workspace, sdk)
        except NDDError as e:
            errors.append(e)
        try:
            await ensure_nemotron_personas_filesets(config, sdk)
        except NDDError as e:
            errors.append(e)

        return errors

    def get_seed_readers(self) -> list[SeedReader]:
        return [
            HuggingFaceSeedReader(),
            FilesetFileSeedReader(self._sdk),
        ]

    def get_person_reader(self) -> PersonReader:
        return FilesetsPersonReader(self._sdk)

    async def get_model_providers(self, model_configs: list[dd.ModelConfig]) -> list[dd.ModelProvider]:
        sdk = self._async_sdk()

        if (
            igw_registry := await make_model_provider_registry(
                model_configs,
                sdk=sdk,
                default_workspace=self._workspace,
            )
        ) is not None:
            return igw_registry.providers

        return [make_noop_provider()]

    def _async_sdk(self) -> AsyncNeMoPlatform:
        if isinstance(self._sdk, NeMoPlatform):
            return sync_to_async_sdk(self._sdk)
        return self._sdk


def create_data_designer_context(
    is_local: bool, sdk: AsyncNeMoPlatform | NeMoPlatform, workspace: str
) -> DataDesignerContext:
    if is_local:
        return LocalDataDesignerContext(sdk, workspace)
    else:
        return RemoteDataDesignerContext(sdk, workspace)
