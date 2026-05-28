# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import yaml
from nemo_guardrails_plugin.benchmarks.constants import (
    APP_MODEL_NAME,
    APP_PROVIDER,
    CS_MODEL_NAME,
    CS_PROVIDER,
    GUARDRAIL_CONFIG,
    VM_NAME,
    WORKSPACE,
)
from nemo_guardrails_plugin.benchmarks.seeding import (
    build_guardrail_config_data,
    seed_benchmark,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_provider(*, provider_name: str, served_model_name: str, entity_suffix: str = "entity") -> SimpleNamespace:
    return SimpleNamespace(
        name=provider_name,
        served_models=[
            SimpleNamespace(
                served_model_name=served_model_name,
                model_entity_id=f"{WORKSPACE}/{served_model_name.replace('/', '-')}-{entity_suffix}",
            )
        ],
    )


def _write_upstream_configs(ng_root: Path) -> Path:
    cs_dir = ng_root / "examples" / "configs" / "content_safety_local"
    cs_dir.mkdir(parents=True)
    (cs_dir / "config.yml").write_text(
        yaml.safe_dump(
            {
                "models": [
                    {
                        "type": "main",
                        "engine": "nim",
                        "model": "meta/llama-3.3-70b-instruct",
                        "parameters": {"base_url": "http://localhost:8000"},
                    },
                ],
                "rails": {"input": {"flows": ["content safety check input $model=content_safety"]}},
            }
        ),
        encoding="utf-8",
    )
    (cs_dir / "prompts.yml").write_text(
        yaml.safe_dump({"prompts": [{"task": "content_safety_check_input", "content": "..."}]}),
        encoding="utf-8",
    )
    return cs_dir


@pytest.fixture
def fake_client() -> MagicMock:
    client = MagicMock()
    client.inference.providers.create = MagicMock()
    client.inference.providers.retrieve = MagicMock(
        side_effect=lambda name, workspace=None: _make_provider(
            provider_name=name,
            served_model_name=APP_MODEL_NAME if name == APP_PROVIDER else CS_MODEL_NAME,
        )
    )
    client.inference.virtual_models.create = MagicMock(
        return_value=SimpleNamespace(name=VM_NAME, default_model_entity=f"{WORKSPACE}/app")
    )
    client.guardrail.configs.create = MagicMock(return_value=SimpleNamespace(name=GUARDRAIL_CONFIG))
    client.workspaces.create = MagicMock(return_value=SimpleNamespace(name=WORKSPACE))
    return client


# ---------------------------------------------------------------------------
# build_guardrail_config_data
# ---------------------------------------------------------------------------


class TestBuildGuardrailConfigData:
    def test_rewrites_models_and_inlines_prompts(self, tmp_path: Path) -> None:
        cs_dir = _write_upstream_configs(tmp_path)

        data = build_guardrail_config_data(
            source_config_dir=cs_dir,
            content_safety_model_entity="benchmark/cs-entity",
        )

        assert data["models"] == [{"type": "content_safety", "engine": "nim", "model": "benchmark/cs-entity"}]
        assert data["prompts"] == [{"task": "content_safety_check_input", "content": "..."}]
        # Non-models fields preserved.
        assert data["rails"]["input"]["flows"] == ["content safety check input $model=content_safety"]

    def test_missing_config_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="config.yml"):
            build_guardrail_config_data(
                source_config_dir=tmp_path / "nope",
                content_safety_model_entity="x/y",
            )


# ---------------------------------------------------------------------------
# seed_benchmark
# ---------------------------------------------------------------------------


class TestSeedBenchmark:
    def test_calls_sdk_with_expected_payloads(self, fake_client: MagicMock, tmp_path: Path) -> None:
        ng_root = tmp_path / "NeMo-Guardrails"
        _write_upstream_configs(ng_root)
        generated_dir = tmp_path / "generated"

        seeded = seed_benchmark(
            fake_client,
            nemoguardrails_repo_root=ng_root,
            generated_dir=generated_dir,
            provider_wait_timeout=1.0,
        )

        fake_client.workspaces.create.assert_called_once_with(
            name=WORKSPACE,
            description="Local IGW guardrails benchmark workspace",
            exist_ok=True,
        )
        # Both providers registered.
        provider_create_names = [c.kwargs["name"] for c in fake_client.inference.providers.create.call_args_list]
        assert sorted(provider_create_names) == sorted([APP_PROVIDER, CS_PROVIDER])

        # Guardrail config payload uses the discovered content-safety entity.
        gc_call = fake_client.guardrail.configs.create.call_args
        assert gc_call.kwargs["name"] == GUARDRAIL_CONFIG
        assert gc_call.kwargs["workspace"] == WORKSPACE
        assert gc_call.kwargs["exist_ok"] is True
        cs_entity = seeded.cs_model_entity
        assert gc_call.kwargs["data"]["models"][0]["model"] == cs_entity

        # VirtualModel uses the discovered app entity and points middleware at the
        # guardrail config we just created.
        vm_call = fake_client.inference.virtual_models.create.call_args
        assert vm_call.kwargs["name"] == VM_NAME
        assert vm_call.kwargs["default_model_entity"] == seeded.app_model_entity
        assert vm_call.kwargs["models"] == [{"model": seeded.app_model_entity, "backend_format": "OPENAI_CHAT"}]
        expected_middleware = [
            {
                "name": "nemo-guardrails",
                "config_type": "guardrail_config",
                "config_id": f"{WORKSPACE}/{GUARDRAIL_CONFIG}",
            }
        ]
        assert vm_call.kwargs["request_middleware"] == expected_middleware
        assert vm_call.kwargs["response_middleware"] == expected_middleware

    def test_generated_dir_contains_artifacts(self, fake_client: MagicMock, tmp_path: Path) -> None:
        ng_root = tmp_path / "NeMo-Guardrails"
        _write_upstream_configs(ng_root)
        generated_dir = tmp_path / "generated"

        seed_benchmark(
            fake_client,
            nemoguardrails_repo_root=ng_root,
            generated_dir=generated_dir,
            provider_wait_timeout=1.0,
        )

        assert (generated_dir / "app_provider.json").is_file()
        assert (generated_dir / "content_safety_provider.json").is_file()
        assert (generated_dir / "virtual_model.json").is_file()

        request_payload = json.loads(
            (generated_dir / "content_safety_local_nmp_request.json").read_text(encoding="utf-8")
        )
        assert request_payload["name"] == GUARDRAIL_CONFIG
        assert request_payload["exist_ok"] is True
        assert request_payload["data"]["models"][0]["type"] == "content_safety"

    def test_returns_seeded_resources(self, fake_client: MagicMock, tmp_path: Path) -> None:
        ng_root = tmp_path / "NeMo-Guardrails"
        _write_upstream_configs(ng_root)

        seeded = seed_benchmark(
            fake_client,
            nemoguardrails_repo_root=ng_root,
            generated_dir=tmp_path / "generated",
            provider_wait_timeout=1.0,
        )

        assert seeded.workspace == WORKSPACE
        assert seeded.vm_ref == f"{WORKSPACE}/{VM_NAME}"
        assert seeded.guardrail_config_ref == f"{WORKSPACE}/{GUARDRAIL_CONFIG}"

    def test_raises_if_served_models_never_populated(self, tmp_path: Path) -> None:
        ng_root = tmp_path / "NeMo-Guardrails"
        _write_upstream_configs(ng_root)

        client = MagicMock()
        client.workspaces.create = MagicMock()
        client.inference.providers.create = MagicMock()
        client.inference.providers.retrieve = MagicMock(return_value=SimpleNamespace(served_models=[]))

        with pytest.raises(TimeoutError, match="served model"):
            seed_benchmark(
                client,
                nemoguardrails_repo_root=ng_root,
                generated_dir=tmp_path / "generated",
                provider_wait_timeout=0.1,
            )
