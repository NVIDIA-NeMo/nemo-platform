# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""TriageMemoryJob — drive the memory-triage council against a pi-hermes corpus.

Registered under ``nemo.jobs`` as ``agents.triage-memory``. Three intended modes:

1. **Baseline lock**: ``judges=["azure-anthropic-claude-sonnet-4-6"]`` produces
   the gold reference artifact future tuned-model runs diff against.
2. **Candidate eval**: ``judges=["<candidate>"]`` against the same corpus, then
   the eval primitive (bd ``mdubrinsky-7au.6``, future work) computes
   agreement / confusion metrics against the baseline.
3. **Multi-judge research smoke**: pass N judges to bring up an N-judge
   council. First judge is the reference for aggregation tie-breaks.

The job is a thin wrapper around the runtime primitives in
``improvement/memory/``: it talks to the platform's IGW (OpenAI-compatible
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
``plugins/nemo-agents/examples/memory-triage/run_triage.py``. That
script remains as the "drive the primitives directly" alternative for
debugging; the NemoJob is the canonical entry point.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import subprocess
import tempfile
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import ClassVar

from nemo_platform import NeMoPlatform
from nemo_platform_plugin.job import NemoJob
from nemo_platform_plugin.job_context import JobContext
from nemo_platform_plugin.refs import (
    FilesetRef,
    LocalDir,
    OutputTarget,
    classify_output_target,
)
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TriageMemoryConfig(BaseModel):
    """Spec for ``nemo agents triage-memory``.

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


class TriageMemoryJob(NemoJob):
    """Memory-triage council runner."""

    name: ClassVar[str] = "triage-memory"
    description: ClassVar[str] = (
        "Run the memory-triage council against a pi-hermes corpus and emit a staged-proposal artifact."
    )
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
        # actual run path, so `nemo agents triage-memory explain` doesn't
        # pay the cost of pulling in openai / anthropic / the improvement
        # primitives.
        import openai
        from nemo_agents_plugin.improvement.memory.adapters.pi_hermes import PiHermesMemoryStore
        from nemo_agents_plugin.improvement.memory.judges import OpenAICompatibleJudge
        from nemo_agents_plugin.improvement.memory.report import write_artifacts
        from nemo_agents_plugin.improvement.memory.triage import run_triage

        cfg = TriageMemoryConfig.model_validate(config)
        igw_url = cfg.igw_base_url or _resolve_igw_url()

        # Resolve corpus (local path or fileset) and output (local dir or
        # fileset) under a pair of context managers. Local cases are no-op
        # pass-throughs; fileset cases stage to tempdirs and clean up / upload
        # on the way out. The output context only uploads on successful exit,
        # so a crashed run never leaves partial artifacts in a fileset.
        with (
            _resolve_corpus(cfg.corpus, workspace=cfg.workspace, sdk=sdk) as corpus,
            _resolve_output(
                cfg.output,
                workspace=cfg.workspace,
                basename=cfg.basename,
                ctx=ctx,
                sdk=sdk,
            ) as output_dir,
        ):
            logger.info("triage-memory: igw=%s corpus=%s judges=%s", igw_url, corpus, cfg.judges)

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
        logger.info("triage-memory: %d/%d entries judged", done, total)


def _looks_pathy(ref: str) -> bool:
    """True when *ref* looks like a filesystem path rather than a fileset reference.

    Heuristic matches the convention in ``usage/cli.py``: leading ``.``, ``/``,
    or ``~`` are unambiguous path shapes, and any string that already exists
    on disk is treated as a path even when it has no leading sigil. A bare
    name that does not exist locally falls through to fileset resolution.
    """
    if ref.startswith(("/", "./", "../", "~")):
        return True
    try:
        return Path(ref).expanduser().exists()
    except OSError:
        # Path() can raise on pathologically long inputs; treat as non-path.
        return False


@contextlib.contextmanager
def _resolve_corpus(
    corpus_ref: str,
    *,
    workspace: str,
    sdk: NeMoPlatform | None,
) -> Iterator[Path]:
    """Yield a local :class:`Path` to the corpus file.

    When *corpus_ref* is path-shaped, expand + resolve it and yield directly.
    Otherwise, treat it as a fileset reference, download the fileset to a
    tempdir via the existing ``usage.sources.fileset`` helper, find the
    single ``.md`` file inside, and yield that path. The tempdir is cleaned
    up automatically when the context exits.

    Raises :class:`RuntimeError` (not the platform-specific exception types)
    on every failure shape so the caller can surface one consistent error
    message to the job runner regardless of whether the corpus came from
    the filesystem or the platform.
    """
    if _looks_pathy(corpus_ref):
        path = Path(corpus_ref).expanduser().resolve()
        if not path.exists():
            raise RuntimeError(
                f"Corpus path does not exist: {path}. Set 'corpus' to a valid local "
                "file or to a NeMo Platform fileset reference (workspace/name)."
            )
        yield path
        return

    # Fileset reference. Import lazily so a path-only job invocation does
    # not pay the cost of pulling in the staging helper.
    from nemo_agents_plugin.usage.sources.fileset import (
        FilesetDownloadError,
        FilesetRefError,
        fileset_path,
    )

    try:
        ref = FilesetRef(corpus_ref)
    except Exception as err:
        raise RuntimeError(
            f"Could not parse corpus reference {corpus_ref!r} as a fileset reference. "
            "Use 'fileset-name' (with 'workspace' set) or 'workspace/fileset-name'."
        ) from err

    # Same SDK-required guard the evaluate_agent fileset branch uses: surface
    # an actionable message early rather than failing inside the SDK call.
    if sdk is None:
        raise RuntimeError(
            "TriageMemoryJob.run requires a 'sdk: NeMoPlatform' to download "
            f"the corpus fileset {corpus_ref!r}, but no platform SDK was available. "
            "Set NMP_BASE_URL (so the local CLI can build a default SDK), pass "
            "an explicit sdk via NemoJobScheduler.run_local(sdk=...), or use a "
            "local path for 'corpus' instead."
        )

    try:
        with fileset_path(ref, sdk=sdk, workspace=workspace) as tmp:
            md_files = sorted(tmp.rglob("*.md"))
            if not md_files:
                raise RuntimeError(
                    f"Fileset {corpus_ref!r} (workspace={workspace!r}) contains no "
                    ".md files. Upload a single pi-hermes Markdown corpus file to "
                    "the fileset (USER.md / MEMORY.md / failures.md)."
                )
            if len(md_files) > 1:
                names = [p.name for p in md_files]
                raise RuntimeError(
                    f"Fileset {corpus_ref!r} contains multiple .md files: {names}. "
                    "The triage-memory job expects exactly one corpus file per "
                    "fileset; create separate filesets per corpus or remove the extras."
                )
            yield md_files[0]
    except (FilesetRefError, FilesetDownloadError) as err:
        # Re-wrap as RuntimeError so job-runner error handling sees a single
        # error type for every corpus-resolution failure mode.
        raise RuntimeError(f"Failed to stage fileset {corpus_ref!r}: {err}") from err


@contextlib.contextmanager
def _resolve_output(
    output: OutputTarget | None,
    *,
    workspace: str,
    basename: str,
    ctx: JobContext,
    sdk: NeMoPlatform | None,
) -> Iterator[Path]:
    """Yield the local directory artifacts should be written to.

    Branches on the output union shape, matching the EvaluateAgent
    convention exactly:

    - ``None`` → ``ctx.storage.persistent / "triage-output"``. Survives
      across job runs in the platform-injected persistent volume.
    - :class:`LocalDir` → that directory, ``mkdir -p``-ed.
    - :class:`FilesetRef` → a tempdir under ``ctx.storage.ephemeral``. On
      successful exit, the two artifacts (``{basename}.json`` and
      ``{basename}.md``) are uploaded to the named fileset (auto-created
      if missing) via ``sdk.files.upload``, then the tempdir is removed.
      A failed run (any exception propagating out of the ``with`` body)
      skips the upload so the fileset never holds a half-finished pair.

    *sdk* is required only on the fileset branch; we check up front and
    raise :class:`RuntimeError` early so the job doesn't run for ten
    minutes only to discover at the end it can't deliver the artifacts.
    """
    if output is None:
        local = ctx.storage.persistent / "triage-output"
        local.mkdir(parents=True, exist_ok=True)
        logger.info("triage-memory: writing artifacts to platform-persistent dir %s", local)
        yield local
        return

    cls = classify_output_target(str(output))
    if cls is LocalDir:
        local = Path(str(output)).expanduser().resolve()
        local.mkdir(parents=True, exist_ok=True)
        logger.info("triage-memory: writing artifacts to local dir %s", local)
        yield local
        return

    # Fileset branch.
    if sdk is None:
        raise RuntimeError(
            "TriageMemoryJob.run requires a 'sdk: NeMoPlatform' to upload "
            f"artifacts to fileset {output!r}, but no platform SDK was available. "
            "Set NMP_BASE_URL (so the local CLI can build a default SDK), pass "
            "an explicit sdk via NemoJobScheduler.run_local(sdk=...), or use a "
            "local path for 'output' instead."
        )

    ref = FilesetRef(str(output))
    if "/" in ref:
        ws, name = ref.split("/", 1)
    else:
        ws, name = workspace, str(ref)

    with tempfile.TemporaryDirectory(
        prefix=f".triage-output-{name}-",
        dir=str(ctx.storage.ephemeral),
    ) as tmp:
        tmp_path = Path(tmp)
        logger.info(
            "triage-memory: staging artifacts in %s; will upload to fileset %s/%s on success.",
            tmp_path,
            ws,
            name,
        )
        should_upload = True
        try:
            yield tmp_path
        except BaseException:
            # Don't pollute the fileset with broken / partial outputs from a
            # crashed run. Re-raise so the job-runner sees the original error.
            should_upload = False
            raise
        finally:
            if should_upload:
                _upload_artifacts_to_fileset(
                    tmp_path,
                    fileset=name,
                    workspace=ws,
                    basename=basename,
                    sdk=sdk,
                )


def _upload_artifacts_to_fileset(
    local_dir: Path,
    *,
    fileset: str,
    workspace: str,
    basename: str,
    sdk: NeMoPlatform,
) -> None:
    """Upload ``{basename}.json`` and ``{basename}.md`` from *local_dir* to the fileset.

    Auto-creates the fileset if missing (matches ``nemo files upload`` semantics).
    Each artifact is uploaded individually so a partial failure leaves the
    error attached to a specific file in the log rather than to a vague
    "directory upload failed". Caller handles the surrounding tempdir
    lifecycle.
    """
    for suffix in (".json", ".md"):
        artifact = local_dir / f"{basename}{suffix}"
        if not artifact.exists():
            # Should not happen — write_artifacts always produces both — but
            # raise a clear error rather than silently uploading less than
            # the documented pair.
            raise RuntimeError(
                f"triage-memory: expected artifact {artifact} was not produced by write_artifacts. "
                "This is a bug in the job; the fileset upload was aborted to avoid a partial pair."
            )
        sdk.files.upload(
            local_path=str(artifact),
            fileset=fileset,
            workspace=workspace,
            fileset_auto_create=True,
        )
        logger.info(
            "triage-memory: uploaded %s to fileset %s/%s.",
            artifact.name,
            workspace,
            fileset,
        )
