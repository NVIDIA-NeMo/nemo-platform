# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Live examples for evaluator plugin SDK execution."""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import os
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Any, cast

from nemo_evaluator.jobs.evaluate import EvaluateSpec
from nemo_evaluator.sdk import FilesetRef
from nemo_evaluator.sdk.resources import AsyncEvaluator
from nemo_evaluator.sdk.resources import Evaluator as SyncEvaluator
from nemo_evaluator.sdk.types import (
    ExecutionMode,
    PluginDatasetInput,
    RunConfig,
    RunConfigOnlineModel,
)
from nemo_evaluator.shared.metric_bundles.bundles import bundle_metric
from nemo_evaluator.shared.metric_bundles.cloudpickle import CloudpickleMetricBundlePackager
from nemo_evaluator_sdk.enums import MetricType
from nemo_evaluator_sdk.metrics.exact_match import ExactMatchMetric
from nemo_evaluator_sdk.metrics.llm_judge import LLMJudgeMetric
from nemo_evaluator_sdk.metrics.protocol import Metric, MetricInput, MetricOutput, MetricOutputSpec, MetricResult
from nemo_evaluator_sdk.values import (
    InferenceParams,
    JSONScoreParser,
    Model,
    RangeScore,
    SecretRef,
)
from nemo_evaluator_sdk.values.results import EvaluationResult
from nemo_platform import APIError, AsyncNeMoPlatform, ConflictError, NeMoPlatform, NotFoundError
from nemo_platform.types.files import HuggingfaceStorageConfigParam

if TYPE_CHECKING:
    import numpy as np


DEFAULT_BASE_URL = "http://localhost:8080"
DEFAULT_WORKSPACE = os.getenv("NMP_EVALUATOR_DEFAULT_WORKSPACE", "default")
DEFAULT_API_KEY_SECRET = os.getenv("NMP_EVALUATOR_DEFAULT_API_KEY_SECRET", "NVIDIA_API_KEY")
DATASET_NAME = os.getenv("NMP_EVALUATOR_PLUGIN_FILESET", "helpsteer2-eval")
HELPSTEER2_REMOTE_PATH = os.getenv("NMP_EVALUATOR_HELPSTEER2_REMOTE_PATH", "validation.jsonl.gz")
HELPFULNESS_PROMPT_V1 = (
    "You are an evaluator. Rate the response's helpfulness from 0-4. "
    'Return only a JSON object with this shape: {"helpfulness": <integer>}.'
)
ONLINE_CHAT_PROMPT_TEMPLATE = {"messages": [{"role": "user", "content": "{{item.prompt}}"}]}
LOCAL_HELPSTEER2_ROWS = (
    {
        "prompt": "What is the capital of France?",
        "response": "Paris is the capital of France.",
        "helpfulness": 4,
    },
    {
        "prompt": "Name one primary color.",
        "response": "Blue is a primary color.",
        "helpfulness": 4,
    },
)

model = Model(
    url="https://integrate.api.nvidia.com/v1/chat/completions",
    name=os.getenv("NEMO_DEFAULT_MODEL", "nvidia/nemotron-3-nano-30b-a3b"),
    # Local evaluator and local plugin execution resolve this as an environment variable name.
    api_key_secret=SecretRef(root=DEFAULT_API_KEY_SECRET),
)


class CustomResponseLengthMetric:
    """Tiny custom metric used to demonstrate code-generated metric bundles."""

    type = "custom-response-length"
    description = "Scores each row by response length."
    labels = {"source": "plugin-example"}

    def output_spec(self) -> list[MetricOutputSpec]:
        """Return the metric outputs recorded in the bundle metadata."""
        return [MetricOutputSpec.continuous_score("response-length")]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        """Score one row with a deterministic custom Python implementation."""
        response = str(input.row.data.get("response", ""))
        return MetricResult(outputs=[MetricOutput(name="response-length", value=float(len(response)))])


def configure_example_logging() -> None:
    """Enable SDK progress logs when this example file is executed directly."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")


async def _new_client() -> AsyncNeMoPlatform:
    """Create a platform client and verify the evaluator plugin is reachable."""
    client = AsyncNeMoPlatform(
        base_url=os.getenv("NMP_BASE_URL", DEFAULT_BASE_URL),
        workspace=DEFAULT_WORKSPACE,
        timeout=30000.0,
    )
    try:
        await cast(AsyncEvaluator, client.evaluator).plugin_status()
    except APIError as e:
        await _close_client(client)
        raise RuntimeError(
            f"Failed to connect to evaluator plugin. Ensure nemo-evaluator plugin is running along with `nemo services run`. Error: {e}"
        ) from None
    return client


def _new_sync_client() -> NeMoPlatform:
    """Create a sync platform client and verify the evaluator plugin is reachable."""
    client = NeMoPlatform(
        base_url=os.getenv("NMP_BASE_URL", DEFAULT_BASE_URL),
        workspace=DEFAULT_WORKSPACE,
        timeout=30000.0,
    )
    try:
        cast(SyncEvaluator, client.evaluator).plugin_status()
    except APIError as e:
        client.close()
        raise RuntimeError(
            f"Failed to connect to evaluator plugin. Ensure nemo-evaluator plugin is running along with `nemo services run`. Error: {e}"
        ) from None
    return client


async def _close_client(client: AsyncNeMoPlatform) -> None:
    """Close the platform client while tolerating local-run loop shutdown."""
    try:
        await client.close()
    except RuntimeError as error:
        if str(error) != "Event loop is closed":
            raise


def _load_helpsteer2_rows(payload: bytes, *, limit: int | None = None) -> list[dict[str, Any]]:
    """Decode downloaded HelpSteer2 JSONL or JSONL.GZ content into rows."""
    content = gzip.decompress(payload) if HELPSTEER2_REMOTE_PATH.endswith(".gz") else payload
    rows: list[dict[str, Any]] = []
    for line in content.decode("utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rows.append(row)
        if limit is not None and len(rows) >= limit:
            break
    return rows


def _validate_helpsteer2_rows(rows: Sequence[dict[str, Any]]) -> None:
    """Validate that the downloaded HelpSteer2 sample has fields used by the examples."""
    if not rows:
        raise AssertionError("Downloaded HelpSteer2 fileset did not contain any rows")
    missing = {"prompt", "response", "helpfulness"} - rows[0].keys()
    if missing:
        raise AssertionError(f"HelpSteer2 row is missing expected fields: {sorted(missing)}")


def write_local_helpsteer2_dataset(dataset_path: Path, *, row_count: int) -> None:
    """Write a small HelpSteer2-shaped JSONL file for local Path dataset examples."""
    rows = [LOCAL_HELPSTEER2_ROWS[index % len(LOCAL_HELPSTEER2_ROWS)] for index in range(row_count)]
    dataset_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


async def ensure_example_fileset(client: AsyncNeMoPlatform) -> FilesetRef:
    """Create or reuse the HelpSteer2 fileset, then verify the selected split downloads."""
    workspace = client.workspace or DEFAULT_WORKSPACE

    try:
        fileset = await client.files.filesets.create(
            workspace=workspace,
            name=DATASET_NAME,
            description="NVIDIA HelpSteer2 dataset for quality evaluation",
            storage=HuggingfaceStorageConfigParam(
                type="huggingface",
                repo_id="nvidia/HelpSteer2",
                repo_type="dataset",
            ),
        )
        print(f"Registered HelpSteer2 fileset: {fileset}")
    except ConflictError:
        fileset = await client.files.filesets.retrieve(name=DATASET_NAME, workspace=workspace)
        print(f"{fileset.workspace}/{fileset.name} dataset already registered")

    downloaded = await client.files.download_content(
        remote_path=HELPSTEER2_REMOTE_PATH,
        fileset=fileset.name,
        workspace=fileset.workspace,
    )
    rows = _load_helpsteer2_rows(downloaded, limit=2)
    _validate_helpsteer2_rows(rows)
    print(f"Verified HelpSteer2 split: {fileset.workspace}/{fileset.name}#{HELPSTEER2_REMOTE_PATH}")
    return FilesetRef(root=f"{fileset.workspace}/{fileset.name}").with_fragment(HELPSTEER2_REMOTE_PATH)


def ensure_example_fileset_sync(client: NeMoPlatform) -> FilesetRef:
    """Create or reuse the HelpSteer2 fileset with a sync client, then verify the selected split downloads."""
    workspace = client.workspace or DEFAULT_WORKSPACE

    try:
        fileset = client.files.filesets.create(
            workspace=workspace,
            name=DATASET_NAME,
            description="NVIDIA HelpSteer2 dataset for quality evaluation",
            storage=HuggingfaceStorageConfigParam(
                type="huggingface",
                repo_id="nvidia/HelpSteer2",
                repo_type="dataset",
            ),
        )
        print(f"Registered HelpSteer2 fileset: {fileset}")
    except ConflictError:
        fileset = client.files.filesets.retrieve(name=DATASET_NAME, workspace=workspace)
        print(f"{fileset.workspace}/{fileset.name} dataset already registered")

    downloaded = client.files.download_content(
        remote_path=HELPSTEER2_REMOTE_PATH,
        fileset=fileset.name,
        workspace=fileset.workspace,
    )
    rows = _load_helpsteer2_rows(downloaded, limit=2)
    _validate_helpsteer2_rows(rows)
    print(f"Verified HelpSteer2 split: {fileset.workspace}/{fileset.name}#{HELPSTEER2_REMOTE_PATH}")
    return FilesetRef(root=f"{fileset.workspace}/{fileset.name}").with_fragment(HELPSTEER2_REMOTE_PATH)


async def ensure_remote_evaluator_api_key_secret(workspace: str, client: AsyncNeMoPlatform) -> str:
    """Resolve an API key secret name and ensure it exists on the platform."""
    secret_name = DEFAULT_API_KEY_SECRET.lower()
    try:
        await client.secrets.retrieve(secret_name, workspace=workspace)
    except NotFoundError:
        api_key = os.getenv(DEFAULT_API_KEY_SECRET) or os.getenv("NVIDIA_API_KEY") or os.getenv("NVIDIA_BUILD_API_KEY")
        if api_key is None:
            raise RuntimeError(
                f"Remote online evaluation needs a platform secret named '{secret_name}' in workspace "
                f"'{workspace}'. Set NVIDIA_BUILD_API_KEY or NVIDIA_API_KEY to let this "
                "example create it, or create it manually with: "
                f"nemo secrets create {secret_name} --data '<api-key>' --workspace {workspace}"
            ) from None
        try:
            await client.secrets.create(workspace=workspace, name=secret_name, value=api_key)
            print("API key secret created for workspace")
        except ConflictError:
            pass
    return secret_name


async def model_with_valid_secret(
    *,
    execution_mode: ExecutionMode,
    workspace: str,
    client: AsyncNeMoPlatform,
) -> Model:
    """Return a model configured for local or remote NeMo Platform example execution."""
    if execution_mode == "remote":
        secret_name = await ensure_remote_evaluator_api_key_secret(workspace, client)
        return model.model_copy(update={"api_key_secret": SecretRef(root=secret_name)})
    return model


def create_helpfulness_metric(judge_model: Model) -> LLMJudgeMetric:
    """Build a reusable LLM judge metric for helpfulness scoring."""
    return LLMJudgeMetric(
        model=judge_model,
        scores=[
            RangeScore(
                name="helpfulness",
                minimum=0,
                maximum=4,
                parser=JSONScoreParser(json_path="helpfulness"),
                description="How well does the response help the user?",
            )
        ],
        inference=InferenceParams(
            temperature=0.0,
            max_tokens=32768,
        ),
        prompt_template={
            "messages": [
                {"role": "system", "content": HELPFULNESS_PROMPT_V1},
                {
                    "role": "user",
                    "content": (
                        "User prompt: {{item.prompt}}\n\n"
                        "Assistant response: {{sample.output_text | default(item.response)}}\n\n"
                        "Rate this response."
                    ),
                },
            ],
        },
    )


def _print_example_separator(name: str, **params: Any) -> None:
    """Print a visible section header for an independently runnable example."""
    edge = "====="
    inner = name
    if params:
        inner += "(" + ", ".join(f"{k}={v!r}" for k, v in params.items()) + ")"
    middle_line = f"{edge} {inner} {edge}"
    rule = "=" * len(middle_line)
    print(f"\n{rule}\n{middle_line}\n{rule}\n")


def _offline_exact_match_metric() -> ExactMatchMetric:
    """Build a deterministic exact-match metric for offline HelpSteer2 rows."""
    return ExactMatchMetric(
        type=MetricType.EXACT_MATCH,
        reference="{{item.response}}",
        candidate="{{item.response}}",
    )


def _online_exact_match_metric() -> ExactMatchMetric:
    """Build an online exact-match metric that compares model output to HelpSteer2 responses."""
    return ExactMatchMetric(type=MetricType.EXACT_MATCH, reference="{{item.response}}")


def build_custom_metric_submit_spec_example() -> dict[str, Any]:
    """Return the generated job spec for remote custom metric submission.

    The cloudpickle payload contains base64-encoded Python bytes. It is not a
    field users should hand-author; generate it from the metric object with a
    metric payload packager, or pass the packager to ``submit``.
    """
    metric = CustomResponseLengthMetric()
    spec = EvaluateSpec.model_validate(
        {
            "metrics": [
                bundle_metric(metric, CloudpickleMetricBundlePackager()).model_dump(mode="json"),
            ],
            "dataset": [{"response": "Paris is the capital of France."}],
            "params": RunConfig(limit_samples=1).model_dump(mode="json"),
        }
    )
    return spec.model_dump(mode="json")


def _assert_exact_match_result(result: EvaluationResult, *, workflow: str, expected_rows: int) -> None:
    """Assert the deterministic offline exact-match examples scored every selected row."""
    if len(result.row_scores) != expected_rows:
        raise AssertionError(f"{workflow} returned {len(result.row_scores)} row scores, expected {expected_rows}")

    matching_scores = [
        score for score in result.aggregate_scores.scores if score.name in {"exact-match", "exact-match.exact-match"}
    ]
    if not matching_scores:
        raise AssertionError(f"{workflow} did not return an exact-match aggregate score: {result.aggregate_scores}")

    actual_mean = matching_scores[0].mean
    if actual_mean is None or abs(actual_mean - 1.0) > 1e-9:
        raise AssertionError(f"{workflow} exact-match mean was {actual_mean}, expected 1.0")
    print(f"{workflow}: exact-match mean={actual_mean:.3f}, rows={len(result.row_scores)}")


async def _evaluate_metric(
    evaluator_plugin_client: AsyncEvaluator,
    *,
    execution_mode: ExecutionMode,
    metric: Metric,
    dataset: PluginDatasetInput,
    config: RunConfig | RunConfigOnlineModel,
    **run_kwargs: Any,
) -> EvaluationResult:
    """Run locally or submit remotely based on the requested plugin SDK execution mode."""
    if execution_mode == "local":
        return await evaluator_plugin_client.run(
            metric=metric,
            dataset=dataset,
            config=config,
            **run_kwargs,
        )

    job = await evaluator_plugin_client.submit(
        metric=metric,
        dataset=dataset,
        config=config,
        metric_bundle_packager=CloudpickleMetricBundlePackager(),
        **run_kwargs,
    )
    print(f"Submitted evaluator plugin job: {job.name}")
    await job.wait_until_done(
        poll_interval_seconds=1,
        job_timeout_seconds=300,
        pending_timeout_seconds=120,
    )
    return await job.get_result()


def extract_helpfulness_scores(
    row_scores: Sequence[Any],
    *,
    dimension: str = "helpfulness",
    metric_ref: str | None = None,
    judge_response_index: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    """Extract aligned judge and human score arrays from metric-job rows."""
    import numpy as np

    judge_scores = []
    human_scores = []
    failed_requests = 0

    for row in row_scores:
        try:
            human_score = float(row.item[dimension])

            if metric_ref is None:
                if not row.requests:
                    raise ValueError("Missing judge request payload")
                judge_response = row.requests[judge_response_index]["response"]["choices"][0]["message"]["content"]
                judge_data = json.loads(judge_response)
                judge_score = float(judge_data[dimension])
            else:
                judge_score = float(row.metrics[metric_ref][0].value)

            human_scores.append(human_score)
            judge_scores.append(judge_score)
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
            failed_requests += 1
            continue

    print(f"Total errors: {failed_requests}")
    return np.array(judge_scores), np.array(human_scores)


async def _run_online_metric_example_body(
    *,
    client: AsyncNeMoPlatform,
    dataset: PluginDatasetInput,
    workflow_label: str,
    is_online: bool,
    execution_mode: ExecutionMode,
    limit_samples: int,
) -> None:
    """Evaluate one exact-match metric against an already-built dataset.

    Shared body for the FilesetRef and local-file driver examples; callers are
    responsible for constructing the dataset and managing the client lifecycle.
    """
    evaluator_plugin_client = cast(AsyncEvaluator, client.evaluator)
    run_kwargs: dict[str, Any] = {}
    metric: Metric = _offline_exact_match_metric()
    config: RunConfig | RunConfigOnlineModel = RunConfig(limit_samples=limit_samples)

    if is_online:
        metric = _online_exact_match_metric()
        config = RunConfigOnlineModel(parallelism=4, limit_samples=limit_samples)
        run_kwargs["target"] = await model_with_valid_secret(
            execution_mode=execution_mode,
            workspace=DEFAULT_WORKSPACE,
            client=client,
        )
        run_kwargs["prompt_template"] = ONLINE_CHAT_PROMPT_TEMPLATE

    result = await _evaluate_metric(
        evaluator_plugin_client,
        execution_mode=execution_mode,
        metric=metric,
        dataset=dataset,
        config=config,
        **run_kwargs,
    )

    if not is_online:
        _assert_exact_match_result(
            result,
            workflow=f"{execution_mode} {workflow_label}",
            expected_rows=limit_samples,
        )
    else:
        result.print_summary()


async def run_nmp_online_metric_example(
    is_online: bool = False,
    execution_mode: ExecutionMode = "local",
    limit_samples: int = 2,
) -> None:
    """Evaluate one metric through the plugin SDK using local run or remote submit."""
    _print_example_separator(
        run_nmp_online_metric_example.__name__,
        is_online=is_online,
        execution_mode=execution_mode,
        limit_samples=limit_samples,
    )
    client = await _new_client()
    try:
        dataset = await ensure_example_fileset(client)
        await _run_online_metric_example_body(
            client=client,
            dataset=dataset,
            workflow_label="exact-match",
            is_online=is_online,
            execution_mode=execution_mode,
            limit_samples=limit_samples,
        )
    finally:
        await _close_client(client)


def run_nmp_online_metric_example_sync_client(
    is_online: bool = False,
    execution_mode: ExecutionMode = "local",
    limit_samples: int = 2,
) -> None:
    """Evaluate one metric through the plugin SDK using a sync platform client."""
    _print_example_separator(
        run_nmp_online_metric_example_sync_client.__name__,
        is_online=is_online,
        execution_mode=execution_mode,
        limit_samples=limit_samples,
    )
    client = _new_sync_client()
    try:
        dataset = ensure_example_fileset_sync(client)
        evaluator_plugin_client = cast(SyncEvaluator, client.evaluator)
        run_kwargs: dict[str, Any] = {}
        metric: Metric = _offline_exact_match_metric()
        config: RunConfig | RunConfigOnlineModel = RunConfig(limit_samples=limit_samples)

        if is_online:
            metric = _online_exact_match_metric()
            config = RunConfigOnlineModel(parallelism=4, limit_samples=limit_samples)
            run_kwargs["target"] = model
            run_kwargs["prompt_template"] = ONLINE_CHAT_PROMPT_TEMPLATE

        if execution_mode == "local":
            result = evaluator_plugin_client.run(
                metric=metric,
                dataset=dataset,
                config=config,
                **run_kwargs,
            )
        else:
            job = evaluator_plugin_client.submit(
                metric=metric,
                dataset=dataset,
                config=config,
                metric_bundle_packager=CloudpickleMetricBundlePackager(),
                **run_kwargs,
            )
            print(f"Submitted evaluator plugin job: {job.name}")
            job.wait_until_done(
                poll_interval_seconds=1,
                job_timeout_seconds=300,
                pending_timeout_seconds=120,
            )
            result = job.get_result()
            artifacts_dir = job.download_artifacts(path="evaluation_artifacts")
            print(f"Saved artifacts under {artifacts_dir}")

        if not is_online:
            _assert_exact_match_result(
                result,
                workflow=f"sync {execution_mode} exact-match",
                expected_rows=limit_samples,
            )
        else:
            result.print_summary()
    finally:
        client.close()


async def run_nmp_online_metric_local_file_example(
    is_online: bool = False,
    execution_mode: ExecutionMode = "local",
    limit_samples: int = 2,
) -> None:
    """Evaluate one metric through the plugin SDK using a local JSONL Path dataset."""
    _print_example_separator(
        run_nmp_online_metric_local_file_example.__name__,
        is_online=is_online,
        execution_mode=execution_mode,
        limit_samples=limit_samples,
    )
    client = await _new_client()
    try:
        with TemporaryDirectory(prefix="nmp-evaluator-plugin-") as dataset_dir:
            dataset_path = Path(dataset_dir) / "helpsteer2-local.jsonl"
            write_local_helpsteer2_dataset(dataset_path, row_count=limit_samples)
            await _run_online_metric_example_body(
                client=client,
                dataset=dataset_path,
                workflow_label="local-file exact-match",
                is_online=is_online,
                execution_mode=execution_mode,
                limit_samples=limit_samples,
            )
    finally:
        await _close_client(client)


async def run_nmp_llm_judge_example(
    is_online: bool = False,
    limit_samples: int = 2,
    execution_mode: ExecutionMode = "local",
) -> None:
    """Evaluate a helpfulness judge through the plugin SDK using local run or remote submit."""
    _print_example_separator(
        run_nmp_llm_judge_example.__name__,
        is_online=is_online,
        limit_samples=limit_samples,
        execution_mode=execution_mode,
    )
    client = await _new_client()

    try:
        dataset = await ensure_example_fileset(client)
        run_kwargs: dict[str, Any] = {}
        judge_model = await model_with_valid_secret(
            execution_mode=execution_mode,
            workspace=DEFAULT_WORKSPACE,
            client=client,
        )
        evaluator_plugin_client = cast(AsyncEvaluator, client.evaluator)
        config: RunConfig | RunConfigOnlineModel = RunConfig(limit_samples=limit_samples)

        if is_online:
            config = RunConfigOnlineModel(parallelism=4, limit_samples=limit_samples)
            run_kwargs["target"] = judge_model
            run_kwargs["prompt_template"] = ONLINE_CHAT_PROMPT_TEMPLATE

        result = await _evaluate_metric(
            evaluator_plugin_client,
            execution_mode=execution_mode,
            metric=create_helpfulness_metric(judge_model),
            dataset=dataset,
            config=config,
            **run_kwargs,
        )
        result.print_summary()
    finally:
        await _close_client(client)

    judge_scores, human_scores = extract_helpfulness_scores(
        result.row_scores,
        judge_response_index=1 if is_online else 0,
    )
    print(f"\nEvaluated: {len(judge_scores)} samples")
    if len(judge_scores):
        print(f"judge avg: {judge_scores.mean()}")
        print(f"human avg: {human_scores.mean()}")


async def run_examples() -> None:
    """Execute the example workflows exposed by this module."""
    await run_nmp_online_metric_example(is_online=False, execution_mode="local")
    await run_nmp_online_metric_example(is_online=False, execution_mode="remote")
    await run_nmp_llm_judge_example(is_online=False, execution_mode="local")
    await run_nmp_llm_judge_example(is_online=True, execution_mode="remote")
    await run_nmp_online_metric_local_file_example(is_online=False, execution_mode="local")


def run_sync_examples() -> None:
    """Execute the synchronous example workflows exposed by this module."""
    run_nmp_online_metric_example_sync_client(is_online=False, execution_mode="remote")


if __name__ == "__main__":
    configure_example_logging()

    run_sync_examples()
    asyncio.run(run_examples())
