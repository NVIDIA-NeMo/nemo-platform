# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Internal orchestration for the developer-facing ``run.py`` script.

``run.py`` constructs ``CustomGymEnvironmentWorkflow`` and calls ``run()``.
This module owns the ordered operation: prepare and upload an environment,
configure inference, submit an evaluation, verify generic runtime evidence,
and clean up. Submission details, input adapters, and prerequisite checks live
in dedicated modules so this file remains focused on the lifecycle.
"""

from __future__ import annotations

import http.client
import math
import subprocess
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import ascii_tree_example
import prepare
from artifacts import read_json, write_json
from commands import CommandRunner
from config import Settings
from console import Console
from nemo_platform import NeMoPlatform
from prerequisites import DeploymentImages, PrerequisiteChecker
from submit import EvaluationSubmission, submit_and_validate

TOTAL_STEPS = 7


class ResultVerificationError(RuntimeError):
    """Raised when a completed workflow does not meet an acceptance criterion."""


def require_result(condition: bool, message: str) -> None:
    """Raise a focused verification error when an acceptance criterion fails."""
    if not condition:
        raise ResultVerificationError(message)


def nested_messages(value: Any) -> list[str]:
    """Collect every string-valued ``message`` field from nested JSON data."""
    messages: list[str] = []
    if isinstance(value, dict):
        message = value.get("message")
        if isinstance(message, str):
            messages.append(message)
        for child in value.values():
            messages.extend(nested_messages(child))
    elif isinstance(value, list):
        for child in value:
            messages.extend(nested_messages(child))
    return messages


@dataclass(slots=True)
class CreatedResources:
    """Track run-scoped resources that need cleanup."""

    fileset: bool = False
    inference_secret: bool = False
    inference_provider: bool = False


class CustomGymEnvironmentWorkflow:
    """Run the documented developer workflow and clean up temporary resources."""

    def __init__(
        self,
        settings: Settings,
        *,
        runner: CommandRunner | None = None,
        console: Console | None = None,
    ) -> None:
        """Create a workflow with injectable command and output collaborators."""
        self.settings = settings
        self.runner = runner or CommandRunner(working_directory=settings.repo_root)
        self.console = console or Console()
        self.sdk = NeMoPlatform(base_url=settings.base_url, max_retries=2)
        self.images: DeploymentImages | None = None
        self.prepared_environment: prepare.PreparedEnvironment | None = None
        self.job_name: str | None = None
        self.created_resources = CreatedResources()

    def _kubectl(self, *arguments: str, output_path: Path | None = None) -> str:
        """Run kubectl in the caller's current cluster context."""
        return self.runner.run(["kubectl", *arguments], output_path=output_path)

    def _require_images(self) -> DeploymentImages:
        """Return resolved deployment images after prerequisite validation."""
        if self.images is None:
            raise ResultVerificationError("deployment images have not been resolved")
        return self.images

    def _require_prepared_environment(self) -> prepare.PreparedEnvironment:
        """Return validated package metadata after preparation has completed."""
        if self.prepared_environment is None:
            raise ResultVerificationError("custom environment has not been prepared")
        return self.prepared_environment

    def verify_prerequisites(self) -> None:
        """Run the dedicated read-only workstation and cluster checks."""
        self.console.step(1, TOTAL_STEPS, "Checking workstation and cluster prerequisites")
        checker = PrerequisiteChecker(self.settings, self.runner, self.console)
        self.images = checker.check()

    def prepare_custom_environment(self) -> None:
        """Prepare and validate default or caller-provided environment inputs."""
        self.console.step(2, TOTAL_STEPS, "Preparing the custom Gym environment")
        adapter_evidence: dict[str, Any] = {}
        if self.settings.uses_default_example:
            adapter_evidence = ascii_tree_example.prepare_example(
                self.runner,
                converter_environment=self.settings.paths.converter_environment,
                converter_dataset=self.settings.paths.converter_dataset,
                environment_output=self.settings.paths.environment,
                dataset_output=self.settings.paths.dataset,
            )
            prepared_environment = prepare.inspect_prepared_inputs(
                self.settings.paths.environment,
                self.settings.paths.dataset,
                requested_resources_server=self.settings.requested_resources_server,
                input_mode=str(adapter_evidence["input_mode"]),
            )
            self.console.detail("Input", adapter_evidence["input_label"])
        else:
            environment_source = self.settings.environment_source
            dataset_source = self.settings.dataset_source
            if environment_source is None or dataset_source is None:
                raise ResultVerificationError("custom environment inputs are incomplete")
            self.console.detail("Input", environment_source)
            prepared_environment = prepare.prepare_custom_inputs(
                environment_source,
                dataset_source,
                environment_output=self.settings.paths.environment,
                dataset_output=self.settings.paths.dataset,
                requested_resources_server=self.settings.requested_resources_server,
            )

        self.prepared_environment = prepared_environment
        preparation_summary = {
            **prepared_environment.evidence(),
            **adapter_evidence,
        }
        write_json(
            self.settings.paths.evidence / "preparation.json",
            preparation_summary,
        )
        self.console.detail("Environment format", "wheels-v1")
        self.console.detail("Environment", prepared_environment.name)
        self.console.detail("Dataset tasks", prepared_environment.task_count)
        self.console.detail("Custom wheels", ", ".join(prepared_environment.wheel_names))
        self.console.detail("Resources server", prepared_environment.resources_server)

    @staticmethod
    def _api_is_ready(port: int) -> bool:
        """Return whether the local Platform readiness endpoint responds successfully."""
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
        try:
            connection.request("GET", "/health/ready")
            response = connection.getresponse()
            response.read()
            return response.status == 200
        except OSError:
            return False
        finally:
            connection.close()

    @contextmanager
    def platform_connection(self) -> Iterator[None]:
        """Reuse a healthy API endpoint or own a temporary kubectl port-forward."""
        if self._api_is_ready(self.settings.local_port):
            self.console.detail("Platform API", f"{self.settings.base_url} (existing)")
            yield
            return

        port_forward_log = self.settings.paths.evidence / "port-forward.log"
        with port_forward_log.open("a", encoding="utf-8") as log:
            process = self.runner.start(
                [
                    "kubectl",
                    "port-forward",
                    "-n",
                    self.settings.namespace,
                    f"service/{self.settings.platform_api_service}",
                    f"{self.settings.local_port}:8080",
                ],
                stdout=log,
            )
            try:
                for _ in range(30):
                    if self._api_is_ready(self.settings.local_port):
                        break
                    if process.poll() is not None:
                        raise ResultVerificationError(f"Platform API port-forward failed; see {port_forward_log}")
                    time.sleep(1)
                else:
                    raise ResultVerificationError("Platform API port-forward did not become ready")
                self.console.detail(
                    "Platform API",
                    f"{self.settings.base_url} (temporary port-forward)",
                )
                yield
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

    def _model_name(self) -> str:
        """Return the workspace-relative model name required by API routes."""
        workspace_prefix = f"{self.settings.workspace}/"
        require_result(
            self.settings.model_entity_id.startswith(workspace_prefix),
            (f"NMP_GYM_CUSTOM_MODEL_ENTITY_ID must start with {workspace_prefix}"),
        )
        return self.settings.model_entity_id.removeprefix(workspace_prefix)

    def upload_custom_environment(self) -> None:
        """Create a temporary FileSet and upload the custom environment package."""
        self.sdk.files.filesets.create(
            name=self.settings.fileset,
            workspace=self.settings.workspace,
            purpose="environment",
            description="Custom wheels-v1 Gym environment workflow",
        )
        self.created_resources.fileset = True
        self.sdk.files.upload(
            local_path=f"{self.settings.paths.environment}/",
            fileset=self.settings.fileset,
            workspace=self.settings.workspace,
        )
        fileset_listing = self.sdk.files.list(
            fileset=self.settings.fileset,
            workspace=self.settings.workspace,
        )
        expected_paths = {
            path.relative_to(self.settings.paths.environment).as_posix()
            for path in self.settings.paths.environment.rglob("*")
            if path.is_file()
        }
        uploaded_paths = {uploaded_file.path for uploaded_file in fileset_listing.data}
        require_result(
            uploaded_paths == expected_paths,
            (
                "uploaded environment FileSet does not match the local package: "
                f"missing={sorted(expected_paths - uploaded_paths)}, "
                f"unexpected={sorted(uploaded_paths - expected_paths)}"
            ),
        )
        write_json(
            self.settings.paths.evidence / "fileset-listing.json",
            fileset_listing,
        )
        self.console.detail("Environment FileSet", self.settings.fileset)

    def create_inference_provider(self, inference_api_key: str) -> None:
        """Create a temporary NVIDIA Inference Hub Secret and provider."""
        require_result(
            bool(inference_api_key),
            "INFERENCE_NVIDIA_API_KEY is required",
        )
        self.sdk.secrets.create(
            name=self.settings.inference_secret,
            value=inference_api_key,
            workspace=self.settings.workspace,
            description="Temporary key for the custom Gym environment workflow",
        )
        self.created_resources.inference_secret = True
        self.sdk.inference.providers.create(
            name=self.settings.inference_provider,
            workspace=self.settings.workspace,
            host_url="https://inference-api.nvidia.com/v1",
            api_key_secret_name=self.settings.inference_secret,
        )
        self.created_resources.inference_provider = True

        deadline = time.monotonic() + 120
        while True:
            provider = self.sdk.inference.providers.retrieve(
                self.settings.inference_provider,
                workspace=self.settings.workspace,
            )
            served_model_ids = {model.model_entity_id for model in (provider.served_models or [])}
            if self.settings.model_entity_id in served_model_ids:
                break
            if provider.status in {"ERROR", "DELETED", "LOST"}:
                raise ResultVerificationError(
                    f"provider entered {provider.status}: {provider.status_message or 'no status message'}"
                )
            if time.monotonic() >= deadline:
                raise ResultVerificationError(
                    f"provider did not discover {self.settings.model_entity_id} within 120 seconds"
                )
            time.sleep(2)

        write_json(
            self.settings.paths.evidence / "provider.json",
            provider,
        )
        self.console.detail("Model", self.settings.model_entity_id)

    def configure_platform_resources(self, inference_api_key: str) -> None:
        """Upload the environment and create temporary inference resources."""
        self.console.step(3, TOTAL_STEPS, "Creating temporary Platform resources")
        self.upload_custom_environment()
        self.create_inference_provider(inference_api_key)

    def smoke_test_model(self) -> None:
        """Send a small environment-independent prompt through the selected model route."""
        self.console.step(4, TOTAL_STEPS, "Smoke-testing the selected model")
        request_body: dict[str, object] = {
            "model": self.settings.model_entity_id,
            "messages": [{"role": "user", "content": "Reply with OK."}],
            "max_tokens": 16,
            "temperature": 0,
        }
        smoke_response = self.sdk.inference.gateway.model.post(
            "v1/chat/completions",
            name=self._model_name(),
            workspace=self.settings.workspace,
            body=request_body,
        )
        require_result(
            isinstance(smoke_response.get("choices"), list) and bool(smoke_response["choices"]),
            "model smoke test returned no choices",
        )
        write_json(
            self.settings.paths.evidence / "inference-smoke.json",
            smoke_response,
        )
        self.console.detail("Model route", "ready")

    def submit_evaluation(self) -> None:
        """Submit one trial and download its validated result artifacts."""
        self.console.step(5, TOTAL_STEPS, "Running the custom Gym evaluation")
        prepared_environment = self._require_prepared_environment()
        submission = EvaluationSubmission(
            base_url=self.settings.base_url,
            internal_api=self.settings.internal_api,
            workspace=self.settings.workspace,
            fileset=self.settings.fileset,
            model=self._model_name(),
            dataset=self.settings.paths.dataset,
            resources_server=prepared_environment.resources_server,
            evidence_directory=self.settings.paths.evidence,
        )
        evaluation_result = submit_and_validate(
            submission,
            sdk=self.sdk,
            progress=lambda message: self.console.detail("Job progress", message),
        )
        self.job_name = evaluation_result.job_name
        self.console.detail("Job", evaluation_result.job_name)
        self.console.detail("Custom reward", evaluation_result.verification["reward"])

        job_status = self.sdk.jobs.get_status(
            evaluation_result.job_name,
            workspace=self.settings.workspace,
        )
        job_logs = self.sdk.jobs.get_logs(
            evaluation_result.job_name,
            workspace=self.settings.workspace,
        )
        write_json(
            self.settings.paths.evidence / "job-status.json",
            job_status,
        )
        write_json(
            self.settings.paths.evidence / "job-logs.json",
            {"data": list(job_logs)},
        )

    def verify_results(self) -> dict[str, Any]:
        """Verify runtime images, sandbox lifecycle, and complete custom scoring."""
        self.console.step(6, TOTAL_STEPS, "Verifying evaluation evidence")
        images = self._require_images()
        require_result(bool(self.job_name), "evaluation job name is missing")

        job_status = read_json(self.settings.paths.evidence / "job-status.json")
        job_logs = read_json(self.settings.paths.evidence / "job-logs.json")
        verification = read_json(self.settings.paths.evidence / "verification.json")
        summary_files = list((self.settings.paths.evidence / "agent-eval-results").rglob("summary.json"))
        require_result(
            len(summary_files) == 1,
            f"expected one evaluation summary.json, found {summary_files}",
        )
        result_summary = read_json(summary_files[0])
        status_messages = nested_messages(job_status)
        log_messages = nested_messages(job_logs)

        require_result(
            job_status.get("status") == "completed",
            "Platform job did not complete",
        )
        require_result(
            job_status.get("error_details") is None,
            "Platform job contains error details",
        )
        require_result(
            sum(images.cpu_tasks in message for message in status_messages) >= 2,
            "both job steps did not use the configured CPU Tasks image",
        )
        require_result(
            any(f"Creating sandbox with startup source: {images.gym_host}" in message for message in log_messages),
            "OpenSandbox did not use the configured Gym host image",
        )

        # Together these markers show that execution entered and exited OpenSandbox cleanly.
        for expected_message in (
            "Successfully created sandbox:",
            "Collecting 1 example(s)",
            "Successfully terminated sandbox:",
        ):
            require_result(
                any(expected_message in message for message in log_messages),
                f"missing job evidence: {expected_message}",
            )

        reward_coverage = result_summary.get("metric_coverage", {}).get("gym_reward", {}).get("reward")
        require_result(
            reward_coverage == {"failed": 0, "missing": 0, "scored": 1, "total": 1},
            "Gym reward coverage is incomplete",
        )
        reward = verification.get("reward")
        require_result(
            isinstance(reward, int | float) and math.isfinite(reward),
            "custom reward is not finite",
        )
        require_result(
            verification.get("trial_status") == "completed",
            "trial did not complete",
        )
        require_result(
            verification.get("score_status") == "completed",
            "metric did not complete",
        )
        require_result(
            bool(verification.get("output_texts")),
            "model returned no output text",
        )

        run_summary = {
            "status": "passed",
            "job_name": self.job_name,
            "image_registry": images.registry,
            "image_tag": images.tag,
            "cpu_tasks_image": images.cpu_tasks,
            "gym_host_image": images.gym_host,
            "model": self.settings.model_entity_id,
            "evaluation": verification,
        }
        write_json(self.settings.paths.evidence / "run-summary.json", run_summary)
        self.console.detail("CPU Tasks image", images.cpu_tasks)
        self.console.detail("Gym host image", images.gym_host)
        self.console.detail("Sandbox lifecycle", "created and terminated")
        return run_summary

    def cleanup(self) -> None:
        """Delete every run-scoped Platform resource that was created."""
        cleanup_errors: list[str] = []
        resources: tuple[tuple[str, bool, Callable[[], object]], ...] = (
            (
                "inference provider",
                self.created_resources.inference_provider,
                lambda: self.sdk.inference.providers.delete(
                    self.settings.inference_provider,
                    workspace=self.settings.workspace,
                ),
            ),
            (
                "inference secret",
                self.created_resources.inference_secret,
                lambda: self.sdk.secrets.delete(
                    self.settings.inference_secret,
                    workspace=self.settings.workspace,
                ),
            ),
            (
                "environment FileSet",
                self.created_resources.fileset,
                lambda: self.sdk.files.filesets.delete(
                    self.settings.fileset,
                    workspace=self.settings.workspace,
                ),
            ),
        )
        created_count = sum(was_created for _, was_created, _ in resources)
        if created_count == 0:
            self.console.detail("Temporary resources", "none created")
            return

        deleted_count = 0
        for resource_name, was_created, delete_resource in resources:
            if not was_created:
                continue
            try:
                delete_resource()
                deleted_count += 1
            except Exception as error:
                # Attempt all deletions so one failure does not leak unrelated resources.
                cleanup_errors.append(f"{resource_name}: {error}")
        if cleanup_errors:
            raise RuntimeError("cleanup failed:\n" + "\n".join(cleanup_errors))
        self.console.detail("Temporary resources", f"{deleted_count} deleted")

    def run(self, *, inference_api_key: str) -> dict[str, Any]:
        """Execute the complete workflow through one developer-facing invocation."""
        self.settings.paths.evidence.mkdir(parents=True, exist_ok=True)
        self.verify_prerequisites()
        self.prepare_custom_environment()

        workflow_failed = False
        with self.platform_connection():
            try:
                self.configure_platform_resources(inference_api_key)
                self.smoke_test_model()
                self.submit_evaluation()
                run_summary = self.verify_results()
            except Exception:
                workflow_failed = True
                raise
            finally:
                if workflow_failed:
                    self.console.warning("Workflow stopped; cleaning up resources created before the failure")
                else:
                    self.console.step(7, TOTAL_STEPS, "Cleaning up temporary resources")
                try:
                    self.cleanup()
                except RuntimeError as cleanup_error:
                    if workflow_failed:
                        self.console.warning(str(cleanup_error))
                    else:
                        raise

        self.console.success("Custom Gym environment evaluation passed")
        self.console.detail("Job", run_summary["job_name"])
        self.console.detail("Model", run_summary["model"])
        self.console.detail("Reward", run_summary["evaluation"]["reward"])
        self.console.detail("Evidence", self.settings.paths.evidence)
        return run_summary
