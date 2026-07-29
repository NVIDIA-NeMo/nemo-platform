# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import asyncio
import fnmatch
import glob
import json
import logging
import os
import shlex
import shutil
import tempfile
from pathlib import Path

from harbor import AgentContext, BaseAgent, BaseEnvironment

logger = logging.getLogger(__name__)

AGENT_DIR = Path(__file__).parent
ARTIFACTS_DIR = "/app/artifacts"
TRACES_DIR = "/app/traces"
COLLECTED_ARTIFACTS_DIR = "/logs/artifacts"
UV_VERSION = "0.9.14"
INSTALL_ATTEMPTS = 3
# A task's [environment].env only interpolates its docker-compose file, and upstream
# wires those variables into the tau3-runtime sidecar that hosts the user simulator and
# the judge. The main service declares no environment of its own, so the credentials the
# agent needs for its own model calls have to be handed over at exec time.
MODEL_CREDENTIAL_VARS = ("OPENAI_API_KEY", "OPENAI_BASE_URL")

# Artifact contract:
# - Files intended for review/fetching must be written under /app/artifacts.
# - Agent traces must be written under /app/traces.
# - Verifier diagnostics should be printed by the verifier so Harbor captures them
#   in verifier/test-stdout.txt; do not create custom diagnostic artifact files.
# The wrapper mirrors only these locations into /logs/artifacts for Harbor collection.

EXCLUDE = {
    "eval-and-optimize",
    "__pycache__",
    ".git",
    ".claude",
    ".uv",
    ".venv",
    ".env",
    "traces",
    "artifacts",
}
EXCLUDE_GLOB = {"output.*"}


class WrappedAgent(BaseAgent):
    @staticmethod
    def name() -> str:
        return "nemo-experimentalist-tau3-nooa"

    def version(self) -> str | None:
        return "1.0.0"

    async def setup(self, environment: BaseEnvironment) -> None:
        """Upload agent files to the container and install dependencies."""
        for entry in AGENT_DIR.iterdir():
            name = entry.name
            if name in EXCLUDE:
                continue
            if any(fnmatch.fnmatch(name, pat) for pat in EXCLUDE_GLOB):
                continue
            if entry.is_file():
                await environment.upload_file(entry, f"/app/{name}")
            elif entry.is_dir():
                await environment.upload_dir(entry, f"/app/{name}")
        # The tau3 task image is python:3.12-slim: it already has the interpreter the
        # agent needs plus pip, but neither uv nor the curl its installer expects.
        install = (
            f"cd /app && pip install --no-cache-dir --quiet uv=={UV_VERSION} && UV_HTTP_TIMEOUT=300 uv sync --frozen"
        )
        for attempt in range(1, INSTALL_ATTEMPTS + 1):
            proc = await environment.exec(install)
            if proc.return_code == 0:
                logger.info(f"[setup] {proc.stdout}")
                return
            logger.warning(
                f"[setup] install attempt {attempt}/{INSTALL_ATTEMPTS} failed (rc={proc.return_code}): "
                f"stdout={(proc.stdout or '')[-500:]} stderr={(proc.stderr or '')[-500:]}"
            )
            if attempt < INSTALL_ATTEMPTS:
                await asyncio.sleep(10)
        raise RuntimeError(
            f"Installation failed after {INSTALL_ATTEMPTS} attempts. "
            f"Last error (rc={proc.return_code}): {proc.stderr or proc.stdout}"
        )

    @staticmethod
    def _parse_trace_metrics(traces_dir: str) -> dict[str, int]:
        def token_count(attributes: dict[str, dict[str, object]], key: str) -> int:
            value = attributes.get(key, {})
            raw_count = value.get("intValue", value.get("doubleValue", 0))
            if not isinstance(raw_count, int | float | str):
                raise TypeError(f"Invalid token count for {key}: {raw_count!r}")
            return int(raw_count)

        n_input = n_output = n_cache = 0
        paths = glob.glob(f"{traces_dir}/**/*.jsonl", recursive=True)
        if not paths:
            raise FileNotFoundError(f"No JSONL traces found under {traces_dir}")

        for path in paths:
            with open(path, encoding="utf-8") as trace_file:
                for line_number, line in enumerate(trace_file, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        for resource_spans in data.get("resourceSpans", []):
                            for scope_spans in resource_spans.get("scopeSpans", []):
                                for span in scope_spans.get("spans", []):
                                    attributes = {
                                        attribute["key"]: attribute["value"] for attribute in span.get("attributes", [])
                                    }
                                    if attributes.get("openinference.span.kind", {}).get("stringValue") != "LLM":
                                        continue
                                    n_input += token_count(attributes, "llm.token_count.prompt")
                                    n_output += token_count(attributes, "llm.token_count.completion")
                                    n_cache += token_count(
                                        attributes,
                                        "llm.token_count.prompt_details.cache_read",
                                    )
                    except (AttributeError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                        raise ValueError(f"Invalid trace data in {path}:{line_number}: {exc}") from exc
        return {"n_input_tokens": n_input, "n_output_tokens": n_output, "n_cache_tokens": n_cache}

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        env = {name: value for name in MODEL_CREDENTIAL_VARS if (value := os.environ.get(name))}
        if self.model_name:
            env["NEMO_AGENT_MODEL"] = self.model_name
        proc = await environment.exec(
            f"cd /app && uv run --frozen python main.py --prompt {shlex.quote(instruction.strip())}",
            env=env,
        )
        # download traces from container to parse token counts on the host
        _tmp = tempfile.mkdtemp(prefix="agent_traces_")
        metrics_error = None
        try:
            await environment.download_dir(TRACES_DIR, _tmp)
            metrics = self._parse_trace_metrics(_tmp)
            context.n_input_tokens = metrics["n_input_tokens"]
            context.n_output_tokens = metrics["n_output_tokens"]
            context.n_cache_tokens = metrics["n_cache_tokens"]
        except (FileNotFoundError, OSError, ValueError) as exc:
            metrics_error = f"Trace metrics unavailable: {type(exc).__name__}: {exc}"
            logger.warning(metrics_error)
        finally:
            shutil.rmtree(_tmp, ignore_errors=True)
        # copy the traces directory to the artifacts directory (no-op if absent)
        await environment.exec(f"cp -r {TRACES_DIR} {COLLECTED_ARTIFACTS_DIR}/traces 2>/dev/null || true")
        # recursive so subdirs like artifacts/traces/ survive if the agent wrote there
        await environment.exec(f"sh -c 'cp -r {ARTIFACTS_DIR}/* {COLLECTED_ARTIFACTS_DIR}/ 2>/dev/null || true'")

        context.metadata = {
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "returncode": proc.return_code,
            "metrics_error": metrics_error,
        }
        if proc.return_code != 0:
            raise RuntimeError(f"Agent process failed with exit code {proc.return_code}: {proc.stderr or proc.stdout}")
