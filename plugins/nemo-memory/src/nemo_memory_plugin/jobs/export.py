# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ExportJob — build a labeled SFT corpus from a triage artifact.

Registered under ``nemo.jobs`` as ``memory.export``.
Pure offline work, no LLM calls: loads a triage artifact JSON + the
original pi-hermes corpus and emits a labeled JSONL dataset ready for
supervised fine-tuning of a smaller judge model.

Three artifacts land in the output target:

- ``{basename}.jsonl`` (raw labeled records)
- ``{basename}-chat.jsonl`` (messages-format records for direct SFT use)
- ``{basename}.md`` (summary)

See ``triage/finetune.py`` for the core extraction logic
and the prompt-rendering convention.
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


class ExportConfig(BaseModel):
    """Spec for ``nemo memory export``."""

    triage_artifact: str = Field(
        description=(
            "Triage artifact JSON (produced by `report.write_artifacts`). "
            "Accepts a local path OR a NeMo Platform fileset reference. "
            "The artifact must include `reference_judge` in every proposal's "
            "judge_votes; entries where the reference judge had no vote "
            "(timeout, malformed JSON) are skipped and recorded in the "
            "summary's skipped_entries."
        ),
    )
    corpus: str = Field(
        description=(
            "Original pi-hermes Markdown corpus the triage was run against. "
            "Required to attach entry text to each labeled record. Same "
            "path-or-fileset shape as the triage job's corpus field."
        ),
    )
    reference_judge: str = Field(
        description=(
            "Model id (matching `council_models` in the artifact) whose votes "
            "are used as the gold labels. For the v1 Phase 1 artifact use "
            "`azure-anthropic-claude-sonnet-4-5`; for a freshly-locked baseline "
            "use `azure-anthropic-claude-sonnet-4-6`."
        ),
    )
    candidate_judge: str | None = Field(
        default=None,
        description=(
            "Optional model id (matching `council_models` in the artifact) "
            "whose votes get compared against the reference. When set, every "
            "record gets an `is_disagreement` flag plus the candidate verdict "
            "and justification. Required when `only_disagreements` is True."
        ),
    )
    only_disagreements: bool = Field(
        default=False,
        description=(
            "When True, only records where reference_judge != candidate_judge "
            "land in the output. Used to extract just the boundary cases "
            "(the v1 40-entry Sonnet-vs-Nano disagreement set). Requires "
            "candidate_judge to be set."
        ),
    )
    workspace: str = Field(
        default="default",
        description="Workspace for unqualified fileset references. Ignored for local paths.",
    )
    output: OutputTarget | None = Field(
        default=None,
        description=(
            "Where the three artifacts land (raw JSONL + chat JSONL + summary MD). "
            "Same path-or-fileset dispatch as the triage job's output: path-shaped "
            "values write to a local directory; bare names resolve as a fileset "
            "reference (auto-created on success). When omitted, falls back to "
            "ctx.storage.persistent / 'finetune-corpus-output'."
        ),
    )
    basename: str = Field(
        default="finetune-corpus",
        description=(
            "Basename for the artifact triple: writes {basename}.jsonl + {basename}-chat.jsonl + {basename}.md."
        ),
    )


class ExportJob(NemoJob):
    """Labeled fine-tune corpus exporter (judge SFT data extraction)."""

    name: ClassVar[str] = "export"
    description: ClassVar[str] = (
        "Build a labeled SFT corpus from a triage artifact (entry + gold judgment), "
        "ready for fine-tuning a smaller judge model."
    )
    container: ClassVar[str] = "cpu-tasks"

    def run(
        self,
        config: dict,
        *,
        ctx: JobContext,
        sdk: NeMoPlatform | None = None,
    ) -> dict:
        # Inline imports for the same cheap-entry-point reason as the
        # other agents.* NemoJobs.
        from nemo_memory_plugin.triage.fileset_io import (
            resolve_input_artifact,
            resolve_output_target,
        )
        from nemo_memory_plugin.triage.finetune import (
            build_finetune_corpus,
            write_finetune_artifacts,
        )

        cfg = ExportConfig.model_validate(config)

        with (
            resolve_input_artifact(
                cfg.triage_artifact,
                workspace=cfg.workspace,
                sdk=sdk,
                suffix=".json",
                kind_label="triage artifact",
            ) as artifact_path,
            resolve_input_artifact(
                cfg.corpus,
                workspace=cfg.workspace,
                sdk=sdk,
                suffix=".md",
                kind_label="corpus",
            ) as corpus_path,
            # Three output files instead of the usual pair: raw JSONL,
            # chat JSONL, and Markdown summary. expected_suffixes covers
            # both jsonl shapes so the upload helper checks for all
            # three before declaring success.
            resolve_output_target(
                cfg.output,
                workspace=cfg.workspace,
                basename=cfg.basename,
                ctx=ctx,
                sdk=sdk,
                persistent_subdir="memory-export-output",
                job_label="export",
                expected_suffixes=(".jsonl", "-chat.jsonl", ".md"),
            ) as output_dir,
        ):
            logger.info(
                "export: artifact=%s corpus=%s ref=%s cand=%s only_disagreements=%s",
                artifact_path,
                corpus_path,
                cfg.reference_judge,
                cfg.candidate_judge,
                cfg.only_disagreements,
            )
            records, summary = build_finetune_corpus(
                artifact_path,
                corpus_path,
                reference_judge=cfg.reference_judge,
                candidate_judge=cfg.candidate_judge,
                only_disagreements=cfg.only_disagreements,
            )
            paths = write_finetune_artifacts(records, summary, output_dir, basename=cfg.basename)

        return {
            "source_artifact": summary.source_artifact,
            "source_corpus": summary.source_corpus,
            "reference_judge": summary.reference_judge,
            "candidate_judge": summary.candidate_judge,
            "only_disagreements": summary.only_disagreements,
            "total_records": summary.total_records,
            "disagreement_count": summary.disagreement_count,
            "label_verdict_counts": summary.label_verdict_counts,
            "candidate_verdict_counts": summary.candidate_verdict_counts,
            "skipped_entries": len(summary.skipped_entries),
            "artifacts": {kind: str(p) for kind, p in paths.items()},
        }
