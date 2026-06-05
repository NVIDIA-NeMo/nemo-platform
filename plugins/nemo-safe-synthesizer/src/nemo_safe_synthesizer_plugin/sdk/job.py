# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""High-level Safe Synthesizer job SDK helpers."""

from __future__ import annotations

import json
import logging
import time
from base64 import b64encode
from io import BytesIO
from pathlib import Path
from typing import Iterator

import httpx
import pandas as pd
from nemo_platform import NeMoPlatform
from nemo_platform._types import Omit, omit
from nemo_platform.types import PlatformJobLog, PlatformJobStatusResponse
from nemo_safe_synthesizer.config.external_results import SafeSynthesizerSummary
from typing_extensions import Self

logger = logging.getLogger(__name__)


class ReportHtml:
    """Container for a Safe Synthesizer HTML report."""

    def __init__(self, html: str):
        self.raw_html = html
        self.as_data_uri = f"data:text/html;base64,{b64encode(self.raw_html.encode()).decode()}"

    def save(self, path: str | Path) -> None:
        """Save the evaluation report to a file."""
        Path(path).write_text(self.raw_html, encoding="utf-8")

    def display_report_in_notebook(self, width: str = "100%", height: int = 1000) -> None:
        """Display the evaluation report in a Jupyter notebook."""
        try:
            from IPython.display import IFrame, display
        except ImportError:
            logger.warning("IPython is required to display reports in notebooks. Report will not be displayed.")
            return

        display(IFrame(self.as_data_uri, width=width, height=height))

    @classmethod
    def read(cls, path: str | Path) -> Self:
        """Read an evaluation report from a file."""
        return cls(Path(path).read_text(encoding="utf-8"))


class SafeSynthesizerJob:
    """Convenience wrapper for a Safe Synthesizer platform job."""

    def __init__(self, job_name: str, client: NeMoPlatform, workspace: str = "default"):
        self.job_name = job_name
        self._client = client
        self._workspace = workspace

    def fetch_status(self) -> str:
        """Fetch the current job status."""
        return self.fetch_status_info().status

    def fetch_status_info(self) -> PlatformJobStatusResponse:
        """Fetch the current job status response."""
        return self._client.jobs.get_status(self.job_name, workspace=self._workspace)

    def wait_for_completion(
        self, poll_interval: int = 10, verbose: bool = True, log_timeout: float | None = None
    ) -> None:
        """Block until the job reaches a terminal state."""
        last_page_cursor: str | None = None
        seen_log_keys: set[str] = set()
        previous_status_info = None
        current_status_info = self.fetch_status_info()
        while current_status_info.status not in ["completed", "error", "cancelled"]:
            if verbose:
                logging_level = None
                try:
                    httpx_logger = logging.getLogger("httpx")
                    logging_level = httpx_logger.level
                    httpx_logger.setLevel("ERROR")
                    new_logs, last_page_cursor = self._fetch_logs_incremental(
                        page_cursor=last_page_cursor, timeout=log_timeout
                    )
                    for new_log in new_logs:
                        log_key = f"{new_log.timestamp}:{hash(new_log.message)}"
                        if log_key not in seen_log_keys:
                            print(new_log.message.strip())
                            seen_log_keys.add(log_key)
                except httpx.HTTPError as e:
                    logger.warning("Error fetching logs while waiting for job completion: %s", e)
                finally:
                    if logging_level is not None:
                        logging.getLogger("httpx").setLevel(logging_level)
            current_status_info = self.fetch_status_info()
            if current_status_info != previous_status_info:
                if verbose:
                    print(
                        f"Job status changed to status: '{current_status_info.status}',",
                        f"status_details: {current_status_info.status_details},",
                        f"error_details: {current_status_info.error_details}",
                    )
                previous_status_info = current_status_info
            time.sleep(poll_interval)
        if current_status_info.status in ["error", "cancelled"]:
            raise RuntimeError(
                f"Job '{self.job_name}' ended with status '{current_status_info.status}'. "
                f"Details: {current_status_info.status_details}. "
                f"Error: {current_status_info.error_details}. "
                "Check job logs with job.print_logs() for more details."
            )

    def fetch_summary(self) -> SafeSynthesizerSummary:
        """Fetch the machine-readable job summary."""
        response = self._client.jobs.results.download("summary", job=self.job_name, workspace=self._workspace)
        return SafeSynthesizerSummary.model_validate(json.loads(response.read().decode("utf-8")))

    def fetch_report(self) -> ReportHtml:
        """Fetch the evaluation report as HTML."""
        response = self._client.jobs.results.download("evaluation-report", job=self.job_name, workspace=self._workspace)
        return ReportHtml(html=response.read().decode("utf-8"))

    def display_report_in_notebook(self, width: str = "100%", height: int = 1000) -> None:
        """Display the evaluation report in a Jupyter notebook."""
        self.fetch_report().display_report_in_notebook(width=width, height=height)

    def save_report(self, path: str | Path) -> None:
        """Save the evaluation report to a file."""
        self.fetch_report().save(path)

    def fetch_data(self) -> pd.DataFrame:
        """Fetch generated synthetic data as a pandas DataFrame."""
        response = self._client.jobs.results.download("synthetic-data", job=self.job_name, workspace=self._workspace)
        return pd.read_csv(BytesIO(response.read()))

    def _fetch_logs_incremental(
        self, page_cursor: str | None = None, timeout: float | None = None
    ) -> tuple[list[PlatformJobLog], str | None]:
        """Fetch logs incrementally starting from a page cursor."""
        timeout = 300.0 if timeout is None else timeout
        all_logs: list[PlatformJobLog] = []
        current_cursor: str | Omit = omit if page_cursor is None else page_cursor
        last_cursor_with_data: str | None = page_cursor

        while True:
            response = self._client.with_options(timeout=timeout).jobs.get_logs(
                self.job_name,
                page_cursor=current_cursor,
                workspace=self._workspace,
            )

            if response.data:
                all_logs.extend(response.data)
                if isinstance(current_cursor, str):
                    last_cursor_with_data = current_cursor

            if response.next_page is None:
                return all_logs, last_cursor_with_data
            current_cursor = response.next_page

    def fetch_logs(self, timeout: float | None = None) -> Iterator[PlatformJobLog]:
        """Fetch job logs as an iterator over log objects."""
        timeout = 300.0 if timeout is None else timeout
        page_cursor: str | Omit = omit
        while True:
            response = self._client.with_options(timeout=timeout).jobs.get_logs(
                self.job_name,
                page_cursor=page_cursor,
                workspace=self._workspace,
            )
            yield from response.data
            if response.next_page is None:
                break
            page_cursor = response.next_page

    def print_logs(self, timeout: float | None = None) -> None:
        """Print job logs to stdout."""
        for log in self.fetch_logs(timeout=timeout):
            print(log.message.strip())
