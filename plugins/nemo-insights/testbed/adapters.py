# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Per-type testbed adapters that turn a subject into analyst Insights."""

import base64
import json
import os
import shutil
import sys
import time
from collections.abc import Iterator, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import httpx
from google.protobuf.json_format import ParseDict
from nemo_insights_plugin.analyst.run import run_analyst
from nemo_insights_plugin.client import make_client
from nemo_platform import AsyncNeMoPlatform
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from testbed.ingest import (
    create_experiment,
    ensure_experiment_group,
    ensure_workspace,
    mint_agent_id,
    poll_visible,
)
from testbed.intake_client import build_basic_auth_intake_client
from testbed.otlp_build import session_id_for, sim_to_spans
from testbed.otlp_ingest import export_spans, export_trace_request, post_evaluator_results, trace_id_for
from testbed.registry import Subject
from testbed.tau2run import load_tasks, policy_version, read_policy, resolve_paths, run_tau2

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestbedAdapter(Protocol):
    def check(self) -> list[str]: ...

    async def produce(self) -> dict[str, object]: ...

    async def analyze(
        self,
        *,
        record: dict[str, object] | None,
        since: datetime | None,
        verbose: bool,
        out_path: Path,
    ) -> str: ...


class IntakeAdapter:
    """Analyze an agent's existing Intake traces (no production step)."""

    def __init__(self, subject: Subject) -> None:
        self.subject = subject

    def check(self) -> list[str]:
        """Unmet prerequisites for this subject (empty list = ready to run)."""
        cfg = self.subject.config
        missing: list[str] = [f"config key '{k}'" for k in ("agent", "workspace", "base_url") if not cfg.get(k)]
        if cfg.get("auth") == "basic":
            missing.extend(self._missing_basic_auth())
        return missing

    def _missing_basic_auth(self) -> list[str]:
        """Return missing basic-auth configuration and environment values."""
        missing: list[str] = []
        for role, key in (("username", "auth_user_env"), ("password", "auth_password_env")):
            env_name = self.subject.config.get(key)
            if not env_name:
                missing.append(f"config key '{key}' (env var name for the basic-auth {role})")
            elif not os.environ.get(str(env_name)):
                missing.append(f"env {env_name} (basic-auth {role}, in testbed/.env)")
        return missing

    async def produce(self) -> dict[str, object]:
        raise SystemExit(
            f"intake subject '{self.subject.name}' has no produce step — run "
            f"`uv run python -m testbed analyze {self.subject.name} --live`"
        )

    async def analyze(
        self,
        *,
        record: dict[str, object] | None,
        since: datetime | None,
        verbose: bool,
        out_path: Path,
    ) -> str:
        cfg = self.subject.config
        if missing := self.check():
            raise SystemExit(f"intake testbed '{self.subject.name}' is missing: {', '.join(missing)}")
        client = self._basic_auth_client() if cfg.get("auth") == "basic" else make_client(str(cfg["base_url"]))
        return await run_analyst(
            agent=cfg["agent"],
            agent_spec=None,
            workspace=cfg["workspace"],
            base_url=cfg["base_url"],
            client=client,
            insights_output=str(out_path),
            verbose=verbose,
            since=since,
        )

    def _basic_auth_client(self) -> AsyncNeMoPlatform:
        """Build the basic-auth client configured for this Intake subject."""
        cfg = self.subject.config
        real_prefix = str(cfg.get("intake_path_prefix", "/api/intake")).rstrip("/") + "/"
        return build_basic_auth_intake_client(
            base_url=str(cfg["base_url"]),
            username=os.environ[str(cfg["auth_user_env"])],
            password=os.environ[str(cfg["auth_password_env"])],
            real_prefix=real_prefix,
        )


class BenchmarkAdapter:
    """Run a benchmark to produce traces, ingest them, then analyze."""

    def __init__(self, subject: Subject) -> None:
        self.subject = subject

    def check(self) -> list[str]:
        """Unmet prerequisites for this benchmark (empty list = ready to run)."""
        cfg = self.subject.config
        missing: list[str] = []
        for key in ("domain", "base_url", "workspace", "agent_llm", "user_llm"):
            val = cfg.get(key)
            if not val:
                missing.append(f"config key '{key}'")
            elif key in ("agent_llm", "user_llm") and "<your-model>" in str(val):
                missing.append(f"a real model for '{key}' in testbeds.toml (a model your proxy key serves)")
        # The keys build_argv hard-indexes: absent here = a KeyError mid-run, so
        # doctor must name them up front. Absence only — 0 is a valid seed.
        for key in ("task_split_name", "num_trials", "seed", "max_concurrency"):
            if cfg.get(key) is None:
                missing.append(f"config key '{key}'")
        tau2_bin, data_dir = resolve_paths(cfg, repo_root=REPO_ROOT)
        if tau2_bin is None or data_dir is None:
            missing.append("config key 'tau2_repo' (your tau2-bench checkout; or set tau2_bin/tau2_data_dir)")
        else:
            if not data_dir.is_dir():
                missing.append(f"tau2 data dir ({data_dir}) — clone tau2-bench + `uv sync`")
            if shutil.which(tau2_bin) is None:
                missing.append(f"tau2 binary ({tau2_bin}) — run `uv sync` in the tau2 repo")
        for env_key in ("OPENAI_API_KEY", "OPENAI_API_BASE"):
            if not os.environ.get(env_key):
                missing.append(f"env {env_key} (in testbed/.env)")
        return missing

    async def produce(self) -> dict[str, object]:
        cfg = self.subject.config
        if missing := self.check():
            raise SystemExit(f"benchmark testbed '{self.subject.name}' is missing: " + "; ".join(missing))
        tau2_bin, data_dir = resolve_paths(cfg, repo_root=REPO_ROOT)
        assert tau2_bin is not None and data_dir is not None  # guaranteed by check()
        domain = str(cfg["domain"])
        base_url = str(cfg["base_url"])
        base = str(cfg["workspace"])  # stable workspace + agent + experiment-group name
        run_id = mint_agent_id(base)  # the per-run Experiment name + nemo.experiment.id tag
        agent = base  # stable agent name across runs
        created_at = datetime.now(timezone.utc).isoformat()
        # Stable workspaces: the realistic (oracle-free, blind-eval) target is always
        # produced; the oracle twin (answer key, for the UI) only when include_rewards.
        realistic_workspace = base
        include_rewards = bool(cfg.get("include_rewards", True))
        oracle_workspace = f"{base}-oracle" if include_rewards else None
        dataset_name = f"tau2:{domain}"
        ensure_workspace(base_url, realistic_workspace)  # fail fast before tau2
        if oracle_workspace is not None:
            ensure_workspace(base_url, oracle_workspace)
        sims = run_tau2(cfg, run_id, data_dir=data_dir, tau2_bin=tau2_bin)
        if not sims:
            raise SystemExit(f"benchmark testbed '{self.subject.name}': tau2 produced no simulations")
        policy = read_policy(data_dir, domain)
        version = policy_version(policy)
        tasks = load_tasks(data_dir, domain)
        agent_llm = str(cfg["agent_llm"])
        # Register this run as an Experiment on the oracle workspace (where the UI
        # reads it). The realistic side needs only the span tag, not the entity.
        if oracle_workspace is not None:
            group_id = ensure_experiment_group(base_url, oracle_workspace, base)
            create_experiment(
                base_url,
                oracle_workspace,
                name=run_id,
                experiment_group_id=group_id,
                dataset_name=dataset_name,
                dataset_version=version,
                metadata={
                    "agent_llm": agent_llm,
                    "user_llm": str(cfg.get("user_llm", "")),
                    "num_trials": cfg.get("num_trials"),
                    "seed": cfg.get("seed"),
                    "task_split_name": cfg.get("task_split_name"),
                    "num_tasks": cfg.get("num_tasks"),
                    "created_at": created_at,
                },
            )
        session_ids: set[str] = set()
        client = httpx.Client(timeout=30.0)
        try:
            for sim in sims:
                task = tasks.get(str(sim.get("task_id")))
                session_id = session_id_for(sim, experiment_id=run_id)
                trace_id = trace_id_for(session_id)
                # Stamp spans at ingest time (Intake drops spans dated outside its
                # retention window); one base shared by a sim's realistic + oracle twins.
                base_ns = time.time_ns()
                session_ids.add(session_id)
                realistic_spans = sim_to_spans(
                    sim,
                    agent_name=agent,
                    agent_version=version,
                    session_id=session_id,
                    experiment_id=run_id,
                    task=task,
                    include_rewards=False,
                    agent_llm=agent_llm,
                    base_ns=base_ns,
                )
                export_spans(base_url, realistic_workspace, session_id, trace_id, realistic_spans, client=client)
                if oracle_workspace is not None:
                    oracle_spans = sim_to_spans(
                        sim,
                        agent_name=agent,
                        agent_version=version,
                        session_id=session_id,
                        experiment_id=run_id,
                        task=task,
                        include_rewards=True,
                        agent_llm=agent_llm,
                        base_ns=base_ns,
                    )
                    export_spans(base_url, oracle_workspace, session_id, trace_id, oracle_spans, client=client)
                    # OTLP doesn't auto-create the reward row the Analyst reads, so POST it
                    # separately, targeting the EVALUATOR span this oracle build emitted.
                    evaluator = next((s for s in oracle_spans if s["kind"] == "EVALUATOR"), None)
                    if evaluator is not None:
                        post_evaluator_results(
                            base_url,
                            oracle_workspace,
                            span_id=evaluator["span_id"],
                            session_id=session_id,
                            score=float(evaluator["attributes"]["score"]),
                            client=client,
                        )
            if len(session_ids) < 3:
                print(
                    f"warning: only {len(session_ids)} session(s) ingested; the analyst needs 3+ to run.",
                    file=sys.stderr,
                )
            visible = poll_visible(base_url, realistic_workspace, session_ids, client=client)
            if len(visible) < 3:
                print(
                    f"warning: only {len(visible)}/{len(session_ids)} session(s) "
                    "visible in Intake (ingest may still be catching up).",
                    file=sys.stderr,
                )
            if oracle_workspace is not None:
                poll_visible(base_url, oracle_workspace, session_ids, client=client)
        finally:
            client.close()
        return {
            "agent": agent,
            "realistic_workspace": realistic_workspace,
            "oracle_workspace": oracle_workspace,
            "experiment_id": run_id,
            "experiment_group": base,
            "dataset_name": dataset_name,
            "dataset_version": version,
            "base_url": base_url,
            "domain": domain,
            "run_id": run_id,
            "agent_version": version,
            "created_at": created_at,
        }

    async def analyze(
        self,
        *,
        record: dict[str, object] | None,
        since: datetime | None,
        verbose: bool,
        out_path: Path,
    ) -> str:
        if record is None:
            raise SystemExit(
                f"no recorded run for '{self.subject.name}' — run "
                f"`uv run python -m testbed run {self.subject.name}` first"
            )
        _, data_dir = resolve_paths(self.subject.config, repo_root=REPO_ROOT)
        policy = read_policy(data_dir, str(record["domain"])) if data_dir else None
        workspace = str(record["realistic_workspace"])
        evaluation_id = str(record["experiment_id"])
        print(
            f"analyzing realistic workspace '{workspace}' run '{evaluation_id}' (oracle withheld — unaided eval)",
            file=sys.stderr,
        )
        return await run_analyst(
            agent=str(record["agent"]),
            agent_spec=policy,
            workspace=workspace,
            base_url=str(record["base_url"]),
            client=make_client(str(record["base_url"])),
            insights_output=str(out_path),
            verbose=verbose,
            since=since,
            evaluation_id=evaluation_id,
        )


def _export_harbor_trace_files(
    base_url: str,
    workspace: str,
    trace_dir: Path,
    agent_name: str,
    *,
    evaluation_id: str,
    agent_version: str | None = None,
    client: httpx.Client | None = None,
) -> tuple[int, int, set[str]]:
    """Enrich Harbor OTLP-JSONL traces and export them to Intake."""
    headers: dict[str, str] = {}
    if api_key := os.environ.get("INFERENCE_API_KEY"):
        headers["Authorization"] = f"Bearer {api_key}"

    owns_client = client is None
    active_client = client or httpx.Client(timeout=30.0)
    sent = errors = 0
    session_ids: set[str] = set()
    try:
        for path in sorted(trace_dir.rglob("*.jsonl")):
            parsed: list[tuple[int, dict[str, Any]]] = []
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    body = json.loads(line)
                except json.JSONDecodeError as exc:
                    print(f"Harbor trace {path.name} line {line_number}: JSON error — {exc}", file=sys.stderr)
                    errors += 1
                    continue
                if not isinstance(body, dict):
                    print(
                        f"Harbor trace {path.name} line {line_number}: expected a JSON object",
                        file=sys.stderr,
                    )
                    errors += 1
                    continue
                parsed.append((line_number, body))

            test_case_id, input_value, output_value, rewards = _harbor_trace_context(path, trace_dir, parsed)
            evaluator_posted = False
            for line_number, body in parsed:
                resource_spans = body.get("resourceSpans", [])
                if not isinstance(resource_spans, list):
                    errors += 1
                    continue
                session_id = _find_session_id(resource_spans) or path.stem
                session_ids.add(session_id)
                _inject_resource_attributes(
                    resource_spans,
                    {
                        "gen_ai.agent.name": agent_name,
                        "gen_ai.agent.id": agent_name,
                        "gen_ai.agent.version": agent_version,
                        "session.id": session_id,
                        "gen_ai.conversation.id": session_id,
                        "nemo.experiment.id": evaluation_id,
                        "nemo.optimizer.workspace": workspace,
                    },
                )
                _inject_harbor_root_attributes(
                    resource_spans,
                    {
                        "nemo.test_case.id": test_case_id,
                        "input.value": input_value,
                        "input.mime_type": "text/plain" if input_value else None,
                        "output.value": output_value,
                        "output.mime_type": "text/markdown" if output_value else None,
                    },
                )
                root_span_id = _find_harbor_root_span_id(resource_spans)
                try:
                    request = ParseDict(body, ExportTraceServiceRequest())
                    export_trace_request(
                        base_url,
                        workspace,
                        request,
                        client=active_client,
                        headers=headers,
                    )
                    if root_span_id is not None and not evaluator_posted:
                        for reward_name, reward_value in rewards.items():
                            post_evaluator_results(
                                base_url,
                                workspace,
                                span_id=root_span_id,
                                session_id=session_id,
                                score=reward_value,
                                name=reward_name,
                                client=active_client,
                            )
                        evaluator_posted = True
                except Exception as exc:
                    print(f"Harbor trace {path.name} line {line_number}: export error — {exc}", file=sys.stderr)
                    errors += 1
                else:
                    sent += 1
    finally:
        if owns_client:
            active_client.close()
    return sent, errors, session_ids


def _harbor_trace_context(
    path: Path,
    trace_dir: Path,
    parsed: list[tuple[int, dict[str, Any]]],
) -> tuple[str | None, str | None, str | None, dict[str, float]]:
    """Resolve task, input, output, and verifier rewards for one Harbor trial."""
    relative = path.relative_to(trace_dir)
    trial_dir = trace_dir / relative.parts[0] if len(relative.parts) > 1 else None
    test_case_id = None
    output_value = None
    rewards: dict[str, float] = {}
    if trial_dir is not None:
        result_path = trial_dir / "result.json"
        if result_path.is_file():
            try:
                result = json.loads(result_path.read_text(encoding="utf-8"))
                test_case_id = str(result["task_name"])
                raw_rewards = (
                    {} if result.get("exception_info") else (result.get("verifier_result") or {}).get("rewards") or {}
                )
                rewards = {
                    str(name): float(value)
                    for name, value in raw_rewards.items()
                    if isinstance(value, int | float) and not isinstance(value, bool)
                }
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                pass
        artifact_root = trial_dir / "artifacts" / "logs" / "artifacts"
        outputs = sorted(artifact_root.glob("output.*")) if artifact_root.is_dir() else []
        if outputs:
            output_value = outputs[0].read_text(encoding="utf-8", errors="replace")

    input_value, trace_output_value = _root_values_from_trace(parsed)
    if trace_output_value is not None:
        output_value = trace_output_value
    return test_case_id, input_value, output_value, rewards


def _root_values_from_trace(parsed: list[tuple[int, dict[str, Any]]]) -> tuple[str | None, str | None]:
    """Return input and output values from root AGENT spans."""
    input_value = None
    output_value = None
    for _, body in parsed:
        root = _find_harbor_root_span(body.get("resourceSpans", []))
        if root is None:
            continue
        attributes = {item.get("key"): item.get("value", {}) for item in root.get("attributes", [])}
        if input_value is None:
            input_value = attributes.get("input.value", {}).get("stringValue")
        if output_value is None:
            output_value = attributes.get("output.value", {}).get("stringValue")
        if input_value is not None and output_value is not None:
            break
    return input_value, output_value


def _inject_harbor_root_attributes(resource_spans: list[dict[str, Any]], extra: Mapping[str, str | None]) -> None:
    for span in _harbor_root_spans(resource_spans):
        attributes = span.setdefault("attributes", [])
        existing = {item["key"] for item in attributes}
        for key, value in extra.items():
            if value is not None and key not in existing:
                attributes.append({"key": key, "value": {"stringValue": value}})


def _find_harbor_root_span_id(resource_spans: list[dict[str, Any]]) -> str | None:
    """Return root AGENT span ID in Intake's hexadecimal form."""
    root = _find_harbor_root_span(resource_spans)
    if root is None:
        return None
    return base64.b64decode(root["spanId"]).hex()


def _find_harbor_root_span(resource_spans: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next(_harbor_root_spans(resource_spans), None)


def _harbor_root_spans(resource_spans: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    """Yield root AGENT spans from OTLP JSON."""
    for resource_span in resource_spans:
        for scope_spans in resource_span.get("scopeSpans", []):
            for span in scope_spans.get("spans", []):
                kind = next(
                    (
                        item.get("value", {}).get("stringValue")
                        for item in span.get("attributes", [])
                        if item.get("key") == "openinference.span.kind"
                    ),
                    None,
                )
                if not span.get("parentSpanId") and kind == "AGENT":
                    yield span


def _inject_resource_attributes(resource_spans: list[dict[str, Any]], extra: Mapping[str, str | None]) -> None:
    for resource_span in resource_spans:
        attributes = resource_span.setdefault("resource", {}).setdefault("attributes", [])
        existing = {attribute["key"] for attribute in attributes}
        for key, value in extra.items():
            if value is not None and key not in existing:
                attributes.append({"key": key, "value": {"stringValue": value}})


def _find_session_id(resource_spans: list[dict[str, Any]]) -> str | None:
    for resource_span in resource_spans:
        for scope_spans in resource_span.get("scopeSpans", []):
            for span in scope_spans.get("spans", []):
                for attribute in span.get("attributes", []):
                    if attribute.get("key") == "session.id":
                        return attribute.get("value", {}).get("stringValue")
    return None


class HarborAdapter:
    """Run Harbor, ingest collected OTLP traces, then analyze that evaluation."""

    def __init__(self, subject: Subject) -> None:
        self.subject = subject

    @staticmethod
    def _repo_path(value: object, *, repo_root: Path) -> Path:
        path = Path(str(value))
        return (repo_root / path).resolve() if not path.is_absolute() else path.resolve()

    @classmethod
    def _build_dataset_config(cls, cfg: Mapping[str, object], *, repo_root: Path):
        from harbor.models.job.config import DatasetConfig  # noqa: PLC0415

        dataset_path = cfg.get("dataset")
        dataset_ref = cfg.get("dataset_ref")
        dataset_id = cfg.get("dataset_id")
        selected = [value for value in (dataset_path, dataset_ref, dataset_id) if value]
        if len(selected) != 1:
            raise ValueError("exactly one of config keys 'dataset', 'dataset_ref', or 'dataset_id' is required")
        if cfg.get("registry_path") and cfg.get("registry_url"):
            raise ValueError("config keys 'registry_path' and 'registry_url' are mutually exclusive")

        n_tasks = int(str(cfg["num_tasks"])) if cfg.get("num_tasks") is not None else None
        if dataset_path:
            return DatasetConfig(path=cls._repo_path(dataset_path, repo_root=repo_root), n_tasks=n_tasks)

        registry_path = cfg.get("registry_path")
        registry_url = str(cfg["registry_url"]) if cfg.get("registry_url") else None
        resolved_registry_path = cls._repo_path(registry_path, repo_root=repo_root) if registry_path else None
        if dataset_ref:
            dataset_name, separator, dataset_version = str(dataset_ref).rpartition("@")
            if not separator:
                dataset_name = str(dataset_ref)
                dataset_version = ""
            return DatasetConfig(
                name=dataset_name,
                version=dataset_version or None,
                registry_url=registry_url,
                registry_path=resolved_registry_path,
                n_tasks=n_tasks,
            )
        return DatasetConfig(
            name=str(dataset_id),
            version=str(cfg["dataset_version"]) if cfg.get("dataset_version") else None,
            registry_url=registry_url,
            registry_path=resolved_registry_path,
            n_tasks=n_tasks,
        )

    @classmethod
    def _build_job_config(cls, cfg: Mapping[str, object], *, run_id: str, repo_root: Path):
        from harbor.models.job.config import AgentConfig, EnvironmentConfig, JobConfig, VerifierConfig  # noqa: PLC0415

        environment_env: dict[str, str] = {}
        if user_llm := cfg.get("user_llm"):
            environment_env["TAU2_USER_MODEL"] = str(user_llm)
        for config_key, env_key in (
            ("user_reasoning_effort", "TAU2_USER_REASONING_EFFORT"),
            ("user_temperature", "TAU2_USER_TEMPERATURE"),
            ("user_llm_args_json", "TAU2_USER_LLM_ARGS_JSON"),
        ):
            if (value := cfg.get(config_key)) is not None:
                environment_env[env_key] = str(value)

        verifier_env: dict[str, str] = {}
        if verifier_llm := cfg.get("verifier_llm"):
            verifier_env["TAU2_NL_ASSERTIONS_MODEL"] = str(verifier_llm)
        timeout = float(str(cfg["timeout"])) if cfg.get("timeout") is not None else None
        return JobConfig(
            job_name=run_id,
            jobs_dir=cls._repo_path(cfg.get("jobs_dir", "testbed/tmp/jobs"), repo_root=repo_root),
            n_attempts=int(str(cfg.get("num_trials", 1))),
            datasets=[cls._build_dataset_config(cfg, repo_root=repo_root)],
            agents=[
                AgentConfig(
                    import_path=str(cfg.get("agent_import_path", "harbor_wrapper:WrappedAgent")),
                    model_name=str(cfg["agent_llm"]) if cfg.get("agent_llm") else None,
                    override_timeout_sec=timeout,
                )
            ],
            environment=EnvironmentConfig(env=environment_env),
            verifier=VerifierConfig(env=verifier_env),
            n_concurrent_trials=int(str(cfg.get("max_concurrency", 2))),
        )

    def check(self) -> list[str]:
        cfg = self.subject.config
        missing: list[str] = [f"config key '{key}'" for key in ("base_url", "workspace") if not cfg.get(key)]
        if not (agent_dir_value := cfg.get("agent_dir")):
            missing.append("config key 'agent_dir'")
        elif not self._repo_path(agent_dir_value, repo_root=REPO_ROOT).is_dir():
            missing.append(f"agent_dir '{self._repo_path(agent_dir_value, repo_root=REPO_ROOT)}' is not a directory")
        if not os.environ.get("INFERENCE_API_KEY"):
            missing.append("env INFERENCE_API_KEY")
        try:
            self._build_job_config(cfg, run_id="preflight", repo_root=REPO_ROOT)
        except ModuleNotFoundError:
            missing.append("Harbor is not installed; sync the experimentalist dependency group")
        except (TypeError, ValueError) as exc:
            missing.append(str(exc))
        return missing

    async def produce(self) -> dict[str, object]:
        cfg = self.subject.config
        if missing := self.check():
            raise SystemExit(f"harbor testbed '{self.subject.name}' is missing: " + "; ".join(missing))

        agent_dir = self._repo_path(cfg["agent_dir"], repo_root=REPO_ROOT)
        base_url = str(cfg["base_url"])
        workspace = str(cfg["workspace"])
        agent_name = str(cfg.get("agent_name", "agent-0"))
        run_id = mint_agent_id(workspace)
        created_at = datetime.now(timezone.utc).isoformat()
        raw_dataset = str(cfg.get("dataset_ref") or cfg.get("dataset_id") or Path(str(cfg["dataset"])).name)
        dataset_name, separator, ref_version = raw_dataset.rpartition("@")
        if not separator:
            dataset_name = raw_dataset
        dataset_version = str(cfg.get("dataset_version") or ref_version or "unversioned")

        ensure_workspace(base_url, workspace)
        group_id = ensure_experiment_group(base_url, workspace, workspace)
        create_experiment(
            base_url,
            workspace,
            name=run_id,
            experiment_group_id=group_id,
            dataset_name=dataset_name,
            dataset_version=dataset_version,
            metadata={"agent": agent_name, "model": str(cfg.get("agent_llm", "")), "producer": "harbor"},
        )

        agent_dir_string = str(agent_dir)
        if agent_dir_string not in sys.path:
            sys.path.insert(0, agent_dir_string)

        from harbor.job import Job  # noqa: PLC0415

        job_config = self._build_job_config(cfg, run_id=run_id, repo_root=REPO_ROOT)
        job = await Job.create(job_config)
        await job.run()

        trace_dir = job_config.jobs_dir / run_id
        sent, errors, session_ids = _export_harbor_trace_files(
            base_url,
            workspace,
            trace_dir,
            agent_name,
            evaluation_id=run_id,
            agent_version=str(cfg.get("agent_version", "")) or None,
        )
        if sent == 0:
            raise SystemExit(f"harbor testbed '{self.subject.name}': no OTLP traces found under {trace_dir}")
        if errors:
            print(f"warning: {errors} Harbor trace upload error(s) for '{self.subject.name}'.", file=sys.stderr)
        if len(session_ids) < 3:
            print(f"warning: only {len(session_ids)} session(s) ingested; the analyst needs 3+.", file=sys.stderr)
        if session_ids:
            visible = poll_visible(base_url, workspace, session_ids)
            if len(visible) < len(session_ids):
                print(
                    f"warning: only {len(visible)}/{len(session_ids)} session(s) visible in Intake.",
                    file=sys.stderr,
                )

        return {
            "agent": agent_name,
            "workspace": workspace,
            "base_url": base_url,
            "run_id": run_id,
            "experiment_id": run_id,
            "experiment_group": workspace,
            "dataset_name": dataset_name,
            "dataset_version": dataset_version,
            "created_at": created_at,
        }

    async def analyze(
        self,
        *,
        record: dict[str, object] | None,
        since: datetime | None,
        verbose: bool,
        out_path: Path,
    ) -> str:
        if record is None:
            raise SystemExit(
                f"no recorded run for '{self.subject.name}' — run "
                f"`uv run python -m testbed run {self.subject.name}` first"
            )
        return await run_analyst(
            agent=str(record["agent"]),
            agent_spec=None,
            workspace=str(record["workspace"]),
            base_url=str(record["base_url"]),
            client=make_client(str(record["base_url"])),
            insights_output=str(out_path),
            verbose=verbose,
            since=since,
            evaluation_id=str(record["experiment_id"]),
        )


_ADAPTERS: dict[str, type[IntakeAdapter] | type[BenchmarkAdapter] | type[HarborAdapter]] = {
    "intake": IntakeAdapter,
    "benchmark": BenchmarkAdapter,
    "harbor": HarborAdapter,
}


def build_adapter(subject: Subject) -> TestbedAdapter:
    """Construct the adapter for a subject's ``type``."""
    cls = _ADAPTERS.get(subject.type)
    if cls is None:
        raise SystemExit(
            f"testbed '{subject.name}' has unknown type '{subject.type}'. Known types: {', '.join(sorted(_ADAPTERS))}."
        )
    return cls(subject)
