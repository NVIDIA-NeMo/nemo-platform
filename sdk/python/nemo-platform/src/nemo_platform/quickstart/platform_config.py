# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Platform configuration for the nmp-api container."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from typing_extensions import Self


class PlatformConfig(BaseModel):
    """Platform configuration passed to the nmp-api container.

    This configuration can be passed to the container either via:
    1. Environment variables (via to_env_vars())
    2. Mounted YAML file at /etc/nmp/platform-config.yaml
    """

    nvidia_api_key: str | None = Field(
        default=None,
        description="NVIDIA API key for inference services",
    )

    @classmethod
    def get_default(cls) -> Self:
        """Return default platform configuration."""
        return cls()

    @classmethod
    def load(cls, path: Path) -> Self:
        """Load platform config from YAML file.

        Args:
            path: Path to the YAML configuration file.

        Returns:
            PlatformConfig instance.

        Raises:
            FileNotFoundError: If the config file doesn't exist.
            ValueError: If the YAML is invalid.
        """
        if not path.exists():
            raise FileNotFoundError(f"Platform config file not found: {path}")

        with open(path, "r") as f:
            try:
                config_data = yaml.safe_load(f) or {}
            except yaml.YAMLError as e:
                raise ValueError(f"Error parsing platform config at {path}: {e}") from e

        if "platform" in config_data or "files" in config_data:
            values: dict[str, Any] = {}
            platform_config = config_data.get("platform")
            if isinstance(platform_config, dict):
                nvidia_api_key = platform_config.get("nvidia_api_key")
                if isinstance(nvidia_api_key, str):
                    values["nvidia_api_key"] = nvidia_api_key
            return cls.model_validate(values)

        return cls.model_validate(config_data)

    def to_config_dict(self) -> dict[str, Any]:
        """Convert quickstart settings to the global config shape mounted in the container."""
        config_data: dict[str, Any] = {
            "files": {
                "default_storage_config": {
                    "type": "local",
                    "path": "/data/files_storage",
                }
            }
        }
        if self.nvidia_api_key:
            config_data["platform"] = {"nvidia_api_key": self.nvidia_api_key}
        return config_data

    def save(self, path: Path) -> None:
        """Save platform config to YAML file.

        Args:
            path: Path to save the configuration.
        """
        path.parent.mkdir(parents=True, exist_ok=True)

        config_data = self.to_config_dict()

        with open(path, "w") as f:
            yaml.safe_dump(config_data, f, default_flow_style=False, sort_keys=False)

    def to_env_vars(self) -> dict[str, str]:
        """Convert config to environment variables for the container.

        Returns:
            Dictionary of environment variable name to value.
        """
        env: dict[str, str] = {}

        if self.nvidia_api_key:
            env["NVIDIA_API_KEY"] = self.nvidia_api_key

        return env
