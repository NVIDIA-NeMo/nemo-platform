# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Batch task entry point for the safe-synthesizer service.

This module serves as the entry point for the safe-synthesizer batch task,
which generates synthetic data using the Nemo Safe Synthesizer SDK.
"""

import os

# Disable PyTorch inductor remote cache to avoid Redis warnings from vLLM.
# These must be set before any PyTorch imports.
os.environ.setdefault("TORCHINDUCTOR_FX_GRAPH_REMOTE_CACHE", "0")
os.environ.setdefault("TORCHINDUCTOR_AUTOTUNE_REMOTE_CACHE", "0")

import json
import logging
import tempfile
import time
from pathlib import Path

import pandas as pd
from datasets import DatasetDict, load_dataset
from nemo_platform import NeMoPlatform
from nemo_platform.filesets import parse_fileset_ref
from nemo_safe_synthesizer.config.internal_results import SafeSynthesizerResults
from nemo_safe_synthesizer.config.job import SafeSynthesizerJobConfig
from nemo_safe_synthesizer.observability import initialize_observability
from nemo_safe_synthesizer.results import make_nss_results
from nemo_safe_synthesizer.sdk.library_builder import SafeSynthesizer
from nmp.common.config import Configuration
from nmp.common.jobs.constants import (
    DEFAULT_TASK_STORAGE_PATH,
    EPHEMERAL_TASK_STORAGE_PATH_ENVVAR,
    NEMO_JOB_ID_ENVVAR,
    NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR,
    NEMO_JOB_WORKSPACE_ENVVAR,
)
from nmp.common.jobs.file_manager import FilesetFileManager
from nmp.common.sdk_factory import get_platform_sdk
from nmp.safe_synthesizer.tasks.safe_synthesizer.jsonl_loader import load_jsonl_file
from nmp.safe_synthesizer.tasks.safe_synthesizer.logging_setup import configure_logging
from nmp.safe_synthesizer.tasks.safe_synthesizer.model_init import init_models_sync

configure_logging(os.environ.get("LOG_LEVEL", "INFO"))

logger = logging.getLogger("safe_synthesizer")


def download_from_fileset(fileset_url: str) -> pd.DataFrame:
    """Download a dataset from a fileset and load it as a DataFrame.

    Args:
        fileset_url: The fileset:// URL to download from.

    Returns:
        The loaded dataset as a pandas DataFrame.
    """
    workspace = os.environ.get(NEMO_JOB_WORKSPACE_ENVVAR, "default")
    workspace, fileset_name, _ = parse_fileset_ref(fileset_url, workspace_fallback=workspace)
    sdk = get_platform_sdk()

    file_manager = FilesetFileManager(
        workspace=workspace,
        fileset_name=fileset_name,
        sdk=sdk,
        ensure_fileset_exists=False,  # Fileset should already exist
    )

    logger.info(f"Downloading dataset from fileset: {fileset_url}")

    # Download the file using FilesetFileManager
    tmp_dir_path = file_manager.download_from_url(fileset_url)
    local_path = tmp_dir_path.path

    try:
        # Verify the file was downloaded
        if not local_path.exists():
            raise FileNotFoundError(f"Failed to download file from fileset. File not found at: {local_path}")

        file_size = local_path.stat().st_size
        logger.info(f"Downloaded file to {local_path}, size: {file_size} bytes")

        if file_size == 0:
            raise ValueError(f"Downloaded file is empty: {local_path}")

        # Load based on file extension
        return _load_file_as_dataframe(local_path)
    finally:
        # Clean up temp directory
        tmp_dir_path.cleanup_tmp_dir()


def _load_file_as_dataframe(local_path: Path) -> pd.DataFrame:
    """Load a file as a pandas DataFrame based on its extension."""
    suffix = local_path.suffix.lower()
    if suffix == ".csv":
        logger.info(f"Loading CSV file: {local_path}")
        return pd.read_csv(local_path)
    elif suffix == ".parquet":
        logger.info(f"Loading Parquet file: {local_path}")
        return pd.read_parquet(local_path)
    elif suffix == ".jsonl":
        logger.info(f"Loading JSONL file: {local_path}")
        return load_jsonl_file(str(local_path))
    elif suffix == ".json":
        logger.info(f"Loading JSON file: {local_path}")
        return pd.read_json(local_path)
    else:
        # Fall back to _load_local_dataset for other formats
        return _load_local_dataset(str(local_path))


def _load_local_dataset(path: str) -> pd.DataFrame:
    """Load dataset from local path.

    For JSONL files, uses Python's json module which properly handles:
    - Unicode escape sequences (like \\u2019)
    - Common JSON escaping issues from data conversion

    For other formats (CSV, Parquet, etc.), uses HuggingFace's load_dataset.
    """
    # Find dataset files in the directory
    jsonl_files = []
    other_files = []

    if os.path.isdir(path):
        for filename in os.listdir(path):
            filepath = os.path.join(path, filename)
            if os.path.isfile(filepath):
                if filename.endswith(".jsonl"):
                    jsonl_files.append(filepath)
                elif filename.endswith((".csv", ".parquet", ".json")):
                    other_files.append(filepath)
    elif os.path.isfile(path):
        if path.endswith(".jsonl"):
            jsonl_files.append(path)
        else:
            other_files.append(path)

    # If we have JSONL files, use our custom loader
    if jsonl_files:
        if len(jsonl_files) > 1:
            logger.warning("Multiple JSONL files found (%d), using the first one", len(jsonl_files))
        logger.info("Loading JSONL file with Python json module: %s", jsonl_files[0])
        return load_jsonl_file(jsonl_files[0])

    # For other formats, use HuggingFace's load_dataset
    hf_dataset = load_dataset(path=path)
    if isinstance(hf_dataset, DatasetDict):
        if len(hf_dataset) > 1:
            logger.warning("Multiple datasets found (%d), using the first one", len(hf_dataset))
        hf_dataset = hf_dataset[list(hf_dataset.keys())[0]]
    return hf_dataset.to_pandas()


def upload_results(result: SafeSynthesizerResults, adapter_path: Path | None = None):
    """Upload job results to the files service using FilesetFileManager.

    Args:
        result: The SafeSynthesizerResults to upload.
        adapter_path: Path to the trained adapter directory, if available.
    """
    job_id = os.environ.get(NEMO_JOB_ID_ENVVAR)
    if not job_id:
        raise ValueError(f"{NEMO_JOB_ID_ENVVAR} is not set")

    workspace = os.environ.get(NEMO_JOB_WORKSPACE_ENVVAR, "default")

    # Create SDK instances
    sdk = get_platform_sdk()

    # Create FilesetFileManager for results
    fileset_name = f"job-results-{job_id}"
    file_manager = FilesetFileManager(
        workspace=workspace,
        fileset_name=fileset_name,
        sdk=sdk,
        ensure_fileset_exists=True,  # Create fileset if it doesn't exist
    )

    # Validate/create storage
    file_manager.validate_storage()

    # Get attempt_id from job
    job = sdk.jobs.retrieve(name=job_id, workspace=workspace)
    attempt_id = job.attempt_id

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Upload synthetic data
        result_csv_path = temp_path / "result.csv"
        result.synthetic_data.to_csv(result_csv_path, index=False)
        remote_path = f"results/{attempt_id}/synthetic-data"
        artifact_url = file_manager.upload(result_csv_path, remote_path)
        logger.info(f"Uploaded synthetic data to {artifact_url}")
        _create_job_result(sdk, workspace, job_id, "synthetic-data", artifact_url)

        # Upload summary
        summary_json_path = temp_path / "summary.json"
        with open(summary_json_path, "w", encoding="utf-8") as f:
            json.dump(result.summary.model_dump(), f)
        remote_path = f"results/{attempt_id}/summary"
        artifact_url = file_manager.upload(summary_json_path, remote_path)
        logger.info(f"Uploaded summary to {artifact_url}")
        _create_job_result(sdk, workspace, job_id, "summary", artifact_url)

        # Upload evaluation report if available
        if result.evaluation_report_html:
            report_html_path = temp_path / "report.html"
            with open(report_html_path, "w", encoding="utf-8") as f:
                f.write(result.evaluation_report_html)
            remote_path = f"results/{attempt_id}/evaluation-report"
            artifact_url = file_manager.upload(report_html_path, remote_path)
            logger.info(f"Uploaded evaluation report to {artifact_url}")
            _create_job_result(sdk, workspace, job_id, "evaluation-report", artifact_url)

    # Upload adapter outside temp_dir since it lives on the local filesystem
    if adapter_path is not None and adapter_path.exists():
        remote_path = f"results/{attempt_id}/adapter"
        artifact_url = file_manager.upload(adapter_path, remote_path)
        logger.info(f"Uploaded adapter to {artifact_url}")
        _create_job_result(sdk, workspace, job_id, "adapter", artifact_url)


def _create_job_result(sdk: NeMoPlatform, workspace: str, job_name: str, result_name: str, artifact_url: str):
    """Create a job result record."""
    sdk.jobs.results.create(
        name=result_name,
        job=job_name,
        workspace=workspace,
        artifact_url=artifact_url,
        artifact_storage_type="fileset",
    )
    logger.info(f"Created job result: {result_name}")


def _setup_classify_endpoint():
    """Set up the NIM_ENDPOINT_URL for column classification from platform environment variables.

    The job compiler passes CLASSIFY_LLM_ENDPOINT_PATH (just the path) and the platform
    injects NMP_MODELS_URL. We combine them here to construct the full URL
    that the package code expects in NIM_ENDPOINT_URL.

    This keeps the package code simple - it only needs to know about NIM_ENDPOINT_URL.
    """
    # Check if we have the path-based configuration
    endpoint_path = os.environ.get("CLASSIFY_LLM_ENDPOINT_PATH")
    if endpoint_path:
        models_url = os.environ.get("NMP_MODELS_URL")
        if not models_url:
            logger.warning(
                "CLASSIFY_LLM_ENDPOINT_PATH is set but NMP_MODELS_URL is not available. "
                "Column classification may not work correctly."
            )
            return

        # Construct the full URL and set it as NIM_ENDPOINT_URL
        full_url = models_url.rstrip("/") + endpoint_path
        os.environ["NIM_ENDPOINT_URL"] = full_url
        logger.info(f"Configured column classification endpoint: {full_url}")


def run_task():
    initialize_observability()
    # Initialize model weights from Files API (if configured)
    # This downloads models to the HuggingFace cache before processing
    files_url = Configuration.get_platform_config().get_service_url("files")
    if files_url:
        logger.info("Initializing model weights from Files API...")
        results = init_models_sync(files_api_url=files_url)
        failed = [m for m, success in results.items() if not success]
        if failed:
            logger.warning(f"Some models failed to download: {failed}")
        else:
            logger.info(f"Successfully initialized {len(results)} model(s)")
    else:
        logger.debug("Files API URL not configured, skipping model initialization")

    # Set up column classification endpoint from platform environment variables
    _setup_classify_endpoint()

    data_source_url = os.environ.get("DATA_SOURCE")
    if data_source_url is None:
        raise ValueError("DATA_SOURCE is not set")

    # Download the dataset from the files service
    data_source = download_from_fileset(fileset_url=data_source_url)

    # Load job config
    config_file_path = os.environ[NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR]
    with open(config_file_path, "r") as f:
        job_config: dict = json.load(f)

    logger.debug(f"Nemo Safe Synthesizer passed job config args: {job_config}")

    # Read enable_synthesis from the raw dict before model_validate drops unknown fields.
    # The service stores this at the top level of the job config JSON so the task can
    # skip the training and generation phases for PII-only jobs.
    enable_synthesis: bool = job_config.get("enable_synthesis", True)
    logger.info(f"enable_synthesis={enable_synthesis}")

    if isinstance(job_config, dict):
        nss_job_config = SafeSynthesizerJobConfig.model_validate(job_config)
    else:
        raise ValueError(f"Config must be a dictionary: {job_config}")
    logger.info(f"Nemo Safe Synthesizer runtime job config: {nss_job_config.model_dump_json(indent=2)}")

    save_path = Path(os.environ.get(EPHEMERAL_TASK_STORAGE_PATH_ENVVAR, DEFAULT_TASK_STORAGE_PATH))
    logger.info(f"Using save_path: {save_path}")
    try:
        # NOTE: this is brittle, but open issue(s) exist for offline mode not working
        # quite right, see https://github.com/huggingface/huggingface_hub/issues/3201
        # this essentially disables retries out to huggingface, which we don't need
        # but a lot of huggingface/transformers code does by default
        from huggingface_hub.utils._http import http_backoff

        http_backoff.__kwdefaults__["max_retries"] = 0

        if not enable_synthesis:
            # PII-only mode: skip holdout (no evaluation needed) and skip training/generation.
            # Without this, process_data() enforces a 200-record minimum for the holdout split
            # which is unnecessary when we're only doing PII replacement.
            nss_job_config.config.data.holdout = 0
            nss_job_config.config.data.max_holdout = 0

        ss: SafeSynthesizer = SafeSynthesizer(config=nss_job_config.config, save_path=save_path).with_data_source(
            data_source
        )
        if enable_synthesis:
            ss.run()
        else:
            # PII-only mode: process data (PII replacement) without training or generation.
            ss.process_data()
            total_time = time.monotonic() - (ss._total_start or time.monotonic())
            # _train_df holds the PII-replaced training data after process_data().
            pii_replaced_df = ss._train_df
            if pii_replaced_df is None:
                raise RuntimeError("process_data() completed but _train_df is None")
            ss.results = make_nss_results(generate_results=pii_replaced_df, total_time=total_time)
    finally:
        http_backoff.__kwdefaults__["max_retries"] = 5

    adapter_path = None
    if ss._workdir:
        adapter_path = ss._workdir.adapter_path if enable_synthesis else None
    upload_results(result=ss.results, adapter_path=adapter_path)


if __name__ == "__main__":
    run_task()
