# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the flock/psutil-based process lifecycle in _process.py."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import psutil
import pytest
from nemo_platform_ext.cli.commands.services import _process
from nemo_platform_ext.cli.commands.services._process import (
    ForegroundInstanceError,
    InstanceAlreadyRunningError,
    InstanceDescriptor,
    InstanceStillRunningError,
    _base_state_dir,
    _fallback_base_state_dir,
    _pid_alive,
    _snapshot_children,
    _sweep_orphans,
    acquire_lock,
    compute_scope,
    instance_dir,
    instance_log_bytes,
    is_instance_alive,
    is_removable_ghost,
    list_instances,
    list_stopped_scopes,
    prune_instances,
    read_descriptor,
    remove_descriptor,
    remove_instance,
    rotate_log,
    start_background,
    stop_instance,
    validate_pid,
    write_descriptor,
)


@pytest.fixture()
def base_dir(tmp_path: Path) -> Path:
    return tmp_path / "state" / "nmp"


# ---------------------------------------------------------------------------
# Scope computation
# ---------------------------------------------------------------------------


class TestComputeScope:
    def test_explicit_instance_name(self) -> None:
        assert compute_scope(port=8080, instance_name="myapp") == "myapp"

    def test_default_scope_includes_port(self) -> None:
        scope = compute_scope(port=9090)
        assert scope.endswith("-9090")

    def test_default_scope_is_deterministic(self) -> None:
        a = compute_scope(port=8080)
        b = compute_scope(port=8080)
        assert a == b

    def test_different_ports_different_scopes(self) -> None:
        a = compute_scope(port=8080)
        b = compute_scope(port=9090)
        assert a != b

    def test_hash_prefix_is_8_chars(self) -> None:
        scope = compute_scope(port=8080)
        prefix = scope.rsplit("-", 1)[0]
        assert len(prefix) == 8

    def test_git_failure_falls_back_to_cwd(self) -> None:
        import nemo_platform_ext.cli.commands.services._process as proc_mod

        proc_mod._scope_prefix_cache = None
        try:
            with patch.object(proc_mod, "_find_git_root", return_value="/no/git/here"):
                scope = compute_scope(port=8080)
            assert scope.endswith("-8080")
            assert len(scope.rsplit("-", 1)[0]) == 8
        finally:
            proc_mod._scope_prefix_cache = None

    def test_different_git_roots_produce_different_prefixes(self) -> None:
        """Two different working directories (worktrees) produce distinct scopes."""
        import nemo_platform_ext.cli.commands.services._process as proc_mod

        with patch.object(proc_mod, "_find_git_root", return_value="/workspace/project-a"):
            scope_a = compute_scope(port=8080)

        proc_mod._scope_prefix_cache = None

        with patch.object(proc_mod, "_find_git_root", return_value="/workspace/project-b"):
            scope_b = compute_scope(port=8080)

        assert scope_a != scope_b
        assert scope_a.endswith("-8080")
        assert scope_b.endswith("-8080")
        prefix_a = scope_a.rsplit("-", 1)[0]
        prefix_b = scope_b.rsplit("-", 1)[0]
        assert prefix_a != prefix_b


# ---------------------------------------------------------------------------
# Instance directory
# ---------------------------------------------------------------------------


class TestInstanceDir:
    def test_creates_directory(self, base_dir: Path) -> None:
        d = instance_dir("test-scope", base_dir=base_dir)
        assert d.is_dir()
        assert d.name == "test-scope"

    def test_idempotent(self, base_dir: Path) -> None:
        d1 = instance_dir("test-scope", base_dir=base_dir)
        d2 = instance_dir("test-scope", base_dir=base_dir)
        assert d1 == d2


class TestBaseStateDir:
    """Resolution + creation + unwritable-``$HOME`` fallback for the state dir."""

    @pytest.fixture(autouse=True)
    def _reset_state_globals(self):
        # _base_state_dir memoizes its resolved dir and compute_scope caches a
        # prefix; reset both around every test so neither leaks between tests.
        _process._resolved_base_dir = None
        _process._scope_prefix_cache = None
        yield
        _process._resolved_base_dir = None
        _process._scope_prefix_cache = None

    @pytest.fixture()
    def fallback_root(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        """Force resolution onto the temp fallback and return that root.

        Points the preferred dir under a regular file so its mkdir raises for every uid
        (root-proof, unlike a chmod-based block), then aims ``gettempdir`` at a fresh dir
        -- the resolved base becomes ``<root>/nmp-state-<uid>/nmp``.
        """
        blocker = tmp_path / "not-a-dir"
        blocker.write_text("x")
        monkeypatch.setattr(_process, "_preferred_base_state_dir", lambda: blocker / "nmp")
        root = tmp_path / "tmp"
        root.mkdir()
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(root))
        return root

    def test_resolves_and_creates_under_preferred(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        base = _base_state_dir()
        assert base == tmp_path / "nmp"
        assert (base / "instances").is_dir()  # resolution creates the instances dir

    def test_memoized_within_process(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        first = _base_state_dir()
        # A later env change is ignored: the resolved dir is cached for the process.
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "other"))
        assert _base_state_dir() == first

    def test_falls_back_when_preferred_uncreatable(self, fallback_root: Path) -> None:
        base = _base_state_dir()
        assert base == fallback_root / f"nmp-state-{os.getuid()}" / "nmp"
        assert (base / "instances").is_dir()

    def test_fallback_dir_is_owner_only(self, fallback_root: Path) -> None:
        # The per-uid dir under shared /tmp must not be world-traversable/readable,
        # or another user could read the descriptor (pid/port/config) and the log.
        _base_state_dir()
        per_uid = fallback_root / f"nmp-state-{os.getuid()}"
        assert os.stat(per_uid).st_mode & 0o777 == 0o700

    def test_rejects_squatted_fallback_owned_by_other_uid(
        self, fallback_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Simulate a squat without a second real user: make the process *believe* it is a
        # different uid than the one that owns the temp root it creates. _secure_fallback_root
        # must refuse to write state into a directory it does not own -- and this holds even
        # as root, where a chmod-only check would not (root can chmod a foreign dir).
        real_uid = os.getuid()
        monkeypatch.setattr(_process.os, "getuid", lambda: real_uid + 1)

        with pytest.raises(OSError):
            _base_state_dir()

        # The per-uid root gets created (empty) but no state subtree is written under it.
        squatted = fallback_root / f"nmp-state-{real_uid + 1}"
        assert not (squatted / "nmp").exists()

    def test_rejects_fallback_it_cannot_lock_down(self, fallback_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # The per-uid temp root exists and we own it, but the chmod that would make it
        # owner-only fails (EPERM). The fallback must be rejected -- never written into --
        # rather than silently swallowing the chmod error.
        per_uid = fallback_root / f"nmp-state-{os.getuid()}"
        per_uid.mkdir(mode=0o755)  # a pre-existing, too-permissive root

        real_chmod = os.chmod

        def deny_chmod(path, *args, **kwargs):
            if Path(path) == per_uid:
                raise PermissionError("Operation not permitted")
            return real_chmod(path, *args, **kwargs)

        monkeypatch.setattr(_process.os, "chmod", deny_chmod)

        with pytest.raises(OSError):
            _base_state_dir()
        assert not (per_uid / "nmp").exists()  # no state written under the unsecurable root

    def test_reuses_and_tightens_own_loose_fallback_dir(self, fallback_root: Path) -> None:
        # A per-uid root we already own but that is too permissive -- e.g. a plain mkdir
        # under the default umask, left by an older build -- is not a squat: accept it and
        # tighten it to 0700, don't reject it.
        per_uid = fallback_root / f"nmp-state-{os.getuid()}"
        per_uid.mkdir()
        os.chmod(per_uid, 0o755)  # group/other-readable; _secure_fallback_root must clamp it

        base = _base_state_dir()
        assert base == per_uid / "nmp"
        assert (base / "instances").is_dir()
        # _secure_fallback_root ran an absolute chmod(0o700), overriding the 0o755 above.
        assert os.stat(per_uid).st_mode & 0o777 == 0o700

    def test_fallback_is_none_without_tempdir(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _no_tempdir() -> str:
            raise FileNotFoundError("No usable temporary directory found")

        monkeypatch.setattr(tempfile, "gettempdir", _no_tempdir)
        assert _fallback_base_state_dir() is None

    def test_raises_when_no_location_writable(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        blocker = tmp_path / "not-a-dir"
        blocker.write_text("x")
        monkeypatch.setattr(_process, "_preferred_base_state_dir", lambda: blocker / "nmp")
        monkeypatch.setattr(_process, "_fallback_base_state_dir", lambda: None)
        with pytest.raises(OSError):
            _base_state_dir()

    @pytest.mark.skipif(os.getuid() == 0, reason="root bypasses the DAC write check this test relies on")
    def test_unwritable_home_does_not_crash(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Regression for the LoRA-sidecar crash: ``nemo services run`` under a uid
        that cannot write ``$HOME`` must fall back instead of raising PermissionError.

        Faithfully reproduces the container condition -- ``$HOME`` exists but is not
        writable by the running uid, ``~/.local`` is absent, and ``XDG_STATE_HOME``
        is unset -- which crashed ``instance_dir`` at ``mkdir('$HOME/.local')``
        before the fix.
        """
        fake_home = tmp_path / "home" / "nvs"
        fake_home.mkdir(parents=True)
        fallback_tmp = tmp_path / "tmp"
        fallback_tmp.mkdir()

        monkeypatch.setenv("HOME", str(fake_home))
        monkeypatch.delenv("XDG_STATE_HOME", raising=False)
        monkeypatch.delenv("_NMP_STATE_DIR", raising=False)
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(fallback_tmp))

        os.chmod(fake_home, 0o500)  # r-x for owner only: cannot create
        try:
            d = instance_dir(compute_scope(port=8080))  # base_dir=None; must not raise
            assert d.is_dir()
            assert fake_home not in d.parents  # did NOT land under the unwritable HOME
            assert d.is_relative_to(fallback_tmp)
        finally:
            os.chmod(fake_home, 0o700)  # owner-only access; sufficient for pytest cleanup


# ---------------------------------------------------------------------------
# flock liveness
# ---------------------------------------------------------------------------


class TestFlockLiveness:
    def test_acquire_and_release(self, base_dir: Path) -> None:
        fd = acquire_lock("test", base_dir=base_dir)
        assert fd >= 0
        assert is_instance_alive("test", base_dir=base_dir)
        os.close(fd)
        assert not is_instance_alive("test", base_dir=base_dir)

    def test_double_acquire_raises(self, base_dir: Path) -> None:
        fd = acquire_lock("test", base_dir=base_dir)
        try:
            with pytest.raises(InstanceAlreadyRunningError, match="test"):
                acquire_lock("test", base_dir=base_dir)
        finally:
            os.close(fd)

    def test_different_scopes_independent(self, base_dir: Path) -> None:
        fd1 = acquire_lock("scope-a", base_dir=base_dir)
        fd2 = acquire_lock("scope-b", base_dir=base_dir)
        assert is_instance_alive("scope-a", base_dir=base_dir)
        assert is_instance_alive("scope-b", base_dir=base_dir)
        os.close(fd1)
        assert not is_instance_alive("scope-a", base_dir=base_dir)
        assert is_instance_alive("scope-b", base_dir=base_dir)
        os.close(fd2)

    def test_not_alive_when_no_lock_file(self, base_dir: Path) -> None:
        assert not is_instance_alive("nonexistent", base_dir=base_dir)


# ---------------------------------------------------------------------------
# Descriptor I/O
# ---------------------------------------------------------------------------


class TestDescriptorRoundTrip:
    def test_write_and_read(self, base_dir: Path) -> None:
        desc = InstanceDescriptor(
            pid=12345,
            scope="test-8080",
            host="127.0.0.1",
            port=8080,
            mode="background",
            create_time=1000.0,
            services=["entities", "models"],
            controllers=["jobs"],
        )
        write_descriptor(desc, base_dir=base_dir)
        recovered = read_descriptor("test-8080", base_dir=base_dir)

        assert recovered is not None
        assert recovered.pid == 12345
        assert recovered.scope == "test-8080"
        assert recovered.host == "127.0.0.1"
        assert recovered.port == 8080
        assert recovered.mode == "background"
        assert recovered.create_time == 1000.0
        assert recovered.services == ["entities", "models"]
        assert recovered.controllers == ["jobs"]

    def test_read_missing_returns_none(self, base_dir: Path) -> None:
        assert read_descriptor("no-such-scope", base_dir=base_dir) is None

    def test_read_corrupt_returns_none(self, base_dir: Path) -> None:
        d = instance_dir("corrupt", base_dir=base_dir)
        (d / "instance.json").write_text("not json{{{")
        assert read_descriptor("corrupt", base_dir=base_dir) is None

    def test_remove_descriptor(self, base_dir: Path) -> None:
        desc = InstanceDescriptor(
            pid=1,
            scope="rm-test",
            host="127.0.0.1",
            port=8080,
            mode="background",
            create_time=1.0,
        )
        write_descriptor(desc, base_dir=base_dir)
        assert read_descriptor("rm-test", base_dir=base_dir) is not None
        remove_descriptor("rm-test", base_dir=base_dir)
        assert read_descriptor("rm-test", base_dir=base_dir) is None

    def test_remove_missing_is_noop(self, base_dir: Path) -> None:
        remove_descriptor("nonexistent", base_dir=base_dir)


# ---------------------------------------------------------------------------
# PID validation via psutil
# ---------------------------------------------------------------------------


class TestValidatePid:
    def test_validates_current_process(self) -> None:
        ct = psutil.Process(os.getpid()).create_time()
        assert validate_pid(os.getpid(), ct)

    def test_rejects_wrong_create_time(self) -> None:
        assert not validate_pid(os.getpid(), 0.0)

    def test_rejects_dead_pid(self) -> None:
        assert not validate_pid(999999999, 0.0)


# ---------------------------------------------------------------------------
# list_instances
# ---------------------------------------------------------------------------


class TestListInstances:
    def test_empty_when_no_instances(self, base_dir: Path) -> None:
        assert list_instances(base_dir=base_dir) == []

    def test_lists_alive_instance(self, base_dir: Path) -> None:
        fd = acquire_lock("alive-one", base_dir=base_dir)
        desc = InstanceDescriptor(
            pid=os.getpid(),
            scope="alive-one",
            host="127.0.0.1",
            port=8080,
            mode="foreground",
            create_time=1.0,
        )
        write_descriptor(desc, base_dir=base_dir)
        try:
            instances = list_instances(base_dir=base_dir)
            assert len(instances) == 1
            assert instances[0].scope == "alive-one"
            assert instances[0].alive is True
            assert instances[0].descriptor is not None
        finally:
            os.close(fd)

    def test_cleans_up_dead_descriptor(self, base_dir: Path) -> None:
        d = instance_dir("dead-scope", base_dir=base_dir)
        desc = InstanceDescriptor(
            pid=999999,
            scope="dead-scope",
            host="127.0.0.1",
            port=8080,
            mode="background",
            create_time=1.0,
        )
        write_descriptor(desc, base_dir=base_dir)

        instances = list_instances(base_dir=base_dir)
        assert instances == []
        assert not d.exists()

    def test_stale_descriptor_with_logs_stays_listed(self, base_dir: Path) -> None:
        d = instance_dir("dead-with-logs", base_dir=base_dir)
        desc = InstanceDescriptor(
            pid=999999,
            scope="dead-with-logs",
            host="127.0.0.1",
            port=8080,
            mode="background",
            create_time=1.0,
        )
        write_descriptor(desc, base_dir=base_dir)
        (d / "services.log").write_text("crash output\n")

        instances = list_instances(base_dir=base_dir)
        assert len(instances) == 1
        assert instances[0].scope == "dead-with-logs"
        assert instances[0].alive is False
        assert instances[0].descriptor is None
        assert d.exists()

    def test_auto_removes_lock_only_ghost(self, base_dir: Path) -> None:
        d = instance_dir("ghost-lock", base_dir=base_dir)
        (d / "services.lock").touch()

        instances = list_instances(base_dir=base_dir)
        assert instances == []
        assert not d.exists()

    def test_keeps_stopped_instance_with_logs(self, base_dir: Path) -> None:
        d = instance_dir("stopped-logs", base_dir=base_dir)
        (d / "services.lock").touch()
        (d / "services.log").write_text("crash output\n")

        instances = list_instances(base_dir=base_dir)
        assert len(instances) == 1
        assert instances[0].scope == "stopped-logs"
        assert instances[0].alive is False
        assert instances[0].descriptor is None
        assert d.exists()

    def test_keeps_stopped_instance_with_rotated_logs_only(self, base_dir: Path) -> None:
        d = instance_dir("rotated-logs", base_dir=base_dir)
        (d / "services.lock").touch()
        (d / "services.log.20250101T000000Z").write_text("old boot\n")

        instances = list_instances(base_dir=base_dir)
        assert len(instances) == 1
        assert instances[0].scope == "rotated-logs"

    def test_empty_services_log_is_still_a_ghost(self, base_dir: Path) -> None:
        d = instance_dir("empty-log", base_dir=base_dir)
        (d / "services.lock").touch()
        (d / "services.log").touch()

        instances = list_instances(base_dir=base_dir)
        assert instances == []
        assert not d.exists()

    def test_running_instance_not_auto_removed(self, base_dir: Path) -> None:
        fd = acquire_lock("alive-ghost-check", base_dir=base_dir)
        try:
            instances = list_instances(base_dir=base_dir)
            assert len(instances) == 1
            assert instances[0].alive is True
        finally:
            os.close(fd)


# ---------------------------------------------------------------------------
# remove_instance / prune_instances
# ---------------------------------------------------------------------------


class TestRemoveInstance:
    def test_removes_dead_scope_dir(self, base_dir: Path) -> None:
        d = instance_dir("rm-me", base_dir=base_dir)
        (d / "services.log").write_text("logs\n")

        assert remove_instance("rm-me", base_dir=base_dir) is True
        assert not d.exists()

    def test_missing_scope_returns_false(self, base_dir: Path) -> None:
        assert remove_instance("missing", base_dir=base_dir) is False

    def test_refuses_running_instance(self, base_dir: Path) -> None:
        fd = acquire_lock("running-rm", base_dir=base_dir)
        try:
            with pytest.raises(InstanceStillRunningError, match="running-rm"):
                remove_instance("running-rm", base_dir=base_dir)
        finally:
            os.close(fd)

    def test_rejects_invalid_scope(self, base_dir: Path) -> None:
        with pytest.raises(ValueError, match="Invalid instance scope"):
            remove_instance("../escape", base_dir=base_dir)

    def test_returns_false_when_rmtree_fails(self, base_dir: Path) -> None:
        d = instance_dir("rmtree-fail", base_dir=base_dir)
        (d / "services.log").write_text("logs\n")

        with patch(
            "nemo_platform_ext.cli.commands.services._process.shutil.rmtree",
            side_effect=OSError("permission denied"),
        ):
            assert remove_instance("rmtree-fail", base_dir=base_dir) is False
        assert d.exists()


class TestPruneInstances:
    def test_removes_all_stopped_scopes(self, base_dir: Path) -> None:
        alive_fd = acquire_lock("alive-prune", base_dir=base_dir)
        stopped = instance_dir("stopped-prune", base_dir=base_dir)
        (stopped / "services.log").write_text("x\n")
        try:
            removed = prune_instances(base_dir=base_dir)
            assert removed == ["stopped-prune"]
            assert not stopped.exists()
            assert is_instance_alive("alive-prune", base_dir=base_dir)
        finally:
            os.close(alive_fd)

    def test_noop_when_empty(self, base_dir: Path) -> None:
        assert prune_instances(base_dir=base_dir) == []


class TestInstanceLogBytes:
    def test_sums_active_and_rotated_logs(self, base_dir: Path) -> None:
        d = instance_dir("log-bytes", base_dir=base_dir)
        (d / "services.log").write_text("abc")
        (d / "services.log.old").write_text("de")

        assert instance_log_bytes("log-bytes", base_dir=base_dir) == 5


class TestIsRemovableGhost:
    def test_true_for_lock_only(self, base_dir: Path) -> None:
        d = instance_dir("ghost", base_dir=base_dir)
        (d / "services.lock").touch()
        assert is_removable_ghost("ghost", base_dir=base_dir) is True

    def test_false_when_logs_present(self, base_dir: Path) -> None:
        d = instance_dir("not-ghost", base_dir=base_dir)
        (d / "services.log").write_text("data\n")
        assert is_removable_ghost("not-ghost", base_dir=base_dir) is False


class TestListStoppedScopes:
    def test_lists_only_stopped(self, base_dir: Path) -> None:
        fd = acquire_lock("up", base_dir=base_dir)
        down = instance_dir("down", base_dir=base_dir)
        (down / "services.log").write_text("x\n")
        try:
            assert list_stopped_scopes(base_dir=base_dir) == ["down"]
        finally:
            os.close(fd)


# ---------------------------------------------------------------------------
# Log rotation
# ---------------------------------------------------------------------------


class TestLogRotation:
    def test_rotate_empty_log(self, base_dir: Path) -> None:
        log = rotate_log("test", base_dir=base_dir)
        assert log.name == "services.log"

    def test_rotate_existing_log(self, base_dir: Path) -> None:
        d = instance_dir("test", base_dir=base_dir)
        log = d / "services.log"
        log.write_text("old content\n")

        new_log = rotate_log("test", base_dir=base_dir)
        assert new_log == log
        assert not log.exists()
        rotated = list(d.glob("services.log.*"))
        assert len(rotated) == 1
        assert rotated[0].read_text() == "old content\n"

    def test_keeps_all_rotated_logs(self, base_dir: Path) -> None:
        d = instance_dir("test", base_dir=base_dir)
        for i in range(8):
            (d / f"services.log.2025010{i}T000000Z").write_text(f"log {i}\n")
        log = d / "services.log"
        log.write_text("current\n")

        rotate_log("test", base_dir=base_dir)
        rotated = list(d.glob("services.log.*"))
        assert len(rotated) == 9


# ---------------------------------------------------------------------------
# stop_instance
# ---------------------------------------------------------------------------


class TestStopInstance:
    def test_not_running_returns_empty(self, base_dir: Path) -> None:
        result = stop_instance("nothing", base_dir=base_dir)
        assert result.stopped_pids == []

    def test_stops_running_process(self, base_dir: Path) -> None:
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            scope = "stop-test"
            fd = acquire_lock(scope, base_dir=base_dir)
            desc = InstanceDescriptor(
                pid=proc.pid,
                scope=scope,
                host="127.0.0.1",
                port=8080,
                mode="background",
                create_time=psutil.Process(proc.pid).create_time(),
            )
            write_descriptor(desc, base_dir=base_dir)

            os.close(fd)

            result = stop_instance(scope, base_dir=base_dir, timeout=5.0)
            assert proc.pid in result.stopped_pids
            proc.wait(timeout=5)
            assert proc.poll() is not None
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)

    def test_cleans_up_stale_descriptor(self, base_dir: Path) -> None:
        scope = "stale"
        desc = InstanceDescriptor(
            pid=999999999,
            scope=scope,
            host="127.0.0.1",
            port=8080,
            mode="background",
            create_time=0.0,
        )
        write_descriptor(desc, base_dir=base_dir)
        result = stop_instance(scope, base_dir=base_dir)
        assert result.stopped_pids == []
        assert read_descriptor(scope, base_dir=base_dir) is None

    def test_refuses_to_stop_foreground_instance(self, base_dir: Path) -> None:
        scope = "fg-protect"
        fd = acquire_lock(scope, base_dir=base_dir)
        try:
            desc = InstanceDescriptor(
                pid=os.getpid(),
                scope=scope,
                host="127.0.0.1",
                port=8080,
                mode="foreground",
                create_time=1.0,
            )
            write_descriptor(desc, base_dir=base_dir)

            with pytest.raises(ForegroundInstanceError, match="foreground"):
                stop_instance(scope, base_dir=base_dir)

            assert is_instance_alive(scope, base_dir=base_dir)
            assert read_descriptor(scope, base_dir=base_dir) is not None
        finally:
            os.close(fd)

    def test_force_stops_foreground_instance(self, base_dir: Path) -> None:
        scope = "fg-force"
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            desc = InstanceDescriptor(
                pid=proc.pid,
                scope=scope,
                host="127.0.0.1",
                port=8080,
                mode="foreground",
                create_time=psutil.Process(proc.pid).create_time(),
            )
            write_descriptor(desc, base_dir=base_dir)

            result = stop_instance(scope, base_dir=base_dir, force=True)
            assert proc.pid in result.stopped_pids
            proc.wait(timeout=5)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)


# ---------------------------------------------------------------------------
# start_background
# ---------------------------------------------------------------------------


class TestStartBackground:
    def test_launches_detached_subprocess(self, base_dir: Path) -> None:
        mock_proc = MagicMock()
        mock_proc.pid = 99999

        with patch(
            "nemo_platform_ext.cli.commands.services._process.subprocess.Popen",
            return_value=mock_proc,
        ) as mock_popen:
            proc = start_background(
                scope="bg-test",
                services=["entities", "models"],
                controllers=["jobs"],
                host="127.0.0.1",
                port=8080,
                base_dir=base_dir,
            )

        assert proc.pid == 99999
        call_kwargs = mock_popen.call_args[1]
        assert call_kwargs["start_new_session"] is True
        assert call_kwargs["stdin"] == subprocess.DEVNULL
        assert call_kwargs["close_fds"] is True

    def test_injects_nmp_data_dir_when_unset(self, base_dir: Path, monkeypatch) -> None:
        monkeypatch.delenv("NMP_DATA_DIR", raising=False)
        mock_proc = MagicMock()
        mock_proc.pid = 4242
        captured_env: dict[str, str] = {}

        def fake_popen(args, **kwargs):
            captured_env.update(kwargs["env"])
            return mock_proc

        with patch(
            "nemo_platform_ext.cli.commands.services._process.subprocess.Popen",
            side_effect=fake_popen,
        ):
            start_background(
                scope="data-dir-test",
                data_dir="/chosen/data/dir",
                base_dir=base_dir,
            )

        assert captured_env.get("NMP_DATA_DIR") == "/chosen/data/dir"

    def test_does_not_override_shell_nmp_data_dir(self, base_dir: Path, monkeypatch) -> None:
        monkeypatch.setenv("NMP_DATA_DIR", "/shell/wins")
        mock_proc = MagicMock()
        mock_proc.pid = 4243
        captured_env: dict[str, str] = {}

        def fake_popen(args, **kwargs):
            captured_env.update(kwargs["env"])
            return mock_proc

        with patch(
            "nemo_platform_ext.cli.commands.services._process.subprocess.Popen",
            side_effect=fake_popen,
        ):
            start_background(
                scope="shell-env-test",
                data_dir="/chosen/data/dir",
                base_dir=base_dir,
            )

        assert captured_env.get("NMP_DATA_DIR") == "/shell/wins"

    def test_rotates_log_before_start(self, base_dir: Path) -> None:
        d = instance_dir("rotate-test", base_dir=base_dir)
        log = d / "services.log"
        log.write_text("old log content\n")

        mock_proc = MagicMock()
        mock_proc.pid = 5555

        with patch(
            "nemo_platform_ext.cli.commands.services._process.subprocess.Popen",
            return_value=mock_proc,
        ):
            start_background(scope="rotate-test", base_dir=base_dir)

        rotated = list(d.glob("services.log.*"))
        assert len(rotated) == 1
        assert rotated[0].read_text() == "old log content\n"

    def test_forwards_instance_scope_to_child(self, base_dir: Path) -> None:
        mock_proc = MagicMock()
        mock_proc.pid = 7777
        captured_args: list[str] = []

        def fake_popen(args, **kwargs):
            captured_args.extend(args)
            return mock_proc

        with patch(
            "nemo_platform_ext.cli.commands.services._process.subprocess.Popen",
            side_effect=fake_popen,
        ):
            start_background(
                scope="custom-scope",
                services=["entities"],
                host="127.0.0.1",
                port=9090,
                base_dir=base_dir,
            )

        assert "--instance" in captured_args
        idx = captured_args.index("--instance")
        assert captured_args[idx + 1] == "custom-scope"

    def test_sets_launch_mode_background_in_child_env(self, base_dir: Path) -> None:
        mock_proc = MagicMock()
        mock_proc.pid = 8888
        captured_env: dict[str, str] = {}

        def fake_popen(args, **kwargs):
            captured_env.update(kwargs["env"])
            return mock_proc

        with patch(
            "nemo_platform_ext.cli.commands.services._process.subprocess.Popen",
            side_effect=fake_popen,
        ):
            start_background(scope="mode-test", base_dir=base_dir)

        assert captured_env.get("_NMP_LAUNCH_MODE") == "background"


# ---------------------------------------------------------------------------
# _snapshot_children / _sweep_orphans
# ---------------------------------------------------------------------------


def _wait_for_children(pid: int, timeout: float = 5.0) -> list[psutil.Process]:
    """Poll until *pid* has at least one child process, or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            children = psutil.Process(pid).children(recursive=True)
            if children:
                return children
        except psutil.NoSuchProcess:
            break
        time.sleep(0.1)
    return []


_SPAWN_CHILD_SCRIPT = (
    "import subprocess, sys, time; "
    "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
    "time.sleep(60)"
)


class TestSnapshotChildren:
    def test_captures_child_processes(self) -> None:
        parent = subprocess.Popen(
            [sys.executable, "-c", _SPAWN_CHILD_SCRIPT],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            _wait_for_children(parent.pid)
            children = _snapshot_children(parent.pid)
            assert len(children) >= 1
            child_pids = [c.pid for c in children]
            assert all(isinstance(p, int) for p in child_pids)
        finally:
            for c in psutil.Process(parent.pid).children(recursive=True):
                c.kill()
            parent.kill()
            parent.wait(timeout=5)

    def test_returns_empty_for_dead_pid(self) -> None:
        assert _snapshot_children(999999999) == []

    def test_returns_empty_for_process_with_no_children(self) -> None:
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            children = _snapshot_children(proc.pid)
            assert children == []
        finally:
            proc.kill()
            proc.wait(timeout=5)


class TestSweepOrphans:
    def test_terminates_surviving_children(self) -> None:
        procs = []
        for _ in range(3):
            p = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(60)"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            procs.append(p)
        try:
            ps_children = [psutil.Process(p.pid) for p in procs]
            killed = _sweep_orphans(ps_children, timeout=3.0)
            assert len(killed) == 3
            for p in procs:
                p.wait(timeout=5)
                assert p.poll() is not None
        finally:
            for p in procs:
                if p.poll() is None:
                    p.kill()
                    p.wait(timeout=5)

    def test_noop_when_all_already_exited(self) -> None:
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        ps_child = psutil.Process(proc.pid)
        proc.kill()
        proc.wait(timeout=5)
        killed = _sweep_orphans([ps_child], timeout=1.0)
        assert killed == []

    def test_escalates_to_sigkill(self) -> None:
        proc = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            time.sleep(0.3)
            ps_child = psutil.Process(proc.pid)
            killed = _sweep_orphans([ps_child], timeout=2.0)
            assert proc.pid in killed
            proc.wait(timeout=5)
            assert proc.poll() is not None
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)


# ---------------------------------------------------------------------------
# stop_instance — child sweep integration
# ---------------------------------------------------------------------------


class TestStopInstanceChildSweep:
    def test_sweeps_surviving_children(self, base_dir: Path) -> None:
        """Parent + child spawned; stop should kill both and report the child."""
        parent = subprocess.Popen(
            [sys.executable, "-c", _SPAWN_CHILD_SCRIPT],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            _wait_for_children(parent.pid)

            scope = "sweep-test"
            fd = acquire_lock(scope, base_dir=base_dir)
            desc = InstanceDescriptor(
                pid=parent.pid,
                scope=scope,
                host="127.0.0.1",
                port=8080,
                mode="background",
                create_time=psutil.Process(parent.pid).create_time(),
            )
            write_descriptor(desc, base_dir=base_dir)
            os.close(fd)

            result = stop_instance(scope, base_dir=base_dir, timeout=5.0)
            assert parent.pid in result.stopped_pids
            assert len(result.swept_children) >= 1
            for child_pid in result.swept_children:
                assert not _pid_alive(child_pid)
            parent.wait(timeout=5)
        finally:
            try:
                for c in psutil.Process(parent.pid).children(recursive=True):
                    c.kill()
            except psutil.NoSuchProcess:
                pass  # Parent already exited — children cleaned up.
            if parent.poll() is None:
                parent.kill()
                parent.wait(timeout=5)

    def test_swept_children_empty_when_no_children(self, base_dir: Path) -> None:
        """Process with no children -- swept_children should be empty."""
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            scope = "clean-stop"
            fd = acquire_lock(scope, base_dir=base_dir)
            desc = InstanceDescriptor(
                pid=proc.pid,
                scope=scope,
                host="127.0.0.1",
                port=8080,
                mode="background",
                create_time=psutil.Process(proc.pid).create_time(),
            )
            write_descriptor(desc, base_dir=base_dir)
            os.close(fd)

            result = stop_instance(scope, base_dir=base_dir, timeout=5.0)
            assert proc.pid in result.stopped_pids
            assert result.swept_children == []
            proc.wait(timeout=5)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)

    def test_restart_path_sweeps_children(self, base_dir: Path) -> None:
        """The restart flow calls stop_instance(force=True); verify it sweeps children too."""
        parent = subprocess.Popen(
            [sys.executable, "-c", _SPAWN_CHILD_SCRIPT],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            _wait_for_children(parent.pid)
            child_pids_before = [c.pid for c in psutil.Process(parent.pid).children(recursive=True)]
            assert len(child_pids_before) >= 1

            scope = "restart-sweep"
            fd = acquire_lock(scope, base_dir=base_dir)
            desc = InstanceDescriptor(
                pid=parent.pid,
                scope=scope,
                host="127.0.0.1",
                port=8080,
                mode="foreground",
                create_time=psutil.Process(parent.pid).create_time(),
            )
            write_descriptor(desc, base_dir=base_dir)
            os.close(fd)

            result = stop_instance(scope, base_dir=base_dir, force=True, timeout=5.0)
            assert parent.pid in result.stopped_pids
            assert len(result.swept_children) >= 1
            for child_pid in result.swept_children:
                assert not _pid_alive(child_pid)
            parent.wait(timeout=5)
        finally:
            try:
                for c in psutil.Process(parent.pid).children(recursive=True):
                    c.kill()
            except psutil.NoSuchProcess:
                pass  # Parent already exited — children cleaned up.
            if parent.poll() is None:
                parent.kill()
                parent.wait(timeout=5)
