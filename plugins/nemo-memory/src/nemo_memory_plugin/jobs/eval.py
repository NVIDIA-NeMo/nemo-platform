# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""EvalJob — diff two memory-triage artifacts and emit an agreement report.

Registered under ``nemo.jobs`` as ``memory.eval``. Pure offline
work, no LLM calls: loads two JSON artifacts produced by the
``triage`` job and computes strict / two-way / confusion-matrix
agreement metrics plus the per-entry delta set.

Both inputs (``baseline``, ``candidate``) and the output accept either
local paths or NeMo Platform fileset references. The same dispatch
heuristic the triage job uses applies: leading ``.``, ``/``,
``..``, or ``~`` (or any existing local file) is a path; everything
else resolves as a fileset reference.

Typical uses:

1. **Intra-judge stability check**: Sonnet-laptop baseline vs
   Sonnet-omnistation run on the same corpus. Establishes the noise
   floor (~95% strict on the PoC USER corpus).
2. **Tuned-model evaluation**: Sonnet baseline vs tuned-Nemotron
   candidate (the production target).
3. **Cross-judge calibration**: Sonnet vs Nemotron over the same
   corpus. Research signal for the v1 calibration findings in
   ``triage/RESULTS.md``.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from nemo_platform import NeMoPlatform
from nemo_platform_plugin.job import NemoJob
from nemo_platform_plugin.job_context import JobContext
from nemo_platform_plugin.refs import OutputTarget
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class EvalConfig(BaseModel):
    """Spec for ``nemo memory eval``.

    Both ``baseline`` and ``candidate`` point at a JSON artifact produced
    by the ``triage`` job. Either may be a local path or a
    fileset reference; mixing-and-matching is fine (baseline on disk,
    candidate in a fileset, or vice-versa).
    """

    baseline: str = Field(
        description=(
            "Baseline triage artifact (the reference). Accepts EITHER a local "
            "path to a .json file OR a NeMo Platform fileset reference "
            "('fileset-name' or 'workspace/fileset-name'). For fileset refs, "
            "the fileset must contain exactly one .json file."
        ),
    )
    candidate: str = Field(
        description=(
            "Candidate triage artifact to compare against the baseline. Same "
            "shape as 'baseline': local path or fileset reference. The "
            "candidate is conventionally the run under evaluation (tuned model, "
            "different judge, fresh run on a different machine, etc.)."
        ),
    )
    workspace: str = Field(
        default="default",
        description=(
            "Workspace used to resolve unqualified fileset references in "
            "baseline / candidate / output. Ignored for local paths."
        ),
    )
    output: OutputTarget | None = Field(
        default=None,
        description=(
            "Where the JSON + Markdown agreement report lands. Same path-or-"
            "fileset dispatch as the triage job: path-shaped values write to a "
            "local directory; bare names resolve as a fileset reference. "
            "Filesets auto-create on success. When omitted, falls back to "
            "ctx.storage.persistent / 'memory-eval-output'."
        ),
    )
    basename: str = Field(
        default="memory-eval",
        description=(
            "Basename for the report pair: writes {basename}.json + {basename}.md. "
            "Use a versioned basename (e.g. 'sonnet-vs-self-omnistation') so "
            "comparable reports don't overwrite each other."
        ),
    )


class EvalJob(NemoJob):
    """Memory-triage baseline-vs-candidate evaluator."""

    name: ClassVar[str] = "eval"
    description: ClassVar[str] = (
        "Diff two memory-triage artifacts and emit an agreement report (strict / 2-way / confusion / deltas)."
    )
    container: ClassVar[str] = "cpu-tasks"

    def run(
        self,
        config: dict,
        *,
        ctx: JobContext,
        sdk: NeMoPlatform | None = None,
    ) -> dict:
        # Inline imports: keep entry-point load cheap and isolate eval-only
        # dependencies to the actual run path.
        from nemo_memory_plugin.triage.eval import compare_runs, write_report_artifacts
        from nemo_memory_plugin.triage.fileset_io import (
            resolve_input_artifact,
            resolve_output_target,
        )

        cfg = EvalConfig.model_validate(config)

        with (
            resolve_input_artifact(
                cfg.baseline,
                workspace=cfg.workspace,
                sdk=sdk,
                suffix=".json",
                kind_label="baseline artifact",
            ) as baseline_path,
            resolve_input_artifact(
                cfg.candidate,
                workspace=cfg.workspace,
                sdk=sdk,
                suffix=".json",
                kind_label="candidate artifact",
            ) as candidate_path,
            resolve_output_target(
                cfg.output,
                workspace=cfg.workspace,
                basename=cfg.basename,
                ctx=ctx,
                sdk=sdk,
                persistent_subdir="memory-eval-output",
                job_label="eval",
            ) as output_dir,
        ):
            logger.info(
                "eval: baseline=%s candidate=%s output=%s",
                baseline_path,
                candidate_path,
                output_dir,
            )
            report = compare_runs(baseline_path, candidate_path)
            json_path, md_path = write_report_artifacts(report, output_dir, basename=cfg.basename)

        # Headline metrics in the return value so platform UI / logs surface
        # them without cracking open the JSON. Three rates plus coverage.
        return {
            "baseline_store_name": report.baseline_store_name,
            "candidate_store_name": report.candidate_store_name,
            "baseline_council": report.baseline_council,
            "candidate_council": report.candidate_council,
            "common_entries": report.common_entries,
            "baseline_only_entries": len(report.baseline_only_entries),
            "candidate_only_entries": len(report.candidate_only_entries),
            "strict_rate": report.strict_rate,
            "retain_vs_drop_rate": report.retain_vs_drop_rate,
            "promote_threshold_rate": report.promote_threshold_rate,
            "disagreements": len(report.deltas),
            "artifacts": {
                "json": str(json_path),
                "markdown": str(md_path),
            },
        }
