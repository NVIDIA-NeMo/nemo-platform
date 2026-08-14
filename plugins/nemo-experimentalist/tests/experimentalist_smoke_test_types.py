# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Type contract for the smoke-agent sandbox fixture."""

from pathlib import Path
from typing import Protocol


class SandboxRunner(Protocol):
    """Operations the smoke-agent E2E tests require from their fixture."""

    @property
    def platform_url(self) -> str: ...

    def run(
        self,
        command: list[str],
        *,
        log: Path,
        environment: dict[str, str] | None = None,
        capture_output: bool = False,
    ) -> str: ...

    def prepare_fixture(self, artifact_parent: Path, *, log: Path) -> tuple[str, str]: ...

    def source_path(self, path: Path) -> str: ...

    def replace_text(self, path: str, old: str, new: str, *, log: Path) -> None: ...

    def make_directories(self, *paths: str, log: Path) -> None: ...

    def copy_in(self, source: Path, destination: str, *, log: Path) -> None: ...

    def fetch(self, remote_path: str, local_parent: Path, *, log: Path) -> None: ...
