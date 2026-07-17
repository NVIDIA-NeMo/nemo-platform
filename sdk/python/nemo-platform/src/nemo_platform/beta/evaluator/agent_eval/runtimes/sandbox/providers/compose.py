# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Docker Compose implementation of the evaluator SDK sandbox protocol."""

# ruff: noqa: I001 - the vendored SDK mirror uses different import-order settings.

from __future__ import annotations

import asyncio
import contextlib
import errno
import json
import logging
import os
import posixpath
import re
import signal
import socket
import tempfile
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any, Literal

from nemo_platform.beta.evaluator.agent_eval.runtimes.sandbox.base import (
    SANDBOX_RUNTIME_RETURN_CODE,
    SandboxCreateError,
    SandboxExecResult,
    SandboxHandle,
    SandboxSpec,
    SandboxStatus,
)

logger = logging.getLogger(__name__)

_CLEANUP_ATTEMPTS = 3
_CLEANUP_RETRY_DELAY_SECONDS = 0.5
_SECRET_ENV_FRAGMENT = re.compile(r"(?:TOKEN|KEY|PASSWORD|SECRET)", re.IGNORECASE)
_INLINE_SECRET = re.compile(
    r"""(?ix)
    (?P<prefix>
        ["']?(?:authorization|x-api-key|api[_-]?key|token|password)["']?
        \s*[:=]\s*
    )
    (?:
        (?P<quote>["'])(?P<quoted>.*?)(?P=quote)
        |
        (?P<unquoted>[^\r\n,}\]]+)
    )
    """
)


class ComposeCleanupError(RuntimeError):
    """The managed Compose project could not be completely stopped."""


@dataclass(frozen=True)
class ComposeServiceTopology:
    """Expected active services for one Compose project.

    The rendered active service set must match these two groups exactly. Long-running
    services must be running and healthy when a health check is configured; one-shot
    services must have exited successfully.

    Attributes:
        target_service: Long-running service used for sandbox command execution and file transfer.
        long_running_services: Services that must remain running after startup.
        one_shot_services: Services that must finish successfully during startup.

    Example:
        ``ComposeServiceTopology("agent", frozenset({"agent", "redis"}), frozenset({"init"}))``
        targets ``agent``, requires ``agent`` and ``redis`` to stay up, and requires ``init`` to exit zero.
    """

    target_service: str
    long_running_services: frozenset[str]
    one_shot_services: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        """Normalize service collections and validate their lifecycle roles.

        Raises:
            ValueError: If a service has two roles or the target is not long-running.
        """
        object.__setattr__(self, "long_running_services", frozenset(self.long_running_services))
        object.__setattr__(self, "one_shot_services", frozenset(self.one_shot_services))
        overlap = self.long_running_services & self.one_shot_services
        if overlap:
            raise ValueError(f"Compose services cannot be both long-running and one-shot: {sorted(overlap)}")
        if self.target_service not in self.long_running_services:
            raise ValueError("target_service must be one of long_running_services")

    @property
    def active_services(self) -> frozenset[str]:
        """Return every service expected in the rendered Compose project."""
        return self.long_running_services | self.one_shot_services


@dataclass
class _ComposeProjectLock:
    """Exclusive POSIX lock lease for one managed Compose project.

    Attributes:
        path: Host lock-file path.
        fd: Open file descriptor holding the lock, or ``None`` after release.
    """

    path: Path
    fd: int | None = None

    @classmethod
    def acquire(cls, path: Path) -> _ComposeProjectLock:
        """Acquire and return a nonblocking project lock lease.

        Args:
            path: Host lock-file path to create and lock.

        Returns:
            Lease whose open descriptor holds the exclusive lock.

        Raises:
            SandboxCreateError: If POSIX locking is unavailable or another process holds the lock.
            OSError: If the lock file cannot be created or locked for another reason.
        """
        try:
            import fcntl
        except ImportError as exc:
            raise SandboxCreateError("DockerComposeSandboxProvider requires POSIX fcntl file locking") from exc

        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(fd)
            if exc.errno in {errno.EACCES, errno.EAGAIN}:
                raise SandboxCreateError(f"Another Compose sandbox holds {path}") from exc
            raise
        return cls(path=path, fd=fd)

    def release(self) -> None:
        """Release and close the lease when it is still held."""
        if self.fd is None:
            return
        fd = self.fd
        try:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            try:
                os.close(fd)
            finally:
                self.fd = None


@dataclass
class _ComposeSession:
    """State and ownership resources for one provider lifecycle.

    Attributes:
        session_id: Unique identifier used by the public sandbox handle.
        environment: Environment used for all commands in this lifecycle.
        lock: Exclusive project lock held until cleanup completes.
        owns_project: Whether startup reached the point requiring Compose teardown.
        target_identity: Cached ``UID:GID`` of the target service runtime user.
    """

    session_id: str
    environment: dict[str, str]
    lock: _ComposeProjectLock
    owns_project: bool = False
    target_identity: str | None = None


@dataclass(frozen=True)
class ComposeCommandResult:
    """Result returned for a Docker or Compose command.

    Attributes:
        argv: Exact argument vector passed to the subprocess.
        return_code: Process return code, or the sandbox runtime code after a timeout.
        stdout: Captured standard output.
        stderr: Captured standard error.
        timed_out: Whether the provider terminated the command at its deadline.
    """

    argv: tuple[str, ...]
    return_code: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        """Return whether the command completed successfully before its deadline."""
        return self.return_code == 0 and not self.timed_out


@dataclass(frozen=True)
class _ComposeCommandScope:
    """Current project settings needed to construct Docker CLI commands.

    Attributes:
        docker_bin: Docker CLI executable name or path.
        project_directory: Host working directory and Compose project directory.
        compose_files: Ordered Compose configuration files.
        project_name: Explicit Compose project name.
        profiles: Ordered enabled Compose profiles.
    """

    docker_bin: str
    project_directory: Path
    compose_files: tuple[Path, ...]
    project_name: str
    profiles: tuple[str, ...]


class _ComposeCli:
    """Command gateway for one dynamically configured Compose provider."""

    def __init__(self, scope: Callable[[], _ComposeCommandScope]) -> None:
        """Bind command execution to a provider command-scope factory.

        Args:
            scope: Zero-argument function returning the provider's current project settings.
        """
        self._scope = scope

    async def run_compose(
        self,
        args: Sequence[str],
        *,
        environment: Mapping[str, str],
        timeout: float,
        stdin: bytes | None = None,
        stream_output: IO[str] | None = None,
    ) -> ComposeCommandResult:
        """Run one project-scoped Docker Compose command.

        Args:
            args: Compose subcommand and arguments, excluding configured global options.
            environment: Complete subprocess environment.
            timeout: Command deadline in seconds.
            stdin: Optional bytes forwarded to standard input.
            stream_output: Optional text sink for line-buffered, redacted progress output.

        Returns:
            Captured command result with the fully rendered argument vector.
        """
        scope = self._scope()
        argv: tuple[str, ...] = (
            scope.docker_bin,
            "compose",
            "--ansi",
            "never",
            "--progress",
            "plain",
            "--project-directory",
            str(scope.project_directory),
            *(item for compose_file in scope.compose_files for item in ("--file", str(compose_file))),
            "--project-name",
            scope.project_name,
            *(item for profile in scope.profiles for item in ("--profile", profile)),
            *args,
        )
        return await _run_command(
            argv,
            cwd=scope.project_directory,
            environment=environment,
            timeout=timeout,
            stdin=stdin,
            stream_output=stream_output,
        )

    async def run_docker(
        self,
        args: Sequence[str],
        *,
        environment: Mapping[str, str],
        timeout: float,
    ) -> ComposeCommandResult:
        """Run one Docker CLI command outside the Compose subcommand.

        Args:
            args: Docker subcommand and arguments.
            environment: Complete subprocess environment.
            timeout: Command deadline in seconds.

        Returns:
            Captured command result.
        """
        scope = self._scope()
        return await _run_command(
            (scope.docker_bin, *args),
            cwd=scope.project_directory,
            environment=environment,
            timeout=timeout,
            stdin=None,
            stream_output=None,
        )

    async def retry_compose(
        self,
        args: Sequence[str],
        *,
        environment: Mapping[str, str],
        timeout: float,
    ) -> ComposeCommandResult:
        """Run a Compose operation with the cleanup retry policy.

        Args:
            args: Compose subcommand and arguments, excluding global project options.
            environment: Environment forwarded to Compose.
            timeout: Deadline applied independently to each attempt.

        Returns:
            First successful result or the final failed result after all attempts.
        """
        return await _retry_command(
            lambda: self.run_compose(
                args,
                environment=environment,
                timeout=timeout,
            )
        )

    @staticmethod
    def failure_message(
        prefix: str,
        result: ComposeCommandResult,
        environment: Mapping[str, str],
    ) -> str:
        """Build a redacted message from command output.

        Args:
            prefix: Human-readable operation description.
            result: Failed or timed-out command result.
            environment: Command environment used to identify secrets.

        Returns:
            Message containing the prefix, timeout state, and redacted output or return code.
        """
        captured = "\n".join(stream.strip() for stream in (result.stdout, result.stderr) if stream.strip())
        details = _redact(captured, environment)
        timeout = " (timed out)" if result.timed_out else ""
        return f"{prefix}{timeout}: {details or f'exit {result.return_code}'}"


@dataclass(frozen=True, order=True)
class _PublishedPort:
    """One rendered host-to-container port publication.

    Attributes:
        service: Compose service that declares the publication.
        host_ip: Host address on which Docker publishes the port.
        published: Published host port number.
        target: Container port number.
        protocol: Lowercase transport protocol such as ``tcp`` or ``udp``.
    """

    service: str
    host_ip: str
    published: int
    target: int
    protocol: str


PullPolicy = Literal["always", "missing", "never"]
ProgressCallback = Callable[[str], None]


class ComposeTeardownContext:
    """Constrained project operations available to a trusted teardown hook."""

    def __init__(self, provider: DockerComposeSandboxProvider, environment: Mapping[str, str]) -> None:
        """Bind teardown operations to one provider and its command environment.

        Args:
            provider: Provider that owns the Compose project being torn down.
            environment: Environment to forward to teardown commands.
        """
        self._provider = provider
        self._environment = environment

    async def service_is_running(self, service: str) -> bool:
        """Check whether a named service currently has a running container.

        Args:
            service: Compose service name to inspect.

        Returns:
            ``True`` when at least one matching service row is running.
        """
        return _service_is_running(await self._provider._compose_ps(self._environment), service)

    async def stop_service(self, service: str) -> ComposeCommandResult:
        """Gracefully stop a service, retrying transient command failures.

        Args:
            service: Compose service name to stop.

        Returns:
            Result of the final successful or exhausted stop attempt.
        """
        return await self._provider._cli.retry_compose(
            [
                "stop",
                "--timeout",
                str(max(1, int(self._provider.shutdown_timeout_seconds))),
                service,
            ],
            environment=self._environment,
            timeout=self._provider.shutdown_timeout_seconds + 10,
        )

    async def kill_service(self, service: str) -> ComposeCommandResult:
        """Force-stop a service, retrying transient command failures.

        Args:
            service: Compose service name to kill.

        Returns:
            Result of the final successful or exhausted kill attempt.
        """
        return await self._provider._cli.retry_compose(
            ["kill", service],
            environment=self._environment,
            timeout=self._provider.command_timeout_seconds,
        )

    async def exec_service(
        self,
        service: str,
        command: Sequence[str],
        *,
        timeout_seconds: float | None = None,
    ) -> ComposeCommandResult:
        """Execute an argument-vector command in a running service.

        Args:
            service: Compose service name in which to execute the command.
            command: Command and arguments passed directly to ``docker compose exec``.
            timeout_seconds: Optional command deadline; defaults to the provider command timeout.

        Returns:
            Captured command result, including timeout state.

        Example:
            ``await context.exec_service("redis", ("redis-cli", "PING"))`` executes without shell parsing.
        """
        return await self._provider._cli.run_compose(
            ["exec", "--no-tty", service, *command],
            environment=self._environment,
            timeout=timeout_seconds or self._provider.command_timeout_seconds,
        )

    def failure_message(self, prefix: str, result: ComposeCommandResult) -> str:
        """Format a redacted teardown failure message.

        Args:
            prefix: Human-readable description of the failed operation.
            result: Command result whose captured output should be summarized.

        Returns:
            Redacted message containing the prefix, timeout state, and command output.
        """
        return self._provider._cli.failure_message(prefix, result, self._environment)


TeardownHook = Callable[[ComposeTeardownContext], Awaitable[None]]


class DockerComposeSandboxProvider:
    """Own one exclusive Docker Compose project for a sandbox lifecycle."""

    name = "docker-compose"

    def __init__(
        self,
        *,
        compose_files: Sequence[str | Path],
        service_topology: ComposeServiceTopology,
        project_directory: str | Path | None = None,
        project_name: str | None = None,
        profiles: Sequence[str] = (),
        build: bool = False,
        pull_policy: PullPolicy = "missing",
        startup_timeout_seconds: float = 600,
        command_timeout_seconds: float = 60,
        shutdown_timeout_seconds: float = 30,
        lock_path: str | Path | None = None,
        diagnostics_dir: str | Path | None = None,
        environment_defaults: Mapping[str, str] | None = None,
        port_override_hints: Mapping[str, str] | None = None,
        teardown_hook: TeardownHook | None = None,
        remove_project_volumes: bool = False,
        progress_callback: ProgressCallback | None = None,
        docker_bin: str = "docker",
    ) -> None:
        """Configure one reusable owner for a caller-described Compose project.

        Args:
            compose_files: Ordered Compose files; later files override earlier files.
            service_topology: Exact active services and their expected lifecycle roles.
            project_directory: Base directory for relative Compose paths; defaults to the first file's parent.
            project_name: Compose project name; a unique evaluator name is generated when omitted.
            profiles: Compose profiles to enable, with duplicate names removed in first-seen order.
            build: Whether ``compose up`` may build source images.
            pull_policy: Image pull behavior passed to ``compose up``.
            startup_timeout_seconds: Maximum time allowed for project startup.
            command_timeout_seconds: Default deadline for Compose and Docker commands.
            shutdown_timeout_seconds: Grace period supplied to service stop and project shutdown.
            lock_path: Optional cross-process ownership lock file.
            diagnostics_dir: Optional directory for startup progress, service state, and logs.
            environment_defaults: Lowest-precedence environment values for Compose interpolation.
            port_override_hints: Service-specific configuration hints shown for occupied host ports.
            teardown_hook: Trusted project-specific cleanup run before ``compose down``.
            remove_project_volumes: Whether shutdown removes and verifies project volumes.
            progress_callback: Optional receiver for lifecycle progress messages.
            docker_bin: Docker CLI executable name or path.

        Raises:
            ValueError: If Compose files are empty, the project name is invalid, or the pull policy is unsupported.

        Example:
            ``DockerComposeSandboxProvider(compose_files=("compose.yaml",), service_topology=topology)``
            starts existing images by default; pass ``build=True`` to build provisioned source.
        """
        if isinstance(compose_files, (str, Path)) or not compose_files:
            raise ValueError("compose_files must contain at least one path")
        if pull_policy not in {"always", "missing", "never"}:
            raise ValueError("pull_policy must be one of: always, missing, never")
        self.compose_files = tuple(Path(path).expanduser().resolve() for path in compose_files)
        self.project_directory = (
            Path(project_directory).expanduser().resolve()
            if project_directory is not None
            else self.compose_files[0].parent
        )
        self.project_name = project_name or f"nemo-eval-{uuid.uuid4().hex[:12]}"
        if re.fullmatch(r"[a-z0-9][a-z0-9_-]*", self.project_name) is None:
            raise ValueError(
                "project_name must start with a lowercase letter or digit and contain only "
                "lowercase letters, digits, hyphens, or underscores"
            )
        self.service_topology = service_topology
        self.target_service = service_topology.target_service
        self.profiles = tuple(dict.fromkeys(profiles))
        self.build = build
        self.pull_policy: PullPolicy = pull_policy
        self.startup_timeout_seconds = float(startup_timeout_seconds)
        self.command_timeout_seconds = float(command_timeout_seconds)
        self.shutdown_timeout_seconds = float(shutdown_timeout_seconds)
        self.lock_path = (
            Path(lock_path)
            if lock_path is not None
            else Path(tempfile.gettempdir()) / (f"nemo-eval-compose-{self.project_name}.lock")
        )
        self.environment_defaults = dict(environment_defaults or {})
        self.port_override_hints = dict(port_override_hints or {})
        self.teardown_hook = teardown_hook
        self.remove_project_volumes = remove_project_volumes
        self.progress_callback = progress_callback
        self.docker_bin = docker_bin
        self.diagnostics_dir = Path(diagnostics_dir).expanduser().resolve() if diagnostics_dir is not None else None
        self._session: _ComposeSession | None = None
        self._closed = False
        self._cli = _ComposeCli(self._command_scope)

    async def create(self, spec: SandboxSpec) -> SandboxHandle:
        """Validate, start, and claim exclusive ownership of the Compose project.

        Args:
            spec: Sandbox request. Its environment overrides host and provider defaults;
                provider options are not accepted by this provider.

        Returns:
            Handle targeting the configured long-running service.

        Raises:
            SandboxCreateError: If validation, locking, startup, readiness, or cleanup fails.
            asyncio.CancelledError: If the caller cancels creation after cleanup finishes.
        """
        if self._closed:
            raise SandboxCreateError("DockerComposeSandboxProvider is closed")
        if self._session is not None:
            raise SandboxCreateError("DockerComposeSandboxProvider already owns a stack")
        if spec.provider_options:
            raise SandboxCreateError(
                "DockerComposeSandboxProvider does not accept SandboxSpec.provider_options; "
                "configure the provider through its constructor"
            )
        missing_files = [path for path in self.compose_files if not path.is_file()]
        if missing_files:
            raise SandboxCreateError(f"Compose files do not exist: {missing_files}")
        if not self.project_directory.is_dir():
            raise SandboxCreateError(f"Compose project directory does not exist: {self.project_directory}")

        environment = {**self.environment_defaults, **os.environ, **spec.env}
        for key, value in self.environment_defaults.items():
            if not environment.get(key):
                environment[key] = value
        session = _ComposeSession(
            session_id=f"{self.project_name}:{self.target_service}:{uuid.uuid4().hex}",
            environment=environment,
            lock=_ComposeProjectLock.acquire(self.lock_path),
        )
        self._session = session
        try:
            await self._preflight(environment)
            session.owns_project = True
            up_args = [
                "up",
                "--detach",
                "--wait",
                "--wait-timeout",
                str(max(1, int(self.startup_timeout_seconds))),
                "--build" if self.build else "--no-build",
                "--pull",
                self.pull_policy,
            ]
            build_mode = "build enabled" if self.build else "reusing existing images"
            self._progress(f"Starting managed Compose project {self.project_name!r} ({build_mode})...")
            progress_log_path: Path | None = None
            if self.diagnostics_dir is not None:
                self.diagnostics_dir.mkdir(parents=True, exist_ok=True)
                progress_log_path = self.diagnostics_dir / "compose-up.log"
                self._progress(f"Compose startup log: {progress_log_path.as_uri()}")
            startup_started_at = time.monotonic()
            with contextlib.ExitStack() as stack:
                stream_output = (
                    stack.enter_context(progress_log_path.open("w", encoding="utf-8"))
                    if progress_log_path is not None
                    else None
                )
                result = await self._cli.run_compose(
                    up_args,
                    environment=environment,
                    timeout=self.startup_timeout_seconds,
                    stream_output=stream_output,
                )
            if not result.ok:
                raise SandboxCreateError(self._cli.failure_message("Compose startup failed", result, environment))
            await self._assert_ready(environment)
            self._progress(
                f"Managed Compose project {self.project_name!r} ready in {time.monotonic() - startup_started_at:.1f}s."
            )
        except BaseException as exc:
            await self._capture_diagnostics(environment, reason="startup-failure")
            cleanup_error = await self._shielded_cleanup(session)
            if cleanup_error is not None:
                exc.add_note(f"Compose cleanup also failed: {cleanup_error}")
            if isinstance(exc, asyncio.CancelledError):
                raise
            if isinstance(exc, SandboxCreateError):
                raise
            raise SandboxCreateError(str(exc)) from exc

        handle = SandboxHandle(
            sandbox_id=session.session_id,
            provider_name=self.name,
            raw=session,
        )
        return handle

    async def exec(
        self,
        handle: SandboxHandle,
        command: str,
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_s: int | float | None = None,
        stdin: bytes | None = None,
    ) -> SandboxExecResult:
        """Run a shell command in the configured target service.

        Args:
            handle: Active handle returned by this provider.
            command: Shell command evaluated by ``sh -lc`` in the target service.
            cwd: Optional working directory inside the service container.
            env: Optional command-specific environment variables.
            timeout_s: Optional command deadline; defaults to ``command_timeout_seconds``.
            stdin: Optional bytes forwarded to the command's standard input.

        Returns:
            Sandbox result containing captured output, return code, and timeout classification.
        """
        state = self._state(handle)
        args = ["exec", "--no-tty"]
        if cwd is not None:
            args.extend(["--workdir", cwd])
        for key, value in (env or {}).items():
            args.extend(["--env", f"{key}={value}"])
        args.extend([self.target_service, "sh", "-lc", command])
        result = await self._cli.run_compose(
            args,
            environment=state.environment,
            timeout=float(timeout_s or self.command_timeout_seconds),
            stdin=stdin,
        )
        return SandboxExecResult(
            stdout=result.stdout,
            stderr=result.stderr,
            return_code=(SANDBOX_RUNTIME_RETURN_CODE if result.timed_out else result.return_code),
            error_type="timeout" if result.timed_out else None,
        )

    async def upload_file(
        self,
        handle: SandboxHandle,
        source_path: Path,
        target_path: str,
    ) -> None:
        """Upload one file and make it writable by the target service user.

        Args:
            handle: Active handle returned by this provider.
            source_path: Existing host file to copy.
            target_path: Destination file path inside the target service.

        Raises:
            RuntimeError: If target preparation, copying, or ownership repair fails.
        """
        await self._copy_to_service(handle, source_path, target_path, directory=False)

    async def upload_dir(
        self,
        handle: SandboxHandle,
        source_dir: Path,
        target_dir: str,
    ) -> None:
        """Upload directory contents into a service-owned target directory.

        Args:
            handle: Active handle returned by this provider.
            source_dir: Host directory whose contents should be copied.
            target_dir: Destination directory inside the target service. The provider
                recursively assigns this entire target tree to the service runtime user.

        Raises:
            RuntimeError: If target preparation, copying, or ownership repair fails.

        Example:
            Uploading ``/tmp/seed/.`` to ``/workspace`` produces ``/workspace/file`` rather
            than ``/workspace/seed/file``.
        """
        await self._copy_to_service(handle, source_dir, target_dir, directory=True)

    async def download_file(
        self,
        handle: SandboxHandle,
        source_path: str,
        target_path: Path,
    ) -> None:
        """Download one target-service file to the host.

        Args:
            handle: Active handle returned by this provider.
            source_path: File path inside the target service.
            target_path: Host destination file; missing parent directories are created.

        Raises:
            RuntimeError: If the Compose copy command fails.
        """
        await self._copy_from_service(handle, source_path, target_path, directory=False)

    async def download_dir(
        self,
        handle: SandboxHandle,
        source_dir: str,
        target_dir: Path,
    ) -> None:
        """Download directory contents into a host directory.

        Args:
            handle: Active handle returned by this provider.
            source_dir: Directory path inside the target service.
            target_dir: Host directory to create or merge copied contents into.

        Raises:
            RuntimeError: If the Compose copy command fails.
        """
        await self._copy_from_service(handle, source_dir, target_dir, directory=True)

    async def status(self, handle: SandboxHandle) -> SandboxStatus:
        """Return the aggregate lifecycle state of the managed project.

        Args:
            handle: Handle whose project state should be inspected.

        Returns:
            ``RUNNING`` when all configured service roles are ready, ``STOPPED`` when
            the project is absent, ``ERROR`` for an unhealthy topology, or ``UNKNOWN``
            when inspection fails.
        """
        state = self._state(handle)
        if not state.owns_project:
            return SandboxStatus.STOPPED
        try:
            rows = await self._compose_ps(state.environment)
        except Exception:  # noqa: BLE001 - status must collapse provider failures
            return SandboxStatus.UNKNOWN
        if not rows:
            return SandboxStatus.STOPPED
        return SandboxStatus.RUNNING if _services_ready(rows, self.service_topology) is None else SandboxStatus.ERROR

    async def close(self, handle: SandboxHandle) -> None:
        """Tear down the active project and release its ownership lock.

        Args:
            handle: Active handle returned by this provider.

        Raises:
            ComposeCleanupError: If the teardown hook, Compose shutdown, or resource verification fails.
            asyncio.CancelledError: If cancellation arrives while shielded cleanup is running.
        """
        session = self._state(handle)
        error = await self._shielded_cleanup(session)
        if error is not None:
            raise error

    async def aclose(self) -> None:
        """Close provider-scoped resources and tear down any active project.

        The method is idempotent and permanently prevents subsequent ``create`` calls.

        Raises:
            ComposeCleanupError: If the active project cannot be fully removed.
            asyncio.CancelledError: If cancellation arrives while shielded cleanup is running.
        """
        if self._closed:
            return
        self._closed = True
        session = self._session
        if session is None:
            return
        error = await self._shielded_cleanup(session)
        if error is not None:
            raise error

    def _command_scope(self) -> _ComposeCommandScope:
        """Snapshot the provider's current public command configuration.

        Returns:
            Immutable settings used to construct one Docker or Compose command.
        """
        return _ComposeCommandScope(
            docker_bin=self.docker_bin,
            project_directory=self.project_directory,
            compose_files=self.compose_files,
            project_name=self.project_name,
            profiles=self.profiles,
        )

    async def _preflight(self, environment: dict[str, str]) -> None:
        """Validate rendered topology, project ownership, and published host ports.

        Args:
            environment: Fully merged environment used for Compose interpolation.

        Raises:
            SandboxCreateError: If the configuration is invalid, the project already has
                containers, service roles differ, or a published host port is unavailable.
        """
        config, existing = await asyncio.gather(
            self._cli.run_compose(
                ["config", "--format", "json"],
                environment=environment,
                timeout=self.command_timeout_seconds,
            ),
            self._cli.run_compose(
                ["ps", "--all", "--quiet"],
                environment=environment,
                timeout=self.command_timeout_seconds,
            ),
        )
        if not config.ok:
            raise SandboxCreateError(self._cli.failure_message("Invalid Compose configuration", config, environment))
        if not existing.ok:
            raise SandboxCreateError(
                self._cli.failure_message("Could not inspect managed project", existing, environment)
            )
        if existing.stdout.strip():
            raise SandboxCreateError(
                f"Managed Compose project {self.project_name!r} already has containers; "
                "refusing to adopt or remove them"
            )
        try:
            services = _parse_compose_config(config.stdout)
            published_ports = _published_ports(services)
            active_services = frozenset(str(service) for service in services)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise SandboxCreateError(f"Could not inspect rendered Compose configuration: {exc}") from exc
        expected_services = self.service_topology.active_services
        if active_services != expected_services:
            missing = sorted(expected_services - active_services)
            unexpected = sorted(active_services - expected_services)
            raise SandboxCreateError(
                "Rendered Compose service topology does not match the provider configuration: "
                f"missing={missing}, unexpected={unexpected}"
            )
        conflicts = await _find_port_conflicts(published_ports)
        if conflicts:
            details = "\n".join(
                f"- {port.service}: {port.host_ip}:{port.published} -> "
                f"{port.target}/{port.protocol} "
                f"(override {self.port_override_hints.get(port.service, 'its Compose port mapping')})"
                for port in conflicts
            )
            raise SandboxCreateError(
                "Managed Compose host ports are unavailable:\n"
                f"{details}\n"
                "Stop the conflicting stack or override every occupied port."
            )

    async def _assert_ready(self, environment: Mapping[str, str]) -> None:
        """Require every configured service to satisfy its lifecycle role.

        Args:
            environment: Environment used to query Compose state.

        Raises:
            SandboxCreateError: If a long-running or one-shot service is not ready.
        """
        rows = await self._compose_ps(environment)
        problem = _services_ready(rows, self.service_topology)
        if problem is not None:
            raise SandboxCreateError(problem)

    async def _compose_ps(self, environment: Mapping[str, str]) -> list[dict[str, Any]]:
        """Return parsed state rows for all project services.

        Args:
            environment: Environment forwarded to ``docker compose ps``.

        Returns:
            Parsed JSON objects emitted for service containers.

        Raises:
            RuntimeError: If Compose cannot inspect the project.
            json.JSONDecodeError: If Compose emits malformed JSON.
        """
        result = await self._cli.run_compose(
            ["ps", "--all", "--format", "json"],
            environment=environment,
            timeout=self.command_timeout_seconds,
        )
        if not result.ok:
            raise RuntimeError(self._cli.failure_message("Could not inspect Compose services", result, environment))
        return _parse_json_rows(result.stdout)

    async def _cleanup_owned_project(
        self,
        session: _ComposeSession,
    ) -> ComposeCleanupError | None:
        """Run diagnostics, caller cleanup, Compose shutdown, and resource verification.

        Args:
            session: Active lifecycle whose project and lock must be released.

        Returns:
            Aggregated cleanup error when any teardown phase fails; otherwise ``None``.

        Raises:
            asyncio.CancelledError: If the cleanup task itself is cancelled.
        """
        if not session.owns_project:
            self._retire_session(session)
            return None

        environment = session.environment
        errors: list[str] = []
        try:
            await self._capture_diagnostics(environment, reason="shutdown")
            if self.teardown_hook is not None:
                await self.teardown_hook(ComposeTeardownContext(self, environment))
        except BaseException as exc:  # noqa: BLE001 - Compose down must still run
            if isinstance(exc, asyncio.CancelledError):
                raise
            errors.append(f"Compose teardown hook failed: {type(exc).__name__}: {exc}")
        finally:
            try:
                down_args = [
                    "down",
                    "--remove-orphans",
                    "--timeout",
                    str(max(1, int(self.shutdown_timeout_seconds))),
                ]
                if self.remove_project_volumes:
                    down_args.append("--volumes")
                down = await self._cli.retry_compose(
                    down_args,
                    environment=environment,
                    timeout=self.shutdown_timeout_seconds + self.command_timeout_seconds,
                )
                if not down.ok:
                    errors.append(self._cli.failure_message("Compose down failed", down, environment))
                errors.extend(await self._verify_project_destroyed(environment))
            except BaseException as exc:  # noqa: BLE001 - release ownership even if Docker fails
                if isinstance(exc, asyncio.CancelledError):
                    raise
                errors.append(f"Compose teardown failed: {type(exc).__name__}: {exc}")
            finally:
                self._retire_session(session)

        if errors:
            return ComposeCleanupError("; ".join(errors))
        return None

    async def _shielded_cleanup(
        self,
        session: _ComposeSession,
    ) -> ComposeCleanupError | None:
        """Finish project cleanup even when the calling task is cancelled.

        Args:
            session: Active lifecycle to clean up.

        Returns:
            Cleanup error when teardown completes with failures; otherwise ``None``.

        Raises:
            asyncio.CancelledError: Re-raised after cleanup completes when the caller was cancelled.
        """
        result, cancellation = await _run_shielded(self._cleanup_owned_project(session))
        if cancellation is not None:
            if result is not None:
                cancellation.add_note(f"Compose cleanup also failed: {result}")
            raise cancellation
        return result

    def _retire_session(self, session: _ComposeSession) -> None:
        """Release one lifecycle's ownership resources and clear it when active.

        Args:
            session: Lifecycle whose project ownership and lock should be released.
        """
        session.owns_project = False
        session.lock.release()
        if self._session is session:
            self._session = None

    async def _verify_project_destroyed(
        self,
        environment: Mapping[str, str],
    ) -> list[str]:
        """Check that managed Docker resources no longer exist.

        Args:
            environment: Environment forwarded to Docker inspection commands.

        Returns:
            Human-readable verification failures. Volumes are checked only when volume removal is enabled.
        """
        kinds = ["container", "network"]
        if self.remove_project_volumes:
            kinds.append("volume")

        errors: list[str] = []
        for kind in kinds:
            names, query_error = await self._managed_resource_names(kind, environment)
            if query_error is not None:
                errors.append(query_error)
            elif names:
                errors.append(f"Managed Compose {kind}s remain after teardown: {', '.join(names)}")
        return errors

    async def _managed_resource_names(
        self,
        kind: str,
        environment: Mapping[str, str],
    ) -> tuple[list[str], str | None]:
        """List Docker resources carrying this Compose project's label.

        Args:
            kind: Docker resource kind: ``container``, ``network``, or ``volume``.
            environment: Environment forwarded to the Docker CLI.

        Returns:
            Pair of resource names and an optional redacted inspection error.
        """
        args = [kind, "ls"]
        if kind == "container":
            args.append("--all")
        args.extend(
            [
                "--quiet",
                "--filter",
                f"label=com.docker.compose.project={self.project_name}",
            ]
        )
        result = await self._cli.run_docker(
            args,
            environment=environment,
            timeout=self.command_timeout_seconds,
        )
        if not result.ok:
            return [], self._cli.failure_message(
                f"Could not inspect managed {kind}s",
                result,
                environment,
            )
        return [line.strip() for line in result.stdout.splitlines() if line.strip()], None

    async def _run_target_root(
        self,
        command: Sequence[str],
        *,
        environment: Mapping[str, str],
    ) -> ComposeCommandResult:
        """Run a command as root in the configured target service.

        Args:
            command: Executable and arguments to append after the target service name.
            environment: Complete environment forwarded to Docker Compose.

        Returns:
            Captured result for the privileged Compose exec command.
        """
        return await self._cli.run_compose(
            ["exec", "--no-tty", "--user", "0", self.target_service, *command],
            environment=environment,
            timeout=self.command_timeout_seconds,
        )

    async def _copy_to_service(
        self,
        handle: SandboxHandle,
        source: Path,
        target: str,
        *,
        directory: bool,
    ) -> None:
        """Copy a host path into the target service and repair ownership.

        Args:
            handle: Active handle returned by this provider.
            source: Host file or directory to copy.
            target: Destination path inside the target service.
            directory: When ``True``, create the full target and copy only ``source`` contents;
                otherwise create only the file's parent and copy the file itself.

        Raises:
            RuntimeError: If target preparation, copying, or ownership repair fails.
            SandboxCreateError: If the target service runtime identity cannot be determined.

        Example:
            With ``directory=True``, source ``/tmp/work`` is passed as ``/tmp/work/.`` so
            Docker merges its contents directly into the prepared target directory.
        """
        state = self._state(handle)
        remote_directory = target if directory else posixpath.dirname(target)
        if remote_directory:
            prepared = await self._run_target_root(
                ["mkdir", "-p", "--", remote_directory],
                environment=state.environment,
            )
            if not prepared.ok:
                raise RuntimeError(
                    self._cli.failure_message(
                        "Compose upload target preparation failed",
                        prepared,
                        state.environment,
                    )
                )
        copy_source = f"{source}{os.sep}." if directory else str(source)
        result = await self._cli.run_compose(
            ["cp", copy_source, f"{self.target_service}:{target}"],
            environment=state.environment,
            timeout=self.command_timeout_seconds,
        )
        if not result.ok:
            raise RuntimeError(self._cli.failure_message("Compose upload failed", result, state.environment))
        if state.target_identity is None:
            state.target_identity = await self._target_identity(state.environment)
        ownership = await self._run_target_root(
            ["chown", "-R", state.target_identity, "--", target],
            environment=state.environment,
        )
        if not ownership.ok:
            raise RuntimeError(
                self._cli.failure_message("Compose upload ownership repair failed", ownership, state.environment)
            )

    async def _copy_from_service(
        self,
        handle: SandboxHandle,
        source: str,
        target: Path,
        *,
        directory: bool,
    ) -> None:
        """Copy a target-service path to a prepared host destination.

        Args:
            handle: Active handle returned by this provider.
            source: File or directory path inside the target service.
            target: Host destination path.
            directory: When ``True``, create the target directory and copy source contents;
                otherwise create only the target file's parent.

        Raises:
            RuntimeError: If the Compose copy command fails.
        """
        state = self._state(handle)
        if directory:
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
        copy_source = posixpath.join(source, ".") if directory else source
        result = await self._cli.run_compose(
            ["cp", f"{self.target_service}:{copy_source}", str(target)],
            environment=state.environment,
            timeout=self.command_timeout_seconds,
        )
        if not result.ok:
            raise RuntimeError(self._cli.failure_message("Compose download failed", result, state.environment))

    async def _capture_diagnostics(
        self,
        environment: Mapping[str, str],
        *,
        reason: str,
    ) -> None:
        """Best-effort write redacted project state and recent logs.

        Args:
            environment: Environment used for Compose commands and secret redaction.
            reason: Filename-safe lifecycle label such as ``startup-failure`` or ``shutdown``.

        Diagnostics failures are logged and never replace the lifecycle error being investigated.
        """
        if self.diagnostics_dir is None:
            return
        try:
            self.diagnostics_dir.mkdir(parents=True, exist_ok=True)
            ps_result, logs_result = await asyncio.gather(
                self._cli.run_compose(
                    ["ps", "--all"],
                    environment=environment,
                    timeout=self.command_timeout_seconds,
                ),
                self._cli.run_compose(
                    ["logs", "--no-color", "--tail", "200"],
                    environment=environment,
                    timeout=self.command_timeout_seconds,
                ),
            )
            ps_text = _redact(f"{ps_result.stdout}\n{ps_result.stderr}", environment)
            logs_text = _redact(f"{logs_result.stdout}\n{logs_result.stderr}", environment)
            (self.diagnostics_dir / f"compose-{reason}-ps.txt").write_text(
                ps_text,
                encoding="utf-8",
            )
            (self.diagnostics_dir / f"compose-{reason}-logs.txt").write_text(
                logs_text,
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001 - diagnostics must not mask lifecycle errors
            logger.exception("Could not capture Compose diagnostics")

    async def _target_identity(self, environment: Mapping[str, str]) -> str:
        """Read the runtime ``UID:GID`` of the target service user.

        Args:
            environment: Environment forwarded to the Compose exec command.

        Returns:
            Numeric identity formatted as ``UID:GID`` for ``chown``.

        Raises:
            SandboxCreateError: If the identity command fails or emits an unexpected value.
        """
        result = await self._cli.run_compose(
            [
                "exec",
                "--no-tty",
                self.target_service,
                "sh",
                "-lc",
                'printf "%s:%s" "$(id -u)" "$(id -g)"',
            ],
            environment=environment,
            timeout=self.command_timeout_seconds,
        )
        identity = result.stdout.strip()
        if not result.ok or not re.fullmatch(r"\d+:\d+", identity):
            raise SandboxCreateError(
                self._cli.failure_message("Could not determine target service identity", result, environment)
            )
        return identity

    def _state(self, handle: SandboxHandle) -> _ComposeSession:
        """Validate a handle and return its provider-private state.

        Args:
            handle: Sandbox handle supplied to a provider operation.

        Returns:
            Compose state stored on the handle.

        Raises:
            ValueError: If the handle belongs to another provider or is not the active stack.
        """
        if handle.provider_name != self.name or not isinstance(handle.raw, _ComposeSession):
            raise ValueError("Sandbox handle does not belong to this Compose provider")
        if self._session is not handle.raw or handle.sandbox_id != handle.raw.session_id:
            raise ValueError("Sandbox handle is not the active Compose session")
        return handle.raw

    def _progress(self, message: str) -> None:
        """Publish a lifecycle progress message.

        Args:
            message: Human-readable progress text sent to the callback or module logger.
        """
        if self.progress_callback is not None:
            self.progress_callback(message)
        else:
            logger.info(message)


async def _run_command(
    argv: tuple[str, ...],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    timeout: float,
    stdin: bytes | None,
    stream_output: IO[str] | None = None,
) -> ComposeCommandResult:
    """Run a subprocess with process-group cancellation and timeout handling.

    Args:
        argv: Complete executable argument vector.
        cwd: Host working directory for the child process.
        environment: Complete child-process environment.
        timeout: Maximum runtime in seconds, clamped to a small positive value.
        stdin: Optional bytes written to the child process.
        stream_output: Optional text sink that receives redacted output as lines arrive.

    Returns:
        Captured subprocess result. Timeouts are returned as results rather than raised.

    Raises:
        asyncio.CancelledError: If the caller cancels execution after the process group is terminated.
        OSError: If the subprocess cannot be created.
    """
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd),
        env=dict(environment),
        stdin=asyncio.subprocess.PIPE if stdin is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    stdout_chunks: list[bytes] = []
    stderr_chunks: list[bytes] = []
    if stream_output is not None:
        communication = asyncio.create_task(
            _communicate_streaming(
                process,
                stdin=stdin,
                redact=_make_line_redactor(environment),
                stdout_chunks=stdout_chunks,
                stderr_chunks=stderr_chunks,
                output=stream_output,
            )
        )
    else:
        communication = asyncio.create_task(process.communicate(stdin))

    async def _abort() -> None:
        """Cancel communication, terminate the process group, and reap the task."""
        communication.cancel()
        await _terminate_process_group(process)
        await asyncio.gather(communication, return_exceptions=True)

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            communication,
            timeout=max(0.1, timeout),
        )
        return ComposeCommandResult(
            argv=argv,
            return_code=int(process.returncode or 0),
            stdout=stdout_bytes.decode("utf-8", errors="replace"),
            stderr=stderr_bytes.decode("utf-8", errors="replace"),
        )
    except asyncio.CancelledError:
        await _abort()
        raise
    except TimeoutError:
        await _abort()
        return ComposeCommandResult(
            argv=argv,
            return_code=SANDBOX_RUNTIME_RETURN_CODE,
            stdout=b"".join(stdout_chunks).decode("utf-8", errors="replace"),
            stderr=(
                b"".join(stderr_chunks).decode("utf-8", errors="replace") + f"Command timed out after {timeout:.1f}s"
            ),
            timed_out=True,
        )


async def _communicate_streaming(
    process: asyncio.subprocess.Process,
    *,
    stdin: bytes | None,
    redact: Callable[[str], str],
    stdout_chunks: list[bytes],
    stderr_chunks: list[bytes],
    output: IO[str],
) -> tuple[bytes, bytes]:
    """Drain both subprocess streams while writing redacted progress lines.

    Args:
        process: Running subprocess with piped standard streams.
        stdin: Optional bytes to write before waiting for process completion.
        redact: Function that removes secrets from each emitted text line.
        stdout_chunks: Mutable accumulator for raw standard-output bytes.
        stderr_chunks: Mutable accumulator for raw standard-error bytes.
        output: Text sink for redacted progress lines from both streams.

    Returns:
        Complete raw standard-output and standard-error byte strings.

    Raises:
        RuntimeError: If required subprocess pipes are unavailable.
    """
    if process.stdout is None or process.stderr is None:
        raise RuntimeError("Streaming subprocess pipes are unavailable")
    readers = (
        asyncio.create_task(
            _drain_stream(
                process.stdout,
                stdout_chunks,
                redact=redact,
                output=output,
            )
        ),
        asyncio.create_task(
            _drain_stream(
                process.stderr,
                stderr_chunks,
                redact=redact,
                output=output,
            )
        ),
    )
    try:
        if stdin is not None:
            if process.stdin is None:
                raise RuntimeError("Streaming subprocess stdin is unavailable")
            process.stdin.write(stdin)
            await process.stdin.drain()
            process.stdin.close()
            await process.stdin.wait_closed()
        await process.wait()
        await asyncio.gather(*readers)
    finally:
        for reader in readers:
            if not reader.done():
                reader.cancel()
        await asyncio.gather(*readers, return_exceptions=True)
    return b"".join(stdout_chunks), b"".join(stderr_chunks)


async def _drain_stream(
    stream: asyncio.StreamReader,
    chunks: list[bytes],
    *,
    redact: Callable[[str], str],
    output: IO[str],
) -> None:
    """Capture raw stream bytes and emit each decoded line after redaction.

    Args:
        stream: Async subprocess stream to read until EOF.
        chunks: Mutable raw-byte accumulator used for the command result.
        redact: Function applied before a decoded line leaves the provider.
        output: Text sink that receives redacted lines and is flushed immediately.
    """
    while line := await stream.readline():
        chunks.append(line)
        output.write(redact(line.decode("utf-8", errors="replace")))
        output.flush()


async def _retry_command(
    operation: Callable[[], Awaitable[ComposeCommandResult]],
) -> ComposeCommandResult:
    """Retry a cleanup command with short linear backoff.

    Args:
        operation: Zero-argument async function that starts one command attempt.

    Returns:
        First successful result or the final failed result after ``_CLEANUP_ATTEMPTS``.
    """
    result: ComposeCommandResult | None = None
    for attempt in range(_CLEANUP_ATTEMPTS):
        result = await operation()
        if result.ok:
            return result
        if attempt + 1 < _CLEANUP_ATTEMPTS:
            await asyncio.sleep(_CLEANUP_RETRY_DELAY_SECONDS * (attempt + 1))
    if result is None:  # pragma: no cover - attempts is a positive module constant
        raise RuntimeError("Cleanup command was not attempted")
    return result


async def _run_shielded(
    operation: Awaitable[ComposeCleanupError | None],
) -> tuple[ComposeCleanupError | None, asyncio.CancelledError | None]:
    """Let cleanup finish when its caller is cancelled.

    Args:
        operation: Cleanup awaitable that returns an optional aggregated error.

    Returns:
        Pair of the cleanup result and the first cancellation received by the caller.
        The caller decides when to restore that cancellation.
    """
    task = asyncio.ensure_future(operation)
    cancellation: asyncio.CancelledError | None = None
    while True:
        try:
            result = await asyncio.shield(task)
            return result, cancellation
        except asyncio.CancelledError as exc:
            cancellation = cancellation or exc
            if task.done():
                return task.result(), cancellation


async def _terminate_process_group(process: asyncio.subprocess.Process) -> None:
    """Terminate a subprocess group, escalating from ``SIGTERM`` to ``SIGKILL``.

    Args:
        process: Process whose session process group should be stopped and reaped.
    """
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        await asyncio.wait_for(process.wait(), timeout=2)
    except TimeoutError:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await process.wait()


def _parse_json_rows(text: str) -> list[dict[str, Any]]:
    """Parse Compose JSON-array, JSON-object, or JSON-lines output.

    Args:
        text: Raw output from a Compose command such as ``ps --format json``.

    Returns:
        Dictionary rows; non-object JSON values are ignored.

    Raises:
        json.JSONDecodeError: If neither the complete payload nor an individual line is valid JSON.

    Example:
        A JSON array and newline-delimited JSON objects both produce a list of service
        dictionaries.
    """
    stripped = text.strip()
    if not stripped:
        return []
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        rows: list[dict[str, Any]] = []
        for line in stripped.splitlines():
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
        return rows
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return [payload] if isinstance(payload, dict) else []


def _parse_compose_config(text: str) -> dict[str, Any]:
    """Parse and validate the service mapping from rendered Compose configuration.

    Args:
        text: JSON object emitted by ``docker compose config --format json``.

    Returns:
        Rendered service names mapped to their service configuration values.

    Raises:
        json.JSONDecodeError: If ``text`` is not valid JSON.
        TypeError: If the root or ``services`` value is not an object.
    """
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise TypeError("Compose config JSON must be an object")
    services = payload.get("services", {})
    if not isinstance(services, dict):
        raise TypeError("Compose config services must be an object")
    return services


def _published_ports(services: Mapping[str, Any]) -> list[_PublishedPort]:
    """Extract fixed host-port publications from rendered Compose services.

    Args:
        services: Validated rendered Compose service mapping.

    Returns:
        Sorted, de-duplicated publications. Dynamically assigned host ports are omitted.

    Raises:
        ValueError: If a published or target port is not numeric.
    """
    published_ports: set[_PublishedPort] = set()
    for service, service_config in services.items():
        if not isinstance(service_config, dict):
            continue
        ports = service_config.get("ports", [])
        if not isinstance(ports, list):
            continue
        for port in ports:
            if not isinstance(port, dict) or port.get("published") in {None, ""}:
                continue
            published = int(port["published"])
            if published == 0:
                continue
            published_ports.add(
                _PublishedPort(
                    service=str(service),
                    host_ip=str(port.get("host_ip") or "0.0.0.0"),
                    published=published,
                    target=int(port.get("target") or published),
                    protocol=str(port.get("protocol") or "tcp").casefold(),
                )
            )
    return sorted(published_ports)


async def _find_port_conflicts(
    published_ports: list[_PublishedPort],
) -> list[_PublishedPort]:
    """Probe host-port availability without blocking the event loop.

    Args:
        published_ports: Rendered fixed host-port publications to probe.

    Returns:
        Publications whose host address and port cannot be bound locally.
    """
    availability = await asyncio.gather(
        *(asyncio.to_thread(_published_port_available, published_port) for published_port in published_ports)
    )
    return [
        published_port
        for published_port, available in zip(
            published_ports,
            availability,
            strict=True,
        )
        if not available
    ]


def _published_port_available(published_port: _PublishedPort) -> bool:
    """Check whether one host address and port can be bound.

    Args:
        published_port: Publication describing address family, protocol, and host port.

    Returns:
        ``True`` when a temporary matching socket can bind the host endpoint.
    """
    family = socket.AF_INET6 if ":" in published_port.host_ip else socket.AF_INET
    socket_type = socket.SOCK_DGRAM if published_port.protocol == "udp" else socket.SOCK_STREAM
    with socket.socket(family, socket_type) as probe:
        try:
            probe.bind((published_port.host_ip, published_port.published))
        except OSError:
            return False
    return True


def _service_is_running(rows: list[dict[str, Any]], service: str) -> bool:
    """Check whether any Compose state row reports a service as running.

    Args:
        rows: Parsed Compose service-state rows.
        service: Service name to locate.

    Returns:
        ``True`` when a matching row has state ``running``.
    """
    return any(str(row.get("Service")) == service and str(row.get("State", "")).casefold() == "running" for row in rows)


def _services_ready(
    rows: list[dict[str, Any]],
    topology: ComposeServiceTopology,
) -> str | None:
    """Validate service rows against long-running and one-shot expectations.

    Args:
        rows: Parsed Compose service-state rows.
        topology: Exact service roles expected after startup.

    Returns:
        ``None`` when every role is ready; otherwise a concise failure description.
    """
    services = {str(row.get("Service")): row for row in rows}
    missing = sorted(topology.active_services - services.keys())
    if missing:
        return f"Compose services missing after startup: {missing}"
    unexpected = sorted(services.keys() - topology.active_services)
    if unexpected:
        return f"Unexpected Compose services after startup: {unexpected}"
    for service in sorted(topology.long_running_services):
        row = services[service]
        if str(row.get("State", "")).casefold() != "running":
            return f"Compose service {service!r} is not running: {row.get('State')}"
        health = str(row.get("Health", "")).casefold()
        if health and health != "healthy":
            return f"Compose service {service!r} is not healthy: {row.get('Health')}"
    for service in sorted(topology.one_shot_services):
        row = services[service]
        state = str(row.get("State", "")).casefold()
        try:
            exit_code = int(row.get("ExitCode", 1))
        except (TypeError, ValueError):
            exit_code = 1
        if state != "exited" or exit_code != 0:
            return f"Compose one-shot service {service!r} did not exit successfully"
    return None


def _make_line_redactor(environment: Mapping[str, str]) -> Callable[[str], str]:
    """Build a redactor that scans the environment's secrets only once.

    The returned callable is applied to every streamed log line, so the secret
    set and its (potentially large) alternation regex are compiled up front
    rather than rebuilt per line.

    Args:
        environment: Command environment whose secret-looking keys identify literal values to remove.

    Returns:
        Function that redacts known values and inline authorization, API key, token, and password assignments.

    Example:
        With ``{"API_KEY": "secret-value"}``, the returned function replaces both
        ``secret-value`` and ``Authorization: Bearer value``-style credentials.
    """
    secret_values = {
        value for key, value in environment.items() if _SECRET_ENV_FRAGMENT.search(key) and len(value) >= 4
    }
    parts = []
    for value in sorted(secret_values, key=len, reverse=True):
        prefix = r"(?<![A-Za-z0-9])" if value[0].isalnum() else ""
        suffix = r"(?![A-Za-z0-9])" if value[-1].isalnum() else ""
        parts.append(f"{prefix}{re.escape(value)}{suffix}")
    secret_pattern = re.compile("|".join(parts)) if parts else None

    def redact(text: str) -> str:
        """Redact one text fragment using the precompiled secret patterns.

        Args:
            text: Decoded command output or diagnostic text.

        Returns:
            Text with known and inline credential values replaced by ``<redacted>``.
        """
        if secret_pattern is not None:
            text = secret_pattern.sub("<redacted>", text)
        return _INLINE_SECRET.sub(_redact_inline_secret, text)

    return redact


def _redact(text: str, environment: Mapping[str, str]) -> str:
    """Redact known environment secrets and inline credentials from text.

    Args:
        text: Command output or diagnostics to sanitize.
        environment: Environment used to discover literal secret values.

    Returns:
        Sanitized text safe for errors, logs, and diagnostic files.
    """
    return _make_line_redactor(environment)(text)


def _redact_inline_secret(match: re.Match[str]) -> str:
    """Replace a matched inline credential value while preserving its prefix and quotes.

    Args:
        match: Match produced by ``_INLINE_SECRET``.

    Returns:
        Credential assignment with its value replaced by ``<redacted>``.
    """
    quote = match.group("quote") or ""
    return f"{match.group('prefix')}{quote}<redacted>{quote}"


__all__ = [
    "ComposeCleanupError",
    "ComposeCommandResult",
    "ComposeServiceTopology",
    "ComposeTeardownContext",
    "DockerComposeSandboxProvider",
    "ProgressCallback",
    "PullPolicy",
    "TeardownHook",
]
