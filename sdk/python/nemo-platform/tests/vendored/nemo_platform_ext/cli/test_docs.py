# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the nemo docs command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from nemo_platform.cli.app import app
from nemo_platform.quickstart.config import QuickstartConfig
from typer.testing import CliRunner

runner = CliRunner()

qs_no_auth = QuickstartConfig(auth_enabled=False)


def _invoke(*args: str, env: dict[str, str] | None = None):
    """Invoke the CLI with auth disabled."""
    with patch("nemo_platform.quickstart.QuickstartConfig.load", return_value=qs_no_auth):
        return runner.invoke(app, list(args), env=env)


def _listed_topics(output: str) -> list[str]:
    return [line.strip() for line in output.splitlines() if line.startswith("  ")]


class TestDocsCommand:
    def test_docs_help(self):
        result = _invoke("docs", "--help")
        assert result.exit_code == 0
        assert "Read NeMo Platform documentation" in result.stdout

    def test_docs_list(self):
        result = _invoke("docs", "--list")
        assert result.exit_code == 0
        assert "get-started/setup" in result.stdout

    def test_docs_list_independent_of_cwd(self, tmp_path: Path, monkeypatch):
        unrelated_docs = tmp_path / "docs"
        unrelated_docs.mkdir()
        (unrelated_docs / "jenkins-pipeline-guide.md").write_text("# Wrong docs root\n")

        monkeypatch.delenv("NMP_DOCS_ROOT", raising=False)
        monkeypatch.chdir(tmp_path)

        result = _invoke("docs", "--list")

        assert result.exit_code == 0
        assert "get-started/setup" in result.stdout
        assert "jenkins-pipeline-guide" not in result.stdout

    def test_docs_root_prefers_repo_docs_over_package_snapshot(self, tmp_path: Path, monkeypatch):
        from nemo_platform.cli.commands import docs

        monkeypatch.delenv("NMP_DOCS_ROOT", raising=False)
        repo_docs = tmp_path / "docs"
        package_docs = tmp_path / "src" / "nemo_platform_ext" / "cli" / "docs"
        commands_dir = tmp_path / "src" / "nemo_platform_ext" / "cli" / "commands"
        repo_docs.mkdir(parents=True)
        package_docs.mkdir(parents=True)
        commands_dir.mkdir(parents=True)
        (tmp_path / "mkdocs.yml").write_text("site_name: Test\n")
        (repo_docs / "index.md").write_text("# Repo docs\n")
        (package_docs / "index.md").write_text("# Package snapshot\n")

        result = docs._find_docs_root(commands_dir / "docs.py")

        assert result == repo_docs.resolve()

    def test_docs_root_uses_package_snapshot_without_repo_docs(self, tmp_path: Path, monkeypatch):
        from nemo_platform.cli.commands import docs

        monkeypatch.delenv("NMP_DOCS_ROOT", raising=False)
        package_docs = tmp_path / "site-packages" / "nemo_platform" / "cli" / "docs"
        commands_dir = tmp_path / "site-packages" / "nemo_platform" / "cli" / "commands"
        package_docs.mkdir(parents=True)
        commands_dir.mkdir(parents=True)
        (package_docs / "index.md").write_text("# Packaged docs\n")

        result = docs._find_docs_root(commands_dir / "docs.py")

        assert result == package_docs.resolve()

    def test_packaged_docs_are_filtered_by_packaged_mkdocs_config(self, tmp_path: Path):
        from nemo_platform.cli.commands import docs

        package_root = tmp_path / "site-packages" / "nemo_platform" / "cli"
        package_docs = package_root / "docs"
        package_docs.mkdir(parents=True)
        (package_docs / "index.md").write_text("# Home\n")
        (package_docs / "customizer").mkdir()
        (package_docs / "customizer" / "about.md").write_text("# Hidden\n")
        (package_docs / "template").mkdir()
        (package_docs / "template" / "EULA.md").write_text("# Excluded\n")
        (package_root / "mkdocs.yml").write_text(
            """
exclude_docs: |
  template/

extra:
  hidden_docs:
    enabled: true
    paths:
      - customizer/**
""".lstrip()
        )

        assert docs._list_docs(package_docs) == ["index"]

    def test_single_item_env_sequence_is_not_treated_as_default(self, tmp_path: Path, monkeypatch):
        from nemo_platform.cli.commands import docs

        monkeypatch.delenv("NMP_HIDE_TEST_DOCS", raising=False)
        package_root = tmp_path / "site-packages" / "nemo_platform" / "cli"
        package_docs = package_root / "docs"
        package_docs.mkdir(parents=True)
        (package_docs / "index.md").write_text("# Home\n")
        (package_docs / "hidden").mkdir()
        (package_docs / "hidden" / "topic.md").write_text("# Hidden\n")
        (package_root / "mkdocs.yml").write_text(
            """
extra:
  hidden_docs:
    enabled: !ENV [NMP_HIDE_TEST_DOCS]
    paths:
      - hidden/**
""".lstrip()
        )

        assert docs._list_docs(package_docs) == ["hidden/topic", "index"]

    def test_docs_list_filters_unrendered_topics(self):
        result = _invoke("docs", "--list")

        assert result.exit_code == 0
        topics = _listed_topics(result.stdout)
        assert "get-started/setup" in topics
        assert "cli/configuration" in topics
        assert "pysdk/client/index" in topics
        assert "audit/index" not in topics
        assert "auth/concepts" not in topics
        assert "customizer/about" not in topics
        assert "evaluator/metrics/job-management" not in topics
        assert "helm/index" not in topics
        assert "CONTRIBUTING" not in topics
        assert "README" not in topics
        assert "template/EULA" not in topics
        assert "work/guardrails/README" not in topics

    def test_docs_no_args_shows_list(self):
        result = _invoke("docs")
        assert result.exit_code == 0
        assert "Available documentation topics" in result.stdout

    def test_docs_read_setup(self):
        result = _invoke("docs", "get-started/setup")
        assert result.exit_code == 0
        assert "# Setup" in result.stdout
        assert "nemo-setup" in result.stdout

    def test_docs_read_with_md_extension(self):
        result = _invoke("docs", "get-started/setup.md")
        assert result.exit_code == 0
        assert "# Setup" in result.stdout
        assert "nemo-setup" in result.stdout

    def test_docs_nonexistent(self):
        result = _invoke("docs", "nonexistent/path")
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_docs_hidden_topic_not_readable(self):
        result = _invoke("docs", "customizer/about")
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_docs_path_traversal_blocked(self, tmp_path: Path):
        result = _invoke("docs", "../../etc/passwd", env={"NMP_DOCS_ROOT": str(tmp_path)})
        assert result.exit_code == 1
        assert "invalid path" in result.output.lower()

    def test_docs_env_override(self, tmp_path: Path):
        doc_file = tmp_path / "test-topic.md"
        doc_file.write_text("# Test Topic\nHello from test.")

        result = _invoke("docs", "test-topic", env={"NMP_DOCS_ROOT": str(tmp_path)})
        assert result.exit_code == 0
        assert "Hello from test" in result.stdout
