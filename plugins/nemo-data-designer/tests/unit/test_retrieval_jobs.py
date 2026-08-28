# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock, patch

import data_designer.config as dd
import pandas as pd
import pytest
from nemo_data_designer_plugin.jobs.create import CreateJob
from nemo_data_designer_plugin.jobs.retrieval_generate import RetrievalGenerateJob
from nemo_data_designer_plugin.jobs.retrieval_prepare import RetrievalPrepareJob
from nemo_data_designer_plugin.jobs.retrieval_run import RetrievalRunJob
from nemo_data_designer_plugin.jobs.retrieval_spec import (
    RetrievalGenerateJobConfig,
    RetrievalGenerateStepConfig,
    RetrievalPrepareJobConfig,
    RetrievalPrepareStepConfig,
    RetrievalPreviewSpec,
    RetrievalRunJobConfig,
)
from nemo_data_designer_plugin.jobs.spec import DataDesignerJobConfig
from nemo_data_designer_plugin.retrieval.inline import wrapped_to_inline_jsonl
from nemo_data_designer_plugin.retrieval.unroll import unroll_training_data
from nemo_platform_plugin.jobs.api_factory import PlatformJobSpec, PlatformJobStep
from pydantic import ValidationError


def _steps(compiled: PlatformJobSpec) -> list[PlatformJobStep]:
    return list(compiled["steps"])


def _executor(step: PlatformJobStep) -> dict[str, Any]:
    return cast(dict[str, Any], step["executor"])


def _generate_config(**overrides: object) -> RetrievalGenerateJobConfig:
    payload = {"corpus": "default/docs", "provider": "default/nvidia-build", "profile": "embed"}
    payload.update(overrides)
    return RetrievalGenerateJobConfig.model_validate(payload)


def _ctx(tmp_path: Path) -> Mock:
    ephemeral = tmp_path / "ephemeral"
    persistent = tmp_path / "persistent"
    ephemeral.mkdir()
    persistent.mkdir()
    ctx = Mock()
    ctx.workspace = "default"
    ctx.storage.ephemeral = ephemeral
    ctx.storage.persistent = persistent
    ctx.results.save.return_value = SimpleNamespace(model_dump=lambda: {"name": "artifacts"})
    return ctx


@pytest.mark.asyncio
async def test_retrieval_generate_compile_is_cpu() -> None:
    spec = RetrievalGenerateStepConfig(
        job_config=_generate_config(),
        model_providers=[dd.ModelProvider(name="default/nvidia-build", endpoint="http://igw")],
        provider_name="default/nvidia-build",
    )
    compiled = await RetrievalGenerateJob.compile(
        workspace="default",
        spec=spec,
        entity_client=Mock(),
        job_name=None,
        async_sdk=AsyncMock(),
    )
    steps = _steps(compiled)
    assert len(steps) == 1
    executor = _executor(steps[0])
    assert executor["provider"] == "cpu"
    assert "nmp-cpu-tasks" in executor["container"]["image"]


@pytest.mark.asyncio
async def test_retrieval_generate_to_spec_injects_igw_providers() -> None:
    providers = [dd.ModelProvider(name="default/nvidia-build", endpoint="http://igw")]
    dd_ctx = AsyncMock()
    dd_ctx.get_model_providers = AsyncMock(return_value=providers)
    with patch(
        "nemo_data_designer_plugin.jobs.retrieval_generate.create_data_designer_context",
        return_value=dd_ctx,
    ):
        step = await RetrievalGenerateJob.to_spec(
            _generate_config(),
            workspace="default",
            entity_client=Mock(),
            async_sdk=AsyncMock(),
            is_local=False,
        )
    assert isinstance(step, RetrievalGenerateStepConfig)
    assert step.model_providers == providers
    assert step.provider_name == "default/nvidia-build"


def test_retrieval_generate_run_writes_artifacts(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    spec = RetrievalGenerateStepConfig(
        job_config=_generate_config(),
        model_providers=[dd.ModelProvider(name="default/nvidia-build", endpoint="http://igw")],
        provider_name="default/nvidia-build",
    )
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    result = SimpleNamespace(dataset_name="retrieval_sdg", num_records=3, output_path=tmp_path / "out.jsonl")
    with (
        patch("nemo_data_designer_plugin.jobs.retrieval_generate.materialize_corpus", return_value=corpus),
        patch(
            "nemo_data_designer_plugin.jobs.retrieval_generate.execute_generation",
            return_value=result,
        ) as run_generation,
        patch("nemo_data_designer_plugin.jobs.retrieval_generate.build_generation_run_config") as build_cfg,
    ):
        build_cfg.return_value = SimpleNamespace()
        output = RetrievalGenerateJob().run(spec.model_dump(mode="json"), ctx=ctx, sdk=Mock())
    run_generation.assert_called_once()
    assert output["exit_code"] == 0
    ctx.results.save.assert_called_once()


@pytest.mark.asyncio
async def test_retrieval_prepare_convert_only_is_cpu() -> None:
    spec = RetrievalPrepareStepConfig(
        job_config=RetrievalPrepareJobConfig(sdg_input="default/stage0", skip_mining=True),
        phase="convert",
    )
    compiled = await RetrievalPrepareJob.compile(
        workspace="default",
        spec=spec,
        entity_client=Mock(),
        job_name=None,
        async_sdk=AsyncMock(),
    )
    steps = _steps(compiled)
    assert len(steps) == 1
    assert _executor(steps[0])["provider"] == "cpu"


@pytest.mark.asyncio
async def test_retrieval_prepare_compile_adds_gpu_mining_step() -> None:
    spec = RetrievalPrepareStepConfig(
        job_config=RetrievalPrepareJobConfig(sdg_input="default/stage0", skip_mining=False),
        phase="convert",
    )
    compiled = await RetrievalPrepareJob.compile(
        workspace="default",
        spec=spec,
        entity_client=Mock(),
        job_name=None,
        async_sdk=AsyncMock(),
    )
    steps = _steps(compiled)
    assert len(steps) == 2
    assert _executor(steps[0])["provider"] == "cpu"
    assert _executor(steps[1])["provider"] == "gpu"
    assert "nmp-customizer-tasks" in _executor(steps[1])["container"]["image"]


def test_retrieval_prepare_convert_emits_eval_layout(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    sdg = tmp_path / "sdg"
    sdg.mkdir()
    jsonl = sdg / "qa.jsonl"
    jsonl.write_text("{}\n", encoding="utf-8")
    train_file = tmp_path / "converted" / "train.json"
    train_file.parent.mkdir()
    train_file.write_text(
        json.dumps({"corpus": {}, "data": [{"question": "q", "pos_doc": ["p"], "neg_doc": []}]}), encoding="utf-8"
    )
    spec = RetrievalPrepareStepConfig(
        job_config=RetrievalPrepareJobConfig(sdg_input=str(sdg), skip_mining=True),
        phase="convert",
    )
    conversion = SimpleNamespace(train_file=train_file)

    def _fake_convert(**kwargs: Any) -> SimpleNamespace:
        eval_dir = Path(kwargs["output_dir"]) / "eval_beir"
        eval_dir.mkdir(parents=True, exist_ok=True)
        (eval_dir / "corpus.jsonl").write_text("{}\n", encoding="utf-8")
        (eval_dir / "queries.jsonl").write_text("{}\n", encoding="utf-8")
        qrels = eval_dir / "qrels"
        qrels.mkdir()
        (qrels / "test.tsv").write_text("qid\tdocid\trel\n", encoding="utf-8")
        return conversion

    with patch(
        "nemo_data_designer_plugin.jobs.retrieval_prepare.execute_conversion",
        side_effect=_fake_convert,
    ):
        output = RetrievalPrepareJob().run(spec.model_dump(mode="json"), ctx=ctx, sdk=Mock())
    assert output["exit_code"] == 0
    staged = ctx.storage.persistent / "stage1_data_prep"
    assert (staged / "eval_beir" / "corpus.jsonl").exists()
    assert (staged / "training.jsonl").exists()
    assert (staged / "train.json").exists()


def test_retrieval_prepare_mine_calls_mining(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    out = ctx.storage.persistent / "stage1_data_prep"
    out.mkdir()
    (out / "train.json").write_text(json.dumps({"corpus": {}, "data": []}), encoding="utf-8")
    spec = RetrievalPrepareStepConfig(
        job_config=RetrievalPrepareJobConfig(sdg_input="default/stage0", skip_mining=False),
        phase="mine",
    )
    mined = out / "train_mined.automodel.json"
    unrolled = out / "train_mined.automodel_unrolled.json"

    def _fake_mine(**kwargs: Any) -> Path:
        output_file = Path(kwargs["output_file"])
        output_file.write_text(json.dumps({"corpus": {}, "data": []}), encoding="utf-8")
        return output_file

    with (
        patch(
            "nemo_data_designer_plugin.jobs.retrieval_prepare.run_hard_negative_mining", side_effect=_fake_mine
        ) as mine,
        patch(
            "nemo_data_designer_plugin.jobs.retrieval_prepare.unroll_training_file",
            return_value=unrolled,
        ) as unroll,
        patch("nemo_data_designer_plugin.jobs.retrieval_prepare.wrapped_to_inline_jsonl") as inline,
    ):
        unrolled.write_text(json.dumps({"corpus": {}, "data": []}), encoding="utf-8")
        RetrievalPrepareJob().run(spec.model_dump(mode="json"), ctx=ctx, sdk=Mock())
    mine.assert_called_once()
    unroll.assert_called_once()
    inline.assert_called_once()
    assert mined.exists()


@pytest.mark.asyncio
async def test_retrieval_run_compile_chains_generate_then_prepare() -> None:
    providers = [dd.ModelProvider(name="default/nvidia-build", endpoint="http://igw")]
    dd_ctx = AsyncMock()
    dd_ctx.get_model_providers = AsyncMock(return_value=providers)
    spec = RetrievalRunJobConfig(
        generate=_generate_config(),
        prepare=RetrievalPrepareJobConfig(skip_mining=True),
    )
    with patch(
        "nemo_data_designer_plugin.jobs.retrieval_generate.create_data_designer_context",
        return_value=dd_ctx,
    ):
        compiled = await RetrievalRunJob.compile(
            workspace="default",
            spec=spec,
            entity_client=Mock(),
            job_name=None,
            async_sdk=AsyncMock(),
        )
    names = [step["name"] for step in _steps(compiled)]
    assert names[0] == "retrieval-generate"
    assert "retrieval-prepare-convert" in names
    assert all(_executor(step)["provider"] == "cpu" for step in _steps(compiled))


def test_create_job_schema_rejects_dataframe_seeds() -> None:
    config = DataDesignerJobConfig(
        num_records=1,
        config=dd.DataDesignerConfig(
            columns=[dd.ExpressionColumnConfig(name="value", expr="1")],
            seed_config=dd.SeedConfig(source=dd.DataFrameSeedSource(df=pd.DataFrame({"value": [1]}))),
        ),
    )
    with pytest.raises(ValidationError):
        DataDesignerJobConfig.model_validate(config.model_dump())
    assert CreateJob.input_spec_schema is DataDesignerJobConfig


def test_preview_spec_reuses_generate_config() -> None:
    spec = RetrievalPreviewSpec(generate=_generate_config(), num_records=2)
    assert spec.num_records == 2
    assert spec.generate.profile == "embed"


def test_unroll_and_inline_jsonl(tmp_path: Path) -> None:
    records = [
        {
            "question_id": "q1",
            "question": "what?",
            "corpus_id": "c",
            "pos_doc": ["alpha", "beta"],
            "neg_doc": ["gamma"],
        }
    ]
    unrolled = unroll_training_data(records)
    assert len(unrolled) == 2
    wrapped = tmp_path / "train.json"
    wrapped.write_text(json.dumps({"corpus": {}, "data": unrolled}), encoding="utf-8")
    out = tmp_path / "training.jsonl"
    wrapped_to_inline_jsonl(wrapped, out)
    lines = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert lines[0]["query"] == "what?"
    assert lines[0]["pos_doc"] == "alpha"
    assert "gamma" in lines[0]["neg_doc"]


def test_retrieval_cli_prints_spec() -> None:
    from nemo_data_designer_plugin.cli.retrieval import retrieval_app
    from typer.testing import CliRunner

    runner = CliRunner()
    result = runner.invoke(
        retrieval_app,
        ["generate", "--corpus", "default/docs", "--provider", "default/nvidia-build", "--print-spec"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["corpus"] == "default/docs"
    assert payload["profile"] == "embed"
