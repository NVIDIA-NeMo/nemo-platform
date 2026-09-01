# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Curated Harbor runner compatibility catalog.

The catalog is intentionally code-owned and exact-version-only. User input is
resolved before a run is queued, so aliases cannot drift while benchmark
members are being created or when a worker resumes an evaluation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from typing import Any


@lru_cache(maxsize=1)
def qualification_catalog() -> dict[str, Any]:
    """Load the immutable, checked-in Harbor qualification evidence."""
    path = files("scaled_evals").joinpath("data/harbor_runner_qualifications.json")
    return json.loads(path.read_text(encoding="utf-8"))


_CATALOG = qualification_catalog()
DEFAULT_HARBOR_VERSION = str(_CATALOG["default_version"])
SANDBOX_K8S_VERSION = str(_CATALOG["sandbox_k8s"]["version"])
ADAPTER_VERSION = str(_CATALOG["adapter"]["version"])


@dataclass(frozen=True)
class HarborRunner:
    version: str
    harbor_dir: str
    sandbox_k8s_version: str = SANDBOX_K8S_VERSION
    adapter_version: str = ADAPTER_VERSION

    def qualification_metadata(self) -> dict[str, Any]:
        """Return the complete evidence snapshot persisted with each run."""
        catalog = qualification_catalog()
        return {
            "schema_version": catalog["schema_version"],
            "release": {"version": self.version, **catalog["releases"][self.version]},
            "sandbox_k8s": dict(catalog["sandbox_k8s"]),
            "adapter": dict(catalog["adapter"]),
            "validation": dict(catalog["validation"]),
        }


_RUNNERS = {
    version: HarborRunner(version=version, harbor_dir=f"/opt/harbor/{version}")
    for version, release in _CATALOG["releases"].items()
    if release["selectable"]
}
_ALIASES = dict(_CATALOG["aliases"])


class UnsupportedHarborVersion(ValueError):
    """Raised when a caller requests a runner outside the curated catalog."""


def supported_harbor_versions() -> tuple[str, ...]:
    return tuple(_RUNNERS)


def candidate_harbor_versions() -> tuple[str, ...]:
    """Return package-compatible releases awaiting signed-image/E2E qualification."""
    return tuple(version for version, release in _CATALOG["releases"].items() if not release["selectable"])


def resolve_harbor_runner(requested: str | None) -> HarborRunner:
    """Resolve an omitted, aliased, or exact selector to immutable metadata."""
    selector = (requested or "default").strip()
    exact = _ALIASES.get(selector, selector)
    try:
        return _RUNNERS[exact]
    except KeyError as exc:
        choices = ", ".join(supported_harbor_versions())
        aliases = ", ".join(sorted(_ALIASES))
        raise UnsupportedHarborVersion(
            f"unsupported Harbor version {selector!r}; supported exact versions: {choices}; aliases: {aliases}"
        ) from exc
