# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the skills CLI commands."""

from pathlib import Path

import pytest
from nemo_platform_ext.cli.app import app
from nemo_platform_ext.cli.commands.skills.registry import (
    DuplicateSkillError,
    SkillProvider,
    _load_skills_cached,
)
from nemo_platform_ext.skills import skills_dir as platform_skills_dir
from typer.testing import CliRunner

from ...utils import assert_exit_code

runner = CliRunner()


def _example_plugin_skills_root() -> Path:
    return Path(__file__).resolve().parents[6] / "plugins" / "example-plugin" / "src" / "nemo_example_plugin" / "skills"


def _platform_skill_names() -> set[str]:
    """Names of skills shipped under `nemo_platform_ext.skills`, derived from disk.

    Hardcoding the set here would make every test break whenever we add or
    remove a built-in skill, so we discover it the same way the registry does.
    """
    return {
        entry.name for entry in platform_skills_dir().iterdir() if entry.is_dir() and not entry.name.startswith("_")
    }


@pytest.fixture(autouse=True)
def _clear_skill_registry_caches():
    """Reset the registry caches around every test in this module.

    ``_load_skills_cached`` is an ``lru_cache``, and the underlying
    ``nemo_platform_plugin.discovery.discover_entry_points`` is
    ``@cache``-decorated. If any earlier test (in this module or elsewhere)
    populated either cache with a value computed under monkeypatched conditions,
    later tests would inherit that stale view and the CLI would render ``[]``
    skills. Clearing both sides on entry and exit isolates each test from its
    neighbours regardless of test order — which matters under pytest-xdist where
    ordering is not fixed.
    """
    from nemo_platform_plugin.discovery import discover_entry_points as _discover_eps

    _load_skills_cached.cache_clear()
    _discover_eps.cache_clear()
    yield
    _load_skills_cached.cache_clear()
    _discover_eps.cache_clear()


@pytest.fixture
def example_plugin_skills(monkeypatch):
    """Layer the example-plugin skills directory on top of the platform's own skills."""
    _load_skills_cached.cache_clear()
    monkeypatch.setattr(
        "nemo_platform_ext.cli.commands.skills.registry._discover_skill_providers",
        lambda: {
            "platform": SkillProvider(name="platform", path=platform_skills_dir(), dist_name="nemo-platform-ext"),
            "example": SkillProvider(
                name="example", path=_example_plugin_skills_root(), dist_name="nemo-example-plugin"
            ),
        },
    )
    yield
    _load_skills_cached.cache_clear()


class TestList:
    def test_list_shows_skills(self):
        result = runner.invoke(app, "skills list")
        assert_exit_code(result, 0)
        assert "inference" in result.stdout

    def test_list_shows_plugin_skills(self, example_plugin_skills):
        result = runner.invoke(app, "skills list")
        assert_exit_code(result, 0)
        assert "example-hello" in result.stdout
        assert "example-debug" in result.stdout

    def test_list_shows_version(self):
        result = runner.invoke(app, "skills list")
        assert_exit_code(result, 0)
        assert "0.1" in result.stdout

    def test_list_duplicate_skill_error_is_clean(self, monkeypatch):
        monkeypatch.setattr(
            "nemo_platform_ext.cli.commands.skills.cli.load_skills",
            lambda: (_ for _ in ()).throw(DuplicateSkillError("duplicate skill")),
        )
        result = runner.invoke(app, "skills list")
        assert_exit_code(result, 1)
        assert "Error: duplicate skill" in result.output

    def test_list_source_column_shows_distribution_names(self, example_plugin_skills):
        """JSON output is stable and easy to assert against the new ``Source`` semantics.

        The platform's bundled skills must collapse to ``nemo-platform``; plugins
        must render under their distribution name.
        """
        import json

        result = runner.invoke(app, "skills list -f json")
        assert_exit_code(result, 0)
        data = json.loads(result.stdout)
        by_name = {item["name"]: item for item in data}

        # Platform skills always come from the `nemo-platform-ext` (or
        # vendored `nemo-platform-sdk`) distribution; both collapse to
        # `nemo-platform` in the user-facing column.
        assert by_name["inference"]["source"] == "nemo-platform"
        # Raw entry-point name preserved for programmatic consumers.
        assert by_name["inference"]["source_plugin"] == "platform"

        # Plugins render under the distribution name that ships them.
        assert by_name["example-hello"]["source"] == "nemo-example-plugin"
        assert by_name["example-hello"]["source_dist"] == "nemo-example-plugin"
        assert by_name["example-hello"]["source_plugin"] == "example"

    def test_list_source_filter_keeps_only_matching_dist(self, example_plugin_skills):
        """`--source nemo-platform` returns only the platform's own skills."""
        import json

        result = runner.invoke(app, "skills list -f json --source nemo-platform")
        assert_exit_code(result, 0)
        names = {item["name"] for item in json.loads(result.stdout)}
        assert names == _platform_skill_names()

    def test_list_source_filter_repeatable_unions_results(self, example_plugin_skills):
        """`--source` can be repeated; results are the union (OR)."""
        import json

        result = runner.invoke(
            app,
            "skills list -f json --source nemo-platform --source nemo-example-plugin",
        )
        assert_exit_code(result, 0)
        names = {item["name"] for item in json.loads(result.stdout)}
        assert names == _platform_skill_names() | {"example-hello", "example-debug"}

    def test_list_source_filter_is_case_insensitive(self, example_plugin_skills):
        import json

        result = runner.invoke(app, "skills list -f json --source Nemo-Platform")
        assert_exit_code(result, 0)
        names = {item["name"] for item in json.loads(result.stdout)}
        assert names == _platform_skill_names()

    def test_list_source_filter_unknown_source_errors(self, example_plugin_skills):
        """Unknown source must be a hard error listing what's actually available."""
        result = runner.invoke(app, "skills list --source nemo-does-not-exist")
        assert_exit_code(result, 1)
        assert "Unknown source(s): nemo-does-not-exist" in result.output
        # The error must show the user what they could have typed.
        assert "nemo-platform" in result.output
        assert "nemo-example-plugin" in result.output


class TestShow:
    def test_show_with_name_prints_content(self):
        result = runner.invoke(app, "skills show inference")
        assert_exit_code(result, 0)
        assert "name: inference" in result.stdout

    def test_show_with_agent_formats_content(self):
        result = runner.invoke(app, "skills show --agent claude inference")
        assert_exit_code(result, 0)
        assert "name: nemo-inference" in result.stdout

    def test_show_unknown_skill_errors(self):
        result = runner.invoke(app, "skills show nonexistent")
        assert_exit_code(result, 1)
        assert "Unknown skill" in result.output

    def test_show_unknown_agent_errors(self):
        result = runner.invoke(app, "skills show --agent unknown inference")
        assert_exit_code(result, 1)
        assert "Unsupported agent" in result.output

    def test_show_plugin_skill_prints_content(self, example_plugin_skills):
        result = runner.invoke(app, "skills show example-hello")
        assert_exit_code(result, 0)
        assert "Example Hello" in result.stdout

    def test_show_each_skill(self):
        for skill in _platform_skill_names():
            result = runner.invoke(app, f"skills show {skill}")
            assert_exit_code(result, 0)
            assert len(result.stdout.strip()) > 0

    def test_show_duplicate_skill_error_is_clean(self, monkeypatch):
        monkeypatch.setattr(
            "nemo_platform_ext.cli.commands.skills.cli.load_skills",
            lambda: (_ for _ in ()).throw(DuplicateSkillError("duplicate skill")),
        )
        result = runner.invoke(app, "skills show setup")
        assert_exit_code(result, 1)
        assert "Error: duplicate skill" in result.output


class TestInstall:
    def test_install_requires_agent(self):
        result = runner.invoke(app, "skills install")
        assert result.exit_code != 0

    def test_install_claude_project_creates_multiple_files(self, tmp_path: Path, monkeypatch):
        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, "skills install --agent claude")
        assert_exit_code(result, 0)
        # Every built-in skill should install — exercise the multi-skill path
        # without hardcoding which platform skills exist today.
        for skill_name in _platform_skill_names():
            assert (tmp_path / ".claude" / "skills" / f"nemo-{skill_name}" / "SKILL.md").exists()
        assert "Installed" in result.stdout

    def test_install_selective_skills(self, tmp_path: Path, monkeypatch):
        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, "skills install --agent claude --skill inference")
        assert_exit_code(result, 0)
        assert (tmp_path / ".claude" / "skills" / "nemo-inference" / "SKILL.md").exists()
        assert not (tmp_path / ".claude" / "skills" / "nemo-setup" / "SKILL.md").exists()

    def test_install_invalid_skill_name_errors(self, tmp_path: Path, monkeypatch):
        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, "skills install --agent claude --skill nonexistent")
        assert_exit_code(result, 1)
        assert "Unknown skill" in result.output

    def test_install_duplicate_skill_error_is_clean(self, tmp_path: Path, monkeypatch):
        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            "nemo_platform_ext.cli.commands.skills.cli.load_skills",
            lambda: (_ for _ in ()).throw(DuplicateSkillError("duplicate skill")),
        )
        result = runner.invoke(app, "skills install --agent claude --skill inference")
        assert_exit_code(result, 1)
        assert "Error: duplicate skill" in result.output

    def test_install_plugin_skill_copies_companion_files(self, tmp_path: Path, monkeypatch, example_plugin_skills):
        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, "skills install --agent claude --skill example-debug")
        assert_exit_code(result, 0)
        skill_dir = tmp_path / ".claude" / "skills" / "nemo-example-debug"
        assert (skill_dir / "SKILL.md").exists()
        assert (skill_dir / "resources" / "notes.md").exists()

    def test_install_codex_writes_per_skill_directories(self, tmp_path: Path, monkeypatch):
        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, "skills install --agent codex")
        assert_exit_code(result, 0)
        inference = tmp_path / ".agents" / "skills" / "nemo-inference" / "SKILL.md"
        assert inference.exists()
        assert "name: nemo-inference" in inference.read_text()
        # The old marker-comment layout is gone: AGENTS.md must not be touched.
        assert not (tmp_path / "AGENTS.md").exists()

    def test_install_unknown_agent_errors(self, tmp_path: Path, monkeypatch):
        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, "skills install --agent unknown")
        assert_exit_code(result, 1)
        assert "Unsupported agent" in result.output

    def test_install_cursor_user_scope_errors(self, tmp_path: Path, monkeypatch):
        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, "skills install --agent cursor --user")
        assert_exit_code(result, 1)
        assert "does not support" in result.output


class TestFindProjectRoot:
    def test_finds_git_root(self, tmp_path: Path, monkeypatch):
        (tmp_path / ".git").mkdir()
        subdir = tmp_path / "a" / "b"
        subdir.mkdir(parents=True)
        monkeypatch.chdir(subdir)
        from nemo_platform_ext.cli.commands.skills.cli import _find_project_root

        assert _find_project_root() == tmp_path

    def test_falls_back_to_cwd_without_git(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from nemo_platform_ext.cli.commands.skills.cli import _find_project_root

        assert _find_project_root() == tmp_path


class TestHelpText:
    def test_skills_help(self):
        result = runner.invoke(app, "skills --help")
        assert_exit_code(result, 0)

    def test_list_help(self):
        result = runner.invoke(app, "skills list --help")
        assert_exit_code(result, 0)

    def test_show_help(self):
        result = runner.invoke(app, "skills show --help")
        assert_exit_code(result, 0)

    def test_install_help(self):
        result = runner.invoke(app, "skills install --help")
        assert_exit_code(result, 0)

    def test_new_help(self):
        result = runner.invoke(app, "skills new --help")
        assert_exit_code(result, 0)


class TestNew:
    def test_new_scaffolds_skill_directory(self, tmp_path: Path):
        result = runner.invoke(app, f"skills new my-skill --dir {tmp_path}")
        assert_exit_code(result, 0)
        skill_root = tmp_path / "my-skill"
        assert (skill_root / "SKILL.md").is_file()
        assert (skill_root / "tests.json").is_file()
        assert (skill_root / "references").is_dir()
        assert (skill_root / "references" / ".gitkeep").is_file()

    def test_new_seeds_frontmatter(self, tmp_path: Path):
        result = runner.invoke(app, f"skills new my-skill --dir {tmp_path}")
        assert_exit_code(result, 0)
        skill_md = (tmp_path / "my-skill" / "SKILL.md").read_text()
        assert "name: my-skill" in skill_md
        # All required frontmatter fields per the skill spec.
        for field in ("description:", "triggers:", "not-for:", "compatibility:", "maturity:", "license:"):
            assert field in skill_md, f"missing required frontmatter field: {field}"

    def test_new_seeds_description_override(self, tmp_path: Path):
        result = runner.invoke(app, f'skills new my-skill --dir {tmp_path} --description "Does the thing"')
        assert_exit_code(result, 0)
        skill_md = (tmp_path / "my-skill" / "SKILL.md").read_text()
        # JSON-encoded for YAML safety; the description content must still be visible.
        assert '"Does the thing"' in skill_md

    def test_new_escapes_special_characters_in_description(self, tmp_path: Path):
        """Colons, quotes, and other YAML-significant characters must not break the frontmatter."""
        import yaml

        tricky = 'A "tricky" desc: with colons'
        result = runner.invoke(
            app,
            ["skills", "new", "my-skill", "--dir", str(tmp_path), "--description", tricky],
        )
        assert_exit_code(result, 0)
        skill_md = (tmp_path / "my-skill" / "SKILL.md").read_text()
        # The frontmatter must parse cleanly and round-trip the description.
        _, frontmatter, _ = skill_md.split("---", 2)
        meta = yaml.safe_load(frontmatter)
        assert meta["description"] == tricky

    def test_new_accepts_single_character_name(self, tmp_path: Path):
        result = runner.invoke(app, f"skills new a --dir {tmp_path}")
        assert_exit_code(result, 0)
        assert (tmp_path / "a" / "SKILL.md").is_file()

    def test_new_tests_json_has_four_modes(self, tmp_path: Path):
        import json

        result = runner.invoke(app, f"skills new my-skill --dir {tmp_path}")
        assert_exit_code(result, 0)
        tests = json.loads((tmp_path / "my-skill" / "tests.json").read_text())
        assert tests["skill"] == "my-skill"
        by_type: dict[str, int] = {}
        for test in tests["tests"]:
            by_type[test["type"]] = by_type.get(test["type"], 0) + 1
        # NV-BASE four-mode coverage: 3 of each.
        assert by_type == {"explicit": 3, "implicit": 3, "contextual": 3, "negative-control": 3}
        # Positive vs negative semantics match the skill-test.py harness: explicit and
        # implicit assert the skill DOES fire (expected_skill); contextual and
        # negative-control assert it does NOT fire (expected_skill_not).
        for test in tests["tests"]:
            if test["type"] in ("explicit", "implicit"):
                assert "expected_skill" in test, test
                assert "expected_skill_not" not in test, test
            else:
                assert "expected_skill_not" in test, test
                assert "expected_skill" not in test, test

    def test_new_refuses_existing_directory(self, tmp_path: Path):
        (tmp_path / "my-skill").mkdir()
        result = runner.invoke(app, f"skills new my-skill --dir {tmp_path}")
        assert_exit_code(result, 1)
        assert "already exists" in result.output

    def test_new_rejects_invalid_names(self, tmp_path: Path):
        # Leading-dash names ("-skill") get caught by typer's option parser
        # before our validator sees them; that's fine — the user never gets a
        # broken skill regardless of which layer rejects.
        for bad_name in ("MySkill", "my_skill", "1skill", "skill-"):
            result = runner.invoke(app, f"skills new {bad_name} --dir {tmp_path}")
            assert_exit_code(result, 1)
            assert "Invalid skill name" in result.output

    def test_new_defaults_to_current_directory(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, "skills new my-skill")
        assert_exit_code(result, 0)
        assert (tmp_path / "my-skill" / "SKILL.md").is_file()
