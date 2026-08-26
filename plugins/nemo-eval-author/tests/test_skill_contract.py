# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Contract tests for the bundled Eval Author skills.

``eval-author`` is the core skill: it owns the standard, the vocabulary, the
boundaries, and the routing. ``eval-author-discover`` and ``eval-author-audit``
bundle scripts. ``eval-author-inspect-trace`` uses the provider's supported
commands. Sub-flows defer the standard to the core.

These tests are that enforcement:

- The frontmatter of each skill carries every field ``docs/contributing/skills-spec.mdx`` requires.
- The core routes to every sub-flow, and each sub-flow points back at the core
  rather than restating the standard, which is how the two would drift.
- Only the sub-flow can execute. The core routes, so it gets no Bash.
- The bundled scripts depend on Harbor and nothing else. Harbor is acceptable
  because a repository holding Harbor evaluations has Harbor by construction; a
  NeMo import would not be, and that is the boundary these tests defend.
- ``_ladder.py`` stays out of module scope in ``discover.py``, so a repository
  without Harbor gets an inventory instead of an ImportError.
- No bundled directory is named after a provider package. ``scripts/harbor/``
  would be importable as ``harbor``, which makes ``find_spec`` succeed on a
  machine with no Harbor and the probe claim an install that is not there.
- Discovery reports a valid suite runnable and names the rung a broken one fails.
- Discovery scripts write no files, and audit generation writes only the requested
  audit output under ``.eval-author/``.

These tests compare the skill against this repository, never against Harbor's
rules. The skill reimplements no Harbor rule: it asks Harbor for every verdict,
so a Harbor change that tightens a rule flows through without a test change here.

Nothing here imports the platform, for the same reason the bundled scripts do not:
these skills are copied into someone else's repository and have to stand alone. The
tests that make Harbor judge a fixture suite skip when Harbor is absent, so the whole
file runs against nothing but pytest, PyYAML, and jsonschema.
"""

import ast
import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from importlib.util import find_spec
from pathlib import Path
from typing import Any

import pytest
import yaml

_SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"
_CORE_DIR = _SKILLS_DIR / "eval-author"
_DISCOVER_DIR = _SKILLS_DIR / "eval-author-discover"
_AUDIT_DIR = _SKILLS_DIR / "eval-author-audit"
_INSPECT_DIR = _SKILLS_DIR / "eval-author-inspect-trace"
_SKILL_DIRS = (_CORE_DIR, _DISCOVER_DIR, _AUDIT_DIR, _INSPECT_DIR)
_SUB_FLOW_DIRS = (_DISCOVER_DIR, _AUDIT_DIR, _INSPECT_DIR)
_DISCOVER_SCRIPTS_DIR = _DISCOVER_DIR / "scripts"
_AUDIT_SPEC_DIR = _AUDIT_DIR / "scripts" / "audit_spec"
_SCRIPT_DIRS = (_DISCOVER_SCRIPTS_DIR, _AUDIT_SPEC_DIR)
_DISCOVER = _DISCOVER_SCRIPTS_DIR / "discover.py"
_LADDER = _DISCOVER_SCRIPTS_DIR / "providers" / "harbor" / "_ladder.py"
_AUDIT_VALIDATE = _AUDIT_SPEC_DIR / "validate.py"
_AUDIT_GENERATE = _AUDIT_SPEC_DIR / "generate.py"
_AUDIT_MEASURE = _AUDIT_SPEC_DIR / "measure.py"
_AUDIT_TEMPLATE = _AUDIT_DIR / "templates" / "audit.md"
_AUDIT_JSON_SCHEMA = _AUDIT_DIR / "schemas" / "audit.schema.json"
_AUDIT_COVERAGE_JSON_SCHEMA = _AUDIT_DIR / "schemas" / "audit_coverage.schema.json"
_AUDIT_TOOL_CALLS_DETAILS_JSON_SCHEMA = _AUDIT_DIR / "schemas" / "audit_tool_calls_details.schema.json"
_AUDIT_COVERAGE_EXAMPLE = _AUDIT_DIR / "examples" / "schemas" / "tool_calls.coverage.json"
_AUDIT_TOOL_CALLS_DETAILS_EXAMPLE = _AUDIT_DIR / "examples" / "schemas" / "tool_calls.details.json"

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

# Bundled scripts may name only these third-party roots. Anything else would
# become a hidden dependency for repositories that copy the skill.
_PERMITTED_THIRD_PARTY = frozenset({"harbor", "jsonschema", "pydantic", "yaml"})


def _not_for_names(frontmatter: dict) -> set[str]:
    """Return the skill names in not-for, dropping the parenthetical reason."""
    return {entry.split("(", 1)[0].strip() for entry in frontmatter["not-for"]}


def _frontmatter_and_body(skill_dir: Path) -> tuple[dict, str]:
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{skill_dir.name}/SKILL.md must open with YAML frontmatter"
    _, frontmatter, body = text.split("---\n", 2)
    return yaml.safe_load(frontmatter), body


def _bundled_scripts(scripts_dir: Path | None = None) -> list[Path]:
    """Return every bundled module, including the ones under providers/."""
    roots = _SCRIPT_DIRS if scripts_dir is None else (scripts_dir,)
    return sorted(path for root in roots for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def _local_roots(scripts_dir: Path) -> set[str]:
    """Return the top-level names a bundled module can import from scripts/."""
    return {path.stem if path.is_file() else path.name for path in scripts_dir.iterdir()} | {
        path.stem for path in _bundled_scripts(scripts_dir)
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


def _run_json_script(
    script: Path,
    *args: str,
    python_args: tuple[str, ...] = (),
    env: dict[str, str] | None = None,
) -> tuple[int, dict, str]:
    """Run an audit script that emits JSON on stdout."""
    result = subprocess.run(
        [sys.executable, *python_args, str(script), *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.stdout, f"{script.name} printed nothing; stderr:\n{result.stderr}"
    return result.returncode, json.loads(result.stdout), result.stderr


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return f"sha256:{hashlib.file_digest(stream, 'sha256').hexdigest()}"


def _audit_payload(path: Path) -> dict:
    block = re.search(
        r"<!-- BEGIN:nemo-eval-author-audit:v1 -->\s*```yaml\n(?P<body>.*?)\n```\s*"
        r"<!-- END:nemo-eval-author-audit:v1 -->",
        path.read_text(encoding="utf-8"),
        re.DOTALL,
    )
    assert block is not None
    return yaml.safe_load(block.group("body"))


def _assert_literal_block_scalar(text: str, field: str, first_line: str) -> None:
    pattern = rf"(?:^|\n)(?:\s*-\s+|\s+){re.escape(field)}: \|[-+]?\n\s+{re.escape(first_line)}"
    assert re.search(pattern, text), text


def _template_payload() -> dict:
    block = re.search(
        r"<!-- BEGIN:nemo-eval-author-audit:v1 -->\s*```yaml\n(?P<body>.*?)\n```\s*"
        r"<!-- END:nemo-eval-author-audit:v1 -->",
        _AUDIT_TEMPLATE.read_text(encoding="utf-8"),
        re.DOTALL,
    )
    assert block is not None
    return yaml.safe_load(block.group("body"))


def _write_audit_items(path: Path, items: list[dict]) -> None:
    path.write_text(yaml.safe_dump({"items": items}), encoding="utf-8")


def _write_atif_trace(
    path: Path, *, tool_calls: list[str] | None = None, embedded_tool_calls: list[str] | None = None
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schema_version": "ATIF-v1.7",
        "session_id": "session-1",
        "trajectory_id": "root-trajectory",
        "agent": {"name": "example-agent", "version": "1.0.0"},
        "steps": [
            {"step_id": 1, "source": "user", "message": "Help me recover my account."},
            {
                "step_id": 2,
                "source": "agent",
                "message": "I will inspect the account.",
                "tool_calls": [
                    {"tool_call_id": f"root-call-{index}", "function_name": name, "arguments": {}}
                    for index, name in enumerate(tool_calls or [], start=1)
                ],
            },
        ],
    }
    if embedded_tool_calls:
        payload["subagent_trajectories"] = [
            {
                "schema_version": "ATIF-v1.7",
                "session_id": "session-1",
                "trajectory_id": "sub-trajectory",
                "agent": {"name": "helper-agent", "version": "1.0.0"},
                "steps": [
                    {
                        "step_id": 1,
                        "source": "agent",
                        "message": "Looking up the account.",
                        "tool_calls": [
                            {"tool_call_id": f"sub-call-{index}", "function_name": name, "arguments": {}}
                            for index, name in enumerate(embedded_tool_calls, start=1)
                        ],
                    }
                ],
            }
        ]
    path.write_text(json.dumps(payload), encoding="utf-8")


def _ticket_tool_item() -> dict:
    return {
        "kind": "tool",
        "name": "ticket.create",
        "description": "Creates a support ticket for issues requiring human follow-up.",
        "expected_use": "Used when self-service resolution cannot proceed.",
        "expected_failure_behavior": "If ticket creation fails, the agent explains the failure and avoids duplicates.",
        "evidence_required": [
            {
                "kind": "tool_call",
                "tool": "ticket.create",
                "description": "Trace shows a ticket.create call for an escalation.",
            }
        ],
    }


def _write_audit(tmp_path: Path, transform: Callable[[str], str] | None = None) -> Path:
    ethos = tmp_path / "ETHOS.md"
    ethos.write_text("# Ethos\n\n## Tools\n\n- customer.lookup\n", encoding="utf-8")

    audit_dir = tmp_path / ".eval-author"
    audit_dir.mkdir()
    audit = audit_dir / "audit.md"
    text = _AUDIT_TEMPLATE.read_text(encoding="utf-8").replace(
        'sha256: "sha256:<replace-with-64-hex-digest>"',
        f"sha256: {_digest(ethos)}",
    )
    if transform is not None:
        text = transform(text)
    audit.write_text(text, encoding="utf-8")
    return audit


def _run_script(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a bundled script and return the completed process."""
    return subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True, check=False)


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

    ``Write`` covers sub-flow artifacts under ``.eval-author/``. ``Edit`` would let
    it rewrite files that predate it, which is the permission customers declined to
    grant and the reason these ship as skills.
    """
    frontmatter, _ = _frontmatter_and_body(skill_dir)
    tools = set(frontmatter["allowed-tools"])
    assert not {"Edit", "MultiEdit", "NotebookEdit"} & tools, (
        f"{skill_dir.name} edits nothing that predates it, so {sorted(tools)} is too broad"
    )


def test_the_core_routes_and_the_sub_flow_executes() -> None:
    """The core only picks a sub-flow, so it neither runs nor saves anything."""
    core_tools = set(_frontmatter_and_body(_CORE_DIR)[0]["allowed-tools"])
    discover_tools = set(_frontmatter_and_body(_DISCOVER_DIR)[0]["allowed-tools"])
    audit_tools = set(_frontmatter_and_body(_AUDIT_DIR)[0]["allowed-tools"])
    inspect_tools = set(_frontmatter_and_body(_INSPECT_DIR)[0]["allowed-tools"])

    assert not {"Bash", "Write"} & core_tools, f"the core routes and explains; {sorted(core_tools)} is too broad"
    assert {"Bash", "Write"} <= discover_tools, (
        f"{_DISCOVER_DIR.name} runs a script and saves a report; it has {sorted(discover_tools)}"
    )
    assert {"Bash", "Write"} <= audit_tools, (
        f"{_AUDIT_DIR.name} generates and validates audit files; it has {sorted(audit_tools)}"
    )
    assert {"Bash", "Write"} <= inspect_tools, (
        f"{_INSPECT_DIR.name} runs provider commands and saves a report; it has {sorted(inspect_tools)}"
    )


def test_the_core_names_every_sub_flow() -> None:
    """A sub-flow the core never mentions cannot be routed to."""
    _, body = _frontmatter_and_body(_CORE_DIR)
    for skill_dir in _SUB_FLOW_DIRS:
        assert skill_dir.name in body, f"the core does not route to {skill_dir.name}"


def test_inspect_flow_is_reached_only_through_eval_author() -> None:
    """Generic Intake questions must not match the inspect-trace sub-flow.

    ``nemo-intake`` already owns instrumentation, ingest, and query. If this
    sub-flow stays user-invocable and repeats those phrases, an agent with both
    skills loaded cannot tell which one to start.
    """
    inspect_frontmatter, inspect_body = _frontmatter_and_body(_INSPECT_DIR)
    core_frontmatter, _ = _frontmatter_and_body(_CORE_DIR)
    overlapping = (
        "inspect this agent trace",
        "what happened in this agent trace",
        "explain this production agent run",
        "did this trace succeed",
        "why did this trace fail",
        "inspecting agent runs",
    )

    assert inspect_frontmatter["user-invocable"] is False
    assert "eval-author has routed" in inspect_frontmatter["description"]
    assert "nemo-intake" in inspect_frontmatter["description"]
    assert "nemo-intake" in _not_for_names(inspect_frontmatter)
    assert "nemo-intake" in _not_for_names(core_frontmatter)
    assert "what happened in this agent trace" in core_frontmatter["triggers"]
    for phrase in overlapping:
        assert phrase not in inspect_frontmatter["triggers"]
        assert phrase not in inspect_frontmatter["description"]
    assert "after `eval-author` selects it" in inspect_body


def test_inspect_flow_is_only_a_cli_driven_skill() -> None:
    _, body = _frontmatter_and_body(_INSPECT_DIR)

    assert {path.name for path in _INSPECT_DIR.iterdir()} == {"SKILL.md"}
    for command in (
        "nemo intake traces",
        "nemo intake spans",
        "nemo intake evaluator-results",
    ):
        assert command in body


def test_inspect_flow_resolves_the_cli_without_changing_the_environment() -> None:
    """The trace reader must handle installed and source-checkout CLI invocations."""
    _, body = _frontmatter_and_body(_INSPECT_DIR)

    candidates = (
        "caller-supplied invocation",
        "command -v nemo",
        ".venv/bin/nemo",
        "uv run --no-sync nemo",
    )
    positions = [body.index(candidate) for candidate in candidates]
    assert positions == sorted(positions), "CLI candidates must appear in priority order"
    assert "Use the resolved invocation for every command" in body


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


def test_every_bundled_path_the_skill_names_exists() -> None:
    _, body = _frontmatter_and_body(_DISCOVER_DIR)
    for relative in (
        "scripts/discover.py",
        "scripts/_checks.py",
        "scripts/providers/harbor/_probe.py",
        "scripts/providers/harbor/_inventory.py",
        "scripts/providers/harbor/_ladder.py",
    ):
        assert relative in body, f"SKILL.md no longer documents {relative}"
        assert (_DISCOVER_DIR / relative).exists(), f"SKILL.md names {relative}, which is missing on disk"


def test_every_audit_spec_path_the_skill_names_exists() -> None:
    _, body = _frontmatter_and_body(_AUDIT_DIR)
    for relative in (
        "scripts/audit_spec/generate.py",
        "scripts/audit_spec/measure.py",
        "scripts/audit_spec/validate.py",
        "scripts/audit_spec/_schema.py",
        "scripts/audit_spec/_markdown.py",
        "scripts/audit_spec/measurements/tool_calls.py",
        "schemas/audit.schema.json",
        "schemas/audit_coverage.schema.json",
        "schemas/audit_tool_calls_details.schema.json",
        "examples/schemas/tool_calls.coverage.json",
        "examples/schemas/tool_calls.details.json",
        "requirements.txt",
        "templates/audit.md",
    ):
        assert relative in body, f"SKILL.md no longer documents {relative}"
        assert (_AUDIT_DIR / relative).exists(), f"SKILL.md names {relative}, which is missing on disk"


def test_audit_skill_reads_schema_before_drafting_items() -> None:
    """The schema should guide authoring, not emerge from validator retries."""
    _, body = _frontmatter_and_body(_AUDIT_DIR)
    step_one = body.split("## Step 2:", 1)[0]
    normalized_step = re.sub(r"\s+", " ", step_one)

    assert "Before drafting or updating" in step_one
    assert "templates/audit.md" in step_one
    assert "schemas/audit.schema.json" in step_one
    assert "Do not use validation as the primary way to discover the format" in normalized_step


def test_audit_skill_anchors_tool_names_to_runtime_measurement_surface() -> None:
    """Tool names should match traces, not plausible aliases from prose."""
    _, body = _frontmatter_and_body(_AUDIT_DIR)
    step_one = body.split("## Step 2:", 1)[0]
    normalized_step = re.sub(r"\s+", " ", step_one)

    assert "actual runtime traces or tool registry" in normalized_step
    assert "eval-specific tools" in normalized_step
    assert "Do not invent tool names that will not appear in the measurement surface" in normalized_step


def test_audit_skill_runs_audit_scripts_through_uv() -> None:
    """Documented script commands should use the repository Python environment."""
    _, body = _frontmatter_and_body(_AUDIT_DIR)

    assert "python <skill_dir>/scripts/audit_spec/" not in body
    assert body.count("uv run <skill_dir>/scripts/audit_spec/generate.py") == 4
    assert "uv run <skill_dir>/scripts/audit_spec/validate.py --audit .eval-author/audit.md" in body


def test_audit_json_schema_is_valid() -> None:
    from jsonschema import Draft202012Validator

    Draft202012Validator.check_schema(json.loads(_AUDIT_JSON_SCHEMA.read_text(encoding="utf-8")))


@pytest.mark.parametrize(
    "schema_path",
    (
        _AUDIT_COVERAGE_JSON_SCHEMA,
        _AUDIT_TOOL_CALLS_DETAILS_JSON_SCHEMA,
    ),
)
def test_audit_measurement_json_schemas_are_valid(schema_path: Path) -> None:
    from jsonschema import Draft202012Validator

    Draft202012Validator.check_schema(json.loads(schema_path.read_text(encoding="utf-8")))


@pytest.mark.parametrize(
    ("schema_path", "example_path"),
    (
        (_AUDIT_COVERAGE_JSON_SCHEMA, _AUDIT_COVERAGE_EXAMPLE),
        (_AUDIT_TOOL_CALLS_DETAILS_JSON_SCHEMA, _AUDIT_TOOL_CALLS_DETAILS_EXAMPLE),
    ),
)
def test_audit_measurement_schema_examples_validate(schema_path: Path, example_path: Path) -> None:
    from jsonschema import Draft202012Validator

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    example = json.loads(example_path.read_text(encoding="utf-8"))

    Draft202012Validator(schema).validate(example)


def test_audit_file_with_matching_source_digest_validates(tmp_path: Path) -> None:
    audit = _write_audit(tmp_path)

    code, report, stderr = _run_json_script(_AUDIT_VALIDATE, "--audit", str(audit))

    assert code == 0, stderr or report
    assert report["valid"] is True
    assert report["item_counts"] == {"capability": 1, "failure_case": 1, "tool": 1}


def test_audit_file_without_sources_allows_source_refs_as_notes(tmp_path: Path) -> None:
    audit = _write_audit(
        tmp_path,
        lambda text: re.sub(
            r"sources:\n  - name: ethos\n    path: ../ETHOS.md\n    sha256: sha256:[0-9a-f]{64}\n",
            "",
            text,
        ),
    )

    code, report, stderr = _run_json_script(_AUDIT_VALIDATE, "--audit", str(audit))

    assert code == 0, stderr or report
    assert report["valid"] is True


def test_audit_file_with_empty_sources_validates(tmp_path: Path) -> None:
    audit = _write_audit(
        tmp_path,
        lambda text: re.sub(
            r"sources:\n  - name: ethos\n    path: ../ETHOS.md\n    sha256: sha256:[0-9a-f]{64}\n",
            "sources: []\n",
            text,
        ),
    )

    code, report, stderr = _run_json_script(_AUDIT_VALIDATE, "--audit", str(audit))

    assert code == 0, stderr or report
    assert report["valid"] is True


def test_audit_validation_compact_output(tmp_path: Path) -> None:
    audit = _write_audit(tmp_path)

    code, report, stderr = _run_json_script(_AUDIT_VALIDATE, "--audit", str(audit), "--compact")

    assert code == 0, stderr or report
    assert report["valid"] is True
    assert report["item_count"] == 3


def test_audit_validation_marks_missing_pyyaml_as_environment_error(tmp_path: Path) -> None:
    audit = _write_audit(tmp_path)

    code, report, _ = _run_json_script(_AUDIT_VALIDATE, "--audit", str(audit), python_args=("-S",))

    assert code == 2
    assert report["valid"] is None
    assert report["error_type"] == "environment"
    assert "PyYAML is required" in report["error"]


def test_audit_validation_marks_missing_jsonschema_as_environment_error(tmp_path: Path) -> None:
    audit = _write_audit(tmp_path)
    (tmp_path / "jsonschema.py").write_text('raise ImportError("simulated missing jsonschema")\n', encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path) if not env.get("PYTHONPATH") else f"{tmp_path}{os.pathsep}{env['PYTHONPATH']}"

    code, report, _ = _run_json_script(_AUDIT_VALIDATE, "--audit", str(audit), "--compact", env=env)

    assert code == 2
    assert report["valid"] is None
    assert report["error_type"] == "environment"
    assert "jsonschema is required" in report["error"]


def test_audit_schema_load_failure_is_environment_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.syspath_prepend(str(_AUDIT_SPEC_DIR))
    schema_module = importlib.import_module("_schema")

    monkeypatch.setattr(schema_module, "SCHEMA_PATH", tmp_path / "missing.schema.json")

    with pytest.raises(schema_module.AuditEnvironmentError, match="could not load audit JSON Schema"):
        schema_module.validate_audit_spec({})


def test_audit_validation_rejects_unknown_tool_reference(tmp_path: Path) -> None:
    audit = _write_audit(
        tmp_path,
        lambda text: text.replace(
            "    required_tools:\n      - customer.lookup\n",
            "    required_tools:\n      - ticket.create\n",
        ),
    )

    code, report, _ = _run_json_script(_AUDIT_VALIDATE, "--audit", str(audit))

    assert code == 1
    assert report["valid"] is False
    assert "unknown tool name 'ticket.create'" in report["error"]


def test_audit_validation_rejects_unknown_schema_field(tmp_path: Path) -> None:
    audit = _write_audit(
        tmp_path,
        lambda text: text.replace(
            "status: draft\n",
            "status: draft\nunexpected: true\n",
        ),
    )

    code, report, _ = _run_json_script(_AUDIT_VALIDATE, "--audit", str(audit))

    assert code == 1
    assert report["valid"] is False
    assert "unexpected" in report["error"]


def test_audit_validation_rejects_all_zero_source_digest(tmp_path: Path) -> None:
    audit = _write_audit(
        tmp_path,
        lambda text: re.sub(
            r"sha256: sha256:[0-9a-f]{64}",
            "sha256: sha256:" + ("0" * 64),
            text,
        ),
    )

    code, report, _ = _run_json_script(_AUDIT_VALIDATE, "--audit", str(audit))

    assert code == 1
    assert report["valid"] is False
    assert "all-zero placeholder" in report["error"]


def test_audit_validation_rejects_stale_source_digest(tmp_path: Path) -> None:
    audit = _write_audit(
        tmp_path,
        lambda text: re.sub(
            r"sha256: sha256:[0-9a-f]{64}",
            "sha256: sha256:" + ("1" * 64),
            text,
        ),
    )

    code, report, _ = _run_json_script(_AUDIT_VALIDATE, "--audit", str(audit))

    assert code == 1
    assert report["valid"] is False
    assert "does not match" in report["error"]


def test_audit_validation_rejects_source_digest_without_path(tmp_path: Path) -> None:
    audit = _write_audit(
        tmp_path,
        lambda text: text.replace("    path: ../ETHOS.md\n", ""),
    )

    code, report, _ = _run_json_script(_AUDIT_VALIDATE, "--audit", str(audit))

    assert code == 1
    assert report["valid"] is False
    assert "path" in report["error"]


def test_audit_validation_rejects_duplicate_source_names(tmp_path: Path) -> None:
    audit = _write_audit(
        tmp_path,
        lambda text: re.sub(
            r"(sources:\n  - name: ethos\n    path: ../ETHOS.md\n    sha256: sha256:[0-9a-f]{64}\n)",
            "\\1  - name: ethos\n    description: duplicate\n",
            text,
        ),
    )

    code, report, _ = _run_json_script(_AUDIT_VALIDATE, "--audit", str(audit))

    assert code == 1
    assert report["valid"] is False
    assert "audit.sources[1].name 'ethos' is duplicated" in report["error"]


def test_audit_validation_allows_unknown_prohibited_tool(tmp_path: Path) -> None:
    audit = _write_audit(
        tmp_path,
        lambda text: text.replace(
            "    prohibited_tools: []\n",
            "    prohibited_tools:\n      - admin.reset_password\n",
        ),
    )

    code, report, stderr = _run_json_script(_AUDIT_VALIDATE, "--audit", str(audit))

    assert code == 0, stderr or report
    assert report["valid"] is True


def test_audit_validation_requires_tool_for_tool_call_evidence(tmp_path: Path) -> None:
    audit = _write_audit(
        tmp_path,
        lambda text: text.replace(
            "      - kind: tool_call\n        tool: customer.lookup\n        description:",
            "      - kind: tool_call\n        description:",
            1,
        ),
    )

    code, report, _ = _run_json_script(_AUDIT_VALIDATE, "--audit", str(audit))

    assert code == 1
    assert report["valid"] is False
    assert "tool" in report["error"]


def test_audit_validation_rejects_tool_on_non_tool_evidence(tmp_path: Path) -> None:
    audit = _write_audit(
        tmp_path,
        lambda text: text.replace(
            "      - kind: user_intent\n        description:",
            "      - kind: user_intent\n        tool: customer.lookup\n        description:",
            1,
        ),
    )

    code, report, _ = _run_json_script(_AUDIT_VALIDATE, "--audit", str(audit))

    assert code == 1
    assert report["valid"] is False
    assert "tool" in report["error"]


def test_audit_validation_rejects_duplicate_names(tmp_path: Path) -> None:
    audit = _write_audit(
        tmp_path,
        lambda text: text.replace(
            "    name: account_recovery_unverified_identity\n",
            "    name: account_recovery\n",
        ),
    )

    code, report, _ = _run_json_script(_AUDIT_VALIDATE, "--audit", str(audit))

    assert code == 1
    assert report["valid"] is False
    assert "duplicated" in report["error"]


def test_audit_validation_rejects_unknown_capability_reference(tmp_path: Path) -> None:
    audit = _write_audit(
        tmp_path,
        lambda text: text.replace(
            "      - account_recovery\n",
            "      - account_closure\n",
            1,
        ),
    )

    code, report, _ = _run_json_script(_AUDIT_VALIDATE, "--audit", str(audit))

    assert code == 1
    assert report["valid"] is False
    assert "unknown capability name 'account_closure'" in report["error"]


def test_audit_validation_allows_toolless_capability(tmp_path: Path) -> None:
    audit = _write_audit(
        tmp_path,
        lambda text: text.replace(
            "    required_tools:\n      - customer.lookup\n",
            "    required_tools: []\n",
        ),
    )

    code, report, stderr = _run_json_script(_AUDIT_VALIDATE, "--audit", str(audit))

    assert code == 0, stderr or report
    assert report["valid"] is True


def test_audit_validation_allows_marker_mentions_in_prose(tmp_path: Path) -> None:
    audit = _write_audit(
        tmp_path,
        lambda text: (
            "The literal <!-- BEGIN:nemo-eval-author-audit:v1 --> marker can be discussed in prose.\n\n"
            + text
            + "\nThe literal <!-- END:nemo-eval-author-audit:v1 --> marker can be discussed too.\n"
        ),
    )

    code, report, stderr = _run_json_script(_AUDIT_VALIDATE, "--audit", str(audit))

    assert code == 0, stderr or report
    assert report["valid"] is True


def test_audit_validation_rejects_missing_marker(tmp_path: Path) -> None:
    audit = _write_audit(tmp_path, lambda text: text.replace("<!-- END:nemo-eval-author-audit:v1 -->", ""))

    code, report, _ = _run_json_script(_AUDIT_VALIDATE, "--audit", str(audit))

    assert code == 1
    assert report["valid"] is False
    assert "must contain exactly one" in report["error"]


def test_audit_validation_rejects_multiple_yaml_blocks(tmp_path: Path) -> None:
    audit = _write_audit(
        tmp_path,
        lambda text: text.replace(
            "```\n<!-- END:nemo-eval-author-audit:v1 -->",
            "```\n\n```yaml\nschema: conflicting.audit.v1\n```\n<!-- END:nemo-eval-author-audit:v1 -->",
        ),
    )

    code, report, _ = _run_json_script(_AUDIT_VALIDATE, "--audit", str(audit))

    assert code == 1
    assert report["valid"] is False
    assert "must contain one fenced yaml block" in report["error"]


def test_audit_validation_rejects_prefixed_yaml_fence(tmp_path: Path) -> None:
    audit = _write_audit(tmp_path, lambda text: text.replace("```yaml\n", "prefix ```yaml\n", 1))

    code, report, _ = _run_json_script(_AUDIT_VALIDATE, "--audit", str(audit))

    assert code == 1
    assert report["valid"] is False
    assert "must contain one fenced yaml block" in report["error"]


def test_audit_generate_renders_valid_audit_from_items(tmp_path: Path) -> None:
    ethos = tmp_path / "ETHOS.md"
    ethos.write_text(
        "---\nname: support-agent\ncreated_timestamp: '2026-08-25T00:00:00+00:00'\nauthor: tester\n---\n"
        "\n# Ethos: support-agent\n",
        encoding="utf-8",
    )
    items = tmp_path / "items.yaml"
    items_payload = _template_payload()["items"]
    items_payload[0]["expected_use"] = (
        "Used when account-specific information is required.\nDo not use for unrelated billing questions."
    )
    _write_audit_items(items, items_payload)
    out = tmp_path / ".eval-author" / "audit.md"

    result = _run_script(_AUDIT_GENERATE, "--ethos", str(ethos), "--items", str(items), "--out", str(out))
    assert result.returncode == 0, result.stderr
    code, report, stderr = _run_json_script(_AUDIT_VALIDATE, "--audit", str(out))
    summary = json.loads(result.stdout)
    payload = _audit_payload(out)
    text = out.read_text(encoding="utf-8")

    assert code == 0, stderr or report
    assert summary["mode"] == "reconcile"
    assert summary["action"] == "create"
    assert summary["items_mode"] == "partial"
    assert summary["written"] is True
    assert summary["conflicting_items"] == []
    assert summary["conflicting_items_applied"] is True
    assert report["agent"] == "support-agent"
    assert payload["sources"] == [{"name": "ethos", "path": "../ETHOS.md", "sha256": _digest(ethos)}]
    assert "source_ethos" not in payload
    assert "source_ethos_sha256" not in payload
    _assert_literal_block_scalar(text, "description", "Looks up customer profile, plan, account status")
    _assert_literal_block_scalar(text, "expected_use", "Used when account-specific information is required.")
    _assert_literal_block_scalar(
        text,
        "expected_behavior",
        "The agent grounds recovery in customer identity and routes to an approved recovery path.",
    )


def test_audit_generate_rejects_outputs_outside_eval_author(tmp_path: Path) -> None:
    ethos = tmp_path / "ETHOS.md"
    ethos.write_text("# Ethos\n", encoding="utf-8")
    items = tmp_path / "items.yaml"
    _write_audit_items(items, _template_payload()["items"])
    out = tmp_path / "README.md"
    out.write_text("customer source must stay intact\n", encoding="utf-8")

    result = _run_script(
        _AUDIT_GENERATE,
        "--ethos",
        str(ethos),
        "--items",
        str(items),
        "--out",
        str(out),
        "--mode",
        "replace",
    )

    assert result.returncode == 1
    assert "--out must resolve inside a .eval-author/ directory" in result.stderr
    assert "Traceback" not in result.stderr
    assert out.read_text(encoding="utf-8") == "customer source must stay intact\n"


def test_audit_generate_rejects_missing_candidate_name_before_reconcile(tmp_path: Path) -> None:
    audit = _write_audit(tmp_path)
    before = audit.read_bytes()
    items_payload = _template_payload()["items"]
    del items_payload[0]["name"]
    items = tmp_path / "items.yaml"
    _write_audit_items(items, items_payload)

    result = _run_script(
        _AUDIT_GENERATE,
        "--ethos",
        str(tmp_path / "ETHOS.md"),
        "--items",
        str(items),
        "--out",
        str(audit),
    )

    assert result.returncode == 1
    assert "name" in result.stderr
    assert "Traceback" not in result.stderr
    assert audit.read_bytes() == before


def test_audit_generate_rejects_duplicate_candidate_names_before_reconcile(tmp_path: Path) -> None:
    audit = _write_audit(tmp_path)
    before = audit.read_bytes()
    items_payload = _template_payload()["items"]
    duplicate = dict(items_payload[0])
    duplicate["expected_use"] = "Different proposal for the existing tool."
    items_payload.append(duplicate)
    items = tmp_path / "items.yaml"
    _write_audit_items(items, items_payload)

    result = _run_script(
        _AUDIT_GENERATE,
        "--ethos",
        str(tmp_path / "ETHOS.md"),
        "--items",
        str(items),
        "--out",
        str(audit),
    )

    assert result.returncode == 1
    assert "duplicated" in result.stderr
    assert "Traceback" not in result.stderr
    assert audit.read_bytes() == before


def test_audit_generate_reconciles_existing_audit_by_default(tmp_path: Path) -> None:
    audit = _write_audit(
        tmp_path,
        lambda text: (
            "Manual reviewer notes must stay outside the block.\n\n"
            + text.replace(
                "Looks up customer profile, plan, account status, and contact details.",
                "Hand reviewed lookup tool description.",
                1,
            )
            + "\nManual footer must stay too.\n"
        ),
    )
    (tmp_path / "ETHOS.md").write_text("# Ethos\n\n## Tools\n\n- customer.lookup\n- ticket.create\n", encoding="utf-8")
    items_payload = _template_payload()["items"]
    items_payload.append(_ticket_tool_item())
    items = tmp_path / "items.yaml"
    _write_audit_items(items, items_payload)

    result = _run_script(
        _AUDIT_GENERATE,
        "--ethos",
        str(tmp_path / "ETHOS.md"),
        "--items",
        str(items),
        "--out",
        str(audit),
        "--agent",
        "example-agent",
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    payload = _audit_payload(audit)
    text = audit.read_text(encoding="utf-8")
    items_by_name = {item["name"]: item for item in payload["items"]}

    assert summary["action"] == "reconcile"
    assert summary["written"] is True
    assert summary["added_items"] == ["ticket.create"]
    assert summary["conflicting_items"] == ["customer.lookup"]
    assert summary["conflicting_items_applied"] is False
    assert summary["possibly_stale_items"] == []
    assert payload["sources"][0]["sha256"] == _digest(tmp_path / "ETHOS.md")
    assert items_by_name["customer.lookup"]["description"] == "Hand reviewed lookup tool description.\n"
    assert items_by_name["ticket.create"]["kind"] == "tool"
    assert "Manual reviewer notes must stay outside the block." in text
    assert "Manual footer must stay too." in text
    _assert_literal_block_scalar(text, "description", "Hand reviewed lookup tool description.")


def test_audit_generate_suggests_without_writing(tmp_path: Path) -> None:
    audit = _write_audit(tmp_path)
    before = audit.read_bytes()
    items_payload = _template_payload()["items"]
    items_payload.append(_ticket_tool_item())
    items = tmp_path / "items.yaml"
    _write_audit_items(items, items_payload)

    result = _run_script(
        _AUDIT_GENERATE,
        "--ethos",
        str(tmp_path / "ETHOS.md"),
        "--items",
        str(items),
        "--out",
        str(audit),
        "--agent",
        "example-agent",
        "--mode",
        "suggest",
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert audit.read_bytes() == before
    assert summary["action"] == "suggest_reconcile"
    assert summary["written"] is False
    assert summary["added_items"] == ["ticket.create"]
    assert summary["conflicting_items"] == []
    assert summary["possibly_stale_items"] == []


def test_audit_generate_partial_update_does_not_report_stale_items(tmp_path: Path) -> None:
    audit = _write_audit(tmp_path)
    (tmp_path / "ETHOS.md").write_text("# Ethos\n\n## Tools\n\n- customer.lookup\n- ticket.create\n", encoding="utf-8")
    items = tmp_path / "items.yaml"
    _write_audit_items(items, [_ticket_tool_item()])

    result = _run_script(
        _AUDIT_GENERATE,
        "--ethos",
        str(tmp_path / "ETHOS.md"),
        "--items",
        str(items),
        "--out",
        str(audit),
        "--agent",
        "example-agent",
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    payload = _audit_payload(audit)

    assert summary["items_mode"] == "partial"
    assert summary["added_items"] == ["ticket.create"]
    assert summary["possibly_stale_items"] == []
    assert {item["name"] for item in payload["items"]} == {
        "customer.lookup",
        "account_recovery",
        "account_recovery_unverified_identity",
        "ticket.create",
    }


def test_audit_generate_full_items_mode_reports_stale_items(tmp_path: Path) -> None:
    audit = _write_audit(tmp_path)
    (tmp_path / "ETHOS.md").write_text("# Ethos\n\n## Tools\n\n- customer.lookup\n- ticket.create\n", encoding="utf-8")
    items = tmp_path / "items.yaml"
    _write_audit_items(items, [_ticket_tool_item()])

    result = _run_script(
        _AUDIT_GENERATE,
        "--ethos",
        str(tmp_path / "ETHOS.md"),
        "--items",
        str(items),
        "--out",
        str(audit),
        "--agent",
        "example-agent",
        "--items-mode",
        "full",
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)

    assert summary["items_mode"] == "full"
    assert summary["added_items"] == ["ticket.create"]
    assert summary["possibly_stale_items"] == [
        "customer.lookup",
        "account_recovery",
        "account_recovery_unverified_identity",
    ]


def test_audit_generate_demotes_approved_audit_when_reconcile_adds_items(tmp_path: Path) -> None:
    audit = _write_audit(tmp_path, lambda text: text.replace("status: draft\n", "status: approved\n", 1))
    (tmp_path / "ETHOS.md").write_text("# Ethos\n\n## Tools\n\n- customer.lookup\n- ticket.create\n", encoding="utf-8")
    items = tmp_path / "items.yaml"
    _write_audit_items(items, [_ticket_tool_item()])

    result = _run_script(
        _AUDIT_GENERATE,
        "--ethos",
        str(tmp_path / "ETHOS.md"),
        "--items",
        str(items),
        "--out",
        str(audit),
        "--agent",
        "example-agent",
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    payload = _audit_payload(audit)

    assert summary["status"] == "draft"
    assert payload["status"] == "draft"


def test_audit_generate_preserves_existing_agent_unless_explicit(tmp_path: Path) -> None:
    audit = _write_audit(tmp_path)
    (tmp_path / "ETHOS.md").write_text("---\nname: other-agent\n---\n# Ethos\n", encoding="utf-8")
    items = tmp_path / "items.yaml"
    _write_audit_items(items, _template_payload()["items"])

    result = _run_script(
        _AUDIT_GENERATE,
        "--ethos",
        str(tmp_path / "ETHOS.md"),
        "--items",
        str(items),
        "--out",
        str(audit),
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    payload = _audit_payload(audit)

    assert payload["agent"] == "example-agent"
    assert summary["agent"] == "example-agent"
    assert summary["agent_change"] == {"from": "example-agent", "to": "other-agent", "applied": False}


def test_audit_generate_replace_mode_overwrites_existing_audit(tmp_path: Path) -> None:
    audit = _write_audit(
        tmp_path,
        lambda text: (
            "Manual reviewer notes should be discarded by replace mode.\n\n"
            + text.replace(
                "Looks up customer profile, plan, account status, and contact details.",
                "Hand reviewed lookup tool description.",
                1,
            )
        ),
    )
    items = tmp_path / "items.yaml"
    _write_audit_items(items, _template_payload()["items"])

    result = _run_script(
        _AUDIT_GENERATE,
        "--ethos",
        str(tmp_path / "ETHOS.md"),
        "--items",
        str(items),
        "--out",
        str(audit),
        "--agent",
        "example-agent",
        "--mode",
        "replace",
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    payload = _audit_payload(audit)
    text = audit.read_text(encoding="utf-8")
    items_by_name = {item["name"]: item for item in payload["items"]}

    assert summary["action"] == "replace"
    assert summary["written"] is True
    assert "Manual reviewer notes should be discarded by replace mode." not in text
    assert items_by_name["customer.lookup"]["description"].startswith("Looks up customer profile")


@_needs_harbor
def test_audit_measure_reports_tool_call_coverage_from_atif_trace(tmp_path: Path) -> None:
    audit = _write_audit(tmp_path)
    trace = tmp_path / "trajectory.json"
    _write_atif_trace(trace, embedded_tool_calls=["customer.lookup"])
    out_dir = tmp_path / ".eval-author" / "audit-measurements"

    code, summary, stderr = _run_json_script(
        _AUDIT_MEASURE,
        "--audit",
        str(audit),
        "--trace",
        str(trace),
        "--task-id",
        "account-recovery",
        "--out-dir",
        str(out_dir),
    )

    assert code == 0, stderr or summary
    coverage_path = out_dir / "account-recovery" / "tool_calls" / "coverage.json"
    details_path = out_dir / "account-recovery" / "tool_calls" / "details.json"
    coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    details = json.loads(details_path.read_text(encoding="utf-8"))

    assert summary["written"] is True
    assert summary["coverage"] == str(coverage_path)
    assert summary["details"] == str(details_path)
    assert summary["covered"] == ["customer.lookup"]
    assert summary["covered_count"] == 1
    assert coverage == {
        "schema": "nemo.eval_author.audit_coverage.v1",
        "audit": {
            "path": str(audit),
            "schema": "nemo.eval_author.audit.v1",
            "agent": "example-agent",
            "status": "draft",
            "item_count": 3,
        },
        "subject": {
            "trace": str(trace),
            "trace_format": "atif",
            "task_id": "account-recovery",
        },
        "method": {"name": "tool_calls"},
        "item_kind": "tool",
        "covered": ["customer.lookup"],
    }
    assert details["schema"] == "nemo.eval_author.audit_tool_calls_details.v1"
    assert details["subject"]["task_id"] == "account-recovery"
    assert details["audit_tools"] == ["customer.lookup"]
    assert details["covered"] == ["customer.lookup"]
    assert details["missing"] == []
    assert details["tool_call_counts"] == {"customer.lookup": 1}
    assert details["matches"]["customer.lookup"] == [
        {
            "step_id": 1,
            "tool": "customer.lookup",
            "tool_call_id": "sub-call-1",
            "trajectory_id": "sub-trajectory",
            "trajectory_path": "$.subagent_trajectories[0]",
        }
    ]


@_needs_harbor
def test_audit_measure_reports_missing_tool_calls_as_not_covered(tmp_path: Path) -> None:
    audit = _write_audit(tmp_path)
    trace = tmp_path / "trajectory.json"
    _write_atif_trace(trace, tool_calls=["ticket.create"])
    out_dir = tmp_path / ".eval-author" / "audit-measurements"

    code, summary, stderr = _run_json_script(
        _AUDIT_MEASURE,
        "--audit",
        str(audit),
        "--trace",
        str(trace),
        "--task-id",
        "account-recovery",
        "--out-dir",
        str(out_dir),
    )

    assert code == 0, stderr or summary
    coverage = json.loads((out_dir / "account-recovery" / "tool_calls" / "coverage.json").read_text(encoding="utf-8"))
    details = json.loads((out_dir / "account-recovery" / "tool_calls" / "details.json").read_text(encoding="utf-8"))

    assert summary["covered"] == []
    assert coverage["covered"] == []
    assert details["covered"] == []
    assert details["missing"] == ["customer.lookup"]
    assert details["tool_call_counts"] == {"ticket.create": 1}


@_needs_harbor
def test_audit_measure_reads_harbor_trial_metadata(tmp_path: Path) -> None:
    audit = _write_audit(tmp_path)
    trial_dir = tmp_path / "job" / "account-recovery__abc"
    _write_atif_trace(trial_dir / "agent" / "trajectory.json", tool_calls=["customer.lookup"])
    (trial_dir / "result.json").write_text(
        json.dumps({"task_name": "account-recovery", "trial_name": "account-recovery__abc"}),
        encoding="utf-8",
    )
    out_dir = tmp_path / ".eval-author" / "audit-measurements"

    code, summary, stderr = _run_json_script(
        _AUDIT_MEASURE,
        "--audit",
        str(audit),
        "--trial-dir",
        str(trial_dir),
        "--out-dir",
        str(out_dir),
    )

    assert code == 0, stderr or summary
    coverage = json.loads((out_dir / "account-recovery" / "tool_calls" / "coverage.json").read_text(encoding="utf-8"))

    assert summary["task_id"] == "account-recovery"
    assert coverage["subject"]["task_id"] == "account-recovery"
    assert coverage["subject"]["trial_id"] == "account-recovery__abc"
    assert coverage["subject"]["harbor_trial_dir"] == str(trial_dir)
    assert coverage["subject"]["harbor_result"] == str(trial_dir / "result.json")


@_needs_harbor
def test_audit_measure_rejects_non_atif_trace_without_writing(tmp_path: Path) -> None:
    audit = _write_audit(tmp_path)
    trace = tmp_path / "trajectory.json"
    trace.write_text("{}", encoding="utf-8")
    out_dir = tmp_path / ".eval-author" / "audit-measurements"

    code, report, _ = _run_json_script(
        _AUDIT_MEASURE,
        "--audit",
        str(audit),
        "--trace",
        str(trace),
        "--task-id",
        "account-recovery",
        "--out-dir",
        str(out_dir),
    )

    assert code == 1
    assert report["valid"] is True
    assert report["written"] is False
    assert report["error_type"] == "trace"
    assert "not an ATIF trajectory" in report["error"]
    assert not out_dir.exists()


def test_bundled_scripts_never_import_the_platform() -> None:
    """The boundary that makes the skill copyable: Harbor is fine, NeMo is not."""
    offenders: dict[str, set[str]] = {}
    for scripts_dir in _SCRIPT_DIRS:
        permitted = _local_roots(scripts_dir) | sys.stdlib_module_names | _PERMITTED_THIRD_PARTY
        for path in _bundled_scripts(scripts_dir):
            found = {root for root in _imported_roots(path) if root not in permitted}
            if found:
                offenders[path.relative_to(scripts_dir).as_posix()] = found
    assert not offenders, (
        "Bundled scripts may import the standard library, a sibling, or "
        f"{sorted(_PERMITTED_THIRD_PARTY)}, found: "
        + "; ".join(f"{filename} imports {sorted(names)}" for filename, names in sorted(offenders.items()))
    )


def test_no_bundled_directory_is_named_after_a_provider_package() -> None:
    """The trap that makes a literal ``scripts/harbor/`` unusable.

    A directory on the path named ``harbor`` is importable as a namespace package.
    On a machine with no Harbor installed that makes ``find_spec("harbor")``
    succeed, so the probe reports an install that is not there and the ladder then
    fails on import. Provider code sits one level down for exactly this reason.
    """
    for scripts_dir in _SCRIPT_DIRS:
        collisions = _local_roots(scripts_dir) & _PERMITTED_THIRD_PARTY
        assert not collisions, (
            f"{sorted(collisions)} shadows a package the skill imports; "
            "keep it under scripts/providers/ rather than directly in scripts/"
        )


def test_only_the_ladder_imports_harbor() -> None:
    """Every other module must keep working when Harbor is absent."""
    assert "harbor" in _imported_roots(_LADDER), "the ladder is the Harbor boundary and must import Harbor"
    for path in _bundled_scripts(_DISCOVER_SCRIPTS_DIR):
        if path == _LADDER:
            continue
        assert "harbor" not in _imported_roots(path), (
            f"{path.relative_to(_DISCOVER_SCRIPTS_DIR)} imports Harbor; move that call behind the probe"
        )


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
