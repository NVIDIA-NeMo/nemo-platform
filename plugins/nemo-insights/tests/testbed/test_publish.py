# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""`testbed publish` — laptop-first mint/upload/catalog for export bundles."""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from testbed import cli, publish, release

REPO_ROOT = Path(__file__).resolve().parents[2]
PLATFORM_ROOT = REPO_ROOT.parents[1]

MANIFEST = {
    "kind": "testbed-export",
    "subjects": ["tau2-airline"],
    "workspaces": ["tau2-airline", "tau2-airline-oracle"],
    "counts": {
        "tau2-airline": {"spans": 450, "annotations": 3, "evaluator_results": 30},
        "tau2-airline-oracle": {"spans": 456, "annotations": 1, "evaluator_results": 30},
    },
    "min_start_time": "2026-07-01T00:00:00+00:00",
    "max_start_time": "2026-07-02T00:00:00+00:00",
    "source_url": "http://localhost:8080",
}

RUN_ENV = {"GITHUB_RUN_ID": "99", "GITHUB_REPOSITORY": "o/r"}


def _make_bundle(path: Path, manifest: dict = MANIFEST) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=path.parent) as tmp:
        state = Path(tmp) / "state"
        state.mkdir(parents=True)
        (state / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        subprocess.run(["tar", "--zstd", "-cf", str(path), "-C", tmp, "state"], check=True)
    return path


# --------------------------------------------------------------------------- #
# catalog row: contents from the bundle manifest; minted-by run link | laptop
# --------------------------------------------------------------------------- #


def test_catalog_row_contents_from_manifest_run_variant():
    row = publish.catalog_row("state-v6", MANIFEST, reason="tau2 bump", env=RUN_ENV)
    assert row == (
        "| state-v6 | tau2-airline — 906 spans, 4 annotations, 60 evaluator results "
        "| tau2 bump | [run 99](https://github.com/o/r/actions/runs/99) |"
    )


def test_catalog_row_laptop_variant(monkeypatch):
    monkeypatch.setattr("getpass.getuser", lambda: "ada")
    row = publish.catalog_row("state-v6", MANIFEST, reason="", env={})
    assert row.endswith("| — | laptop (ada) |")  # empty reason -> em dash; no run env -> laptop


def test_minted_by_requires_both_run_env_vars(monkeypatch):
    monkeypatch.setattr("getpass.getuser", lambda: "ada")
    assert publish.minted_by(RUN_ENV).startswith("[run 99]")
    assert publish.minted_by({"GITHUB_RUN_ID": "99"}) == "laptop (ada)"
    assert publish.minted_by({"GITHUB_REPOSITORY": "o/r"}) == "laptop (ada)"


def test_contents_column_empty_manifest_is_honest():
    assert publish.contents_column({}) == "? — 0 spans, 0 annotations, 0 evaluator results"


def test_catalog_row_sanitizes_pipes_in_reason():
    """A raw `|` in --reason would add phantom columns to the catalog table."""
    row = publish.catalog_row("state-v6", MANIFEST, reason="tau2 bump | with pipe", env=RUN_ENV)
    assert "tau2 bump \\| with pipe" in row
    # the row still parses as exactly 4 cells (escaped pipes don't split)
    assert len(re.split(r"(?<!\\)\|", row)) == 6


def test_catalog_row_sanitizes_newlines_in_reason():
    """A newline in --reason would terminate the GH release table, hiding all older rows."""
    row = publish.catalog_row("state-v6", MANIFEST, reason="line one\nline\ttwo\r\n  spaced", env=RUN_ENV)
    assert "\n" not in row and "\r" not in row and "\t" not in row
    assert "| line one line two spaced |" in row  # whitespace runs collapse to single spaces


def test_catalog_row_whitespace_only_reason_falls_back_to_dash():
    row = publish.catalog_row("state-v6", MANIFEST, reason=" \n\t ", env=RUN_ENV)
    assert "| — |" in row


# --------------------------------------------------------------------------- #
# catalog insert: marker sits ABOVE the table; new rows go right after the
# header separator (a non-| line inside a GH release table breaks rendering)
# --------------------------------------------------------------------------- #


def test_insert_catalog_row_newest_first_inside_table():
    body = (
        "intro\n\n" + publish.CATALOG_MARKER + "\n"
        "| Version | Contents | Why it exists | Minted by |\n|---|---|---|---|\n| state-v1 | old | x | y |\n"
    )
    out = publish.insert_catalog_row(body, "| state-v2 | new | x | y |")
    assert out.index("state-v2") < out.index("state-v1")
    # the new row must directly follow the separator — no line may split the table
    lines = out.splitlines()
    sep = next(i for i, ln in enumerate(lines) if ln.startswith("|---"))
    assert lines[sep + 1].startswith("| state-v2 ")


def test_insert_catalog_row_without_marker_appends_section():
    out = publish.insert_catalog_row("hand-edited notes", "| state-v2 | new | x | y |")
    assert publish.CATALOG_MARKER in out
    assert out.rstrip().endswith("| state-v2 | new | x | y |")
    # marker precedes the table header so the table itself stays contiguous
    assert out.index(publish.CATALOG_MARKER) < out.index("| Version |")


# --------------------------------------------------------------------------- #
# publish flow: mint next ref -> copy -> ensure release -> upload -> catalog
# --------------------------------------------------------------------------- #


@pytest.fixture
def fake_gh(monkeypatch):
    """Stub release._gh with a plausible testbed-state release; record every call."""
    state = {
        "calls": [],
        "assets": ["state-v6.tar.zst"],
        "body": (
            "notes\n\n" + publish.CATALOG_MARKER + "\n"
            "| Version | Contents | Why it exists | Minted by |\n|---|---|---|---|\n| state-v6 | old | x | y |\n"
        ),
    }

    def gh(*args):
        state["calls"].append(args)
        if args[:2] == ("release", "view") and "--json" in args:
            field = args[args.index("--json") + 1]
            if field == "assets":
                return json.dumps({"assets": [{"name": n} for n in state["assets"]]})
            if field == "body":
                return json.dumps({"body": state["body"]})
        if args[:2] == ("release", "edit"):
            state["body"] = args[args.index("--notes") + 1]
        return ""

    monkeypatch.setattr(release, "_gh", gh)
    return state


def test_publish_mints_next_ref_uploads_and_prepends_row(fake_gh, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("getpass.getuser", lambda: "ada")
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.delenv("TESTBED_STATE_REPO", raising=False)
    bundle = _make_bundle(tmp_path / "candidate.tar.zst")
    ref = publish.publish(bundle, reason="fresh corpus", env={})
    assert ref == "state-v7"
    assert (tmp_path / "state-v7.tar.zst").is_file()  # candidate copied to the ref name
    uploads = [c for c in fake_gh["calls"] if c[:2] == ("release", "upload")]
    assert uploads == [
        (
            "release",
            "upload",
            release.RELEASE_TAG,
            str(tmp_path / "state-v7.tar.zst"),
            "--clobber",
            "--repo",
            release.DEFAULT_STATE_REPO,
        )
    ]
    assert all(
        call[-2:] == ("--repo", release.DEFAULT_STATE_REPO) for call in fake_gh["calls"] if call[:1] == ("release",)
    )
    # new row lands right under the header separator, above the old row
    assert fake_gh["body"].index("state-v7") < fake_gh["body"].index("| state-v6 |")
    assert "laptop (ada)" in fake_gh["body"]
    assert "fresh corpus" in fake_gh["body"]
    assert "published state-v7" in capsys.readouterr().out


def test_publish_creates_release_when_missing(fake_gh, tmp_path, monkeypatch):
    def view_fails(*args):
        if args[:2] == ("release", "view") and "--json" not in args:
            raise subprocess.CalledProcessError(1, ["gh", *args], stderr="release not found")
        return original_gh(*args)

    original_gh = release._gh
    monkeypatch.setattr(release, "_gh", view_fails)
    publish.publish(_make_bundle(tmp_path / "c.tar.zst"), reason="", env={})
    creates = [c for c in fake_gh["calls"] if c[:2] == ("release", "create")]
    assert len(creates) == 1 and release.RELEASE_TAG in creates[0]


def test_publish_does_not_create_release_after_auth_failure(fake_gh, tmp_path, monkeypatch):
    original_gh = release._gh

    def view_fails(*args):
        if args[:2] == ("release", "view") and "--json" not in args:
            raise subprocess.CalledProcessError(1, ["gh", *args], stderr="HTTP 403: Resource not accessible\n")
        return original_gh(*args)

    monkeypatch.setattr(release, "_gh", view_fails)
    with pytest.raises(subprocess.CalledProcessError):
        publish.publish(_make_bundle(tmp_path / "c.tar.zst"), reason="", env={})
    assert not any(call[:2] == ("release", "create") for call in fake_gh["calls"])
    assert not any(call[:2] == ("release", "upload") for call in fake_gh["calls"])


def test_publish_writes_github_output_only_when_env_set(fake_gh, tmp_path):
    out_file = tmp_path / "gh_output"
    publish.publish(_make_bundle(tmp_path / "a.tar.zst"), reason="", env={"GITHUB_OUTPUT": str(out_file)})
    assert out_file.read_text(encoding="utf-8") == "state_ref=state-v7\n"
    publish.publish(_make_bundle(tmp_path / "b.tar.zst"), reason="", env={})  # no env -> nothing written


def test_publish_reason_falls_back_to_candidate_manifest(fake_gh, tmp_path):
    manifest = {**MANIFEST, "reason": "captured during produce"}
    publish.publish(_make_bundle(tmp_path / "candidate.tar.zst", manifest=manifest), reason=None, env={})

    assert "captured during produce" in fake_gh["body"]


def test_publish_rejects_non_export_bundles(fake_gh, tmp_path):
    legacy = _make_bundle(tmp_path / "legacy.tar.zst", manifest={"created_at": "2026-01-01"})
    with pytest.raises(SystemExit) as exc:
        publish.publish(legacy, reason="", env={})
    assert "testbed-export" in str(exc.value)
    assert all(c[:2] != ("release", "upload") for c in fake_gh["calls"])  # nothing uploaded


def test_publish_missing_bundle_exits(fake_gh, tmp_path):
    with pytest.raises(SystemExit) as exc:
        publish.publish(tmp_path / "nope.tar.zst", reason="", env={})
    assert "no such bundle" in str(exc.value)


# --------------------------------------------------------------------------- #
# CLI surface: testbed publish FILE [--reason TEXT] (--base URL | --no-verify)
# minting is immutable, so publish enforces verify-or-explicit-skip
# --------------------------------------------------------------------------- #


def test_cli_publish_reason_flag_wins_over_env(fake_gh, tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.setenv("REASON", "from-env")
    bundle = _make_bundle(tmp_path / "c.tar.zst")
    monkeypatch.setattr(sys, "argv", ["testbed", "publish", str(bundle), "--no-verify", "--reason", "from-flag"])
    cli.main()
    assert "from-flag" in fake_gh["body"]
    assert "from-env" not in fake_gh["body"]


def test_cli_publish_reason_falls_back_to_env(fake_gh, tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.setenv("REASON", "from-env")
    bundle = _make_bundle(tmp_path / "c.tar.zst")
    monkeypatch.setattr(sys, "argv", ["testbed", "publish", str(bundle), "--no-verify"])
    cli.main()
    assert "from-env" in fake_gh["body"]


def test_cli_publish_without_verify_flags_exits_with_guidance(fake_gh, tmp_path, monkeypatch):
    """Bare `publish FILE` must refuse: minting is immutable, verify first."""
    bundle = _make_bundle(tmp_path / "c.tar.zst")
    monkeypatch.setattr(sys, "argv", ["testbed", "publish", str(bundle)])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    message = str(exc.value)
    assert "--base" in message and "--no-verify" in message and "immutable" in message
    assert all(c[:2] != ("release", "upload") for c in fake_gh["calls"])  # nothing minted


def test_cli_publish_no_verify_mints_without_guard(fake_gh, tmp_path, monkeypatch, capsys):
    guard_calls: list = []
    monkeypatch.setattr(cli, "_run_roundtrip", lambda *a, **k: guard_calls.append(a))
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    bundle = _make_bundle(tmp_path / "c.tar.zst")
    monkeypatch.setattr(sys, "argv", ["testbed", "publish", str(bundle), "--no-verify"])
    cli.main()
    assert guard_calls == []  # guard skipped entirely
    assert any(c[:2] == ("release", "upload") for c in fake_gh["calls"])  # minted
    assert "round-trip guard" in capsys.readouterr().out  # one-line skip notice


def test_cli_publish_base_runs_guard_before_mint(fake_gh, tmp_path, monkeypatch):
    order: list[tuple] = []
    monkeypatch.setattr(
        cli,
        "_run_roundtrip",
        lambda bundle, base, platform_root: order.append(("guard", bundle, base, platform_root)),
    )
    real_publish = publish.publish
    monkeypatch.setattr(
        publish,
        "publish",
        lambda *a, **k: (order.append(("publish",)), real_publish(*a, **k))[1],
    )
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    bundle = _make_bundle(tmp_path / "c.tar.zst")
    monkeypatch.setattr(sys, "argv", ["testbed", "publish", str(bundle), "--base", "http://ci-host:8080"])
    cli.main()
    assert [step[0] for step in order] == ["guard", "publish"]  # guard strictly before mint
    assert order[0][1:] == (bundle, "http://ci-host:8080", None)


def test_cli_publish_guard_failure_prevents_mint(fake_gh, tmp_path, monkeypatch):
    def failing_guard(bundle, base, platform_root):
        sys.exit("round-trip guard: 1 mismatch(es)")

    monkeypatch.setattr(cli, "_run_roundtrip", failing_guard)
    bundle = _make_bundle(tmp_path / "c.tar.zst")
    monkeypatch.setattr(sys, "argv", ["testbed", "publish", str(bundle), "--base", "http://ci-host:8080"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert "mismatch" in str(exc.value)
    assert all(c[:2] != ("release", "upload") for c in fake_gh["calls"])  # never minted


def test_publish_module_has_no_main(tmp_path):
    """`python -m testbed.publish` is not a mint path: the CLI's verify-or-explicit-skip
    gate (`testbed publish --base|--no-verify`) cannot be bypassed by running the module."""
    assert not hasattr(publish, "main")
    assert "__main__" not in Path(publish.__file__).read_text(encoding="utf-8")
    # Running the module does nothing: exit 0, no output, and no gh invocation
    # (a marker-dropping fake gh shadows the real one for the subprocess).
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    marker = tmp_path / "gh-called"
    (fake_bin / "gh").write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
    (fake_bin / "gh").chmod(0o755)
    bundle = _make_bundle(tmp_path / "candidate.tar.zst")
    proc = subprocess.run(
        [sys.executable, "-m", "testbed.publish", str(bundle), "--reason", "bypass attempt"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""
    assert not marker.exists()  # gh never ran — nothing was minted


def test_cli_publish_base_and_no_verify_conflict(fake_gh, tmp_path, monkeypatch, capsys):
    """--base (verify) and --no-verify (skip) contradict each other — argparse rejects."""
    bundle = _make_bundle(tmp_path / "c.tar.zst")
    monkeypatch.setattr(
        sys,
        "argv",
        ["testbed", "publish", str(bundle), "--base", "http://x:8080", "--no-verify"],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2  # argparse mutual-exclusion error
    assert all(c[:2] != ("release", "upload") for c in fake_gh["calls"])


def test_workflow_protects_all_secrets_and_exports_state_repository():
    workflow = (PLATFORM_ROOT / ".github" / "workflows" / "insights-testbed.yml").read_text(encoding="utf-8")
    produce_job, analyze_job = workflow.split("\n  produce:\n", 1)[1].split("\n  analyze:\n", 1)

    assert "    environment: insights-testbed\n" in produce_job
    assert "    environment: insights-testbed\n" in analyze_job
    assert "TESTBED_STATE_REPO: ${{ vars.TESTBED_STATE_REPO || 'NVIDIA-dev/NeMo-Optimizer' }}" in workflow
