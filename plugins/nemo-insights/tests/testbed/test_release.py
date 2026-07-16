# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
import re
import subprocess
from pathlib import Path

import pytest
from testbed import release

_LOCK = '[subjects]\ntau2-airline = "state-v6"\nnvq = "state-v9"\n'


def _write_lock(tmp_path: Path, text: str = _LOCK) -> Path:
    lock = tmp_path / "state.lock"
    lock.write_text(text, encoding="utf-8")
    return lock


def test_latest_ref_numeric_sort():
    names = ["state-v2.tar.zst", "state-v10.tar.zst", "junk.txt", "state-v3-failed.tar.zst"]
    assert release.latest_ref(names) == "state-v10"


def test_latest_ref_empty():
    assert release.latest_ref([]) is None


def test_next_ref():
    assert release.next_ref("state-v10") == "state-v11"
    assert release.next_ref(None) == "state-v1"


def test_state_repo_defaults_to_existing_fixture_home():
    assert release.state_repo({}) == "NVIDIA-dev/NeMo-Optimizer"


def test_state_repo_allows_explicit_override():
    assert release.state_repo({"TESTBED_STATE_REPO": "owner/repository"}) == "owner/repository"


def test_lock_ref_returns_subject_entry(tmp_path):
    lock = _write_lock(tmp_path)
    assert release.lock_ref(lock, "tau2-airline") == "state-v6"
    assert release.lock_ref(lock, "nvq") == "state-v9"


def test_lock_ref_subject_without_entry_returns_none(tmp_path):
    assert release.lock_ref(_write_lock(tmp_path), "tau2-retail") is None


def test_lock_ref_missing_file_returns_none(tmp_path):
    assert release.lock_ref(tmp_path / "absent.lock", "tau2-airline") is None


def test_lock_ref_old_single_pin_format_exits_with_migration_message(tmp_path):
    lock = _write_lock(tmp_path, '# comment\nstate_ref = "state-v6"\n')
    with pytest.raises(SystemExit) as exc:
        release.lock_ref(lock, "tau2-airline")
    message = str(exc.value)
    assert "[subjects]" in message
    assert 'tau2-airline = "state-v6"' in message  # quotes the expected format


def test_repo_lock_file_is_per_subject_and_pins_tau2_airline():
    """The checked-in lock must parse under the new format and pin the live subject."""
    lock = Path(release.__file__).parent / "state.lock"
    ref = release.lock_ref(lock, "tau2-airline")
    assert ref is not None and re.fullmatch(r"state-v\d+", ref)


def test_release_asset_names_missing_release_returns_empty(monkeypatch):
    def fake_gh(*args):
        if args[:1] == ("api",):
            return "[]"
        raise subprocess.CalledProcessError(1, ["gh", *args], stderr="release not found\n")

    monkeypatch.setattr(release, "_gh", fake_gh)
    assert release._release_asset_names() == []


def test_release_asset_names_other_failure_raises(monkeypatch):
    def fake_gh(*args):
        if args[:1] == ("api",):
            return "[]"
        raise subprocess.CalledProcessError(1, ["gh", *args], stderr="HTTP 500 (Internal Server Error)\n")

    monkeypatch.setattr(release, "_gh", fake_gh)
    with pytest.raises(subprocess.CalledProcessError):
        release._release_asset_names()


def test_release_asset_names_inaccessible_repo_raises(monkeypatch):
    def fake_gh(*args):
        raise subprocess.CalledProcessError(1, ["gh", *args], stderr="HTTP 404: Not Found\n")

    monkeypatch.setattr(release, "_gh", fake_gh)
    with pytest.raises(subprocess.CalledProcessError):
        release._release_asset_names()


def test_release_asset_names_does_not_substring_match_auth_error(monkeypatch):
    def fake_gh(*args):
        if args[:1] == ("api",):
            return "[]"
        raise subprocess.CalledProcessError(
            1,
            ["gh", *args],
            stderr="GraphQL: release not found because the token is unauthorized\n",
        )

    monkeypatch.setattr(release, "_gh", fake_gh)
    with pytest.raises(subprocess.CalledProcessError):
        release._release_asset_names()


def test_gh_prints_stderr_on_failure(monkeypatch, capsys):
    def fake_run(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0], stderr="gh: some auth error\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(subprocess.CalledProcessError):
        release._gh("release", "view", "testbed-state", "--json", "assets")
    assert "gh: some auth error" in capsys.readouterr().err


def test_gh_missing_binary_exits_with_install_pointer(monkeypatch):
    """No gh on PATH must be a clean exit with an install pointer, not a raw traceback."""

    def fake_run(*args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "gh")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(SystemExit) as exc:
        release._gh("release", "view", "testbed-state")
    assert str(exc.value) == ("gh CLI not found — install GitHub CLI (https://cli.github.com) and run `gh auth login`")


def test_resolve_state_explicit_ref_bypasses_lock(tmp_path):
    # tau2-retail has no lock entry and the lock pins other subjects to other
    # versions — an explicit ref must be returned verbatim, no lock consulted.
    lock = _write_lock(tmp_path)
    assert release.resolve_state("state-v2", subject="tau2-airline", lock_path=lock) == "state-v2"
    assert release.resolve_state("state-v2", subject="tau2-retail", lock_path=lock) == "state-v2"
    assert release.resolve_state("state-v2", subject=None, lock_path=tmp_path / "absent.lock") == "state-v2"


@pytest.mark.parametrize("bad", ["state-6", "latest", "v6", "state-v6.tar.zst", ""])
def test_resolve_state_rejects_malformed_ref(tmp_path, bad):
    with pytest.raises(SystemExit) as exc:
        release.resolve_state(bad, subject="tau2-airline", lock_path=_write_lock(tmp_path))
    message = str(exc.value)
    assert bad in message  # names the offender
    assert "state-v<N>" in message  # names the expected pattern
    # the file hint must match each command's real surface: analyze takes --state FILE,
    # restore takes the positional FILE (its --state is refs-only)
    assert "--state FILE" in message and "positional FILE" in message


def test_resolve_state_none_uses_subject_lock_entry(tmp_path):
    lock = _write_lock(tmp_path)
    assert release.resolve_state(None, subject="tau2-airline", lock_path=lock) == "state-v6"
    assert release.resolve_state(None, subject="nvq", lock_path=lock) == "state-v9"


def test_resolve_state_rejects_malformed_lock_pin(tmp_path):
    """A typo'd pin must die naming the entry, not flow into a doomed gh download."""
    lock = _write_lock(tmp_path, '[subjects]\ntau2-airline = "v6"\n')
    with pytest.raises(SystemExit) as exc:
        release.resolve_state(None, subject="tau2-airline", lock_path=lock)
    assert str(exc.value) == "state.lock entry for 'tau2-airline' is 'v6' — expected state-v<N> (e.g. state-v6)"


def test_resolve_state_none_missing_entry_exits_with_guidance(tmp_path):
    # resolve_state serves both analyze and restore, so the guidance names each
    # command's real surface instead of recommending flags one of them lacks.
    for lock_path in (_write_lock(tmp_path), tmp_path / "absent.lock"):
        with pytest.raises(SystemExit) as exc:
            release.resolve_state(None, subject="tau2-retail", lock_path=lock_path)
        assert str(exc.value) == (
            "no state.lock entry for subject 'tau2-retail' — add it under [subjects] "
            "after minting a fixture, or pass an explicit state "
            "(analyze: --live / --state <state-vN|FILE>; restore: FILE / --state state-vN)"
        )


def test_resolve_state_none_without_subject_exits(tmp_path):
    """Subject-agnostic callers (restore) have no lock entry — a None state must be loud."""
    with pytest.raises(SystemExit) as exc:
        release.resolve_state(None, subject=None, lock_path=_write_lock(tmp_path))
    assert "--state" in str(exc.value)


def test_download_ref_gh_args_and_return_path(tmp_path, monkeypatch):
    calls: list[tuple[str, ...]] = []

    def fake_gh(*args):
        calls.append(args)
        return ""

    monkeypatch.setattr(release, "_gh", fake_gh)
    dest = tmp_path / "dl"
    result = release.download_ref("state-v4", dest)
    assert calls == [
        (
            "release",
            "download",
            "testbed-state",
            "--pattern",
            "state-v4.tar.zst",
            "--dir",
            str(dest),
            "--clobber",
            "--repo",
            "NVIDIA-dev/NeMo-Optimizer",
        )
    ]
    assert dest.is_dir()
    assert result == tmp_path / "dl" / "state-v4.tar.zst"


def test_download_ref_reuses_cached_file_without_gh(tmp_path, monkeypatch, capsys):
    """Refs are immutable: an already-downloaded tarball is reused, gh never invoked."""
    dest = tmp_path / "dl"
    dest.mkdir()
    (dest / "state-v4.tar.zst").write_bytes(b"cached bytes")
    monkeypatch.setattr(release, "_gh", lambda *args: pytest.fail("cached ref must not invoke gh"))
    result = release.download_ref("state-v4", dest)
    assert result == dest / "state-v4.tar.zst"
    assert result.read_bytes() == b"cached bytes"
    assert "using cached state-v4.tar.zst" in capsys.readouterr().out
