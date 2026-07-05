# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Attack stage: run garak through the Auditor service, or replay a saved hitlog.

Live launch goes through the Auditor SDK (``client.auditor.run``), which returns
report *artifact* URLs, not structured hits; this adapter fetches the
``report-hitlog-jsonl`` artifact and parses it. Replay mode reads a saved hitlog
file for a deterministic run (PRD Requirement 7).

The ``nemo_auditor`` import is deferred into the config/target builders so the
module (and replay mode) load without the Auditor plugin installed.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from nemo_agents_plugin.hardening.hitlog import parse_hitlog
from nemo_agents_plugin.hardening.models import AttackResult

_HITLOG_ARTIFACT_KEY = "report-hitlog-jsonl"


class AuditorAttacker:
    def __init__(
        self,
        platform: Any,
        *,
        probe_spec: str,
        seed: int,
        target_type: str,
        target_model: str,
        target_options: dict[str, Any],
        total_attempts: int,
        workspace: str = "default",
    ) -> None:
        self._platform = platform
        self._probe_spec = probe_spec
        self._seed = seed
        self._target_type = target_type
        self._target_model = target_model
        self._target_options = target_options
        self._total_attempts = total_attempts
        self._workspace = workspace

    def _build_config(self) -> Any:
        from nemo_auditor.entities import AuditConfig, AuditPluginsData, AuditRunData

        return AuditConfig(
            name="hardening-attack",
            workspace=self._workspace,
            plugins=AuditPluginsData(probe_spec=self._probe_spec),
            run=AuditRunData(seed=self._seed),
        )

    def _build_target(self) -> Any:
        from nemo_auditor.entities import AuditTarget

        return AuditTarget(
            name="agent-under-test",
            workspace=self._workspace,
            type=self._target_type,
            model=self._target_model,
            options=self._target_options,
        )

    def _download_artifact(self, artifact_url: str) -> Path:
        """Resolve a report artifact URL to a local path.

        Local Auditor runs emit ``file://<abs-path>`` URLs, so the scheme is
        stripped to a Path. A remote/object-store URL would fetch here; that
        path is out of Phase 1's local-run scope.
        """
        parsed = urlparse(artifact_url)
        if parsed.scheme in ("", "file"):
            return Path(unquote(parsed.path))
        raise RuntimeError(f"Unsupported artifact URL scheme {parsed.scheme!r}; local runs emit file:// URLs.")

    def _result(self, hits: list) -> AttackResult:
        return AttackResult(
            probes=[p.strip() for p in self._probe_spec.split(",") if p.strip()],
            hits=hits,
            total_attempts=self._total_attempts,
            seed=self._seed,
        )

    def attack_live(self) -> AttackResult:
        result = self._platform.auditor.run(config=self._build_config(), target=self._build_target())
        artifacts = result.get("results", {}) if isinstance(result, dict) else {}
        hitlog_ref = artifacts.get(_HITLOG_ARTIFACT_KEY)
        if not hitlog_ref or not hitlog_ref.get("artifact_url"):
            raise RuntimeError(f"Auditor scan returned no {_HITLOG_ARTIFACT_KEY} artifact; cannot parse hits.")
        return self._result(parse_hitlog(self._download_artifact(hitlog_ref["artifact_url"])))

    def attack_replay(self, hitlog_path: Path) -> AttackResult:
        return self._result(parse_hitlog(hitlog_path))
