# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import shutil
from pathlib import Path
from typing import ClassVar, cast

from nemo_data_designer_plugin.jobs.retrieval_common import retrieval_step, work_dir
from nemo_data_designer_plugin.jobs.retrieval_spec import RetrievalPrepareJobConfig, RetrievalPrepareStepConfig
from nemo_data_designer_plugin.retrieval.conversion import execute_conversion
from nemo_data_designer_plugin.retrieval.corpus import materialize_corpus
from nemo_data_designer_plugin.retrieval.inline import wrapped_to_inline_jsonl
from nemo_data_designer_plugin.retrieval.mining import run_hard_negative_mining
from nemo_data_designer_plugin.retrieval.unroll import unroll_training_file
from nemo_platform import NeMoPlatform
from nemo_platform_plugin.job import NemoJob
from nemo_platform_plugin.job_context import JobContext
from nemo_platform_plugin.jobs.api_factory import PlatformJobSpec
from pydantic import BaseModel


class RetrievalPrepareJob(NemoJob):
    name: ClassVar[str] = "retrieval-prepare"
    description: ClassVar[str] = "Convert retrieval SDG output to eval_beir and training JSONL (Nemotron Stage 1)."
    container: ClassVar[str] = "cpu-tasks"
    generate_legacy_verbs: ClassVar[bool] = False

    input_spec_schema = RetrievalPrepareJobConfig
    spec_schema = RetrievalPrepareStepConfig

    @classmethod
    async def to_spec(
        cls,
        input_spec: BaseModel,
        *,
        workspace: str,
        entity_client: object,
        async_sdk: object,
        is_local: bool,
    ) -> BaseModel:
        job_config = cast(RetrievalPrepareJobConfig, input_spec)
        if not job_config.sdg_input and not job_config.train_input_file:
            raise ValueError("One of sdg_input or train_input_file is required.")
        if job_config.sdg_input and job_config.train_input_file:
            raise ValueError("sdg_input and train_input_file are mutually exclusive.")
        return RetrievalPrepareStepConfig(job_config=job_config, phase="convert")

    @classmethod
    async def compile(
        cls,
        *,
        workspace: str,
        spec: BaseModel,
        entity_client: object,
        job_name: str | None,
        async_sdk: object,
        profile: str | None = None,
        options: dict | None = None,
    ) -> PlatformJobSpec:
        spec = cast(RetrievalPrepareStepConfig, spec)
        steps = [
            await retrieval_step(
                "retrieval-prepare-convert",
                "nemo_data_designer_plugin.jobs.retrieval_prepare",
                spec,
                profile=profile,
                async_sdk=async_sdk,
            )
        ]
        if not spec.job_config.skip_mining:
            mine_spec = spec.model_copy(update={"phase": "mine"})
            steps.append(
                await retrieval_step(
                    "retrieval-prepare-mine",
                    "nemo_data_designer_plugin.jobs.retrieval_prepare",
                    mine_spec,
                    profile=profile,
                    async_sdk=async_sdk,
                    gpu=True,
                )
            )
        return PlatformJobSpec(steps=steps)

    def run(self, config: dict, *, ctx: JobContext, sdk: NeMoPlatform, is_local: bool = False) -> dict:
        step = RetrievalPrepareStepConfig.model_validate(config)
        output_dir = work_dir(ctx, "stage1_data_prep")
        if step.phase == "mine":
            return _run_mine(step.job_config, output_dir, ctx)
        return _run_convert(step.job_config, output_dir, ctx, sdk)


def _materialize_input(ref: str, dest: Path, ctx: JobContext, sdk: NeMoPlatform) -> Path:
    local = Path(ref)
    if local.exists():
        return local.resolve()
    staged = (ctx.storage.persistent or ctx.storage.ephemeral) / ref
    if staged.exists():
        return staged
    return materialize_corpus(ref, dest=dest, sdk=sdk, workspace=ctx.workspace)


def _run_convert(job: RetrievalPrepareJobConfig, output_dir: Path, ctx: JobContext, sdk: NeMoPlatform) -> dict:
    if job.train_input_file:
        train_file = _materialize_input(job.train_input_file, ctx.storage.ephemeral / "train_input", ctx, sdk)
        if train_file.is_dir():
            candidate = train_file / "train.json"
            train_file = candidate if candidate.exists() else next(train_file.rglob("train.json"))
    else:
        assert job.sdg_input is not None
        sdg_root = _materialize_input(job.sdg_input, ctx.storage.ephemeral / "sdg_input", ctx, sdk)
        input_path = sdg_root if sdg_root.is_file() else _find_generation_input(sdg_root)
        conversion = execute_conversion(
            input_path=input_path,
            output_dir=output_dir,
            corpus_id=job.corpus_id,
            quality_threshold=job.quality_threshold,
            train_ratio=job.train_ratio,
            val_ratio=job.val_ratio,
            seed=job.seed,
            max_pos_docs=job.max_pos_docs,
            use_group_id_in_eval=job.use_group_id_in_eval,
            split_strategy=job.split_strategy,
        )
        if conversion.train_file is None:
            raise RuntimeError("Retrieval SDG conversion did not produce a training file")
        train_file = conversion.train_file

    train_file = _stage_train_file(Path(train_file), output_dir)

    if job.skip_mining:
        inline_path = output_dir / "training.jsonl"
        wrapped_to_inline_jsonl(train_file, inline_path)
        artifacts = ctx.results.save(name="artifacts", local_path=output_dir)
        return {
            "exit_code": 0,
            "workspace": ctx.workspace,
            "train_file": str(train_file),
            "results": {"artifacts": artifacts.model_dump()},
        }

    artifacts = ctx.results.save(name="artifacts", local_path=output_dir)
    return {
        "exit_code": 0,
        "workspace": ctx.workspace,
        "train_file": str(train_file),
        "results": {"artifacts": artifacts.model_dump()},
    }


def _run_mine(job: RetrievalPrepareJobConfig, output_dir: Path, ctx: JobContext) -> dict:
    train_file = output_dir / "train.json"
    if not train_file.exists():
        matches = list(output_dir.rglob("train.json"))
        if not matches:
            raise FileNotFoundError(f"train.json not found under {output_dir}")
        train_file = matches[0]
    mined = output_dir / "train_mined.automodel.json"
    run_hard_negative_mining(
        train_file=train_file,
        output_file=mined,
        cache_dir=output_dir / "cache_embeddings",
        base_model=job.base_model,
        hard_negatives_to_mine=job.hard_negatives_to_mine,
        hard_neg_margin=job.hard_neg_margin,
        mining_batch_size=job.mining_batch_size,
        query_prefix=job.query_prefix,
        passage_prefix=job.passage_prefix,
        query_max_length=job.query_max_length,
        passage_max_length=job.passage_max_length,
        attn_implementation=job.attn_implementation,
        trust_remote_code=job.trust_remote_code,
    )
    unrolled = unroll_training_file(mined, output_dir / "train_mined.automodel_unrolled.json")
    wrapped_to_inline_jsonl(unrolled, output_dir / "training.jsonl")
    artifacts = ctx.results.save(name="artifacts", local_path=output_dir)
    return {
        "exit_code": 0,
        "workspace": ctx.workspace,
        "train_file": str(unrolled),
        "results": {"artifacts": artifacts.model_dump()},
    }


def _stage_train_file(train_file: Path, output_dir: Path) -> Path:
    dest = output_dir / "train.json"
    if train_file.resolve() == dest.resolve():
        return dest
    if train_file.is_file():
        shutil.copy2(train_file, dest)
        return dest
    raise FileNotFoundError(f"Training file is not a file: {train_file}")


def _find_generation_input(root: Path) -> Path:
    manifest = root / "generation_result.json"
    if manifest.exists():
        return manifest
    jsonl = list(root.rglob("*.jsonl"))
    if jsonl:
        return jsonl[0]
    raise FileNotFoundError(f"No generation_result.json or JSONL under {root}")


if __name__ == "__main__":
    from nemo_data_designer_plugin.jobs.retrieval_bridge import run_job_module

    raise SystemExit(run_job_module(RetrievalPrepareJob, RetrievalPrepareStepConfig))
