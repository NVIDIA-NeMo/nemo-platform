# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Task sandbox image build.

Split into two layers so it's clear what every build approach shares versus
what's specific to one approach (see docs/internals/ARCHITECTURE.md § Container Build):

- ``queue_worker`` — durable database-leased worker used in production.
- ``worker`` — legacy synchronous primitives retained for compatibility.
- ``buildkit`` — the current build *approach*: drive BuildKit via `buildctl`
  over gRPC.
- ``image_builder_service`` — uploaded-context build/sign integration.
- ``cloud_build`` — Google Cloud Build + GAR integration for GKE installs.

Re-exported so callers use a stable `scaled_evals.api.build` surface regardless
of how the internals are split.
"""

from __future__ import annotations

from typing import Any

from scaled_evals.api.build.errors import BuildError

__all__ = [
    "BuildError",
    "build_cloud_revision_image",
    "build_revision_image",
    "resolve_uploaded_revision_image",
    "run_finalize_build",
    "run_finalize_uploaded",
]


def __getattr__(name: str) -> Any:
    if name == "build_cloud_revision_image":
        from scaled_evals.api.build.cloud_build import build_revision_image

        return build_revision_image
    if name == "build_revision_image":
        from scaled_evals.api.build.buildkit import build_revision_image

        return build_revision_image
    if name == "resolve_uploaded_revision_image":
        from scaled_evals.api.build.image_builder_service import resolve_uploaded_revision_image

        return resolve_uploaded_revision_image
    if name in {"run_finalize_build", "run_finalize_uploaded"}:
        from scaled_evals.api.build.worker import run_finalize_build, run_finalize_uploaded

        return {
            "run_finalize_build": run_finalize_build,
            "run_finalize_uploaded": run_finalize_uploaded,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
