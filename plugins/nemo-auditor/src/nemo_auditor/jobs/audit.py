# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Audit job — runs garak against a target using inline config + target.

Local-run only for now: ``nemo auditor audit run --spec-file spec.yaml`` shells
out to a pre-installed garak interpreter (default ``~/.auditor/.venv/bin/python``,
overridable via ``NEMO_AUDITOR_GARAK_PYTHON``), then registers the resulting
JSONL / HTML / hitlog reports as job results via
:meth:`~nemo_platform_plugin.job_results.JobResults.save`.

The plugin uses a single garak invocation across the whole probe spec — there
is no per-probe splitting and no pause/resume scaffolding (those exist in
``services/auditor`` to support remote runs that the platform may interrupt
and resume; local runs run to completion).
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Annotated, ClassVar, TypeVar, cast

import yaml
from nemo_auditor.entities import AuditConfig, AuditTarget
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform.resources.entities import AsyncEntitiesResource
from nemo_platform_plugin.entities import parse_qualified_name
from nemo_platform_plugin.entity_client import NemoEntitiesClient, NemoEntityNotFoundError
from nemo_platform_plugin.job import NemoJob
from nemo_platform_plugin.job_context import JobContext
from nemo_platform_plugin.job_results import JobResults
from pydantic import BaseModel, ConfigDict, StringConstraints

logger = logging.getLogger(__name__)

DEFAULT_GARAK_PYTHON = "~/.auditor/.venv/bin/python"
GARAK_PYTHON_ENVVAR = "NEMO_AUDITOR_GARAK_PYTHON"

# garak writes reports to <XDG_DATA_HOME>/garak/<reporting.report_dir>/
# with filenames driven by reporting.report_prefix. Same layout
# services/auditor relies on.
_GARAK_OUTPUT_TYPES = (
    ("report-jsonl", ".report.jsonl"),
    ("report-html", ".report.html"),
    ("report-hitlog-jsonl", ".hitlog.jsonl"),
)

# garak refuses to start unless these are set even when unused (e.g. when
# the actual creds come through IGW). services/auditor sets the same four.
_REQUIRED_API_KEY_VARS = (
    "NIM_API_KEY",
    "OPENAI_API_KEY",
    "REST_API_KEY",
    "OPENAICOMPATIBLE_API_KEY",
)

# Stdout/stderr can be MB-sized after a long garak run; keep just a tail in
# the result envelope so it stays useful for diagnostics without blowing up
# the JSON payload.
_LOG_TAIL_BYTES = 4000


# Workspace-qualified-or-bare name reference, e.g. "my-cfg" or "prod/my-cfg".
NonEmptyStr = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]


class AuditInputSpec(BaseModel):
    """User-facing spec — each field accepts an inline entity payload OR a
    workspace-qualified name string referencing one in the entity store.

    Resolved by :meth:`AuditJob.to_spec` into a canonical :class:`AuditSpec`
    before :meth:`AuditJob.run` is invoked.
    """

    model_config = ConfigDict(extra="forbid")

    config: AuditConfig | NonEmptyStr
    target: AuditTarget | NonEmptyStr


class AuditSpec(BaseModel):
    """Canonical, fully-resolved spec passed to :meth:`AuditJob.run`."""

    model_config = ConfigDict(extra="forbid")

    config: AuditConfig
    target: AuditTarget


def _garak_config_dict(config: AuditConfig) -> dict:
    """Project ``AuditConfig`` to the dict shape garak's ``--config`` expects.

    Drops the ``NemoEntity`` base fields (``name``/``workspace``/etc.) and the
    plugin-specific ``description`` — garak's config schema only knows about
    ``system``/``run``/``plugins``/``reporting``.
    """
    return config.model_dump(mode="json", include={"system", "run", "plugins", "reporting"})


def _collect_report_artifacts(
    report_dir: Path,
    report_prefix: str,
    results: JobResults,
) -> dict[str, dict]:
    """Register whichever of the three garak reports exist as job results."""
    artifacts: dict[str, dict] = {}
    for name, suffix in _GARAK_OUTPUT_TYPES:
        path = report_dir / f"{report_prefix}{suffix}"
        if path.exists():
            ref = results.save(name, path)
            artifacts[name] = ref.model_dump()
        else:
            logger.debug("Garak report %s not found at %s", name, path)
    return artifacts


def _resolve_garak_python() -> str:
    return os.environ.get(GARAK_PYTHON_ENVVAR) or os.path.expanduser(DEFAULT_GARAK_PYTHON)


_EntityT = TypeVar("_EntityT", AuditConfig, AuditTarget)


async def _resolve_ref(
    value: _EntityT | str,
    entity_class: type[_EntityT],
    *,
    default_workspace: str,
    entity_client: NemoEntitiesClient | None,
    kind: str,
) -> _EntityT:
    """Return ``value`` if it's already an entity, otherwise look it up by name.

    ``entity_client`` may be ``None`` only when ``value`` is already an entity
    (the inline case). The str path always requires a client; the caller is
    expected to have surfaced a clear error before reaching here if no client
    was available.
    """
    if isinstance(value, entity_class):
        return value
    assert entity_client is not None, f"entity_client is required to resolve {kind} name ref {value!r}"
    # value is NonEmptyStr; parse "[ws/]name" via the platform helper.
    ws, name = parse_qualified_name(value, default_workspace=default_workspace)
    try:
        return await entity_client.get(entity_class, name=name, workspace=ws)
    except NemoEntityNotFoundError as exc:
        raise RuntimeError(f"{kind} '{ws}/{name}' not found in entity store") from exc


def _rewrite_options_uris(
    options: dict,
    sdk: NeMoPlatform | None,
    async_sdk: AsyncNeMoPlatform | None = None,
) -> None:
    """Replace ``nmp_uri_spec`` sentinels in ``options`` with concrete ``uri`` values.

    Walks the options tree (BFS over dict values, non-dicts are skipped) and,
    for every dict containing an ``nmp_uri_spec`` key, resolves
    ``nmp_uri_spec.inference_gateway`` (which must contain ``workspace`` and
    ``provider``) through the platform SDK, sets the dict's ``uri`` to the
    resolved URL, and removes the sentinel.

    Mutates ``options`` in place. Mirrors
    ``services/auditor/src/nmp/auditor/tasks/audit/main.py:rewrite_target``.

    Raises:
        ValueError: malformed sentinel, or ``uri``/``nmp_uri_spec`` conflict
            in the same dict.
        RuntimeError: sentinel present but no SDK was injected, or the SDK
            lookup itself failed.
    """
    queue: list = list(options.values())
    while queue:
        node = queue.pop()
        if not isinstance(node, dict):
            continue
        queue.extend(node.values())
        spec = node.get("nmp_uri_spec")
        if not spec:
            continue
        igw_ref = spec.get("inference_gateway") if isinstance(spec, dict) else None
        if not isinstance(igw_ref, dict) or "workspace" not in igw_ref or "provider" not in igw_ref:
            raise ValueError(
                f"Invalid nmp_uri_spec: {spec!r} (expected inference_gateway with both 'workspace' and 'provider')."
            )
        if "uri" in node:
            raise ValueError("Cannot specify both 'uri' and 'nmp_uri_spec' in the same options block.")
        if sdk is None and async_sdk is None:
            raise RuntimeError(
                "nmp_uri_spec resolution requires a connected platform SDK; AuditJob.run was invoked without one."
            )
        try:
            if sdk is not None:
                provider = sdk.inference.providers.retrieve(workspace=igw_ref["workspace"], name=igw_ref["provider"])
                uri = sdk.models.get_provider_route_openai_url(provider)
            else:
                # async_sdk path: AuditJob.run() executes inside asyncio.to_thread(), so
                # this worker thread has no running event loop — asyncio.run() is safe.
                provider = asyncio.run(
                    async_sdk.inference.providers.retrieve(  # type: ignore[union-attr]
                        workspace=igw_ref["workspace"], name=igw_ref["provider"]
                    )
                )
                uri = async_sdk.models.get_provider_route_openai_url(provider)  # type: ignore[union-attr]
        except Exception as exc:
            raise RuntimeError(
                f"Failed to resolve inference gateway provider '{igw_ref['workspace']}/{igw_ref['provider']}': {exc}"
            ) from exc
        node["uri"] = uri
        del node["nmp_uri_spec"]


def _build_env(persistent_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    for key in _REQUIRED_API_KEY_VARS:
        env.setdefault(key, "NOT_SET")
    env["XDG_DATA_HOME"] = str(persistent_dir)
    env["GARAK_LOG_FILE"] = str(persistent_dir / "garak.log")
    return env


class AuditJob(NemoJob):
    """Run an audit (single garak invocation) against a configured target."""

    name: ClassVar[str] = "audit"
    description: ClassVar[str] = "Run an auditor scan against a configured target."
    container: ClassVar[str] = "cpu-tasks"
    input_spec_schema: ClassVar[type[BaseModel] | None] = AuditInputSpec
    spec_schema: ClassVar[type[BaseModel] | None] = AuditSpec

    @classmethod
    async def to_spec(
        cls,
        input_spec: BaseModel,
        *,
        workspace: str,
        entity_client: object,
        async_sdk: object,
        is_local: bool,
    ) -> BaseModel:
        """Resolve any name-string refs on ``input_spec`` into inline entities.

        Signature matches :meth:`NemoJob.to_spec` exactly so the override is
        Liskov-clean; we narrow types internally.

        Local-run mode: the platform scheduler passes ``entity_client=None``,
        so we build one on demand from ``async_sdk.entities`` (an
        ``AsyncEntitiesResource``). API-mode submissions go through the same
        path with whatever client the platform already constructed.

        ``workspace`` is used as the fallback for unqualified name strings;
        a string like ``"prod/my-cfg"`` overrides it via ``parse_qualified_name``.
        """
        assert isinstance(input_spec, AuditInputSpec), (
            f"AuditJob.to_spec received unexpected input type: {type(input_spec).__name__}"
        )
        # Only need a client if at least one field is a name reference.
        needs_lookup = isinstance(input_spec.config, str) or isinstance(input_spec.target, str)
        client = cls._resolve_entity_client(entity_client, async_sdk) if needs_lookup else None
        config = await _resolve_ref(
            input_spec.config,
            AuditConfig,
            default_workspace=workspace,
            entity_client=client,
            kind="audit config",
        )
        target = await _resolve_ref(
            input_spec.target,
            AuditTarget,
            default_workspace=workspace,
            entity_client=client,
            kind="audit target",
        )
        return AuditSpec(config=config, target=target)

    @staticmethod
    def _resolve_entity_client(
        entity_client: object,
        async_sdk: object,
    ) -> NemoEntitiesClient:
        """Return a ``NemoEntitiesClient`` from whatever the scheduler handed us.

        Order of preference: existing client → wrap ``async_sdk.entities``.
        Raises ``RuntimeError`` if neither is available, which is the case
        when ``run`` is invoked locally with no SDK and the input spec
        contains a name reference (no way to resolve it).
        """
        if entity_client is not None:
            return cast(NemoEntitiesClient, entity_client)
        if async_sdk is not None and hasattr(async_sdk, "entities"):
            return NemoEntitiesClient(cast(AsyncEntitiesResource, async_sdk.entities))
        raise RuntimeError(
            "AuditInputSpec contained a name reference but no platform "
            "client was injected. Either inline the config/target payloads, "
            "or run with a connected platform SDK."
        )

    def run(
        self,
        config: dict,
        *,
        ctx: JobContext,
        sdk: NeMoPlatform | None = None,
        async_sdk: AsyncNeMoPlatform | None = None,
    ) -> dict:
        spec = AuditSpec.model_validate(config)

        work_dir = ctx.storage.ephemeral
        work_dir.mkdir(parents=True, exist_ok=True)
        ctx.storage.persistent.mkdir(parents=True, exist_ok=True)

        # Render config + (optional) target options to disk for garak to pick up.
        garak_config_path = work_dir / "garak_config.yaml"
        garak_config_path.write_text(yaml.safe_dump(_garak_config_dict(spec.config)))

        target_opts_path: Path | None = None
        if spec.target.options:
            # Deep-copy before rewriting so the validated AuditTarget on the spec
            # stays pristine; only the on-disk JSON we hand to garak is mutated.
            rewritten_options = copy.deepcopy(spec.target.options)
            _rewrite_options_uris(rewritten_options, sdk, async_sdk)
            target_opts_path = work_dir / "target_options.json"
            target_opts_path.write_text(json.dumps(rewritten_options))

        garak_python = _resolve_garak_python()
        if not Path(garak_python).exists():
            raise FileNotFoundError(
                f"garak interpreter not found at {garak_python}. "
                f"Install garak in a venv there, or set ${GARAK_PYTHON_ENVVAR} "
                "to point at an existing one."
            )

        cmd = [
            garak_python,
            "-m",
            "garak",
            "--config",
            str(garak_config_path),
            "--target_type",
            spec.target.type,
            "--target_name",
            spec.target.model,
        ]
        if target_opts_path is not None:
            cmd += ["--generator_option_file", str(target_opts_path)]

        env = _build_env(ctx.storage.persistent)

        logger.info("Running garak: %s (cwd=%s)", " ".join(cmd), work_dir)
        completed = subprocess.run(
            cmd,
            env=env,
            cwd=work_dir,
            capture_output=True,
            text=True,
            check=False,
        )

        # garak emits to <XDG_DATA_HOME>/garak/<reporting.report_dir>/<prefix>.*
        report_dir = ctx.storage.persistent / "garak" / spec.config.reporting.report_dir
        artifacts = _collect_report_artifacts(
            report_dir,
            spec.config.reporting.report_prefix,
            ctx.results,
        )

        status = "completed" if completed.returncode == 0 else "failed"
        self.report_progress(
            ctx,
            work_done=1,
            work_total=1,
            status=status,
            details={"returncode": str(completed.returncode)},
        )

        return {
            "status": status,
            "returncode": completed.returncode,
            "stdout_tail": completed.stdout[-_LOG_TAIL_BYTES:] if completed.stdout else "",
            "stderr_tail": completed.stderr[-_LOG_TAIL_BYTES:] if completed.stderr else "",
            "results": artifacts,
        }
