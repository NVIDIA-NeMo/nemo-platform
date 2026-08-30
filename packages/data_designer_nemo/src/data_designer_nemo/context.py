# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import data_designer.config as dd
from data_designer.engine.resources.person_reader import PersonReader
from data_designer.engine.resources.seed_reader import (
    DirectorySeedReader,
    FileContentsSeedReader,
    HuggingFaceSeedReader,
    SeedReader,
)
from data_designer.engine.secret_resolver import SecretResolver
from data_designer_nemo.columns import validate_config_has_no_custom_columns
from data_designer_nemo.errors import NDDError
from data_designer_nemo.fileset_file_seed_reader import FilesetFileSeedReader
from data_designer_nemo.fileset_filesystem_provider import (
    FilesetFileSystemProvider,
)
from data_designer_nemo.model_provider import (
    make_model_provider_registry,
    make_noop_provider,
)
from data_designer_nemo.person_reader import FilesetsPersonReader
from data_designer_nemo.person_sampling import ensure_nemotron_personas_filesets
from data_designer_nemo.sdk_translation import sync_to_async_sdk
from data_designer_nemo.secret_resolver import NMPSecretResolver
from data_designer_nemo.seed import validate_seed
from data_designer_nemo.tool_configs import validate_no_tool_configs
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform


class DataDesignerContext:
    def __init__(self, sdk: AsyncNeMoPlatform | NeMoPlatform, workspace: str):
        self._sdk = sdk
        self._workspace = workspace
        self._validated_filesystem_roots: set[str] = set()

    def get_secret_resolver(self) -> SecretResolver:
        return NMPSecretResolver(self._sdk, self._workspace)

    async def validate(self, config: dd.DataDesignerConfig) -> list[NDDError]:
        async_sdk = self._async_sdk()
        errors: list[NDDError] = []

        try:
            validate_config_has_no_custom_columns(config)
        except NDDError as e:
            errors.append(e)

        try:
            validate_no_tool_configs(config)
        except NDDError as e:
            errors.append(e)

        try:
            if validated_root := await validate_seed(config, self._workspace, async_sdk):
                self._validated_filesystem_roots.add(validated_root)
        except NDDError as e:
            errors.append(e)

        try:
            await ensure_nemotron_personas_filesets(config, async_sdk)
        except NDDError as e:
            errors.append(e)

        return errors

    def get_seed_readers(self) -> list[SeedReader]:
        provider = FilesetFileSystemProvider(
            self._sdk,
            workspace=self._workspace,
            validated_roots=self._validated_filesystem_roots,
        )
        return [
            HuggingFaceSeedReader(),
            FilesetFileSeedReader(self._sdk),
            DirectorySeedReader(fs_provider=provider),
            FileContentsSeedReader(fs_provider=provider),
        ]

    def get_person_reader(self) -> PersonReader | None:
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


def create_data_designer_context(sdk: AsyncNeMoPlatform | NeMoPlatform, workspace: str) -> DataDesignerContext:
    return DataDesignerContext(sdk, workspace)
