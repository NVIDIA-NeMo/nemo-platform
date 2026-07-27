# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Configuration for the Iron Swarm plugin.

Declares :attr:`plugin_name` / :attr:`plugin_description` as ``ClassVar`` strings and
plugin-specific fields with defaults, following the
:class:`~nemo_platform_plugin.config.NemoConfig` pattern.

Operators set values via environment variables (``NEMO_IRON_SWARM_*``) or the Helm
``platformConfig.iron_swarm`` key. iron-swarm runs in its own isolated venv (:attr:`venv_path`)
and the plugin invokes its CLI by subprocess rather than importing it. garak — which iron-swarm's
agent_breaker attacker spawns — lives in a *second* dedicated venv (:attr:`garak_venv_path`), kept
separate because garak pulls ``litellm`` (``httpx>=0.28``) and ``torch`` that would otherwise
conflict with iron-swarm's dependencies. The plugin points iron-swarm at it via the
``IRON_SWARM_GARAK_PYTHON`` environment variable.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import ClassVar

import yaml
from nemo_platform_plugin.config import NemoConfig
from pydantic import Field

# Env var iron-swarm reads to locate the garak venv its agent_breaker attacker spawns. The plugin
# exports it (to ``garak_python``) for both ``iron-swarm setup`` (provision) and ``iron-swarm run``.
GARAK_PYTHON_ENVVAR = "IRON_SWARM_GARAK_PYTHON"

# iron-swarm's orchestrator reads this directly from the process env (no IGW routing).
INFERENCE_API_KEY_ENVVAR = "INFERENCE_API_KEY"  # pragma: allowlist secret


def _default_venv_path() -> Path:
    """Default location for iron-swarm's dedicated venv (created by ``nemo iron-swarm setup``)."""
    return Path.home() / ".iron-swarm" / "venv"


def _default_garak_venv_path() -> Path:
    """Default location for the dedicated garak venv iron-swarm's agent_breaker spawns.

    Matches iron-swarm's own default (``~/.iron-swarm/garak-venv``) so the
    ``IRON_SWARM_GARAK_PYTHON`` export and iron-swarm's fallback agree.
    """
    return Path.home() / ".iron-swarm" / "garak-venv"


def _default_operator_env_file() -> Path:
    """Default location for iron-swarm's own operator dotenv (provisioned by ``setup``)."""
    return Path.home() / ".iron-swarm" / ".env"


def read_env_file(path: Path) -> dict[str, str]:
    """Minimal dotenv reader: skips blank/`#` lines, strips `export `/quotes. `{}` if missing."""
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export ") :]
        key, sep, value = stripped.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def write_env_file(path: Path, values: Mapping[str, str]) -> None:
    """Write *values* as a dotenv at *path*, mode 0600 from creation.

    Opened with the mode applied up front rather than chmod'd afterwards: a plain write lands at the
    default umask (typically 0644), leaving the credentials world-readable until the chmod lands.
    Every dotenv this plugin writes holds provider keys, so both call sites go through here.
    """
    body = "".join(f"{key}={value}\n" for key, value in values.items())
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(body)
    os.chmod(path, 0o600)  # O_CREAT ignores the mode when the file already exists


def missing_secrets(
    manifest_path: Path,
    *,
    env_files: Iterable[Path] = (),
    environ: Mapping[str, str] | None = None,
) -> list[str]:
    """Return the manifest's declared victim secrets that no available source provides.

    Sources: *environ* (defaults to ``os.environ``), the manifest's own ``secrets_file`` (resolved
    next to the manifest), and each dotenv in *env_files* (e.g. the operator env + a ``--env-file``).
    A name set to an empty value counts as missing — ``KEY=`` in a dotenv or ``export KEY=""`` would
    otherwise pass this gate and resurface minutes later as a provider auth error.
    Returns the missing names in declaration order; ``[]`` when none are declared or the manifest
    can't be read (parsing is not this check's job).
    """
    try:
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return []
    agent = data.get("agent", {}) if isinstance(data, dict) else {}
    declared = [name for name in (agent.get("secrets") or []) if isinstance(name, str)]
    if not declared:
        return []

    available = _non_empty_keys(os.environ if environ is None else environ)
    secrets_file = agent.get("secrets_file")
    if isinstance(secrets_file, str) and secrets_file:
        # `secrets_file` may be relative to the manifest or already absolute (see jobs/manifest.py);
        # `/` handles both.
        available |= _non_empty_keys(read_env_file(manifest_path.parent / secrets_file))
    for path in env_files:
        available |= _non_empty_keys(read_env_file(Path(path)))
    return [name for name in declared if name not in available]


def _non_empty_keys(values: Mapping[str, str]) -> set[str]:
    """Names in *values* that carry an actual value; a blank one provides nothing."""
    return {name for name, value in values.items() if value and value.strip()}


class IronSwarmConfig(NemoConfig):
    """Configuration for the NeMo Platform Iron Swarm plugin.

    All fields have defaults so the plugin loads without operator configuration; the
    iron-swarm venv itself is provisioned on demand by ``nemo iron-swarm setup``.
    """

    plugin_name: ClassVar[str] = "iron_swarm"
    plugin_description: ClassVar[str] = "Configuration for the NeMo Platform Iron Swarm plugin."

    default_workspace: str = Field(
        default="default",
        description="Workspace used to resolve agents and store run records when none is given.",
    )
    venv_path: Path = Field(
        default_factory=_default_venv_path,
        description=(
            "Directory holding iron-swarm's dedicated venv. The plugin invokes "
            "{venv_path}/bin/iron-swarm by subprocess. Set NEMO_IRON_SWARM_VENV_PATH to override."
        ),
    )
    iron_swarm_spec: str = Field(
        default="iron-swarm",
        description=(
            "Package spec `nemo iron-swarm setup` installs into the venv (e.g. 'iron-swarm', "
            "'iron-swarm==0.0.1', or a local path/VCS URL for development)."
        ),
    )
    garak_venv_path: Path = Field(
        default_factory=_default_garak_venv_path,
        description=(
            "Directory holding the dedicated garak venv. iron-swarm's agent_breaker spawns garak "
            "from {garak_venv_path}/bin/python; the plugin exports IRON_SWARM_GARAK_PYTHON to it so "
            "`iron-swarm setup` provisions there (the garak version pin lives in iron-swarm). "
            "Set NEMO_IRON_SWARM_GARAK_VENV_PATH to override."
        ),
    )
    require_sandbox: bool = Field(
        default=True,
        description=(
            "When True, init/run preflight (doctor) fails hard if Docker or the OpenShell "
            "gateway is unavailable. Set False only for dry-run/manifest-only flows."
        ),
    )
    operator_env_file: Path = Field(
        default_factory=_default_operator_env_file,
        description=(
            "Dotenv holding iron-swarm's own inference credential, provisioned by `setup` and "
            "injected into every `run`. Set NEMO_IRON_SWARM_OPERATOR_ENV_FILE to override."
        ),
    )
    inference_secret_name: str = Field(
        default="iron-swarm-inference-key",
        description="NeMo Secret name `setup` reads iron-swarm's own inference key from, if present.",
    )

    @property
    def state_dir(self) -> Path:
        """Base dir for iron-swarm on-host state (the venvs live under it; also run-event logs)."""
        return self.venv_path.parent

    @property
    def iron_swarm_bin(self) -> Path:
        """Path to the iron-swarm CLI inside the dedicated venv."""
        return self.venv_path / "bin" / "iron-swarm"

    @property
    def garak_python(self) -> Path:
        """Path to the Python interpreter inside the dedicated garak venv."""
        return self.garak_venv_path / "bin" / "python"
