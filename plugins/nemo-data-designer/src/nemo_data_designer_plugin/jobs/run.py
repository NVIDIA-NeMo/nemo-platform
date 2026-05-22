# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import logging

import data_designer.config as dd
from data_designer.logging import _make_json_formatter
from data_designer_nemo.context import create_data_designer_context
from data_designer_nemo.fileset_file_seed_reader import workspace_cvar
from nemo_data_designer_plugin._data_designer import create_data_designer
from nemo_data_designer_plugin.jobs.result_manager import DataDesignerResultManager
from nemo_data_designer_plugin.jobs.spec import DataDesignerStepConfig
from nemo_platform import NeMoPlatform
from nemo_platform_plugin.job_context import JobContext
from nemo_platform_plugin.job_results import ResultRef

logger = logging.getLogger(__name__)

BUFFER_SIZE = 500


def run_step_config(
    step_config: DataDesignerStepConfig,
    ctx: JobContext,
    sdk: NeMoPlatform,
    is_local: bool,
) -> int:
    result = run_step_config_result(step_config, ctx, sdk, is_local)
    exit_code = result.get("exit_code")
    return exit_code if isinstance(exit_code, int) else 1


def run_step_config_result(
    step_config: DataDesignerStepConfig,
    ctx: JobContext,
    sdk: NeMoPlatform,
    is_local: bool,
) -> dict[str, object]:
    try:
        return _run_step_config(step_config, ctx, sdk, is_local)
    except Exception as exc:
        logger.exception("Data Designer job failed: %s", exc)
        return {
            "exit_code": 1,
            "workspace": ctx.workspace,
            "num_records": step_config.job_config.num_records,
            "error": str(exc),
        }


def _run_step_config(
    step_config: DataDesignerStepConfig,
    ctx: JobContext,
    sdk: NeMoPlatform,
    is_local: bool,
) -> dict[str, object]:
    if not is_local:
        # In dispatched-container mode the root logger has no handler;
        # attach our JSON-formatted stderr handler so the container's
        # stdout carries machine-parseable lines for log aggregation.
        #
        # Skip in local mode: the scheduler's _ensure_local_logging_configured
        # already attached a plain stderr handler to the root logger at
        # INFO. Adding a data_designer-scoped handler on top would
        # double-emit every log line (one JSON, one plain) because
        # records propagate up the logger hierarchy by default.
        _configure_logging()

    workspace = ctx.workspace
    workspace_cvar.set(workspace)

    dd_ctx = create_data_designer_context(is_local, sdk, workspace)

    config_builder = dd.DataDesignerConfigBuilder.from_config(step_config.job_config.config.to_dict())

    artifact_path = ctx.storage.ephemeral

    result_manager = DataDesignerResultManager(
        results=ctx.results,
        artifacts_path=artifact_path,
    )

    data_designer = create_data_designer(
        artifact_path=artifact_path,
        model_providers=step_config.model_providers,
        dd_ctx=dd_ctx,
    )
    data_designer.set_run_config(dd.RunConfig(buffer_size=BUFFER_SIZE))
    # TODO: set `on_batch_complete=lambda _: result_manager.save_artifacts()` once it is available here
    dataset_creation_results = data_designer.create(config_builder, num_records=step_config.job_config.num_records)

    artifacts_result = result_manager.save_artifacts()
    analysis_result = result_manager.save_analysis(dataset_creation_results.load_analysis())

    logger.info("Job complete")
    return {
        "exit_code": 0,
        "workspace": workspace,
        "num_records": step_config.job_config.num_records,
        "results": {
            "artifacts": artifacts_result.model_dump(),
            "analysis": analysis_result.model_dump(),
        },
        "dataset_path": _artifact_child_url(artifacts_result, "dataset/parquet-files"),
    }


def _artifact_child_url(result: ResultRef, child_path: str) -> str:
    return f"{result.artifact_url.rstrip('/')}/{child_path.lstrip('/')}"


def _configure_logging() -> None:
    formatter = _make_json_formatter()
    formatter_type = type(formatter)

    for module in ["data_designer", "nemo_data_designer_plugin"]:
        module_logger = logging.getLogger(module)
        if any(
            isinstance(handler, logging.StreamHandler) and isinstance(handler.formatter, formatter_type)
            for handler in module_logger.handlers
        ):
            continue

        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        module_logger.addHandler(handler)
        module_logger.setLevel("INFO")
