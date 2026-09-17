# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import contextlib
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator, cast
from unittest.mock import MagicMock, patch

import pytest
import yaml
from nemo_agent_optimization_plugin.schemas.optimize import AgentOptimizeSpec
from nemo_optimization.jobs.optimize import OptimizeJob, _apply_tuned_params
from nemo_optimization.schemas.optimize import FILESET_REQUIRED, OptimizeSpec, OptimizeSubmitSpec
from nemo_platform import NeMoPlatform
from nemo_platform_plugin.job_context import JobContext
from nemo_platform_plugin.jobs.exceptions import (
    PlatformJobCompilationError,
    PlatformJobDependencyUnavailableError,
)
from nemo_platform_plugin.jobs.execution_profiles import (
    DockerJobExecutionProfile,
    DockerJobExecutionProfileConfig,
    SubprocessJobExecutionProfile,
)
from nemo_platform_plugin.refs import FilesetRef
from nemo_platform_plugin.run_dependencies import LocalRunError
from nemo_platform_plugin.scheduler import NemoJobScheduler
from pydantic import ValidationError

MINIMAL_CONFIG = {"optimizer": {"numeric": {"enabled": True}}}

SUBPROCESS_PROFILE = SubprocessJobExecutionProfile(profile="default")
CPU_PROFILE = DockerJobExecutionProfile(provider="cpu", profile="default", config=DockerJobExecutionProfileConfig())

#: A minimal but valid ``nemo-agents-spec-v1`` agent config — everything ``_to_fabric_agent_package``
#: (study input) and ``register_optimized_agent`` (study output) validate via ``AgentConfig``.
SOURCE_AGENT_CONFIG: dict[str, Any] = {
    "config_format": "nemo-agents-spec-v1",
    "name": "source-agent",
    "default_harness": "hermes",
    "harnesses": {
        "hermes": {
            "kind": "hermes",
            "model": {
                "provider": "openai",
                "model": "demo-model",
                "base_url": "http://localhost:8080/apis/inference-gateway/v2/workspaces/default/openai/-/v1",
                "api_key_env": "NEMO_AGENTS_IGW_API_KEY",
            },
            "settings": {"max_tokens": 256, "reasoning_config": {"effort": "none"}},
        }
    },
    "instructions": {"system": {"content": "Be brief."}},
    "environment": {"provider": "local", "workspace": "./workspace", "artifacts": "./artifacts"},
}


def run_payload(**overrides: Any) -> dict[str, Any]:
    """A valid ``run()`` config dict: agent + fileset bundle + workspace + output_agent.

    Every field here is now required by ``AgentOptimizeSpec`` — a study always resolves a
    platform agent and always registers a new one — so every ``run()`` test starts from this
    and overrides only what it's testing.
    """
    payload = {
        "optimize_config": "optimize.yml",
        "optimize_config_fileset": "opt-bundle",
        "workspace": "default",
        "agent": "react-agent",
        "output_agent": "react-agent-tuned",
    }
    payload.update(overrides)
    return payload


class _StubAgents:
    """Stubs ``sdk.agents``.

    ``get`` hands back *source_config* (recording the call args in *fetched* when given);
    ``create`` accepts the optimized-agent registration every successful study now performs,
    recording the payload in *created* when given.
    """

    def __init__(
        self,
        source_config: dict[str, Any],
        *,
        fetched: dict[str, Any] | None = None,
        created: dict[str, Any] | None = None,
    ) -> None:
        self._source_config = source_config
        self._fetched = fetched
        self._created = created

    def get(self, name: str, *, workspace: str) -> dict[str, Any]:
        if self._fetched is not None:
            self._fetched.update(name=name, workspace=workspace)
        return {"config": self._source_config}

    def create(self, *, name: str, config: dict[str, Any], description: str, config_format: str, workspace: str) -> Any:
        if self._created is not None:
            self._created.update(
                name=name, config=config, description=description, config_format=config_format, workspace=workspace
            )
        return SimpleNamespace(name=name)


class _StubFiles:
    """Stubs ``sdk.files``.

    ``download`` serves *bundles* keyed by fileset name (so a config bundle and a separately
    staged dataset can be told apart). A call carrying ``remote_path`` is the optimized-agent
    registration's ``ETHOS.md`` probe — stub agents never have one, so it raises, and
    ``registration.py`` treats any such failure as a clean "nothing to copy" by design.
    ``upload`` accepts the registration's fileset write, recording it in *uploaded* when given.
    """

    def __init__(
        self,
        bundles: dict[str, dict[str, str]],
        *,
        downloaded: dict[str, Any] | None = None,
        uploaded: dict[str, Any] | None = None,
    ) -> None:
        self._bundles = bundles
        self._downloaded = downloaded
        self._uploaded = uploaded

    def download(self, *, local_path: str, fileset: str, workspace: str, remote_path: str | None = None) -> None:
        if remote_path is not None:
            raise FileNotFoundError(f"{remote_path!r} not staged in fileset {workspace}/{fileset}")
        if self._downloaded is not None:
            self._downloaded.update(fileset=fileset, workspace=workspace)
        for relative, contents in self._bundles.get(fileset, {}).items():
            target = Path(local_path) / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(contents)

    def upload(self, *, local_path: str, fileset: str, workspace: str, fileset_auto_create: bool) -> Any:
        if self._uploaded is not None:
            self._uploaded.update(
                local_path=local_path, fileset=fileset, workspace=workspace, auto_create=fileset_auto_create
            )
        return SimpleNamespace(name=fileset)


def bundle_sdk(
    bundle: dict[str, str],
    *,
    fileset: str = "opt-bundle",
    extra_bundles: dict[str, dict[str, str]] | None = None,
    source_agent: dict[str, Any] = SOURCE_AGENT_CONFIG,
    downloaded: dict[str, Any] | None = None,
    uploaded: dict[str, Any] | None = None,
    fetched: dict[str, Any] | None = None,
    created: dict[str, Any] | None = None,
) -> NeMoPlatform:
    """An SDK stub for a full ``run()`` pass: stages *bundle* under *fileset* (plus any
    ``extra_bundles`` under their own fileset names — e.g. a dataset staged from a second
    fileset), resolves ``agents.get`` to *source_agent*, and accepts the ``agents.create`` /
    ``files.upload`` registration call every successful run now makes.
    """

    class _StubSDK:
        agents = _StubAgents(source_agent, fetched=fetched, created=created)
        files = _StubFiles({fileset: bundle, **(extra_bundles or {})}, downloaded=downloaded, uploaded=uploaded)

    return cast(NeMoPlatform, _StubSDK())


@contextlib.contextmanager
def profiles(*execution_profiles: Any) -> Iterator[None]:
    """Patch the Jobs client so ``compile`` sees exactly *execution_profiles*."""

    async def _get_execution_profiles() -> Any:
        return SimpleNamespace(data=lambda: list(execution_profiles))

    client = MagicMock()
    client.get_execution_profiles = _get_execution_profiles
    with patch("nemo_optimization.jobs.optimize.client_from_platform", return_value=client):
        yield


async def compile_spec(spec: OptimizeSpec, *, workspace: str = "default", profile: str | None = None) -> Any:
    # ``compile`` now declares ``spec: AgentOptimizeSpec`` (the router's normalized contract).
    # These tests build the older, still-supported ``OptimizeSpec`` shape directly — it carries
    # exactly the fields ``compile`` reads (``optimize_config``, ``optimize_config_fileset``) —
    # so the cast documents the intentional, duck-typed cross-schema call rather than papering
    # over a real mismatch.
    return await OptimizeJob.compile(
        workspace=workspace,
        spec=cast(AgentOptimizeSpec, spec),
        entity_client=MagicMock(),
        job_name=None,
        async_sdk=MagicMock(),
        profile=profile,
    )


def staged_spec(**overrides: Any) -> OptimizeSpec:
    return OptimizeSpec.model_validate(
        {"optimize_config": "optimize.yml", "optimize_config_fileset": "default/opt-bundle", **overrides}
    )


# ---------------------------------------------------------------------------
# compile — fileset requirement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compile_stamps_the_fileset_ref_into_the_step_config() -> None:
    with profiles(SUBPROCESS_PROFILE):
        platform_spec = await compile_spec(staged_spec(), workspace="staging")

    step = next(iter(platform_spec["steps"]))
    assert step["name"] == "optimize"
    assert step["config"]["workspace"] == "staging"
    assert step["config"]["optimize_config_fileset"] == "default/opt-bundle"
    assert step["config"]["optimize_config"] == "optimize.yml"


@pytest.mark.asyncio
async def test_compile_requires_a_staged_fileset() -> None:
    spec = OptimizeSpec(optimize_config="/abs/optimize.yml")
    with pytest.raises(PlatformJobCompilationError, match="prepare-fileset"):
        await compile_spec(spec)


def test_spec_rejects_absolute_config_alongside_a_fileset() -> None:
    with pytest.raises(ValidationError, match="relative to the fileset root"):
        OptimizeSpec(optimize_config="/abs/optimize.yml", optimize_config_fileset=FilesetRef("opt-bundle"))


@pytest.mark.parametrize("config_path", ["../escape.yml", "~/optimize.yml", "C:\\bundle\\optimize.yml"])
def test_spec_rejects_config_paths_that_escape_the_fileset(config_path: str) -> None:
    with pytest.raises(ValidationError, match="relative to the fileset root"):
        OptimizeSpec(optimize_config=config_path, optimize_config_fileset=FilesetRef("opt-bundle"))


def test_spec_rejects_a_malformed_fileset_ref() -> None:
    with pytest.raises(ValidationError, match="'name' or 'workspace/name'"):
        OptimizeSpec(optimize_config="optimize.yml", optimize_config_fileset=FilesetRef("ws/fs/extra"))


def test_spec_requires_a_config_location() -> None:
    with pytest.raises(ValidationError):
        OptimizeSpec.model_validate({})


def test_submit_spec_requires_fileset_for_remote_requests() -> None:
    with pytest.raises(ValidationError, match="prepare-fileset") as missing:
        OptimizeSubmitSpec.model_validate({"optimize_config": "optimize.yml"})
    assert FILESET_REQUIRED in str(missing.value)

    with pytest.raises(ValidationError, match="prepare-fileset") as explicit_none:
        OptimizeSubmitSpec.model_validate({"optimize_config": "optimize.yml", "optimize_config_fileset": None})
    assert FILESET_REQUIRED in str(explicit_none.value)


def test_submit_spec_allows_missing_fileset_for_local_scheduler() -> None:
    spec = OptimizeSubmitSpec.model_validate({"optimize_config": "/abs/optimize.yml"}, context={"is_local": True})

    assert spec.optimize_config == "/abs/optimize.yml"
    assert spec.optimize_config_fileset is None


# ---------------------------------------------------------------------------
# compile — executor selection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compile_prefers_the_subprocess_profile() -> None:
    with profiles(SUBPROCESS_PROFILE, CPU_PROFILE):
        platform_spec = await compile_spec(staged_spec())

    executor = next(iter(platform_spec["steps"]))["executor"]
    assert executor["provider"] == "subprocess"
    assert executor["profile"] == "default"
    assert executor["command"] == ["python", "-m", "nemo_optimization.tasks.optimize"]


@pytest.mark.asyncio
async def test_compile_falls_back_to_the_cpu_profile_with_a_task_image() -> None:
    with (
        profiles(CPU_PROFILE),
        patch("nemo_optimization.jobs.optimize.get_qualified_image", return_value="reg.example/nmp-cpu-tasks:test"),
    ):
        platform_spec = await compile_spec(staged_spec())

    executor = next(iter(platform_spec["steps"]))["executor"]
    assert executor["provider"] == "cpu"
    assert executor["profile"] == "default"
    assert executor["container"]["image"] == "reg.example/nmp-cpu-tasks:test"
    assert [*executor["container"]["entrypoint"], *executor["container"]["command"]] == [
        "python",
        "-m",
        "nemo_optimization.tasks.optimize",
    ]


@pytest.mark.asyncio
async def test_compile_matches_the_requested_profile_name() -> None:
    """A subprocess backend registered under another name must not capture 'high-mem'."""
    with (
        profiles(
            SUBPROCESS_PROFILE,
            DockerJobExecutionProfile(provider="cpu", profile="high-mem", config=DockerJobExecutionProfileConfig()),
        ),
        patch("nemo_optimization.jobs.optimize.get_qualified_image", return_value="reg.example/nmp-cpu-tasks:test"),
    ):
        platform_spec = await compile_spec(staged_spec(), profile="high-mem")

    executor = next(iter(platform_spec["steps"]))["executor"]
    assert executor["provider"] == "cpu"
    assert executor["profile"] == "high-mem"


@pytest.mark.asyncio
async def test_compile_reports_available_profiles_when_none_match() -> None:
    with profiles(DockerJobExecutionProfile(provider="gpu", profile="a100", config=DockerJobExecutionProfileConfig())):
        with pytest.raises(PlatformJobCompilationError, match=r"Available profiles: \['gpu/a100'\]"):
            await compile_spec(staged_spec())


@pytest.mark.asyncio
async def test_compile_is_retryable_when_jobs_is_unreachable() -> None:
    import httpx
    from nemo_platform_plugin.client.errors import NemoTransportError

    async def _boom() -> Any:
        raise NemoTransportError(httpx.ConnectError("connection refused", request=httpx.Request("GET", "http://x")))

    client = MagicMock()

    client.get_execution_profiles = _boom
    with (
        patch("nemo_optimization.jobs.optimize.client_from_platform", return_value=client),
        pytest.raises(PlatformJobDependencyUnavailableError, match="temporarily unavailable"),
    ):
        await compile_spec(staged_spec())


# ---------------------------------------------------------------------------
# run — every study resolves a platform agent and stages its config from a fileset
# ---------------------------------------------------------------------------
#
# ``AgentOptimizeSpec`` now requires ``agent``, ``optimize_config_fileset``, and
# ``output_agent`` on every submission, so a bare local path with no SDK — the old
# "inline Fabric config" mode this job used to support — can no longer be constructed at
# all. Every test below goes through ``bundle_sdk`` + ``run_payload`` accordingly.


def test_run_dispatches_a_local_fabric_config(ctx: JobContext) -> None:
    """``run`` loads the staged config and hands it to ``OptimizeRouter.dispatch``.

    Inline Fabric agent packages are gone: every study now resolves ``agent`` through the
    SDK first, so this also confirms that resolution feeds a real ``agent_config`` (the old
    assertion here was ``agent_config is None``, which is no longer reachable).
    """
    sdk = bundle_sdk({"optimize.yml": yaml.safe_dump(MINIMAL_CONFIG)})

    with patch(
        "nemo_optimization.jobs.optimize.OptimizeRouter.dispatch", return_value={"status": "completed"}
    ) as dispatch:
        result = OptimizeJob().run(run_payload(), ctx=ctx, sdk=sdk)

    assert result["status"] == "completed"
    kwargs = dispatch.call_args.kwargs
    assert kwargs["agent_config"]["schema_version"] == "fabric.agent/v1alpha1"
    assert kwargs["optimize_config"]["optimizer"]["numeric"]["enabled"] is True


def test_scheduler_run_local_preserves_workspace_through_a_staged_config(ctx: JobContext) -> None:
    """``workspace`` still flows from the submitted spec into ``preflight_validate_llm_models``
    — but no longer via ``NemoJobScheduler.run_local``'s ``workspace=`` kwarg.  ``OptimizeJob``
    no longer declares an ``input_spec_schema``, so ``to_spec`` (which used to stamp
    ``workspace`` onto the spec on the local path) never runs; the submitted config dict has to
    set ``workspace`` itself now. (The old test name/premise, "for absolute config without
    fileset", is doubly gone: a fileset is mandatory too.)
    """
    sdk = bundle_sdk({"optimize.yml": yaml.safe_dump(MINIMAL_CONFIG)})
    observed: dict[str, str] = {}

    def _preflight(*args: Any, workspace: str, **kwargs: Any) -> None:
        del args, kwargs
        observed["workspace"] = workspace

    with (
        patch("nemo_optimization.jobs.optimize.preflight_validate_llm_models", side_effect=_preflight),
        patch("nemo_optimization.jobs.optimize.OptimizeRouter.dispatch", return_value={"status": "completed"}),
    ):
        result = NemoJobScheduler().run_local(
            OptimizeJob,
            run_payload(workspace="research"),
            workspace="research",
            sdk=sdk,
            ctx=ctx,
        )

    assert result["status"] == "completed"
    assert observed["workspace"] == "research"


def test_run_restores_the_working_directory_after_a_successful_study(ctx: JobContext) -> None:
    """A fileset is mandatory now, so ``run`` always stages the config into a download dir and
    always chdirs there for the dispatch — the old "never touches cwd" local-path guarantee
    this test's name described is gone. What survives, and what this checks instead: cwd
    always comes back afterward. (The failure-path counterpart is
    ``test_run_restores_the_working_directory_when_the_study_raises``.)
    """
    sdk = bundle_sdk({"optimize.yml": yaml.safe_dump(MINIMAL_CONFIG)})
    cwd = Path.cwd()
    observed: dict[str, Path] = {}

    def _dispatch(**kwargs: Any) -> dict[str, Any]:
        observed["cwd"] = Path.cwd()
        return {"status": "completed"}

    with patch("nemo_optimization.jobs.optimize.OptimizeRouter.dispatch", side_effect=_dispatch):
        OptimizeJob().run(run_payload(), ctx=ctx, sdk=sdk)

    assert observed["cwd"] != cwd
    assert Path.cwd() == cwd


def test_run_expands_env_vars_in_the_config(ctx: JobContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPTIMIZE_TEST_MODEL", "demo-model")
    sdk = bundle_sdk({"optimize.yml": yaml.safe_dump({"models": {"default": {"model": "${OPTIMIZE_TEST_MODEL}"}}})})

    with patch(
        "nemo_optimization.jobs.optimize.OptimizeRouter.dispatch", return_value={"status": "completed"}
    ) as dispatch:
        OptimizeJob().run(run_payload(), ctx=ctx, sdk=sdk)

    assert dispatch.call_args.kwargs["optimize_config"]["models"]["default"]["model"] == "demo-model"


def test_run_resolves_platform_agent_before_dispatch(ctx: JobContext) -> None:
    platform_agent = {
        "config_format": "nemo-agents-spec-v1",
        "name": "react-agent",
        "default_harness": "hermes",
        "harnesses": {
            "hermes": {
                "kind": "hermes",
                "model": {
                    "provider": "openai",
                    "model": "demo-model",
                    "base_url": "http://localhost:8080/apis/inference-gateway/v2/workspaces/default/openai/-/v1",
                    "api_key_env": "NEMO_AGENTS_IGW_API_KEY",
                },
                "settings": {"max_tokens": 256, "reasoning_config": {"effort": "none"}},
            }
        },
        "instructions": {"system": {"content": "Be brief."}},
        "environment": {"provider": "local", "workspace": "./workspace", "artifacts": "./artifacts"},
        "models": {
            "judge": {
                "provider": "openai",
                "model": "demo-model",
                "base_url": "http://localhost:8080/apis/inference-gateway/v2/workspaces/default/openai/-/v1",
                "api_key_env": "NEMO_AGENTS_IGW_API_KEY",
            }
        },
    }
    fetched: dict[str, Any] = {}
    sdk = bundle_sdk({"optimize.yml": yaml.safe_dump(MINIMAL_CONFIG)}, source_agent=platform_agent, fetched=fetched)

    with patch(
        "nemo_optimization.jobs.optimize.OptimizeRouter.dispatch", return_value={"status": "completed"}
    ) as dispatch:
        OptimizeJob().run(run_payload(agent="react-agent"), ctx=ctx, sdk=sdk)

    assert fetched == {"name": "react-agent", "workspace": "default"}
    agent_config = dispatch.call_args.kwargs["agent_config"]
    assert agent_config["schema_version"] == "fabric.agent/v1alpha1"
    assert agent_config["harness"]["adapter_id"] == "nvidia.fabric.hermes"
    assert agent_config["models"]["default"]["model"] == "demo-model"
    assert agent_config["models"]["judge"]["model"] == "demo-model"


# ---------------------------------------------------------------------------
# run — staged (fileset) mode
# ---------------------------------------------------------------------------


def test_run_stages_the_config_from_the_fileset(ctx: JobContext) -> None:
    downloaded: dict[str, Any] = {}
    sdk = bundle_sdk({"configs/optimize.yml": yaml.safe_dump(MINIMAL_CONFIG)}, downloaded=downloaded)

    with patch(
        "nemo_optimization.jobs.optimize.OptimizeRouter.dispatch", return_value={"status": "completed"}
    ) as dispatch:
        result = OptimizeJob().run(
            run_payload(optimize_config="configs/optimize.yml", optimize_config_fileset="default/opt-bundle"),
            ctx=ctx,
            sdk=sdk,
        )

    assert result["status"] == "completed"
    assert downloaded == {"fileset": "opt-bundle", "workspace": "default"}
    assert dispatch.call_args.kwargs["optimize_config"]["optimizer"]["numeric"]["enabled"] is True


def test_run_resolves_relative_assets_against_the_staged_bundle(ctx: JobContext) -> None:
    """Relative dataset / base_dir entries must resolve inside the download, not the task's cwd."""
    config = {
        **MINIMAL_CONFIG,
        "eval": {
            "general": {"dataset": {"file_path": "data/rows.json"}},
            "fabric": {"base_dir": "."},
        },
    }
    sdk = bundle_sdk(
        {
            "optimize.yml": yaml.safe_dump(config),
            "data/rows.json": json.dumps([{"question": "q", "answer": "a"}]),
        }
    )
    observed: dict[str, Any] = {}

    def _dispatch(**kwargs: Any) -> dict[str, Any]:
        dataset = kwargs["optimize_config"]["eval"]["general"]["dataset"]["file_path"]
        observed["rows"] = json.loads(Path(dataset).read_text())
        observed["cwd"] = Path.cwd()
        return {"status": "completed"}

    cwd = Path.cwd()
    with patch("nemo_optimization.jobs.optimize.OptimizeRouter.dispatch", side_effect=_dispatch):
        OptimizeJob().run(run_payload(), ctx=ctx, sdk=sdk)

    assert observed["rows"] == [{"question": "q", "answer": "a"}]
    assert observed["cwd"] != cwd
    # The chdir is undone even though the study ran inside it.
    assert Path.cwd() == cwd


def test_run_restores_the_working_directory_when_the_study_raises(ctx: JobContext) -> None:
    sdk = bundle_sdk({"optimize.yml": yaml.safe_dump(MINIMAL_CONFIG)})
    cwd = Path.cwd()

    with (
        patch("nemo_optimization.jobs.optimize.OptimizeRouter.dispatch", side_effect=RuntimeError("study blew up")),
        pytest.raises(RuntimeError, match="study blew up"),
    ):
        OptimizeJob().run(run_payload(), ctx=ctx, sdk=sdk)

    assert Path.cwd() == cwd


def test_run_rejects_a_staged_config_missing_from_the_fileset(ctx: JobContext) -> None:
    sdk = bundle_sdk({"other.yml": yaml.safe_dump(MINIMAL_CONFIG)})

    with pytest.raises(FileNotFoundError, match="was not found in fileset"):
        OptimizeJob().run(run_payload(), ctx=ctx, sdk=sdk)


def test_run_rejects_a_staged_config_without_an_sdk(ctx: JobContext) -> None:
    """``run()`` no longer checks ``sdk`` up front; a fileset-backed config still needs one to
    stage the bundle, so the fileset-staging helper's own "no sdk" message is what surfaces.
    """
    with pytest.raises(LocalRunError, match="Staging optimize-config from a fileset requires a 'sdk"):
        OptimizeJob().run(run_payload(), ctx=ctx)


# ---------------------------------------------------------------------------
# run — dataset staged from its own fileset
# ---------------------------------------------------------------------------


def _config_with_dataset(dataset: Any) -> dict[str, Any]:
    return {
        **MINIMAL_CONFIG,
        "eval": {"general": {"dataset": dataset, "max_concurrency": 1}},
    }


def test_run_stages_dataset_from_fileset_ref(ctx: JobContext) -> None:
    downloaded: dict[str, Any] = {}
    config = _config_with_dataset({"file_path": "default/evals#rows.json"})
    sdk = bundle_sdk(
        {"optimize.yml": yaml.safe_dump(config)},
        extra_bundles={"evals": {"rows.json": '[{"question": "q", "answer": "a"}]'}},
        downloaded=downloaded,
    )

    with patch(
        "nemo_optimization.jobs.optimize.OptimizeRouter.dispatch", return_value={"status": "completed"}
    ) as dispatch:
        OptimizeJob().run(run_payload(), ctx=ctx, sdk=sdk)

    # Two filesets are downloaded (the config bundle, then the dataset); the dataset's is last.
    assert downloaded == {"fileset": "evals", "workspace": "default"}
    staged = dispatch.call_args.kwargs["optimize_config"]["eval"]["general"]["dataset"]["file_path"]
    assert staged.endswith("rows.json")
    assert Path(staged).is_absolute()
    # Sibling keys survive the rewrite.
    assert dispatch.call_args.kwargs["optimize_config"]["eval"]["general"]["max_concurrency"] == 1


def test_run_leaves_plain_dataset_path_untouched(ctx: JobContext) -> None:
    config = _config_with_dataset({"file_path": "/data/rows.json"})
    sdk = bundle_sdk({"optimize.yml": yaml.safe_dump(config)})

    with patch(
        "nemo_optimization.jobs.optimize.OptimizeRouter.dispatch", return_value={"status": "completed"}
    ) as dispatch:
        OptimizeJob().run(run_payload(), ctx=ctx, sdk=sdk)

    dataset = dispatch.call_args.kwargs["optimize_config"]["eval"]["general"]["dataset"]
    assert dataset == {"file_path": "/data/rows.json"}


# ---------------------------------------------------------------------------
# _apply_tuned_params
# ---------------------------------------------------------------------------


def _tunable_source_agent(*, harness: str = "hermes", model: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "config_format": "nemo-agents-spec-v1",
        "name": "source-agent",
        "default_harness": harness,
        "harnesses": {
            harness: {
                "kind": harness,
                "model": model
                if model is not None
                else {"provider": "openai", "model": "demo-model", "temperature": 0.2},
            }
        },
    }


def _search_space(**paths: str) -> dict[str, Any]:
    """An ``optimizer`` mapping declaring one Fabric-typed dotted path per logical param name."""
    return {
        "search_space": {name: {"type": "fabric", "path": path, "values": [0.0, 1.0]} for name, path in paths.items()}
    }


def test_apply_tuned_params_lands_temperature_on_the_default_harness_model() -> None:
    source = _tunable_source_agent()
    optimize_config = {"optimizer": _search_space(temp="models.default.temperature")}
    result = {"best_params": {"temp": 0.73}}

    optimized = _apply_tuned_params(source, optimize_config, result)

    assert optimized["harnesses"]["hermes"]["model"]["temperature"] == 0.73


def test_apply_tuned_params_leaves_an_unplaceable_leaf_unapplied() -> None:
    """``top_p`` has no home in ``_TUNABLE_MODEL_FIELDS`` — it must not be invented as a key."""
    source = _tunable_source_agent()
    optimize_config = {"optimizer": _search_space(top_p="models.default.top_p")}
    result = {"best_params": {"top_p": 0.9}}

    optimized = _apply_tuned_params(source, optimize_config, result)

    assert "top_p" not in optimized["harnesses"]["hermes"]["model"]
    assert optimized["harnesses"]["hermes"]["model"] == source["harnesses"]["hermes"]["model"]


def test_apply_tuned_params_does_not_mutate_its_input() -> None:
    """The whole point is not producing an agent that looks optimized without being so —
    starting with the caller's own dict never even in scratch space."""
    source = _tunable_source_agent()
    original = copy.deepcopy(source)
    optimize_config = {"optimizer": _search_space(temp="models.default.temperature")}
    result = {"best_params": {"temp": 0.73}}

    _apply_tuned_params(source, optimize_config, result)

    assert source == original


def test_optimize_task_module_is_importable() -> None:
    """Both executors invoke this module by name; a rename must fail here, not in a job."""
    import importlib

    from nemo_optimization.jobs.optimize import OPTIMIZE_TASK_MODULE

    assert importlib.import_module(OPTIMIZE_TASK_MODULE) is not None
