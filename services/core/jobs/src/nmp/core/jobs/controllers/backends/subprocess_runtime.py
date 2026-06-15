# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import time_ns
from typing import IO
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlparse
from urllib.request import Request, urlopen

from nmp.common.auth.models import NMP_PRINCIPAL_ENVVAR, Principal
from nmp.common.jobs.constants import NEMO_JOB_SECRETS_ENVVAR
from opentelemetry._logs import Logger
from opentelemetry._logs.severity import SeverityNumber
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SecretReference:
    env_var_name: str
    workspace: str
    secret_name: str


@dataclass
class SubprocessOtelLogger:
    logger: Logger
    provider: LoggerProvider

    def emit(self, message: str, stream_name: str) -> None:
        severity_number = SeverityNumber.INFO if stream_name == "stdout" else SeverityNumber.ERROR
        severity_text = "INFO" if stream_name == "stdout" else "ERROR"
        self.logger.emit(
            body=message,
            timestamp=time_ns(),
            severity_number=severity_number,
            severity_text=severity_text,
            attributes={"stream": stream_name},
        )

    def close(self) -> None:
        self.provider.force_flush()
        self.provider.shutdown()


def parse_secret_references(secrets_env: str) -> list[SecretReference]:
    if not secrets_env:
        return []

    references: list[SecretReference] = []
    for pair in secrets_env.split(","):
        pair = pair.strip()
        if not pair:
            continue
        env_var_name, sep, secret_ref = pair.partition("=")
        if sep != "=" or not env_var_name.strip():
            raise ValueError(f"invalid secret reference format: {pair} (expected ENV_VAR=workspace/secret_name)")
        workspace, slash, secret_name = secret_ref.strip().partition("/")
        workspace = workspace.strip()
        secret_name = secret_name.strip()
        if slash != "/" or not workspace or not secret_name:
            raise ValueError(f"invalid secret reference format: {secret_ref.strip()} (expected workspace/secret_name)")
        references.append(
            SecretReference(
                env_var_name=env_var_name.strip(),
                workspace=workspace,
                secret_name=secret_name,
            )
        )
    return references


def inject_secret_env_vars(env: dict[str, str], *, secrets_url: str | None = None) -> dict[str, str]:
    secrets_env = env.get(NEMO_JOB_SECRETS_ENVVAR, "")
    references = parse_secret_references(secrets_env)
    if not references:
        return env

    api_base_url = secrets_url or env.get("NMP_SECRETS_URL", "")
    if not api_base_url:
        raise ValueError("NMP_SECRETS_URL is required when NEMO_JOB_SECRETS is set")
    _validate_http_url(api_base_url, "NMP_SECRETS_URL")

    principal = _principal_from_env(env)
    for reference in references:
        env[reference.env_var_name] = _fetch_secret(
            api_base_url=api_base_url,
            principal=principal,
            workspace=reference.workspace,
            secret_name=reference.secret_name,
        )
    return env


def start_log_capture(
    pipe: IO[str] | None,
    *,
    log_path: Path,
    log_lock: threading.Lock,
    otel_logger: SubprocessOtelLogger | None,
    stream_name: str,
    job: str,
    step: str,
    task_id: str,
) -> threading.Thread | None:
    if pipe is None:
        return None

    def capture() -> None:
        try:
            for line in pipe:
                message = line.rstrip("\n")
                if not message:
                    continue
                if stream_name != "stdout":
                    message = f"[{stream_name}] {message}"
                record = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "job": job,
                    "job_step": step,
                    "job_task": task_id,
                    "message": message,
                }
                with log_lock:
                    with log_path.open("a", encoding="utf-8") as log_file:
                        log_file.write(json.dumps(record) + "\n")
                if otel_logger is not None:
                    otel_logger.emit(message, stream_name)
        finally:
            pipe.close()

    thread = threading.Thread(target=capture, name=f"jobs-log-capture-{task_id}-{stream_name}", daemon=True)
    thread.start()
    return thread


def create_otel_logger(
    *,
    env: dict[str, str],
    workspace: str,
    job: str,
    attempt_id: str,
    step: str,
    task_id: str,
) -> SubprocessOtelLogger | None:
    endpoint = env.get("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT") or env.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return None

    headers = _parse_otel_headers(env.get("OTEL_EXPORTER_OTLP_LOGS_HEADERS", ""))
    resource = Resource.create(
        {
            "workspace": workspace,
            "job": job,
            "job_attempt": attempt_id,
            "job_step": step,
            "job_task": task_id,
        }
    )
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint, headers=headers or None))
    )
    logger.info("Created local OTEL logger", extra={"endpoint": endpoint, "job": job, "step": step})
    return SubprocessOtelLogger(logger_provider.get_logger("nmp.jobs.subprocess"), logger_provider)


def _parse_otel_headers(headers_env: str) -> dict[str, str]:
    if not headers_env:
        return {}

    headers: dict[str, str] = {}
    for item in headers_env.split(","):
        item = item.strip()
        if not item:
            continue
        key, sep, value = item.partition("=")
        if sep != "=" or not key:
            continue
        headers[key] = unquote(value)
    return headers


def _principal_from_env(env: dict[str, str]) -> Principal | None:
    principal_json = env.get(NMP_PRINCIPAL_ENVVAR, "")
    if not principal_json:
        return None
    try:
        return Principal.model_validate_json(principal_json)
    except Exception:
        return None


def _fetch_secret(*, api_base_url: str, principal: Principal | None, workspace: str, secret_name: str) -> str:
    request = Request(
        url=f"{api_base_url}/apis/secrets/v2/workspaces/{quote(workspace, safe='')}/secrets/{quote(secret_name, safe='')}/access",
        method="GET",
    )
    for name, value in _secret_request_headers(principal).items():
        request.add_header(name, value)

    try:
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"failed to fetch secret {workspace}/{secret_name}: status code {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"failed to fetch secret {workspace}/{secret_name}: {exc.reason}") from exc

    value = payload.get("value")
    if not isinstance(value, str):
        raise RuntimeError(f"failed to fetch secret {workspace}/{secret_name}: missing string value field")
    return value


def _validate_http_url(url: str, field_name: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field_name} must be an absolute http or https URL")


def _secret_request_headers(principal: Principal | None) -> dict[str, str]:
    if principal is None or not principal.id:
        return {"X-NMP-Principal-Id": "service:jobs"}
    service_principal = Principal(
        id="service:jobs",
        on_behalf_of=principal.effective_id,
        on_behalf_of_email=principal.effective_email,
        on_behalf_of_groups=principal.effective_groups,
    )
    return service_principal.get_headers()
