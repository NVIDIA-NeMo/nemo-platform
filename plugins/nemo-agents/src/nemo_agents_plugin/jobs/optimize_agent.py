# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""OptimizeAgentJob — optimize a NAT agent workflow via prompt/parameter tuning.

Registered under the ``nemo.jobs`` entry-point group as ``agents.optimize``.

Optimization is provided by the ``nvidia-nat-core`` package (parameter
optimization, profiling) and optionally ``nvidia-nat-nemo-customizer``
(fine-tuning orchestration).  This job delegates to the ``nat optimize``
CLI subprocess so it remains decoupled from the optimization Python APIs.

The job runs in the ``cpu-tasks`` container since the optimization
orchestration itself is CPU-only; the agent processes and LLM inference
APIs run elsewhere.

Resolution model
----------------

The ``agent`` field accepts three shapes:

* :class:`~nemo_agents_plugin.refs.AgentRef` — a platform-managed name
  (``"react-agent"`` or ``"workspace/react-agent"``).  The job fetches
  the agent's stored NAT config from the platform, merges it with the
  user-supplied optimize config (workflow/functions/telemetry from the
  agent; eval/optimizer/judge LLMs and any tuning overrides on shared
  LLM keys from the optimize side — see
  :func:`~nemo_agents_plugin.utils.merge_agent_config`), and runs
  ``nat optimize`` locally with the merged file.  The workflow runs
  in-process; LLM calls route through the Inference Gateway via the
  same URL injection used by deployed agents.  This is the path that
  makes per-trial ``temperature`` / ``top_p`` sweeps actually take
  effect on the agent's behaviour, since each trial gets its own
  in-process workflow built from the trial-specific config.
* :class:`~nemo_platform_plugin.refs.EndpointURL` — a literal HTTP(S) URL.
  Forwarded to ``nat optimize --endpoint`` verbatim and treated as an
  opaque service.  Useful for non-platform agent servers, but be aware
  that LLM hyperparameter sweeps in the optimize config are *local* to
  the optimizer process and never reach the remote agent — every trial
  evaluates the same remote behaviour.  This mode is preserved for
  backward compatibility and for non-platform deployments.
* ``None`` — the optimize config is expected to declare an inline
  workflow itself (no agent fetch, no merge, no ``--endpoint``).

Before invoking ``nat optimize`` (in any of the three modes) the
config's LLMs are injected with the platform Inference Gateway URL via
``setdefault`` semantics, so agents and optimize configs can omit
``base_url``/``api_key`` and route through the IGW automatically.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any, ClassVar

from nemo_agents_plugin.refs import AgentRef, AgentTarget, classify_agent_target
from nemo_agents_plugin.utils import (
    preflight_validate_llm_models,
    temp_injected_config,
)
from nemo_platform import NeMoPlatform
from nemo_platform_plugin.job import NemoJob
from nemo_platform_plugin.job_context import JobContext
from nemo_platform_plugin.jobs.api_factory import PlatformJobSpec
from nemo_platform_plugin.refs import EndpointURL
from nemo_platform_plugin.run_dependencies import LocalRunError
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class OptimizeAgentSpec(BaseModel):
    """Spec for an agent optimization job.

    Field declaration order also drives the auto-generated CLI flag
    order — keep the most-frequently-set knobs first.

    Attributes:
        agent: The agent to optimize.  Accepts either a platform-managed
            agent reference (``"name"`` or ``"workspace/name"``) or a
            literal HTTP(S) endpoint URL.  Bare names cause the job to
            fetch the agent's stored config from the platform and merge
            it with the optimize config so trials run the agent's
            workflow locally with the swept parameters; URLs are
            forwarded to ``nat optimize --endpoint`` and treated as an
            opaque service (sweeps don't affect the remote agent — see
            module docstring).  When ``None`` the optimize config is
            expected to include an inline agent workflow.
        optimize_config: Path to the NAT optimization YAML config file.
            The output path is controlled by ``optimizer.output_path``
            inside the YAML.
        workspace: NeMo Platform workspace used to scope the agent fetch and the
            gateway URL injection.
    """

    # Field order is intentional — it's also the order the auto-generated
    # CLI surfaces flags in `--help`.  Mirrors EvaluateAgentSpec so the
    # optimize and evaluate subcommands feel consistent.
    agent: AgentTarget | None = Field(
        default=None,
        description="Agent to optimize — either a platform-managed agent reference "
        "(e.g. 'react-agent', 'workspace/react-agent') or an HTTP(S) endpoint URL "
        "(e.g. 'http://localhost:8080').  Bare names fetch the agent's stored "
        "config and merge it with the optimize config so trials run the agent's "
        "workflow locally with swept parameters; URLs are passed through to "
        "'nat optimize --endpoint' verbatim (opaque service mode — local "
        "parameter sweeps don't reach the remote agent).  When omitted, the "
        "optimize config must include an inline agent workflow.",
    )
    optimize_config: str = Field(description="Path to the NAT optimization YAML config file.")
    workspace: str = Field(
        default="default",
        description="Workspace name used to fetch the agent's stored config when "
        "--agent is a bare name, and to construct the Inference Gateway URL when "
        "injecting base_url into LLMs that have none set.",
    )


class OptimizeAgentJob(NemoJob):
    """Optimize a NAT agent workflow via prompt/parameter tuning.

    Entry point: ``agents.optimize = nemo_agents_plugin.jobs.optimize_agent:OptimizeAgentJob``
    """

    name: ClassVar[str] = "optimize"
    description: ClassVar[str] = "Optimize an agent workflow (prompt tuning, HPO) as a scheduled platform job."
    container: ClassVar[str] = "cpu-tasks"
    spec_schema: ClassVar[type[BaseModel]] = OptimizeAgentSpec

    @classmethod
    async def compile(  # type: ignore[override]
        cls,
        *,
        workspace: str,
        spec: OptimizeAgentSpec,
        entity_client: object,
        job_name: str | None,
        async_sdk: object,
        profile: str | None = None,
        options: dict | None = None,
    ) -> PlatformJobSpec:
        """Single-step PlatformJobSpec running ``nemo_agents_plugin.tasks.optimize``."""
        from nemo_agents_plugin.jobs.evaluate_suite import _require_absolute
        from nemo_platform_plugin.jobs.api_factory import (
            EnvironmentVariable,
            PlatformJobStep,
            SubprocessExecutionProviderSpec,
        )
        from nmp.common.jobs.constants import (
            DEFAULT_JOB_STORAGE_PATH,
            PERSISTENT_JOB_STORAGE_PATH_ENVVAR,
        )

        _require_absolute(spec.optimize_config, "optimize_config")

        spec_dict = spec.model_dump(mode="json")
        # URL workspace is the auth boundary; overwrites any spec workspace.
        spec_dict["workspace"] = workspace

        return PlatformJobSpec(
            steps=[
                PlatformJobStep(
                    name="optimize-agent",
                    executor=SubprocessExecutionProviderSpec(
                        provider="subprocess",
                        command=["python", "-m", "nemo_agents_plugin.tasks.optimize"],
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
        """Run optimization by delegating to the ``nat optimize`` CLI.

        See the module docstring for the three resolution modes.  In all
        modes, the (possibly merged) config has the Inference Gateway URL
        injected into any LLMs that don't already declare ``base_url``,
        and a temporary copy is written to the same directory as the
        original optimize config so relative paths (datasets, output dirs)
        continue to resolve.

        Output paths in the config (``eval.general.output_dir`` and
        ``optimizer.output_path``) are rebased to write under
        ``ctx.storage.persistent / "results"`` instead of the source tree,
        preventing unstaged git changes during local CLI runs.

        Args:
            config: Dict matching :class:`OptimizeAgentSpec`.
            ctx: Job execution context providing storage paths (persistent,
                ephemeral) and metadata. Used to determine where optimization
                artifacts should be written.
            sdk: Platform SDK handle, injected by
                :class:`~nemo_platform_plugin.scheduler.NemoJobScheduler` from the
                ambient SDK handle.  Required only when ``cfg.agent`` is
                a platform-managed :class:`AgentRef` (the agent-fetch
                mode); URL and ``None`` modes don't need it.  When
                missing in a mode that requires it, we raise
                :class:`LocalRunError` early so the user gets an
                actionable error before the subprocess runs.

        Returns:
            Dict with ``status`` and ``returncode`` keys.
        """
        cfg = OptimizeAgentSpec.model_validate(config)
        optimize_config_path = Path(cfg.optimize_config)

        agent_config, endpoint = self._resolve_agent(cfg.agent, workspace=cfg.workspace, sdk=sdk)

        # Pre-flight: surface a missing-VirtualModel error before the
        # ``nat optimize`` subprocess starts.  ``agent_config`` is merged
        # under the YAML in the same shape ``temp_injected_config`` will
        # use, so an agent-fetched LLM gets validated alongside the
        # optimize-side judge.  No-op when ``sdk`` is None
        # (URL/inline-workflow modes have nothing to look up against).
        preflight_validate_llm_models(
            optimize_config_path,
            workspace=cfg.workspace,
            sdk=sdk,
            agent_config=agent_config,
        )

        output_base = ctx.storage.persistent / "results"
        output_base.mkdir(parents=True, exist_ok=True)

        with temp_injected_config(
            optimize_config_path,
            cfg.workspace,
            extra_config=agent_config,
            output_base=output_base,
        ) as injected_path:
            cwd = injected_path.parent
            cmd = ["nat", "optimize", "--config_file", injected_path.name]

            # Only the explicit URL mode hands ``--endpoint`` to NAT.  The
            # AgentRef mode merges the agent's workflow into the config so
            # ``nat optimize`` runs it locally and per-trial param overrides
            # actually take effect; the inline-workflow mode (agent=None)
            # similarly relies on the user's config to declare a workflow.
            if endpoint is not None:
                cmd.extend(["--endpoint", endpoint])
                logger.info("Optimizing against agent endpoint %s (opaque service mode)", endpoint)

            logger.info("Writing optimize outputs to platform-persistent dir %s", output_base)
            logger.info("Running: %s (cwd=%s)", " ".join(cmd), cwd)
            try:
                result = subprocess.run(cmd, check=True, cwd=cwd)
                logger.info("OptimizeAgentJob completed (returncode=%d).", result.returncode)
                return {"status": "completed", "returncode": result.returncode}
            except subprocess.CalledProcessError as exc:
                logger.error("Optimization failed (returncode=%d).", exc.returncode)
                return {"status": "failed", "returncode": exc.returncode}
            except FileNotFoundError as exc:
                raise RuntimeError(
                    "'nat optimize' command not found.  Install the NAT config optimizer: "
                    "uv pip install 'nvidia-nat-config-optimizer>=1.5.0,<2.0'"
                ) from exc

    @staticmethod
    def _resolve_agent(
        agent: AgentTarget | None,
        *,
        workspace: str,
        sdk: NeMoPlatform | None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Project the union-typed ``agent`` field down to the inputs the runner needs.

        Returns a tuple ``(agent_config, endpoint)``:

        * ``agent_config`` is the dict to merge under the optimize YAML
          before running ``nat optimize`` — this is what carries the
          agent's workflow, tools, telemetry, and base LLM specs into
          each trial.  ``None`` means "no merge needed".
        * ``endpoint`` is a URL to forward as ``nat optimize --endpoint``.
          ``None`` means "run locally / no endpoint".

        Exactly one of the two will be non-None for a given call.

        ``None`` agent → ``(None, None)``: the optimize config is
        expected to declare its own workflow.

        :class:`EndpointURL` agent → ``(None, "<url>")``: pass-through
        to NAT's remote workflow client.  Sweeps don't affect the remote
        agent; we log a warning so the user knows.

        :class:`AgentRef` agent → ``(<agent.config>, None)``: fetch the
        platform-stored agent and return its config dict for merging.
        Requires *sdk*; raises :class:`LocalRunError` when missing.
        """
        if agent is None:
            return None, None

        cls = classify_agent_target(agent)
        if cls is EndpointURL:
            logger.warning(
                "Optimizing against a raw endpoint URL — per-trial parameter sweeps "
                "in the optimize config are local to the optimizer process and won't "
                "affect the remote agent.  Use a platform-managed agent ref to enable "
                "in-process trial execution."
            )
            return None, str(agent)

        ref = AgentRef(agent)
        if "/" in ref:
            ws, name = ref.split("/", 1)
        else:
            ws, name = workspace, ref

        if sdk is None:
            raise LocalRunError(
                f"OptimizeAgentJob.run requires a 'sdk: NeMoPlatform' to fetch agent "
                f"'{ref}' from the platform, but no platform SDK was available. "
                "Set NMP_BASE_URL (so the local CLI can build a default SDK), pass an "
                "explicit sdk via NemoJobScheduler.run_local(sdk=...), or pass a literal "
                "HTTP endpoint URL via --agent http://... to use opaque-service mode."
            )

        agent_dict = sdk.agents.get(name=name, workspace=ws)
        agent_config = agent_dict["config"] if isinstance(agent_dict, dict) else getattr(agent_dict, "config", {})
        if not isinstance(agent_config, dict) or not agent_config:
            raise RuntimeError(
                f"Agent '{ws}/{name}' has an empty or invalid stored config; cannot merge it into the optimize config."
            )
        logger.info(
            "Resolved --agent %s to platform agent %s/%s; merging stored workflow into optimize config.",
            ref,
            ws,
            name,
        )
        return agent_config, None
