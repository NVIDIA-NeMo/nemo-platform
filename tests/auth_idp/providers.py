# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    mode: str
    compose_file: Path | None
    gateway_base_url: str
    issuer_url: str
    discovery_url: str
    nemo_config: Path
    machine_principal_id: str
    machine_expected_groups: list[str]
    token_endpoint: str | None
    human_grant: dict[str, str] | None
    machine_grant: dict[str, str] | None
    healthchecks: list[dict[str, str]]
    startup_timeouts: dict[str, int]
    compose_project_name: str | None = None


def load_provider_config(manifest_path: Path) -> ProviderConfig:
    data = yaml.safe_load(manifest_path.read_text())
    return ProviderConfig(
        name=data["provider"],
        mode=data["mode"],
        compose_file=(None if not data.get("compose_file") else manifest_path.parent / data["compose_file"]),
        gateway_base_url=data["gateway_base_url"],
        issuer_url=data["issuer_url"],
        discovery_url=data["discovery_url"],
        nemo_config=manifest_path.parent / data["nemo_config"],
        machine_principal_id=data["machine_identity"]["principal_id"],
        machine_expected_groups=list(data["machine_identity"]["expected_groups"]),
        token_endpoint=data.get("token_acquisition", {}).get("token_endpoint"),
        human_grant=data.get("token_acquisition", {}).get("human_grant"),
        machine_grant=data.get("token_acquisition", {}).get("machine_grant"),
        healthchecks=list(data.get("healthchecks", [])),
        startup_timeouts=dict(data.get("startup_timeouts", {})),
    )


def load_provider_configs() -> list[ProviderConfig]:
    configs: list[ProviderConfig] = []
    for manifest_path in sorted(Path("contrib/auth").glob("*/manifest.yaml")):
        configs.append(load_provider_config(manifest_path))
    return configs


def load_provider_configs_by_mode(mode: str) -> list[ProviderConfig]:
    return [provider for provider in load_provider_configs() if provider.mode == mode]


def load_provider_names() -> list[str]:
    return [provider.name for provider in load_provider_configs()]


def load_provider_names_by_mode(mode: str) -> list[str]:
    return [provider.name for provider in load_provider_configs_by_mode(mode)]


def load_provider_matrix() -> list[ProviderConfig]:
    return [
        provider
        for provider in load_provider_configs()
        if provider.mode == "compose-ci" and provider.name == "authentik"
    ]
