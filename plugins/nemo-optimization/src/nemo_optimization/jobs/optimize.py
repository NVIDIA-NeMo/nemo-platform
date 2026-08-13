# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""OptimizeJob — Agents numeric HPO (``nemo agents optimize``).

Implementation lives in ``nemo_optimization``; registration and HTTP mounting
are owned by the agents plugin (``agents.optimize``).
"""

from __future__ import annotations

import contextlib
import copy
import logging
import os
import re
import shutil
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any, ClassVar

import yaml
from nemo_platform import NeMoPlatform
from nemo_platform_plugin.job import NemoJob
from nemo_platform_plugin.job_context import JobContext
from nemo_platform_plugin.jobs.api_factory import PlatformJobSpec
from nemo_platform_plugin.jobs.exceptions import PlatformJobCompilationError
from nemo_platform_plugin.refs import (
    FILESET_REF_PATTERN,
    FilesetRef,
    LocalDir,
    classify_output_target,
)
from nemo_platform_plugin.run_dependencies import LocalRunError
from pydantic import BaseModel

from nemo_optimization.agents import resolve_agent_config
from nemo_optimization.preflight import preflight_validate_llm_models
from nemo_optimization.router import OptimizeRouter
from nemo_optimization.schemas.optimize import OptimizeSpec

logger = logging.getLogger(__name__)


class OptimizeJob(NemoJob):
    """Run a Fabric-native numeric optimize study via the Agents optimize job."""

    name: ClassVar[str] = "optimize"
    description: ClassVar[str] = "Optimize a Fabric agent workflow (numeric HPO)."
    container: ClassVar[str] = "cpu-tasks"
    job_collection_path: ClassVar[str | None] = None
    spec_schema: ClassVar[type[BaseModel]] = OptimizeSpec

    @classmethod
    async def compile(  # ty: ignore[invalid-method-override]
        cls,
        *,
        workspace: str,
        spec: OptimizeSpec,
        entity_client: object,
        job_name: str | None,
        async_sdk: object,
        profile: str | None = None,
        options: dict | None = None,
    ) -> PlatformJobSpec:
        from nemo_platform_plugin.jobs.api_factory import (
            EnvironmentVariable,
            PlatformJobStep,
            SubprocessExecutionProviderSpec,
        )
        from nemo_platform_plugin.jobs.constants import (
            DEFAULT_JOB_STORAGE_PATH,
            PERSISTENT_JOB_STORAGE_PATH_ENVVAR,
        )

        # optimize_config_inline needs no host filesystem; only the path form does.
        if spec.optimize_config is not None and not Path(spec.optimize_config).is_absolute():
            raise PlatformJobCompilationError("optimize_config must be an absolute path.")

        spec_dict = spec.model_dump(mode="json")
        spec_dict["workspace"] = workspace

        return PlatformJobSpec(
            steps=[
                PlatformJobStep(
                    name="optimize",
                    executor=SubprocessExecutionProviderSpec(
                        provider="subprocess",
                        command=["python", "-m", "nemo_optimization.tasks.optimize"],
                    ),
                    config=spec_dict,
                    environment=[
                        EnvironmentVariable(
                            name=PERSISTENT_JOB_STORAGE_PATH_ENVVAR,
                            value=DEFAULT_JOB_STORAGE_PATH,
                        ),
                    ],
                ),
            ],
        )

    def run(self, config: dict, *, ctx: JobContext, sdk: NeMoPlatform | None = None) -> dict:
        spec = OptimizeSpec.model_validate(config)
        optimize_config = _resolve_optimize_config(spec)
        agent_config = resolve_agent_config(spec.agent, workspace=spec.workspace, sdk=sdk)
        preflight_validate_llm_models(
            optimize_config,
            workspace=spec.workspace,
            sdk=sdk,
            agent_config=agent_config,
        )
        with _staged_dataset(
            optimize_config,
            workspace=spec.workspace,
            ctx=ctx,
            sdk=sdk,
        ) as staged_config:
            logger.info("Dispatching agents optimize study via OptimizeRouter")
            result = OptimizeRouter.dispatch(
                agent_config=agent_config,
                optimize_config=staged_config,
                ctx=ctx,
                sdk=sdk,
            )

        published = _publish_results(spec.output, workspace=spec.workspace, ctx=ctx, sdk=sdk)
        return result if published is None else {**result, "output": published}


def _resolve_optimize_config(spec: OptimizeSpec) -> dict[str, Any]:
    """Normalize either config source into a mapping.

    Both forms get ``${VAR}`` expansion so an inline config can reference the
    task subprocess's environment (e.g. ``api_key_env``) the same way a
    file-based one does.  ``OptimizeSpec`` guarantees exactly one is set.
    """
    if spec.optimize_config_inline is not None:
        return _expand_env(spec.optimize_config_inline)
    return _load_yaml(Path(str(spec.optimize_config)))


def _load_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"optimize config must be a mapping: {path}")
    return _expand_env(raw)


@contextlib.contextmanager
def _staged_dataset(
    optimize_config: dict[str, Any],
    *,
    workspace: str,
    ctx: JobContext,
    sdk: NeMoPlatform | None,
) -> Iterator[dict[str, Any]]:
    """Yield *optimize_config* with a fileset dataset reference replaced by a local path.

    ``eval.general.dataset`` may be a plain host path (CLI runs) or a
    ``workspace/fileset#path`` reference (remote submitters, who have no host
    filesystem).  For the reference form the fileset is downloaded to a tempdir
    for the duration of the study and the config is rewritten in place, so
    everything downstream keeps seeing a plain readable path.
    """
    ref = _dataset_fileset_ref(optimize_config)
    if ref is None:
        yield optimize_config
        return

    # Soft dependency, mirroring nemo_optimization.agents' lazy imports.
    from nemo_agents_plugin.jobs.fileset_io import resolve_staged_config

    fileset_ref, _, object_path = ref.partition("#")
    with resolve_staged_config(
        object_path,
        fileset_ref,
        workspace=workspace,
        ctx=ctx,
        sdk=sdk,
        kind="optimize-dataset",
    ) as local_path:
        yield _with_dataset_path(optimize_config, str(local_path))


def _dataset_fileset_ref(optimize_config: Mapping[str, Any]) -> str | None:
    """Return ``eval.general.dataset`` when it is a ``workspace/fileset#path`` ref."""
    dataset = _dataset_node(optimize_config)
    value = dataset if isinstance(dataset, str) else None
    if isinstance(dataset, Mapping):
        candidate = dataset.get("file_path") or dataset.get("path")
        value = candidate if isinstance(candidate, str) else None
    if value is None or not re.match(FILESET_REF_PATTERN, value):
        return None
    return value


def _dataset_node(optimize_config: Mapping[str, Any]) -> Any:
    general = optimize_config.get("eval", {})
    general = general.get("general") if isinstance(general, Mapping) else None
    return general.get("dataset") if isinstance(general, Mapping) else None


def _with_dataset_path(optimize_config: dict[str, Any], local_path: str) -> dict[str, Any]:
    """Copy *optimize_config* with the dataset location swapped for *local_path*."""
    updated = copy.deepcopy(optimize_config)
    general = updated["eval"]["general"]
    dataset = general.get("dataset")
    general["dataset"] = {"file_path": local_path} if isinstance(dataset, str) else {**dataset, "file_path": local_path}
    return updated


def _publish_results(
    output: str | None,
    *,
    workspace: str,
    ctx: JobContext,
    sdk: NeMoPlatform | None,
) -> dict[str, str] | None:
    """Copy the study's artifacts to *output*, returning a pointer for the job result.

    The backends write everything under ``ctx.storage.persistent / "results"``
    and register it via ``ctx.results.save``, which on the platform lands in the
    job's own fileset under ``results/<attempt_id>/``.  That is addressable only
    through ``sdk.jobs.results``, so a remote client that wants to read the
    optimized config back — or hand it to a follow-up job — needs a stable
    location it names up front.  Publishing the whole ``results`` tree keeps
    this backend-agnostic: no ``RESULT_NAME`` coupling, and the ``ga`` backend
    gets it for free.

    Returns ``None`` when no target was requested.
    """
    if output is None:
        return None

    # Soft dependency, mirroring nemo_optimization.agents' lazy imports.
    from nemo_agents_plugin.jobs.fileset_io import split_fileset_ref, upload_to_fileset

    try:
        artifacts = ctx.storage.persistent / "results"
    except RuntimeError as exc:
        raise LocalRunError(
            "Publishing optimize results requires persistent storage, which this job did not "
            "request.  This is a platform-run-only feature; drop 'output' for local runs."
        ) from exc

    if not artifacts.is_dir():
        raise FileNotFoundError(
            f"Optimize study reported success but wrote no artifacts to {artifacts}; nothing to publish."
        )

    if classify_output_target(output) is LocalDir:
        local = Path(output).expanduser().resolve()
        local.mkdir(parents=True, exist_ok=True)
        shutil.copytree(artifacts, local, dirs_exist_ok=True)
        logger.info("Published optimize results from %s to local dir %s", artifacts, local)
        return {"type": "local_dir", "path": str(local)}

    ws, name = split_fileset_ref(FilesetRef(output), workspace)
    if sdk is None:
        raise LocalRunError(
            f"Publishing optimize results to fileset '{ws}/{name}' requires a 'sdk: NeMoPlatform', "
            "but no platform SDK was available.  Set NMP_BASE_URL, pass sdk via "
            "NemoJobScheduler.run_local(sdk=...), or use a local output directory instead."
        )
    upload_to_fileset(artifacts, fileset=name, workspace=ws, sdk=sdk)
    logger.info("Published optimize results from %s to fileset %s/%s", artifacts, ws, name)
    return {"type": "fileset", "fileset": f"{ws}/{name}"}


def _expand_env(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    if isinstance(value, str):
        return os.path.expandvars(value)
    return value
