# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

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
    "dataset",
}
EXCLUDE_GLOB = {"output.*"}


class WrappedAgent(BaseAgent):
    @staticmethod
    def name() -> str:
        return "agent-0"

    def version(self) -> str | None:
        return "1.0.0"

    async def _upload_mcp_config(self, environment: BaseEnvironment) -> None:
        if not self.mcp_servers:
            return

        mcp_servers = {}
        for server in self.mcp_servers:
            server_config = server.model_dump(exclude_none=True)
            name = server_config.pop("name")
            mcp_servers[name] = server_config

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            json.dump({"mcpServers": mcp_servers}, tmp)

        try:
            await environment.upload_file(tmp_path, "/app/.mcp.json")
        finally:
            tmp_path.unlink(missing_ok=True)

    @staticmethod
    async def _upload_nooa_override(environment: BaseEnvironment) -> None:
        wheel_value = os.environ.get("NOOA_WHEEL")
        if not wheel_value:
            return
        wheel = Path(wheel_value).expanduser().resolve()
        if not wheel.is_file():
            raise RuntimeError(f"NOOA_WHEEL does not name a file: {wheel}")

        vendor_dir = "/app/vendor"
        mkdir = await environment.exec(f"mkdir -p {vendor_dir}")
        if mkdir.return_code != 0:
            raise RuntimeError(f"Could not create {vendor_dir}: {mkdir.stderr or mkdir.stdout}")

        remote_wheel = f"{vendor_dir}/{wheel.name}"
        await environment.upload_file(wheel, remote_wheel)

        source_key = "nooa"
        project_lines = (AGENT_DIR / "pyproject.toml").read_text(encoding="utf-8").splitlines()
        in_sources = False
        replaced = False
        for index, line in enumerate(project_lines):
            stripped = line.strip()
            if stripped == "[tool.uv.sources]":
                in_sources = True
                continue
            if in_sources and stripped.startswith("["):
                break
            if in_sources and stripped.partition("=")[0].strip() == source_key:
                project_lines[index] = f'{source_key} = {{ path = "vendor/{wheel.name}" }}'
                replaced = True
                break
        if not replaced:
            raise RuntimeError(f"Could not find {source_key} in [tool.uv.sources]")

        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as tmp:
            project_path = Path(tmp.name)
            tmp.write("\n".join(project_lines) + "\n")
        project_path.chmod(0o644)
        try:
            await environment.upload_file(project_path, "/app/pyproject.toml")
        finally:
            project_path.unlink(missing_ok=True)

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
        await self._upload_mcp_config(environment)
        await self._upload_nooa_override(environment)
        import asyncio as _asyncio

        proc = None
        for _attempt in range(3):
            proc = await environment.exec("cd /app && UV_HTTP_TIMEOUT=300 uv sync")
            if proc.return_code == 0:
                break
            logger.warning(
                f"[setup] install attempt {_attempt + 1} failed (rc={proc.return_code}): stdout={(proc.stdout or '')[-500:]} stderr={(proc.stderr or '')[-500:]}"
            )
            if _attempt < 2:
                await _asyncio.sleep(10)
        if proc and proc.return_code != 0:
            logger.error(
                f"[setup] install failed after 3 attempts (rc={proc.return_code}): stdout={(proc.stdout or '')[-500:]} stderr={(proc.stderr or '')[-500:]}"
            )
            raise RuntimeError(
                f"Installation failed after 3 attempts. "
                f"Last error (rc={proc.return_code}): {proc.stderr or proc.stdout}"
            )

        logger.info(f"[setup] {proc.stdout if proc else ''}")

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
        env = {"NEMO_AGENT_MODEL": self.model_name} if self.model_name else None
        proc = await environment.exec(
            f"cd /app && uv run python main.py --prompt {shlex.quote(instruction.strip())}",
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
