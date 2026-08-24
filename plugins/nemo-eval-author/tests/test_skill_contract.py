# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Contract tests for the bundled Eval Author skills.

``eval-author`` is the core skill: it owns the standard, the vocabulary, the
boundaries, and the routing. ``eval-author-discover`` and
``eval-author-inspect-trace`` are sub-flows that carry the steps and defer the
standard to the core. Trace-source adapters belong to the inspection sub-flow.
All three ship as directories customers copy into their own repository, so
nothing at runtime enforces their promises.
These tests are that enforcement:

- The frontmatter of each skill carries every field ``docs/contributing/skills-spec.mdx`` requires.
- The core routes to every sub-flow, and each sub-flow points back at the core
  rather than restating the standard, which is how the two would drift.
- Only the sub-flow can execute. The core routes, so it gets no Bash.
- The bundled scripts depend on the standard library and Harbor only. Harbor is acceptable
  because a repository holding Harbor evaluations has Harbor by construction; a
  NeMo import would not be, and that is the boundary these tests defend.
- ``_ladder.py`` stays out of module scope in ``discover.py``, so a repository
  without Harbor gets an inventory instead of an ImportError.
- No bundled directory is named after a provider package. ``scripts/harbor/``
  would be importable as ``harbor``, which makes ``find_spec`` succeed on a
  machine with no Harbor and the probe claim an install that is not there.
- Discovery reports a valid suite runnable and names the rung a broken one fails.
- The bundled scripts write no files. ``SKILL.md`` tells the agent where to save
  the report, because where a file belongs in someone's repository is a judgement
  rather than a fact about their evals.

These tests compare the skill against this repository, never against Harbor's
rules. The skill reimplements no Harbor rule: it asks Harbor for every verdict,
so a Harbor change that tightens a rule flows through without a test change here.

Nothing here imports the platform, for the same reason the bundled scripts do not:
these skills are copied into someone else's repository and have to stand alone. The
tests that make Harbor judge a fixture suite skip when Harbor is absent, so the whole
file runs against nothing but pytest and PyYAML.
"""

import ast
import json
import os
import re
import subprocess
import sys
from importlib.util import find_spec
from pathlib import Path

import pytest
import yaml

_SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"
_CORE_DIR = _SKILLS_DIR / "eval-author"
_DISCOVER_FLOW_DIR = _SKILLS_DIR / "eval-author-discover"
_INSPECT_FLOW_DIR = _SKILLS_DIR / "eval-author-inspect-trace"
_SKILL_DIRS = (_CORE_DIR, _DISCOVER_FLOW_DIR, _INSPECT_FLOW_DIR)
_SUB_FLOW_DIRS = (_DISCOVER_FLOW_DIR, _INSPECT_FLOW_DIR)
_DISCOVER_SCRIPTS_DIR = _DISCOVER_FLOW_DIR / "scripts"
_INSPECT_SCRIPTS_DIR = _INSPECT_FLOW_DIR / "scripts"
_SCRIPT_DIRS = (_DISCOVER_SCRIPTS_DIR, _INSPECT_SCRIPTS_DIR)
_DISCOVER = _DISCOVER_SCRIPTS_DIR / "discover.py"
_LADDER = _DISCOVER_SCRIPTS_DIR / "providers" / "harbor" / "_ladder.py"

_REQUIRED_FRONTMATTER = (
    "name",
    "description",
    "triggers",
    "not-for",
    "compatibility",
    "maturity",
    "license",
    "user-invocable",
    "allowed-tools",
)
_MAX_BODY_LINES = 500

# Matches the core skill name but not a longer name that starts with it, so a
# reference to eval-author-discover cannot pass for a reference to eval-author.
_CORE_REFERENCE = re.compile(rf"\b{re.escape(_CORE_DIR.name)}\b(?!-)")

# Only the tests that make Harbor judge a fixture suite need Harbor. Skipping rather
# than failing is what lets this file run wherever the skills themselves run.
_needs_harbor = pytest.mark.skipif(
    find_spec("harbor") is None, reason="Harbor is not installed, so it can judge nothing"
)

# Root reads a mode-000 file regardless, so the failure these tests stage cannot
# happen there and the tests would pass without proving anything.
_needs_unreadable_files = pytest.mark.skipif(
    not hasattr(os, "geteuid") or os.geteuid() == 0,
    reason="this user can read a file whatever its mode, so unreadability cannot be staged",
)

# Harbor brings these in, so a bundled script may name them. Nothing else outside
# the standard library may appear.
_PERMITTED_THIRD_PARTY = frozenset({"harbor", "pydantic", "yaml"})


def _not_for_names(frontmatter: dict) -> set[str]:
    """Return the skill names in not-for, dropping the parenthetical reason."""
    return {entry.split("(", 1)[0].strip() for entry in frontmatter["not-for"]}


def _frontmatter_and_body(skill_dir: Path) -> tuple[dict, str]:
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{skill_dir.name}/SKILL.md must open with YAML frontmatter"
    _, frontmatter, body = text.split("---\n", 2)
    return yaml.safe_load(frontmatter), body


def _bundled_scripts() -> list[Path]:
    """Return every bundled module, including the ones under providers/."""
    return sorted(
        path
        for scripts_dir in _SCRIPT_DIRS
        if scripts_dir.exists()
        for path in scripts_dir.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def _local_roots(path: Path) -> set[str]:
    """Return the names a bundled module can import from its scripts directory."""
    scripts_dir = next(root for root in _SCRIPT_DIRS if path.is_relative_to(root))
    return {item.stem if item.is_file() else item.name for item in scripts_dir.iterdir()} | {
        item.stem for item in scripts_dir.rglob("*.py")
    }


def _imported_roots(path: Path) -> set[str]:
    """Return the root package of every import in one module."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module] if node.module and not node.level else []
        else:
            continue
        roots.update(name.split(".")[0] for name in names)
    return roots


def _run_discover(repo: Path, *args: str, with_harbor: bool = True) -> tuple[int, dict]:
    """Run discover.py as the skill documents it, and parse its JSON.

    ``with_harbor=False`` passes ``-S``, which drops site-packages from the path
    so Harbor and PyYAML are both unimportable. That reproduces a customer
    repository with no Harbor install without needing a second interpreter.
    """
    command = [sys.executable, *([] if with_harbor else ["-S"]), str(_DISCOVER), "--repo", str(repo), *args]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.stdout, f"discover.py printed nothing; stderr:\n{result.stderr}"
    return result.returncode, json.loads(result.stdout)


def _write_task(task_dir: Path, *, name: str = "smoke/generated") -> None:
    """Write a Harbor task that mirrors the canonical prebuilt-image layout.

    ``environment/`` has to exist even though the image is prebuilt, because
    ``Task.is_valid_dir`` checks for the directory before reading the config.
    """
    (task_dir / "tests").mkdir(parents=True)
    (task_dir / "environment").mkdir()
    (task_dir / "task.toml").write_text(
        'schema_version = "1.1"\n'
        "\n[task]\n"
        f'name = "{name}"\n'
        'authors = [{ name = "NVIDIA" }]\n'
        "\n[agent]\ntimeout_sec = 120.0\n"
        "\n[verifier]\ntimeout_sec = 60.0\n"
        '\n[environment]\ndocker_image = "smoke-agent-env:latest"\ncpus = 1\nmemory_mb = 1024\n',
        encoding="utf-8",
    )
    (task_dir / "instruction.md").write_text("Look up the total hours for Ada.\n", encoding="utf-8")
    (task_dir / "tests" / "test.sh").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")


@pytest.fixture
def suite(tmp_path: Path) -> Path:
    """Build a repository with one valid task and one Harbor job config."""
    _write_task(tmp_path / "dataset" / "task-one")
    (tmp_path / "harbor-job.yaml").write_text(
        "job_name: fixture\ndatasets:\n  - path: ./dataset\nagents:\n  - name: oracle\n",
        encoding="utf-8",
    )
    return tmp_path


def _tree_state(root: Path) -> dict[str, bytes | None]:
    """Map every path under root to its bytes, so an in-place edit is visible.

    Comparing names alone cannot catch a script that rewrote a file that was
    already there, which is the promise this is here to hold.
    """
    return {
        path.relative_to(root).as_posix(): path.read_bytes() if path.is_file() else None for path in root.rglob("*")
    }


def _named(report: dict, name: str) -> dict:
    """Return one check by name, failing loudly when the ladder never ran it."""
    found = next((check for check in report["checks"] if check["name"] == name), None)
    assert found is not None, f"no {name!r} check in report; ran {[c['name'] for c in report['checks']]}"
    return found


@pytest.mark.parametrize("skill_dir", _SKILL_DIRS, ids=lambda path: path.name)
def test_frontmatter_carries_every_required_field(skill_dir: Path) -> None:
    frontmatter, _ = _frontmatter_and_body(skill_dir)
    missing = [field for field in _REQUIRED_FRONTMATTER if field not in frontmatter]
    assert not missing, f"{skill_dir.name} frontmatter is missing {missing}"
    assert frontmatter["name"] == skill_dir.name, "frontmatter name must match the skill directory name"
    assert frontmatter["maturity"] in {"alpha", "beta", "active", "deprecated"}
    assert isinstance(frontmatter["user-invocable"], bool)
    assert len(frontmatter["triggers"]) >= 3, "the routing audit needs at least three trigger phrases"
    assert len(frontmatter["not-for"]) >= 2, "not-for needs at least two sibling skills to prevent collisions"


@pytest.mark.parametrize("skill_dir", _SKILL_DIRS, ids=lambda path: path.name)
def test_no_skill_can_edit_what_it_did_not_write(skill_dir: Path) -> None:
    """Eval Author creates its own report and changes nothing that was already there.

    ``Write`` covers the discovery report, which is the one artifact a sub-flow
    leaves behind. ``Edit`` would let it rewrite files that predate it, which is the
    permission customers declined to grant and the reason these ship as skills.
    """
    frontmatter, _ = _frontmatter_and_body(skill_dir)
    tools = set(frontmatter["allowed-tools"])
    assert not {"Edit", "MultiEdit", "NotebookEdit"} & tools, (
        f"{skill_dir.name} edits nothing that predates it, so {sorted(tools)} is too broad"
    )


def test_the_core_routes_and_the_sub_flow_executes() -> None:
    """The core only picks a sub-flow, so it neither runs nor saves anything."""
    core_tools = set(_frontmatter_and_body(_CORE_DIR)[0]["allowed-tools"])
    assert not {"Bash", "Write"} & core_tools, f"the core routes and explains; {sorted(core_tools)} is too broad"
    for skill_dir in _SUB_FLOW_DIRS:
        tools = set(_frontmatter_and_body(skill_dir)[0]["allowed-tools"])
        assert {"Bash", "Write"} <= tools, f"{skill_dir.name} runs a script and saves a report; it has {sorted(tools)}"


def test_the_core_names_every_sub_flow() -> None:
    """A sub-flow the core never mentions cannot be routed to."""
    _, body = _frontmatter_and_body(_CORE_DIR)
    for skill_dir in _SUB_FLOW_DIRS:
        assert skill_dir.name in body, f"the core does not route to {skill_dir.name}"


def test_the_core_treats_trace_sources_as_pluggable() -> None:
    frontmatter, body = _frontmatter_and_body(_CORE_DIR)
    core_text = json.dumps(frontmatter) + body

    assert "trace source" in core_text.lower()
    assert "Intake" not in core_text


def test_inspect_flow_selects_source_guidance_from_a_qualified_reference() -> None:
    frontmatter, body = _frontmatter_and_body(_INSPECT_FLOW_DIR)
    inspect_text = json.dumps(frontmatter) + body
    lower_body = body.lower()

    assert "source-qualified" in inspect_text
    assert "`references/intake.md`" in body
    assert "bare trace" in lower_body and "reject" in lower_body


def test_the_entry_point_owns_no_source_specific_arguments_or_internals() -> None:
    """The entry point names one adapter function; the source owns its own flags and client."""
    entry_point = (_INSPECT_SCRIPTS_DIR / "inspect_trace.py").read_text(encoding="utf-8")

    for detail in ("--workspace", "NMP_BASE_URL", "NMP_ACCESS_TOKEN", "IntakeClient", "IntakeError", "read_trace"):
        assert detail not in entry_point


@pytest.mark.parametrize("skill_dir", _SUB_FLOW_DIRS, ids=lambda path: path.name)
def test_each_sub_flow_defers_to_the_core(skill_dir: Path) -> None:
    """A sub-flow points at the core rather than restating the standard itself.

    Restating it is how the two drift: the copy in the sub-flow gets edited and the
    core keeps saying something else. The match rejects a bare prefix, so naming
    ``eval-author-discover`` does not count as pointing at ``eval-author``.
    """
    frontmatter, body = _frontmatter_and_body(skill_dir)
    assert _CORE_REFERENCE.search(body), f"{skill_dir.name} must point at {_CORE_DIR.name} for the standard"
    assert _CORE_DIR.name in _not_for_names(frontmatter), (
        f"{skill_dir.name} must name {_CORE_DIR.name} in not-for so the router can tell them apart"
    )


@pytest.mark.parametrize("skill_dir", _SKILL_DIRS, ids=lambda path: path.name)
def test_skill_body_stays_within_the_line_budget(skill_dir: Path) -> None:
    _, body = _frontmatter_and_body(skill_dir)
    line_count = len(body.splitlines())
    assert line_count <= _MAX_BODY_LINES, (
        f"{skill_dir.name} body is {line_count} lines, over the {_MAX_BODY_LINES} budget"
    )


def test_inspect_flow_requires_neutral_evidence_based_reporting() -> None:
    _, body = _frontmatter_and_body(_INSPECT_FLOW_DIR)

    for value in ("`success`", "`failure`", "`unknown`"):
        assert value in body
    for category in ("`behavior`", "`issue`", "`recovery`", "`uncertainty`"):
        assert category in body
    for requirement in ("span ID", "path and symbol", '"overview"', "`report_path`", ".eval-author/traces/"):
        assert requirement in body
    assert "invent an" in body


def test_every_bundled_path_the_skill_names_exists() -> None:
    expected = (
        (
            _DISCOVER_FLOW_DIR,
            _DISCOVER_FLOW_DIR / "SKILL.md",
            (
                "scripts/discover.py",
                "scripts/_checks.py",
                "scripts/providers/harbor/_probe.py",
                "scripts/providers/harbor/_inventory.py",
                "scripts/providers/harbor/_ladder.py",
            ),
        ),
        (
            _INSPECT_FLOW_DIR,
            _INSPECT_FLOW_DIR / "SKILL.md",
            (
                "scripts/inspect_trace.py",
                "scripts/overview.py",
                "references/intake.md",
            ),
        ),
        (
            _INSPECT_FLOW_DIR,
            _INSPECT_FLOW_DIR / "references" / "intake.md",
            (
                "scripts/sources/intake/adapter.py",
                "scripts/sources/intake/_http.py",
                "scripts/sources/intake/traces.py",
                "scripts/sources/intake/reader.py",
            ),
        ),
    )
    for skill_dir, document, paths in expected:
        body = document.read_text(encoding="utf-8")
        for relative in paths:
            assert relative in body, f"{document.relative_to(skill_dir)} no longer documents {relative}"
            assert (skill_dir / relative).exists(), f"{document.relative_to(skill_dir)} names missing {relative}"


def test_bundled_scripts_respect_each_flow_dependency_boundary() -> None:
    """Only discovery can use Harbor packages; trace-source scripts stay dependency-free."""
    offenders: dict[str, set[str]] = {}
    for path in _bundled_scripts():
        permitted = _local_roots(path) | sys.stdlib_module_names
        if path.is_relative_to(_DISCOVER_SCRIPTS_DIR):
            permitted.update(_PERMITTED_THIRD_PARTY)
        found = {root for root in _imported_roots(path) if root not in permitted}
        if found:
            offenders[path.name] = found
    assert not offenders, (
        "Bundled scripts exceeded their standard-library, local-module, or discovery-provider boundary: "
        + "; ".join(f"{filename} imports {sorted(names)}" for filename, names in sorted(offenders.items()))
    )


def test_no_bundled_directory_is_named_after_a_provider_package() -> None:
    """The trap that makes a literal ``scripts/harbor/`` unusable.

    A directory on the path named ``harbor`` is importable as a namespace package.
    On a machine with no Harbor installed that makes ``find_spec("harbor")``
    succeed, so the probe reports an install that is not there and the ladder then
    fails on import. Provider code sits one level down for exactly this reason.
    """
    collisions = {
        root
        for scripts_dir in _SCRIPT_DIRS
        if scripts_dir.exists()
        for root in _local_roots(next(scripts_dir.rglob("*.py"), scripts_dir))
        if root in _PERMITTED_THIRD_PARTY
    }
    assert not collisions, (
        f"{sorted(collisions)} shadows a package the skill imports; "
        "keep it under scripts/providers/ rather than directly in scripts/"
    )


def test_only_the_ladder_imports_harbor() -> None:
    """Every other module must keep working when Harbor is absent."""
    assert "harbor" in _imported_roots(_LADDER), "the ladder is the Harbor boundary and must import Harbor"
    for path in _bundled_scripts():
        if path == _LADDER:
            continue
        assert "harbor" not in _imported_roots(path), f"{path.name} imports Harbor; move that call behind the probe"


def test_discover_defers_the_ladder_import_to_call_time() -> None:
    """A module-scope ladder import would break every Harbor-free repository."""
    tree = ast.parse(_DISCOVER.read_text(encoding="utf-8"), filename=str(_DISCOVER))
    module_scope: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            module_scope.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module_scope.update(alias.name for alias in node.names)
            if node.module:
                module_scope.add(node.module)
    named = sorted(name for name in module_scope if "_ladder" in name)
    assert not named, f"discover.py imports {named} at module scope; move it inside a function, after the probe"


@_needs_harbor
def test_discover_proves_a_valid_suite_runnable(suite: Path) -> None:
    code, report = _run_discover(suite)

    assert report["proven"] is True, f"Harbor must judge this report; runtime was {report['runtime']}"
    assert report["task_count"] == 1
    assert report["dataset_paths"] == ["dataset"]
    assert len(report["configs"]) == 1

    for name in ("schema", "resolution", "tasks", "coverage", "credentials", "agent"):
        check = _named(report, name)
        assert check["status"] == "pass", f"{name} failed: {check['message']}"
        assert check["proven"] is True

    backend = _named(report, "backend")
    if backend["status"] != "pass":
        pytest.skip(f"no environment backend available: {backend['message']}")
    assert code == 0
    assert report["runnable"] is True
    assert report["run_command"] == f"cd {suite} && harbor job start -c harbor-job.yaml"


@_needs_harbor
def test_discover_names_the_rung_a_broken_config_fails(suite: Path) -> None:
    """A dataset path that does not exist must fail resolution, not schema."""
    (suite / "harbor-job.yaml").write_text(
        "job_name: fixture\ndatasets:\n  - path: ./no-such-dataset\nagents:\n  - name: oracle\n",
        encoding="utf-8",
    )

    code, report = _run_discover(suite)

    assert code == 1
    assert report["runnable"] is False
    assert _named(report, "schema")["status"] == "pass", "the shape is valid; only the path is wrong"
    resolution = _named(report, "resolution")
    assert resolution["status"] == "fail"
    assert "no-such-dataset" in resolution["message"]


@_needs_harbor
def test_discover_names_an_unknown_agent(suite: Path) -> None:
    (suite / "harbor-job.yaml").write_text(
        "job_name: fixture\ndatasets:\n  - path: ./dataset\nagents:\n  - name: no-such-agent\n",
        encoding="utf-8",
    )

    code, report = _run_discover(suite)

    assert code == 1
    agent = _named(report, "agent")
    assert agent["status"] == "fail"
    assert "no-such-agent" in agent["message"]


@_needs_harbor
def test_discover_reports_required_host_variables(suite: Path) -> None:
    task_toml = suite / "dataset" / "task-one" / "task.toml"
    task_toml.write_text(
        task_toml.read_text(encoding="utf-8") + '\n[environment.env]\nACME_API_KEY = "${ACME_API_KEY}"\n',
        encoding="utf-8",
    )

    _, report = _run_discover(suite)

    credentials = _named(report, "credentials")
    assert credentials["status"] == "pass"
    assert "ACME_API_KEY" in credentials["message"]
    assert [item["name"] for item in report["configs"][0]["required_env_vars"]] == ["ACME_API_KEY"]


@_needs_harbor
def test_discover_reports_a_task_harbor_silently_dropped(suite: Path) -> None:
    """Harbor skips an unparseable task without raising, which coverage must catch."""
    broken = suite / "dataset" / "task-two"
    _write_task(broken)
    (broken / "task.toml").write_text("this is not valid toml = = =\n", encoding="utf-8")

    code, report = _run_discover(suite)

    assert code == 1
    coverage = _named(report, "coverage")
    assert coverage["status"] == "fail"
    assert "task-two" in coverage["message"]


def test_discover_marks_every_finding_unproven_without_harbor(suite: Path) -> None:
    """The promise that keeps an inventory from reading as evidence."""
    code, report = _run_discover(suite, with_harbor=False)

    assert code == 1, "no Harbor means no proof, so discovery cannot report success"
    assert report["proven"] is False
    assert report["runnable"] is False
    assert report["run_command"] is None
    assert report["runtime"]["harbor_importable"] is False

    harbor_check = _named(report, "harbor")
    assert harbor_check["status"] == "fail"
    assert harbor_check["severity"] == "required"
    assert harbor_check["hint"], "a missing Harbor must tell the user what to do"

    observed = [check for check in report["checks"] if check["name"] != "harbor"]
    assert observed, "an unproven inventory is still worth reporting"
    assert all(check["proven"] is False for check in observed), (
        f"these findings claim proof without Harbor: {[c['name'] for c in observed if c['proven']]}"
    )


def test_discover_finds_configs_without_pyyaml(suite: Path) -> None:
    """Without PyYAML the fallback still finds YAML configs, and says it cannot read them."""
    _, report = _run_discover(suite, with_harbor=False)

    assert [config["path"] for config in report["configs"]] == ["harbor-job.yaml"]
    parse = _named(report, "config-parse")
    assert parse["status"] == "fail"
    assert "harbor-job.yaml" in parse["message"]


def test_discovery_writes_no_files(suite: Path) -> None:
    """The scripts report and the agent saves, which is what makes the skill safe to run."""
    before = _tree_state(suite)

    _run_discover(suite)

    assert _tree_state(suite) == before


def test_discover_reports_a_config_pyyaml_cannot_parse(suite: Path) -> None:
    """Broken YAML is a finding, not a crash.

    A tab cannot start a YAML token, so PyYAML raises ``yaml.YAMLError``, which is
    not a ``ValueError``. Left uncaught it escaped the scan and took the whole run
    down with a traceback and no report at all. The file still names Harbor work,
    so it is reported through the same fallback that runs when PyYAML is absent.
    """
    (suite / "broken.yaml").write_text("datasets:\n\t- path: ./tabbed\n", encoding="utf-8")

    _, report = _run_discover(suite)

    assert "harbor-job.yaml" in [config["path"] for config in report["configs"]], (
        "one broken file must not hide the configs around it"
    )
    parse = _named(report, "config-parse")
    assert parse["status"] == "fail"
    assert "broken.yaml" in parse["message"]
    assert parse["hint"], "an unreadable config must tell the user what to do"


def test_discover_ignores_a_yaml_file_that_declares_no_harbor_work(suite: Path) -> None:
    """Broken YAML that names no datasets or tasks is somebody else's file."""
    (suite / "docker-compose.yaml").write_text("services:\n\t- broken\n", encoding="utf-8")

    _, report = _run_discover(suite)

    assert [config["path"] for config in report["configs"]] == ["harbor-job.yaml"]


@_needs_unreadable_files
def test_discover_reports_an_unreadable_ethos(suite: Path) -> None:
    """ETHOS.md is advisory, so failing to read it must not cost the whole report."""
    ethos = suite / "ETHOS.md"
    ethos.write_text("# doctrine\n", encoding="utf-8")
    ethos.chmod(0o000)
    try:
        _, report = _run_discover(suite, with_harbor=False)
    finally:
        ethos.chmod(0o644)

    assert report["ethos_path"] is None, "an unread file defines no doctrine"
    check = _named(report, "ethos")
    assert check["status"] == "warn"
    assert check["severity"] == "advisory"


@_needs_unreadable_files
def test_discover_keeps_an_unreadable_dataset_file_out_of_the_fingerprint(suite: Path) -> None:
    """One unreadable file must neither abort the fingerprint nor silently join it."""
    _, baseline = _run_discover(suite, with_harbor=False)

    blocked = suite / "dataset" / "task-one" / "blocked.bin"
    blocked.write_bytes(b"payload")
    blocked.chmod(0o000)
    try:
        _, report = _run_discover(suite, with_harbor=False)
    finally:
        blocked.chmod(0o644)

    assert report["input_file_count"] == baseline["input_file_count"]
    assert report["fingerprint"] == baseline["fingerprint"]


def test_discover_fails_with_a_hint_when_the_path_is_missing(tmp_path: Path) -> None:
    code, report = _run_discover(tmp_path / "nowhere")
    assert code == 1
    assert "error" in report
    assert report["hint"]
