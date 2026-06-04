# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""TriageJob — drive the memory-triage council against a pi-hermes corpus.

Registered under ``nemo.jobs`` as ``memory.triage``. Three intended modes:

1. **Baseline lock**: ``judges=["azure-anthropic-claude-sonnet-4-6"]`` produces
   the gold reference artifact future tuned-model runs diff against.
2. **Candidate eval**: ``judges=["<candidate>"]`` against the same corpus, then
   the eval primitive (bd ``mdubrinsky-7au.6``, future work) computes
   agreement / confusion metrics against the baseline.
3. **Multi-judge research smoke**: pass N judges to bring up an N-judge
   council. First judge is the reference for aggregation tie-breaks.

The job is a thin wrapper around the runtime primitives in
``triage/``: it talks to the platform's IGW (OpenAI-compatible
endpoint) rather than directly to upstream providers, so the same job
runs on a developer laptop and on omnistation without changing model ids
or credentials.

Both the ``corpus`` (input) and ``output`` (artifacts) fields accept
either a local path or a NeMo Platform fileset reference. Filesets are
downloaded / uploaded transparently. This means a job running on
omnistation or in a container can read its corpus from a fileset and
write artifacts back to a fileset without ever touching the host
filesystem at a known path. ``nemo files upload`` / ``download`` from
your laptop is the only ceremony.

Graduates the standalone driver at
``plugins/nemo-memory/examples/triage/triage.py``. That
script remains as the "drive the primitives directly" alternative for
debugging; the NemoJob is the canonical entry point.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
from collections import Counter
from typing import ClassVar

from nemo_platform import NeMoPlatform
from nemo_platform_plugin.job import NemoJob
from nemo_platform_plugin.job_context import JobContext
from nemo_platform_plugin.refs import OutputTarget
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TriageConfig(BaseModel):
    """Spec for ``nemo memory triage``.

    Field defaults match the most common single-judge baseline shape
    against the consolidated PoC USER.md corpus. Override ``corpus`` and
    ``store_name`` when triaging a different store (MEMORY.md,
    failures.md, projects-memory/<proj>/MEMORY.md).
    """

    corpus: str = Field(
        description=(
            "Corpus source. Accepts EITHER (a) a local path to a pi-hermes "
            "Markdown file (USER.md / MEMORY.md / failures.md / "
            "projects-memory/<proj>/MEMORY.md, or the live SQLite-export "
            "equivalent), OR (b) a NeMo Platform fileset reference of the form "
            "'fileset-name' (uses 'workspace' field) or 'workspace/fileset-name'. "
            "Path-shaped values (starting with ., /, ~) and existing local files "
            "are treated as paths; anything else is resolved as a fileset. When "
            "the reference resolves to a fileset, the fileset must contain "
            "exactly one .md file (the corpus); the job will refuse a fileset "
            "with zero or multiple .md files rather than guess."
        ),
    )
    workspace: str = Field(
        default="default",
        description=(
            "Workspace used to resolve unqualified fileset references in 'corpus' "
            "(e.g. when corpus is 'my-fileset' rather than 'my-workspace/my-fileset'). "
            "Ignored when 'corpus' is a local path."
        ),
    )
    judges: list[str] = Field(
        min_length=1,
        description=(
            "Judge model ids from `nemo models list`. Repeat for a council. "
            "The first judge is the reference model for aggregation tie-breaks: "
            "when it agrees with the council majority, its refined_text / "
            "merge_with / justification populate the aggregate proposal."
        ),
    )
    store_name: str = Field(
        default="pi-hermes:memory",
        description=(
            "Store name recorded on every emitted proposal. Use a stable name "
            "(e.g. 'pi-hermes:CONSOLIDATED:user') so downstream eval diffs can "
            "match runs of the same underlying store."
        ),
    )
    output: OutputTarget | None = Field(
        default=None,
        description=(
            "Where the JSON + Markdown artifacts land. Two shapes; dispatch "
            "matches the platform RFC LJ-3 convention via "
            "`classify_output_target`: path-shaped values (starting with '/', "
            "'./', '../', '~/', or the bare '~') write to a local directory, "
            "created if absent; bare names resolve as a NeMo Platform fileset "
            "reference ('fileset-name' or 'workspace/fileset-name'). Fileset "
            "targets stage to a tempdir, upload both artifacts with "
            "fileset_auto_create=True on job success, then clean up. A failed "
            "run skips the upload so partial / broken artifacts never pollute the "
            "fileset. When omitted, falls back to ctx.storage.persistent / "
            "'triage-output' (the platform-injected persistent volume), matching "
            "the EvaluateAgent convention."
        ),
    )
    basename: str = Field(
        default="triage",
        description=(
            "Basename for the artifact pair: writes {basename}.json + {basename}.md. "
            "Use a versioned basename (e.g. 'baseline-sonnet-4-6-user') when locking "
            "a baseline so the file is not overwritten by a later run."
        ),
    )
    max_tokens: int = Field(
        default=4096,
        ge=512,
        description=(
            "Per-judge max_tokens budget. Reasoning models (Nemotron-Nano, Kimi, "
            "Super v1-5) burn 500-1500 tokens on internal reasoning before emitting "
            "JSON; 4096 is the safe default. Bump to 6144 if Kimi or Super surface "
            "empty-content errors."
        ),
    )
    max_entries: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Cap on entries processed. Useful for pilot runs against a small slice "
            "(e.g. max_entries=3) before committing to a full corpus pass."
        ),
    )
    timeout_sec: float = Field(
        default=180,
        gt=0,
        description="Per-request timeout for judge calls.",
    )
    igw_base_url: str | None = Field(
        default=None,
        description=(
            "Override the IGW OpenAI-compatible base URL. Defaults to whatever "
            "`nemo inference get-url` returns (resolves the local platform's IGW). "
            "Set explicitly when targeting a non-default platform or running "
            "outside a checkout where the CLI is not on PATH."
        ),
    )
    igw_api_key: str = Field(
        default="not-needed",
        description=(
            "API key passed to the IGW client. Default 'not-needed' works because "
            "the IGW handles upstream provider auth itself; only override when "
            "talking to a non-IGW OpenAI-compatible endpoint."
        ),
    )


class TriageJob(NemoJob):
    """Memory-triage council runner."""

    name: ClassVar[str] = "triage"
    description: ClassVar[str] = "Run the council against a pi-hermes corpus and emit a staged-proposal artifact."
    container: ClassVar[str] = "cpu-tasks"

    def run(
        self,
        config: dict,
        *,
        ctx: JobContext,
        sdk: NeMoPlatform | None = None,
    ) -> dict:
        # Inline imports follow the pattern in optimize_skills / analyze_batch:
        # keeps the entry-point load cheap and isolates heavy deps to the
        # actual run path, so `nemo memory triage explain` doesn't
        # pay the cost of pulling in openai / anthropic / the improvement
        # primitives.
        import openai
        from nemo_memory_plugin.triage.adapters.pi_hermes import PiHermesMemoryStore
        from nemo_memory_plugin.triage.judges import OpenAICompatibleJudge
        from nemo_memory_plugin.triage.report import write_artifacts
        from nemo_memory_plugin.triage.triage import run_triage

        cfg = TriageConfig.model_validate(config)
        igw_url = cfg.igw_base_url or _resolve_igw_url()

        # Resolve corpus (local path or fileset) and output (local dir or
        # fileset) under a pair of context managers. Local cases are no-op
        # pass-throughs; fileset cases stage to tempdirs and clean up / upload
        # on the way out. The output context only uploads on successful exit,
        # so a crashed run never leaves partial artifacts in a fileset.
        from nemo_memory_plugin.triage.fileset_io import (
            resolve_input_artifact,
            resolve_output_target,
        )

        with (
            resolve_input_artifact(
                cfg.corpus,
                workspace=cfg.workspace,
                sdk=sdk,
                suffix=".md",
                kind_label="corpus",
            ) as corpus,
            resolve_output_target(
                cfg.output,
                workspace=cfg.workspace,
                basename=cfg.basename,
                ctx=ctx,
                sdk=sdk,
                persistent_subdir="triage-output",
                job_label="triage",
            ) as output_dir,
        ):
            logger.info("triage: igw=%s corpus=%s judges=%s", igw_url, corpus, cfg.judges)

            client = openai.AsyncOpenAI(
                api_key=cfg.igw_api_key,
                base_url=igw_url,
                timeout=cfg.timeout_sec,
            )
            judges = [
                OpenAICompatibleJudge(client=client, model=model, max_tokens=cfg.max_tokens) for model in cfg.judges
            ]

            store = PiHermesMemoryStore(path=corpus, name=cfg.store_name)
            entries = list(store.list_entries())
            entries_by_id = {e.id: e.content for e in entries}
            if not entries:
                raise RuntimeError(f"Corpus at {corpus} contained no parseable entries.")

            run = asyncio.run(
                run_triage(
                    store,
                    judges,
                    reference_model=cfg.judges[0],
                    max_entries=cfg.max_entries,
                    progress=_log_progress,
                )
            )

            json_path, md_path = write_artifacts(
                run,
                output_dir,
                entries_by_id=entries_by_id,
                basename=cfg.basename,
            )

        # Per-judge calibration breakdown is the most useful at-a-glance
        # signal for a reviewer scanning job output. Include it in the
        # returned summary so platform views / logs surface it without
        # having to crack open the JSON artifact.
        per_judge_counts: dict[str, dict[str, int]] = {}
        for model in cfg.judges:
            counts: Counter[str] = Counter()
            for p in run.proposals:
                vote = p.judge_votes.get(model)
                if vote:
                    counts[vote.verdict.value] += 1
            per_judge_counts[model] = dict(counts)

        return {
            "store_name": run.store_name,
            "council_models": run.council_models,
            "reference_model": cfg.judges[0],
            "corpus": str(corpus),
            "elapsed_sec": run.elapsed_sec,
            "proposals": len(run.proposals),
            "errors": len(run.errors),
            "skipped_entries": len(run.skipped_entries),
            "verdict_counts": run.verdict_counts,
            "per_judge_verdict_counts": per_judge_counts,
            "artifacts": {
                "json": str(json_path),
                "markdown": str(md_path),
            },
        }


def _resolve_igw_url() -> str:
    """Resolve the local IGW base URL via ``nemo inference get-url``.

    Raises ``RuntimeError`` with a helpful message when the CLI is not
    on PATH or the platform is not running, so the caller sees a real
    error rather than a confusing 404 / connection refused later.
    """
    try:
        out = subprocess.run(
            ["nemo", "inference", "get-url"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except FileNotFoundError as err:
        raise RuntimeError(
            "Could not resolve IGW URL: `nemo` CLI not found on PATH. "
            "Set igw_base_url explicitly in the spec or run from a checkout."
        ) from err
    except subprocess.TimeoutExpired as err:
        raise RuntimeError(
            "Could not resolve IGW URL: `nemo inference get-url` timed out. "
            "Is the platform running (`nemo services run`)?"
        ) from err
    except subprocess.CalledProcessError as err:
        raise RuntimeError(f"Could not resolve IGW URL: `nemo inference get-url` failed: {err.stderr.strip()}") from err
    url = out.stdout.strip().splitlines()[-1]
    if not url.startswith("http"):
        raise RuntimeError(f"`nemo inference get-url` returned unexpected output: {out.stdout!r}")
    return url


def _log_progress(done: int, total: int) -> None:
    """Per-entry progress callback. Logs every 5 entries to keep job output readable."""
    if done == total or done % 5 == 0 or done == 1:
        logger.info("triage: %d/%d entries judged", done, total)


# Path/fileset dispatch helpers were factored into
# ``triage/fileset_io.py`` so the eval job can share
# them. We re-export ``_looks_pathy`` and ``_resolve_corpus`` at module
# scope so existing tests that import them by name keep working without
# having to chase the indirection.


def _resolve_corpus(
    corpus_ref: str,
    *,
    workspace: str,
    sdk: NeMoPlatform | None,
):
    """Back-compat shim around the shared ``resolve_input_artifact`` helper.

    Existing unit tests import ``_resolve_corpus`` directly. The shared
    helper has identical semantics for the corpus case (single .md file
    from a fileset, or a local path). New callers should import
    ``resolve_input_artifact`` from ``_fileset_io`` directly.

    Returns the context manager so ``with _resolve_corpus(...) as path:``
    continues to work; not decorated with ``@contextlib.contextmanager``
    because the helper itself is already a context manager.
    """
    from nemo_memory_plugin.triage.fileset_io import resolve_input_artifact

    return resolve_input_artifact(
        corpus_ref,
        workspace=workspace,
        sdk=sdk,
        suffix=".md",
        kind_label="Corpus",
    )
