# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Broker + Gym host lifecycle (Ray-free). Returns raw Gym host results."""

from __future__ import annotations

import asyncio
import atexit
import concurrent.futures
import json
import logging
import os
import signal
import urllib.error
import urllib.request
from collections.abc import Callable, Coroutine, Mapping
from types import FrameType
from typing import Any, TypeVar
from urllib.parse import urlparse

from sandboxed_gym.broker import EpisodeBrokerServer
from sandboxed_gym.config import BrokerEndpoint
from sandboxed_gym.host.models import (
    GymHostEgressRule,
    GymHostHandle,
    GymHostSpec,
    GymHostVolumeMount,
    build_bootstrap_env,
)
from sandboxed_gym.host.provider import SandboxedGymHostProvider, get_host_provider
from sandboxed_gym.runtime.gym_host_runtime import GYM_GLOBAL_CONFIG_ENV_KEY
from sandboxed_gym.serve_config import (
    SandboxedGymServeConfig,
    SandboxedGymSessionDescriptor,
)

LOGGER = logging.getLogger(__name__)

T = TypeVar("T")


def _run_coro_sync(coro: Coroutine[Any, Any, T]) -> T:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        # `Future.result()` is typed with its own TypeVar, which does not unify with T here.
        return pool.submit(asyncio.run, coro).result()  # ty: ignore[invalid-return-type]


#: Signals a container runtime sends before SIGKILL. SIGKILL and node loss cannot be caught and
#: stay the sandbox ttl_s's problem.
TERMINATION_SIGNALS = (signal.SIGTERM, signal.SIGINT)


def install_termination_cleanup(shutdown: Callable[[], None]) -> None:
    """Run ``shutdown`` when this process exits without it having been called.

    A process that owns a sandbox is the only thing that can name it. Ray tears an actor's worker
    down without running user teardown, so a job that is cancelled, evicted or preempted otherwise
    leaves its sandbox running until ttl_s. ``shutdown`` must tolerate being called twice: an
    ordinary exit runs it directly and then again from ``atexit``.

    For a process the caller owns -- an actor, a CLI. Not for a library embedded in someone else's
    host, whose signal handling is not ours to replace.
    """
    atexit.register(shutdown)

    def _terminate(signum: int, _frame: FrameType | None) -> None:
        # Restored before the cleanup runs, not after: a second signal arriving mid-shutdown then
        # takes the default action and terminates, rather than re-entering this handler on top of
        # an in-flight destroy. Two SIGTERMs mean the sender wants the process gone.
        signal.signal(signum, signal.SIG_DFL)
        LOGGER.warning("received signal %s; destroying sandboxed Gym host before exit", signum)
        try:
            shutdown()
        finally:
            # Re-raised even if cleanup failed, so the exit status still reports the signal --
            # swallowing it would make a cancelled job look like a clean stop.
            os.kill(os.getpid(), signum)

    for signum in TERMINATION_SIGNALS:
        try:
            signal.signal(signum, _terminate)
        except ValueError:
            # Only the main thread may install handlers, and Ray does not promise to call an
            # actor method there. atexit still covers the ordinary exit.
            LOGGER.debug("cannot install a %s handler off the main thread", signum)


def apply_sandbox_runtime_defaults(global_config: dict[str, Any]) -> dict[str, Any]:
    """Inject sandbox-local infra defaults only (not RL training knobs)."""
    from sandboxed_gym.host.entrypoint import gym_uv_cache_dir, gym_uv_venv_dir
    from sandboxed_gym.netutil import (
        DEFAULT_BROKER_PORT_RANGE_HIGH,
        DEFAULT_BROKER_PORT_RANGE_LOW,
    )

    cfg = dict(global_config)
    cfg.pop("ray_head_node_address", None)
    cfg.setdefault("default_host", "127.0.0.1")
    cfg.setdefault("port_range_low", DEFAULT_BROKER_PORT_RANGE_LOW)
    cfg.setdefault("port_range_high", DEFAULT_BROKER_PORT_RANGE_HIGH)
    cfg.setdefault("global_aiohttp_connector_limit_per_host", 16_384)
    cfg.setdefault("global_aiohttp_connector_limit", 65_536)
    cfg.setdefault("uv_cache_dir", gym_uv_cache_dir())
    cfg.setdefault("uv_venv_dir", gym_uv_venv_dir())
    return cfg


def collect_gym_host_egress_allows(
    *,
    configured: list[GymHostEgressRule] | tuple[GymHostEgressRule, ...],
    broker_host: str,
    broker_port: int,
    base_urls: list[str] | tuple[str, ...],
    extra: tuple[GymHostEgressRule, ...] = (),
) -> tuple[GymHostEgressRule, ...]:
    rules = list(configured)
    rules.extend(extra)
    rules.append(GymHostEgressRule(host=broker_host, port=broker_port))
    for base_url in base_urls:
        if not base_url:
            continue
        parsed = urlparse(str(base_url))
        if not parsed.hostname:
            continue
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        rules.append(GymHostEgressRule(host=parsed.hostname, port=port))
    deduped: dict[tuple[str, int], GymHostEgressRule] = {}
    for rule in rules:
        deduped.setdefault((rule.host, rule.port), rule)
    return tuple(deduped.values())


def build_gym_host_spec(
    cfg: SandboxedGymServeConfig,
    broker: BrokerEndpoint,
) -> GymHostSpec:
    sandbox = cfg.sandbox
    broker_host = broker.host
    parsed = urlparse(broker.url)
    if parsed.hostname and not parsed.hostname.replace(".", "").isdigit():
        broker_host = parsed.hostname

    dataset_path = None
    dataset_mount = None
    if sandbox.dataset_pvc_claim:
        dataset_path = sandbox.dataset_mount_path
        dataset_mount = GymHostVolumeMount(
            pvc_claim=sandbox.dataset_pvc_claim,
            sub_path=sandbox.dataset_sub_path,
            mount_path=sandbox.dataset_mount_path,
            read_only=True,
        )

    gym_global = apply_sandbox_runtime_defaults(cfg.gym_global_config)
    bootstrap_env = build_bootstrap_env(
        cfg.job_id,
        cfg.environment_path or sandbox.env_mount_path,
        sandbox.work_mount_path,
        broker.url,
        broker.token,
        sandbox.max_request_bytes,
        sandbox.max_response_bytes,
        dataset_path=dataset_path,
        # The caller's own variables first, so nothing it passes can displace the broker endpoint
        # or the mount paths the runtime needs to come up.
        extra={**cfg.host_env, GYM_GLOBAL_CONFIG_ENV_KEY: json.dumps(gym_global, sort_keys=True)},
    )

    egress_allow = collect_gym_host_egress_allows(
        configured=sandbox.network_policy.egress_allow,
        broker_host=broker_host,
        broker_port=broker.port,
        base_urls=list(cfg.policy_base_urls),
        extra=cfg.egress_extra,
    )

    return GymHostSpec(
        job_id=cfg.job_id,
        runtime_image=sandbox.image,
        environment_mount=GymHostVolumeMount(
            pvc_claim=sandbox.environment_pvc_claim,
            sub_path=sandbox.environment_sub_path,
            mount_path=sandbox.env_mount_path,
            read_only=True,
        ),
        dataset_mount=dataset_mount,
        workspace_mount=GymHostVolumeMount(
            pvc_claim=sandbox.workspace_pvc_claim,
            sub_path=sandbox.workspace_sub_path,
            mount_path=sandbox.work_mount_path,
            read_only=False,
        ),
        egress_allow=egress_allow,
        bootstrap_env=bootstrap_env,
        max_request_bytes=sandbox.max_request_bytes,
        max_response_bytes=sandbox.max_response_bytes,
        ttl_s=sandbox.ttl_s,
        ready_timeout_s=sandbox.ready_timeout_s,
        resources=sandbox.resources,
        runtime_http_port=sandbox.runtime_http_port,
        allow_internet=sandbox.allow_internet,
        public_dns_allow=sandbox.network_policy.public_dns_allow,
        resolver_addresses=sandbox.network_policy.resolver_addresses,
        # No entrypoint configured means the runtime image starts itself through its own CMD. The
        # old default called `default_gym_host_entrypoint()`, which resolves `gym_host.sh` and
        # `gym_host_runtime.py` from *this* process's installed package -- a path inside the
        # orchestrator's container, handed to a host running a different image. It only ever
        # resolved because the two images happened to share a layout.
        entrypoint=(tuple(sandbox.entrypoint) if sandbox.entrypoint else None),
    )


class SandboxedGymSession:
    """Live broker + host session. ``run_rollouts`` returns raw Gym host results."""

    def __init__(
        self,
        *,
        cfg: SandboxedGymServeConfig,
        broker_server: EpisodeBrokerServer,
        broker: BrokerEndpoint,
        host_provider: SandboxedGymHostProvider,
        host: GymHostHandle,
        orchestrator_url: str | None = None,
    ) -> None:
        self.cfg = cfg
        self._broker_server = broker_server
        self.broker = broker
        self._host_provider = host_provider
        self.host = host
        self.orchestrator_url = orchestrator_url
        self._rollout_timeout_s = float(cfg.sandbox.rollout_timeout_s)
        self._max_request_bytes = cfg.sandbox.max_request_bytes
        self._max_response_bytes = cfg.sandbox.max_response_bytes

    def descriptor(
        self, *, mode: str | None = None, orchestrator_url: str | None = None
    ) -> SandboxedGymSessionDescriptor:
        url = orchestrator_url if orchestrator_url is not None else self.orchestrator_url
        serve_mode = mode or self.cfg.serve_mode
        return SandboxedGymSessionDescriptor(
            job_id=self.cfg.job_id,
            mode=serve_mode,  # ty: ignore[invalid-argument-type]
            orchestrator_url=url,
            health_url=self.host.health_url,
            rollout_url=(f"{url.rstrip('/')}/rollouts/run" if url else self.host.rollout_url),
            headers=dict(self.host.headers),
            broker_url=self.broker.url,
            broker_token=self.broker.token,
            rollout_auth_token=self.cfg.rollout_auth_token,
        )

    def run_rollouts(self, examples: list[dict[str, Any]]) -> list[Any]:
        if not examples:
            raise ValueError("rollout batch must not be empty")
        body = json.dumps({"examples": examples}).encode("utf-8")
        if len(body) > self._max_request_bytes:
            raise ValueError(f"rollout request exceeds max_request_bytes ({len(body)} > {self._max_request_bytes})")
        request = urllib.request.Request(
            self.host.rollout_url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                **self.host.headers,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self._rollout_timeout_s) as response:
                payload = response.read()
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"rollout POST failed with HTTP {exc.code}: {error_body}") from exc
        if len(payload) > self._max_response_bytes:
            raise ValueError(
                f"rollout response exceeds max_response_bytes ({len(payload)} > {self._max_response_bytes})"
            )
        decoded = json.loads(payload.decode("utf-8"))
        if isinstance(decoded, dict) and "error" in decoded:
            raise RuntimeError(f"rollout runtime error: {decoded['error']}")
        if isinstance(decoded, dict) and "results" in decoded:
            return list(decoded["results"])
        if isinstance(decoded, list):
            return decoded
        raise RuntimeError(f"unexpected rollout response shape: {type(decoded)}")

    def shutdown(self) -> None:
        try:
            _run_coro_sync(self._host_provider.destroy_host(self.host))
        except Exception:
            LOGGER.exception("Failed to destroy sandboxed Gym host")
        try:
            self._broker_server.shutdown()
        except Exception:
            LOGGER.exception("Failed to shut down episode broker")


class SandboxedGymOrchestrator:
    """Start episode broker, provision Gym host, return a live session."""

    def start(self, cfg: SandboxedGymServeConfig | Mapping[str, Any]) -> SandboxedGymSession:
        if not isinstance(cfg, SandboxedGymServeConfig):
            cfg = SandboxedGymServeConfig.model_validate(cfg)

        broker_cfg = cfg.broker_config()
        broker_server = EpisodeBrokerServer(broker_cfg)
        broker = broker_server.start()

        host_spec = build_gym_host_spec(cfg, broker)
        host_provider = get_host_provider(cfg.host_provider, cfg.sandbox.host_provider_options)
        host = _run_coro_sync(host_provider.create_host(host_spec))
        try:
            _run_coro_sync(host_provider.wait_ready(host, cfg.sandbox.ready_timeout_s))
        except Exception:
            _run_coro_sync(host_provider.destroy_host(host))
            broker_server.shutdown()
            raise

        return SandboxedGymSession(
            cfg=cfg,
            broker_server=broker_server,
            broker=broker,
            host_provider=host_provider,
            host=host,
        )
