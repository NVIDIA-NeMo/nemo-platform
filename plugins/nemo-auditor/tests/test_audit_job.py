# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for ``AuditJob.run`` — exercises the garak invocation and
result-collection plumbing without actually shelling out to garak."""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from nemo_auditor.entities import (
    AuditConfig,
    AuditPluginsData,
    AuditReportData,
    AuditRunData,
    AuditSystemData,
)
from nemo_auditor.entities import (
    AuditTarget as AuditTargetEntity,
)
from nemo_auditor.jobs.audit import (
    AuditInputSpec,
    AuditJob,
    AuditSpec,
    _collect_report_artifacts,
    _garak_config_dict,
    _rewrite_options_uris,
)
from nemo_platform_plugin.entity_client import NemoEntityNotFoundError
from nemo_platform_plugin.job_context import JobContext, StoragePaths
from nemo_platform_plugin.job_results import LocalJobResults


def _make_ctx(tmp_path: Path) -> JobContext:
    ephemeral = tmp_path / "ephemeral"
    persistent = tmp_path / "persistent"
    ephemeral.mkdir()
    persistent.mkdir()
    return JobContext(
        workspace="default",
        storage=StoragePaths(ephemeral=ephemeral, persistent=persistent),
        results=LocalJobResults(persistent / "results"),
        job_id=None,
    )


def _make_config(**overrides) -> AuditConfig:
    defaults: dict = {
        "name": "test-cfg",
        "workspace": "default",
        "description": "test",
        "system": AuditSystemData(lite=True, parallel_attempts=1),
        "run": AuditRunData(generations=1),
        "plugins": AuditPluginsData(probe_spec="encoding.InjectAscii85"),
        "reporting": AuditReportData(report_prefix="run1", report_dir="garak_runs"),
    }
    defaults.update(overrides)
    return AuditConfig(**defaults)


def _make_target(**overrides) -> AuditTargetEntity:
    defaults: dict = {
        "name": "test-tgt",
        "workspace": "default",
        "type": "test",
        "model": "test.Blank",
        "options": {},
    }
    defaults.update(overrides)
    return AuditTargetEntity(**defaults)


def _make_spec_dict(**overrides) -> dict:
    cfg = overrides.pop("config", _make_config())
    tgt = overrides.pop("target", _make_target())
    return {
        "config": cfg.model_dump(mode="json"),
        "target": tgt.model_dump(mode="json"),
    }


def _plant_reports(persistent: Path, prefix: str, kinds: tuple[str, ...]) -> None:
    """Plant fake garak report files where ``run`` will look for them."""
    report_dir = persistent / "garak" / "garak_runs"
    report_dir.mkdir(parents=True, exist_ok=True)
    for kind in kinds:
        (report_dir / f"{prefix}{kind}").write_text(f"fake-{kind}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestGarakConfigDict:
    def test_drops_entity_base_fields_and_description(self) -> None:
        cfg = _make_config()
        out = _garak_config_dict(cfg)
        assert set(out.keys()) == {"system", "run", "plugins", "reporting"}
        for forbidden in ("name", "workspace", "description", "id", "entity_type"):
            assert forbidden not in out

    def test_preserves_nested_values(self) -> None:
        cfg = _make_config(
            system=AuditSystemData(lite=False, parallel_attempts=8),
            run=AuditRunData(generations=5, eval_threshold=0.7),
        )
        out = _garak_config_dict(cfg)
        assert out["system"]["parallel_attempts"] == 8
        assert out["run"]["generations"] == 5
        assert out["run"]["eval_threshold"] == 0.7


# ---------------------------------------------------------------------------
# Subprocess invocation
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_garak_python(tmp_path: Path, monkeypatch) -> Path:
    """Create an empty file standing in for the garak interpreter and point the
    job at it via the env var. AuditJob only checks existence, never executes
    it (subprocess.run is patched separately)."""
    interp = tmp_path / "garak-python"
    interp.touch()
    monkeypatch.setenv("NEMO_AUDITOR_GARAK_PYTHON", str(interp))
    return interp


class TestAuditJobRun:
    def test_invokes_garak_with_expected_argv_and_env(self, tmp_path: Path, fake_garak_python: Path) -> None:
        ctx = _make_ctx(tmp_path)
        spec = _make_spec_dict()

        with patch("nemo_auditor.jobs.audit.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            AuditJob().run(spec, ctx=ctx)

        assert mock_run.call_count == 1
        call_args = mock_run.call_args
        argv = call_args.args[0]

        assert argv[0] == str(fake_garak_python)
        assert argv[1:3] == ["-m", "garak"]
        assert "--config" in argv
        cfg_idx = argv.index("--config")
        assert argv[cfg_idx + 1].endswith("garak_config.yaml")
        assert ["--target_type", "test"] == argv[argv.index("--target_type") : argv.index("--target_type") + 2]
        assert ["--target_name", "test.Blank"] == argv[argv.index("--target_name") : argv.index("--target_name") + 2]
        # No options on the default target → no --generator_option_file.
        assert "--generator_option_file" not in argv

        env = call_args.kwargs["env"]
        # Either the test process inherited the var, or the job stubbed it
        # to "NOT_SET". Either way the key must be present and non-empty so
        # garak doesn't reject startup.
        for key in ("NIM_API_KEY", "OPENAI_API_KEY", "REST_API_KEY", "OPENAICOMPATIBLE_API_KEY"):
            assert env[key]
        assert env["XDG_DATA_HOME"] == str(ctx.storage.persistent)
        assert env["GARAK_LOG_FILE"].endswith("garak.log")

        # cwd is the ephemeral working dir.
        assert call_args.kwargs["cwd"] == ctx.storage.ephemeral

    def test_yaml_config_only_has_garak_sections(self, tmp_path: Path, fake_garak_python: Path) -> None:
        ctx = _make_ctx(tmp_path)
        spec = _make_spec_dict(config=_make_config(description="will-be-stripped"))

        with patch("nemo_auditor.jobs.audit.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            AuditJob().run(spec, ctx=ctx)

        garak_config_path = ctx.storage.ephemeral / "garak_config.yaml"
        assert garak_config_path.exists()
        loaded = yaml.safe_load(garak_config_path.read_text())
        assert set(loaded.keys()) == {"system", "run", "plugins", "reporting"}
        assert "description" not in loaded
        assert "name" not in loaded

    def test_target_options_written_when_present_and_flag_added(self, tmp_path: Path, fake_garak_python: Path) -> None:
        ctx = _make_ctx(tmp_path)
        spec = _make_spec_dict(target=_make_target(options={"endpoint": "https://example.invalid", "key_env": "X"}))

        with patch("nemo_auditor.jobs.audit.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            AuditJob().run(spec, ctx=ctx)

        opts_path = ctx.storage.ephemeral / "target_options.json"
        assert opts_path.exists()
        assert json.loads(opts_path.read_text()) == {"endpoint": "https://example.invalid", "key_env": "X"}

        argv = mock_run.call_args.args[0]
        assert "--generator_option_file" in argv
        assert argv[argv.index("--generator_option_file") + 1].endswith("target_options.json")

    def test_missing_garak_interpreter_raises_clear_error(self, tmp_path: Path, monkeypatch) -> None:
        ctx = _make_ctx(tmp_path)
        monkeypatch.setenv("NEMO_AUDITOR_GARAK_PYTHON", str(tmp_path / "does-not-exist"))
        with pytest.raises(FileNotFoundError, match="garak interpreter not found"):
            AuditJob().run(_make_spec_dict(), ctx=ctx)

    def test_completed_run_collects_all_three_artifacts(self, tmp_path: Path, fake_garak_python: Path) -> None:
        ctx = _make_ctx(tmp_path)
        spec = _make_spec_dict()

        def fake_run(*args, **kwargs):
            _plant_reports(
                ctx.storage.persistent,
                "run1",
                (".report.jsonl", ".report.html", ".hitlog.jsonl"),
            )
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")

        with patch("nemo_auditor.jobs.audit.subprocess.run", side_effect=fake_run):
            result = AuditJob().run(spec, ctx=ctx)

        assert result["status"] == "completed"
        assert result["returncode"] == 0
        assert set(result["results"].keys()) == {"report-jsonl", "report-html", "report-hitlog-jsonl"}
        for ref in result["results"].values():
            assert ref["artifact_url"].startswith("file://")
            # Local sink copies to <persistent>/results/<name>.
            assert Path(ref["artifact_url"][len("file://") :]).exists()

    def test_failed_run_returns_failed_status_and_collects_partial_artifacts(
        self, tmp_path: Path, fake_garak_python: Path
    ) -> None:
        ctx = _make_ctx(tmp_path)
        spec = _make_spec_dict()

        def fake_run(*args, **kwargs):
            # Garak got far enough to emit the jsonl but crashed before the html.
            _plant_reports(ctx.storage.persistent, "run1", (".report.jsonl",))
            return subprocess.CompletedProcess(args=[], returncode=2, stdout="", stderr="garak exploded\n")

        with patch("nemo_auditor.jobs.audit.subprocess.run", side_effect=fake_run):
            result = AuditJob().run(spec, ctx=ctx)

        assert result["status"] == "failed"
        assert result["returncode"] == 2
        assert "garak exploded" in result["stderr_tail"]
        assert set(result["results"].keys()) == {"report-jsonl"}

    def test_failed_run_with_no_artifacts_still_returns_envelope(self, tmp_path: Path, fake_garak_python: Path) -> None:
        ctx = _make_ctx(tmp_path)
        spec = _make_spec_dict()

        with patch("nemo_auditor.jobs.audit.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="early death")
            result = AuditJob().run(spec, ctx=ctx)

        assert result["status"] == "failed"
        assert result["returncode"] == 1
        assert result["results"] == {}

    def test_uses_custom_report_prefix_and_dir(self, tmp_path: Path, fake_garak_python: Path) -> None:
        ctx = _make_ctx(tmp_path)
        cfg = _make_config(reporting=AuditReportData(report_prefix="custom-prefix", report_dir="custom_dir"))
        spec = _make_spec_dict(config=cfg)

        def fake_run(*args, **kwargs):
            d = ctx.storage.persistent / "garak" / "custom_dir"
            d.mkdir(parents=True, exist_ok=True)
            (d / "custom-prefix.report.jsonl").write_text("hi")
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        with patch("nemo_auditor.jobs.audit.subprocess.run", side_effect=fake_run):
            result = AuditJob().run(spec, ctx=ctx)

        assert result["status"] == "completed"
        assert "report-jsonl" in result["results"]


# ---------------------------------------------------------------------------
# Schema-level tests
# ---------------------------------------------------------------------------


class TestAuditSpec:
    def test_rejects_extra_top_level_fields(self) -> None:
        with pytest.raises(ValueError):
            AuditSpec.model_validate(
                {
                    "config": _make_config().model_dump(mode="json"),
                    "target": _make_target().model_dump(mode="json"),
                    "extra": "not-allowed",
                }
            )

    def test_requires_config_and_target(self) -> None:
        with pytest.raises(ValueError):
            AuditSpec.model_validate({"target": _make_target().model_dump(mode="json")})
        with pytest.raises(ValueError):
            AuditSpec.model_validate({"config": _make_config().model_dump(mode="json")})


# ---------------------------------------------------------------------------
# Optional smoke: real ~/.auditor venv reachable
# ---------------------------------------------------------------------------


GARAK_VENV_PYTHON = Path("~/.auditor/.venv/bin/python").expanduser()


@pytest.mark.skipif(
    not GARAK_VENV_PYTHON.exists(),
    reason="garak venv not present at ~/.auditor/.venv",
)
def test_garak_venv_is_reachable() -> None:
    """Sanity: the dev assumption that ``~/.auditor/.venv`` ships garak holds."""
    completed = subprocess.run(
        [str(GARAK_VENV_PYTHON), "-c", "import garak; print(garak.__version__)"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip(), "expected a version string from garak"


# ---------------------------------------------------------------------------
# _collect_report_artifacts
# ---------------------------------------------------------------------------


class TestCollectReportArtifacts:
    def test_skips_missing_files(self, tmp_path: Path) -> None:
        results = LocalJobResults(tmp_path / "results")
        report_dir = tmp_path / "reports"
        report_dir.mkdir()
        # Only the jsonl exists.
        (report_dir / "run1.report.jsonl").write_text("hi")

        artifacts = _collect_report_artifacts(report_dir, "run1", results)
        assert set(artifacts.keys()) == {"report-jsonl"}

    def test_returns_refs_with_local_file_urls(self, tmp_path: Path) -> None:
        results = LocalJobResults(tmp_path / "results")
        report_dir = tmp_path / "reports"
        report_dir.mkdir()
        (report_dir / "run1.report.jsonl").write_text("a")
        (report_dir / "run1.report.html").write_text("b")

        artifacts = _collect_report_artifacts(report_dir, "run1", results)
        for name, ref in artifacts.items():
            assert ref["name"] == name
            assert ref["artifact_url"].startswith("file://")


# ---------------------------------------------------------------------------
# _rewrite_options_uris — nmp_uri_spec resolution via the platform SDK
# ---------------------------------------------------------------------------


def _mock_sdk(uri: str = "https://igw.example.invalid/v1") -> MagicMock:
    """Return a MagicMock that mimics the SDK calls _rewrite_options_uris uses."""
    sdk = MagicMock()
    sdk.models.get_provider_route_openai_url.return_value = uri
    return sdk


class TestRewriteOptionsUris:
    def test_replaces_nmp_uri_spec_at_top_level_nim(self) -> None:
        options = {
            "nim": {
                "skip_seq_start": "<think>",
                "skip_seq_end": "</think>",
                "max_tokens": 4000,
                "nmp_uri_spec": {
                    "inference_gateway": {"workspace": "default", "provider": "build"},
                },
            }
        }
        sdk = _mock_sdk("https://replaced-url")
        _rewrite_options_uris(options, sdk)

        assert options == {
            "nim": {
                "skip_seq_start": "<think>",
                "skip_seq_end": "</think>",
                "max_tokens": 4000,
                "uri": "https://replaced-url",
            }
        }
        sdk.inference.providers.retrieve.assert_called_once_with(workspace="default", name="build")

    def test_replaces_at_nested_openai_compatible(self) -> None:
        options = {
            "openai": {
                "OpenAICompatible": {
                    "nmp_uri_spec": {
                        "inference_gateway": {"workspace": "default", "provider": "openai"},
                    }
                }
            }
        }
        sdk = _mock_sdk("https://replaced-url")
        _rewrite_options_uris(options, sdk)
        assert options == {"openai": {"OpenAICompatible": {"uri": "https://replaced-url"}}}

    def test_no_op_when_no_sentinel(self) -> None:
        options = {
            "nim": {
                "skip_seq_start": "<think>",
                "max_tokens": 4000,
                "uri": "https://dont-replace-me",
            }
        }
        sdk = _mock_sdk()
        _rewrite_options_uris(options, sdk)
        assert options == {
            "nim": {
                "skip_seq_start": "<think>",
                "max_tokens": 4000,
                "uri": "https://dont-replace-me",
            }
        }
        sdk.inference.providers.retrieve.assert_not_called()

    def test_no_sdk_calls_when_options_have_no_sentinel_at_all(self) -> None:
        options = {"a": {"b": {"c": "leaf"}}, "d": "string"}
        sdk = _mock_sdk()
        _rewrite_options_uris(options, sdk)
        assert options == {"a": {"b": {"c": "leaf"}}, "d": "string"}
        sdk.inference.providers.retrieve.assert_not_called()

    def test_raises_on_missing_provider(self) -> None:
        options = {"nim": {"nmp_uri_spec": {"inference_gateway": {"workspace": "default"}}}}
        with pytest.raises(ValueError, match="Invalid nmp_uri_spec"):
            _rewrite_options_uris(options, _mock_sdk())

    def test_raises_on_missing_workspace(self) -> None:
        options = {"nim": {"nmp_uri_spec": {"inference_gateway": {"provider": "build"}}}}
        with pytest.raises(ValueError, match="Invalid nmp_uri_spec"):
            _rewrite_options_uris(options, _mock_sdk())

    def test_raises_on_missing_inference_gateway_key(self) -> None:
        options = {"nim": {"nmp_uri_spec": {"some_other_resolver": {}}}}
        with pytest.raises(ValueError, match="Invalid nmp_uri_spec"):
            _rewrite_options_uris(options, _mock_sdk())

    def test_raises_on_uri_and_sentinel_conflict(self) -> None:
        options = {
            "nim": {
                "uri": "https://this-should-not-exist",
                "nmp_uri_spec": {
                    "inference_gateway": {"workspace": "default", "provider": "build"},
                },
            }
        }
        with pytest.raises(ValueError, match="both 'uri' and 'nmp_uri_spec'"):
            _rewrite_options_uris(options, _mock_sdk())

    def test_raises_when_sentinel_present_but_sdk_is_none(self) -> None:
        options = {
            "nim": {
                "nmp_uri_spec": {
                    "inference_gateway": {"workspace": "default", "provider": "build"},
                }
            }
        }
        with pytest.raises(RuntimeError, match="requires a connected platform SDK"):
            _rewrite_options_uris(options, None)

    def test_raises_when_both_sdk_and_async_sdk_are_none(self) -> None:
        options = {
            "nim": {
                "nmp_uri_spec": {
                    "inference_gateway": {"workspace": "default", "provider": "build"},
                }
            }
        }
        with pytest.raises(RuntimeError, match="requires a connected platform SDK"):
            _rewrite_options_uris(options, None, async_sdk=None)

    def test_resolves_nmp_uri_spec_via_async_sdk(self) -> None:
        options = {
            "nim": {
                "max_tokens": 32,
                "nmp_uri_spec": {
                    "inference_gateway": {"workspace": "default", "provider": "nvidia-inference-api"},
                },
            }
        }
        async_sdk = MagicMock()
        async_sdk.inference.providers.retrieve = AsyncMock(return_value=MagicMock())
        async_sdk.models.get_provider_route_openai_url.return_value = "https://igw-async.example/v1"

        _rewrite_options_uris(options, sdk=None, async_sdk=async_sdk)

        assert options == {"nim": {"max_tokens": 32, "uri": "https://igw-async.example/v1"}}
        async_sdk.inference.providers.retrieve.assert_called_once_with(workspace="default", name="nvidia-inference-api")

    def test_wraps_sdk_lookup_failure_in_runtimeerror(self) -> None:
        sdk = MagicMock()
        sdk.inference.providers.retrieve.side_effect = LookupError("no such provider")
        options = {
            "nim": {
                "nmp_uri_spec": {
                    "inference_gateway": {"workspace": "default", "provider": "ghost"},
                }
            }
        }
        with pytest.raises(RuntimeError, match="Failed to resolve inference gateway provider"):
            _rewrite_options_uris(options, sdk)


# ---------------------------------------------------------------------------
# AuditJob.run — end-to-end with nmp_uri_spec
# ---------------------------------------------------------------------------


class TestAuditJobIGW:
    def test_run_writes_options_with_resolved_uri_and_drops_sentinel(
        self, tmp_path: Path, fake_garak_python: Path
    ) -> None:
        ctx = _make_ctx(tmp_path)
        target = _make_target(
            options={
                "nim": {
                    "max_tokens": 4000,
                    "nmp_uri_spec": {
                        "inference_gateway": {"workspace": "default", "provider": "build"},
                    },
                }
            }
        )
        spec = _make_spec_dict(target=target)
        sdk = _mock_sdk("https://igw-resolved.example/v1")

        with patch("nemo_auditor.jobs.audit.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            AuditJob().run(spec, ctx=ctx, sdk=sdk)

        opts_path = ctx.storage.ephemeral / "target_options.json"
        assert opts_path.exists()
        on_disk = json.loads(opts_path.read_text())
        assert on_disk == {
            "nim": {
                "max_tokens": 4000,
                "uri": "https://igw-resolved.example/v1",
            }
        }
        # And the original validated spec is untouched.
        assert "nmp_uri_spec" in target.options["nim"]

    def test_run_without_sdk_when_no_sentinel_works(self, tmp_path: Path, fake_garak_python: Path) -> None:
        """sdk=None is fine when options carry no nmp_uri_spec."""
        ctx = _make_ctx(tmp_path)
        spec = _make_spec_dict(target=_make_target(options={"nim": {"max_tokens": 100}}))

        with patch("nemo_auditor.jobs.audit.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            AuditJob().run(spec, ctx=ctx)  # no sdk kwarg

        on_disk = json.loads((ctx.storage.ephemeral / "target_options.json").read_text())
        assert on_disk == {"nim": {"max_tokens": 100}}

    def test_run_resolves_nmp_uri_spec_via_async_sdk(self, tmp_path: Path, fake_garak_python: Path) -> None:
        """async_sdk path: nmp_uri_spec is rewritten when sdk=None but async_sdk is provided."""
        ctx = _make_ctx(tmp_path)
        target = _make_target(
            options={
                "nim": {
                    "max_tokens": 32,
                    "nmp_uri_spec": {
                        "inference_gateway": {"workspace": "default", "provider": "nvidia-inference-api"},
                    },
                }
            }
        )
        spec = _make_spec_dict(target=target)

        async_sdk = MagicMock()
        async_sdk.inference.providers.retrieve = AsyncMock(return_value=MagicMock())
        async_sdk.models.get_provider_route_openai_url.return_value = "https://igw-async.example/v1"

        with patch("nemo_auditor.jobs.audit.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            AuditJob().run(spec, ctx=ctx, sdk=None, async_sdk=async_sdk)

        opts_path = ctx.storage.ephemeral / "target_options.json"
        assert opts_path.exists()
        on_disk = json.loads(opts_path.read_text())
        assert on_disk == {"nim": {"max_tokens": 32, "uri": "https://igw-async.example/v1"}}
        assert "nmp_uri_spec" in target.options["nim"]  # original spec untouched


# ---------------------------------------------------------------------------
# AuditInputSpec — schema-level validation (inline / ref / mixed)
# ---------------------------------------------------------------------------


class TestAuditInputSpec:
    def test_inline_inline(self) -> None:
        validated = AuditInputSpec.model_validate(
            {
                "config": _make_config().model_dump(mode="json"),
                "target": _make_target().model_dump(mode="json"),
            }
        )
        assert isinstance(validated.config, AuditConfig)
        assert isinstance(validated.target, AuditTargetEntity)

    def test_ref_ref(self) -> None:
        validated = AuditInputSpec.model_validate({"config": "my-cfg", "target": "my-tgt"})
        assert validated.config == "my-cfg"
        assert validated.target == "my-tgt"

    def test_inline_ref_mixed(self) -> None:
        validated = AuditInputSpec.model_validate(
            {"config": _make_config().model_dump(mode="json"), "target": "prod/my-tgt"}
        )
        assert isinstance(validated.config, AuditConfig)
        assert validated.target == "prod/my-tgt"

    def test_ref_inline_mixed(self) -> None:
        validated = AuditInputSpec.model_validate(
            {"config": "my-cfg", "target": _make_target().model_dump(mode="json")}
        )
        assert validated.config == "my-cfg"
        assert isinstance(validated.target, AuditTargetEntity)

    def test_workspace_qualified_string_preserved(self) -> None:
        validated = AuditInputSpec.model_validate({"config": "prod/my-cfg", "target": "qa/my-tgt"})
        assert validated.config == "prod/my-cfg"
        assert validated.target == "qa/my-tgt"

    def test_rejects_empty_string(self) -> None:
        with pytest.raises(ValueError):
            AuditInputSpec.model_validate({"config": "", "target": "my-tgt"})

    def test_rejects_whitespace_only_string(self) -> None:
        # strip_whitespace + min_length=1 means "   " collapses to "" → rejected.
        with pytest.raises(ValueError):
            AuditInputSpec.model_validate({"config": "   ", "target": "my-tgt"})

    def test_rejects_extra_field(self) -> None:
        with pytest.raises(ValueError):
            AuditInputSpec.model_validate(
                {"config": "my-cfg", "target": "my-tgt", "extra": "no"},
            )

    def test_requires_config_and_target(self) -> None:
        with pytest.raises(ValueError):
            AuditInputSpec.model_validate({"target": "my-tgt"})
        with pytest.raises(ValueError):
            AuditInputSpec.model_validate({"config": "my-cfg"})


# ---------------------------------------------------------------------------
# AuditJob.to_spec — name resolution via entity_client
# ---------------------------------------------------------------------------


def _run_to_spec(input_spec: AuditInputSpec, *, workspace: str, entity_client) -> AuditSpec:
    """Sync wrapper around the async classmethod for use in synchronous tests."""
    return asyncio.run(
        AuditJob.to_spec(
            input_spec,
            workspace=workspace,
            entity_client=entity_client,
            async_sdk=None,
            is_local=True,
        )
    )


class TestToSpec:
    def test_inline_inline_is_identity_and_no_lookups(self) -> None:
        cfg = _make_config()
        tgt = _make_target()
        client = AsyncMock()

        out = _run_to_spec(AuditInputSpec(config=cfg, target=tgt), workspace="default", entity_client=client)
        assert out.config is cfg
        assert out.target is tgt
        client.get.assert_not_awaited()

    def test_ref_ref_resolves_both_with_default_workspace(self) -> None:
        resolved_cfg = _make_config(name="resolved-cfg")
        resolved_tgt = _make_target(name="resolved-tgt")

        client = AsyncMock()

        async def fake_get(entity_class, **kwargs):
            return resolved_cfg if entity_class is AuditConfig else resolved_tgt

        client.get = AsyncMock(side_effect=fake_get)

        out = _run_to_spec(
            AuditInputSpec(config="my-cfg", target="my-tgt"),
            workspace="default",
            entity_client=client,
        )

        assert out.config is resolved_cfg
        assert out.target is resolved_tgt
        # Both calls used the runtime-default workspace.
        calls = client.get.await_args_list
        assert len(calls) == 2
        assert {c.args[0] for c in calls} == {AuditConfig, AuditTargetEntity}
        for c in calls:
            assert c.kwargs["workspace"] == "default"
        assert {c.kwargs["name"] for c in calls} == {"my-cfg", "my-tgt"}

    def test_workspace_qualified_string_overrides_default(self) -> None:
        client = AsyncMock()
        client.get = AsyncMock(side_effect=[_make_config(workspace="prod"), _make_target(workspace="qa")])

        _run_to_spec(
            AuditInputSpec(config="prod/cfg-a", target="qa/tgt-b"),
            workspace="default",
            entity_client=client,
        )

        calls = client.get.await_args_list
        ws_by_name = {c.kwargs["name"]: c.kwargs["workspace"] for c in calls}
        assert ws_by_name == {"cfg-a": "prod", "tgt-b": "qa"}

    def test_unqualified_uses_runtime_workspace(self) -> None:
        client = AsyncMock()
        client.get = AsyncMock(side_effect=[_make_config(workspace="dev"), _make_target(workspace="dev")])

        _run_to_spec(
            AuditInputSpec(config="cfg", target="tgt"),
            workspace="dev",
            entity_client=client,
        )

        calls = client.get.await_args_list
        for c in calls:
            assert c.kwargs["workspace"] == "dev"

    def test_mixed_inline_config_ref_target(self) -> None:
        inline_cfg = _make_config(name="inline-cfg")
        resolved_tgt = _make_target(name="resolved-tgt")
        client = AsyncMock()
        client.get = AsyncMock(return_value=resolved_tgt)

        out = _run_to_spec(
            AuditInputSpec(config=inline_cfg, target="my-tgt"),
            workspace="default",
            entity_client=client,
        )

        assert out.config is inline_cfg
        assert out.target is resolved_tgt
        # Only one entity-client call: target.
        client.get.assert_awaited_once()
        assert client.get.await_args.args[0] is AuditTargetEntity

    def test_not_found_wraps_in_runtimeerror_with_kind_and_path(self) -> None:
        client = AsyncMock()
        client.get = AsyncMock(side_effect=NemoEntityNotFoundError("no such entity"))

        with pytest.raises(RuntimeError, match=r"audit config 'prod/missing-cfg' not found"):
            _run_to_spec(
                AuditInputSpec(config="prod/missing-cfg", target=_make_target()),
                workspace="default",
                entity_client=client,
            )

    def test_target_not_found_message_uses_target_kind(self) -> None:
        client = AsyncMock()
        client.get = AsyncMock(side_effect=NemoEntityNotFoundError("nope"))

        with pytest.raises(RuntimeError, match=r"audit target 'default/missing-tgt' not found"):
            _run_to_spec(
                AuditInputSpec(config=_make_config(), target="missing-tgt"),
                workspace="default",
                entity_client=client,
            )

    def test_falls_back_to_async_sdk_entities_when_client_is_none(self) -> None:
        """Local-mode scheduler passes ``entity_client=None``; we wrap async_sdk.entities."""
        resolved_cfg = _make_config(name="from-sdk")
        resolved_tgt = _make_target(name="from-sdk")

        # Wrap an EntityClient mock so the inner client.get is awaited.
        sdk_entities = MagicMock()
        async_sdk = MagicMock(entities=sdk_entities)

        with patch("nemo_auditor.jobs.audit.NemoEntitiesClient") as mock_cls:
            client = AsyncMock()
            client.get = AsyncMock(side_effect=[resolved_cfg, resolved_tgt])
            mock_cls.return_value = client

            out = asyncio.run(
                AuditJob.to_spec(
                    AuditInputSpec(config="cfg", target="tgt"),
                    workspace="default",
                    entity_client=None,
                    async_sdk=async_sdk,
                    is_local=True,
                )
            )

        # NemoEntitiesClient was constructed from async_sdk.entities exactly once.
        mock_cls.assert_called_once_with(sdk_entities)
        assert out.config is resolved_cfg
        assert out.target is resolved_tgt

    def test_raises_when_neither_client_nor_sdk_present_and_refs_used(self) -> None:
        """No client + name refs = unresolvable; clear error."""
        with pytest.raises(RuntimeError, match=r"no platform client was injected"):
            asyncio.run(
                AuditJob.to_spec(
                    AuditInputSpec(config="cfg", target="tgt"),
                    workspace="default",
                    entity_client=None,
                    async_sdk=None,
                    is_local=True,
                )
            )

    def test_no_client_required_when_both_inline(self) -> None:
        """Inline-only specs don't need any client at all."""
        out = asyncio.run(
            AuditJob.to_spec(
                AuditInputSpec(config=_make_config(), target=_make_target()),
                workspace="default",
                entity_client=None,
                async_sdk=None,
                is_local=True,
            )
        )
        assert isinstance(out, AuditSpec)
