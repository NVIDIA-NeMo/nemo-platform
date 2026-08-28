# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import ClassVar, Literal

from data_designer_nemo.context import create_data_designer_context
from data_designer_nemo.sdk_translation import async_to_sync_sdk
from nemo_data_designer_plugin.jobs.retrieval_spec import RetrievalPreviewSpec
from nemo_data_designer_plugin.retrieval.corpus import materialize_corpus
from nemo_data_designer_plugin.retrieval.generation import build_generation_run_config, execute_generation
from nemo_data_designer_plugin.retrieval.providers import build_retrieval_model_configs, resolve_retrieval_providers
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.function import NemoFunction
from nemo_platform_plugin.function_context import FunctionContext
from nemo_platform_plugin.functions.frames import Done, Error
from pydantic import BaseModel


class RetrievalPreviewFrame(BaseModel):
    kind: Literal["retrieval_preview"] = "retrieval_preview"
    num_seed_records: int
    num_preview_records: int


class RetrievalPreviewFunction(NemoFunction[RetrievalPreviewSpec]):
    name: ClassVar[str] = "retrieval-preview"
    description: ClassVar[str] = "Preview retrieval SDG generation without publishing a full job fileset."
    spec_schema: ClassVar[type[RetrievalPreviewSpec]] = RetrievalPreviewSpec
    generate_legacy_verbs: ClassVar[bool] = False

    async def run(
        self,
        spec: RetrievalPreviewSpec,
        *,
        ctx: FunctionContext,
        async_sdk: AsyncNeMoPlatform,
        is_local: bool = False,
    ) -> AsyncIterator[BaseModel]:
        job = spec.generate
        dd_ctx = create_data_designer_context(is_local, async_sdk, ctx.workspace)
        model_configs = build_retrieval_model_configs(
            profile=job.profile,
            provider=job.provider,
            chat_provider=job.chat_provider,
            embed_provider=job.embed_provider,
            artifact_extraction_model=job.artifact_extraction_model,
            qa_generation_model=job.qa_generation_model,
            quality_judge_model=job.quality_judge_model,
            embed_model=job.embed_model,
        )
        try:
            model_providers = await resolve_retrieval_providers(dd_ctx, model_configs)
        except Exception as exc:
            yield Error(message=str(exc), details={"type": type(exc).__name__})
            return

        sdk = async_sdk if isinstance(async_sdk, NeMoPlatform) else async_to_sync_sdk(async_sdk)
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            corpus_dir = materialize_corpus(
                job.corpus,
                dest=tmp_path / "corpus",
                sdk=sdk,
                workspace=ctx.workspace,
            )
            run_config = build_generation_run_config(
                corpus_dir=corpus_dir,
                output_dir=tmp_path / "out",
                artifact_path=tmp_path / "artifacts",
                dataset_name=job.dataset_name or job.corpus_id,
                chat_provider_name=job.chat_provider or job.provider,
                embed_provider_name=job.embed_provider or job.provider,
                model_providers=model_providers,
                profile=job.profile,
                file_extensions=job.file_extensions,
                min_text_length=job.min_text_length,
                sentences_per_chunk=job.sentences_per_chunk,
                num_sections=job.num_sections,
                num_files=job.num_files,
                max_artifacts_per_type=job.max_artifacts_per_type,
                num_pairs=job.num_pairs,
                query_counts=job.query_counts,
                min_hops=job.min_hops,
                max_hops=job.max_hops,
                reasoning_counts=job.reasoning_counts,
                min_complexity=job.min_complexity,
                similarity_threshold=job.similarity_threshold,
                buffer_size=job.buffer_size,
                resume=job.resume,
                num_records=spec.num_records,
                artifact_extraction_model=job.artifact_extraction_model,
                qa_generation_model=job.qa_generation_model,
                quality_judge_model=job.quality_judge_model,
                embed_model=job.embed_model,
            )
            result = execute_generation(run_config, preview=True)
            yield RetrievalPreviewFrame(
                num_seed_records=getattr(result, "num_seed_records", 0),
                num_preview_records=getattr(result, "num_preview_records", spec.num_records),
            )
        yield Done()
