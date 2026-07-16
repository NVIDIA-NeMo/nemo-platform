# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for periodic insights analysis plumbing."""

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import httpx
import pytest
from nemo_insights_plugin.analyst.analyst_backend import (
    LocalAnalystBackend,
    RemoteAnalystBackend,
    _merge_eval_filter,
    _merge_since_filter,
)
from nemo_insights_plugin.analyst.result import AnalystResult, InsightUpdate
from nemo_insights_plugin.config import (
    AnalystSchedulerConfig,
    Frequency,
    InsightsConfig,
    Weekday,
)
from nemo_insights_plugin.controller import InsightsAnalysisController, _job_name
from nemo_insights_plugin.entities import (
    AnalysisConfig,
    AnalysisConfigStatus,
    AnalysisRunStatus,
)
from nemo_insights_plugin.jobs.analyze import AnalyzeJob, AnalyzeSpec
from nemo_insights_plugin.schedule import is_due, previous_scheduled
from nemo_platform.types.intake.spans.span_group import SpanGroup
from nemo_platform_plugin.entity_client import NemoEntityNotFoundError
from nemo_platform_plugin.job_context import JobContext, StoragePaths
from nemo_platform_plugin.jobs.constants import (
    DEFAULT_JOB_STORAGE_PATH,
    PERSISTENT_JOB_STORAGE_PATH_ENVVAR,
)
from pydantic import ValidationError


def test_merge_since_filter_adds_lower_bound() -> None:
    since = datetime(2026, 6, 4, 12, tzinfo=timezone.utc)

    result = _merge_since_filter({"agent_name": "research-agent"}, since=since)

    assert result == {
        "agent_name": "research-agent",
        "started_at": {"gte": "2026-06-04T12:00:00+00:00"},
    }


def test_merge_since_filter_keeps_later_existing_lower_bound() -> None:
    since = datetime(2026, 6, 4, 12, tzinfo=timezone.utc)

    result = _merge_since_filter(
        {"started_at": {"gte": "2026-06-04T13:00:00+00:00"}},
        since=since,
    )

    assert result == {"started_at": {"gte": "2026-06-04T13:00:00+00:00"}}


def test_merge_since_filter_compares_equivalent_iso_representations() -> None:
    since = datetime(2026, 6, 4, 12, tzinfo=timezone.utc)
    current = "2026-06-04T07:00:00-05:00"

    result = _merge_since_filter({"started_at": {"gte": current}}, since=since)

    assert result == {"started_at": {"gte": current}}


class _MissingInsights:
    async def get(self, **kwargs: object) -> None:
        del kwargs
        request = httpx.Request("GET", "https://example.com/insights/missing")
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("not found", request=request, response=response)


@pytest.mark.asyncio
async def test_remote_persist_validates_updates_without_trace_refs() -> None:
    client = SimpleNamespace(insights=SimpleNamespace(insights=_MissingInsights()))
    backend = RemoteAnalystBackend(client)  # type: ignore[arg-type]
    result = AnalystResult(
        summary="Nothing new.",
        updated_insights=[InsightUpdate(id="missing-insight")],
    )

    report = await backend.persist_result(workspace="default", agent="research-agent", result=result)

    assert "- skipped (insight not found): missing-insight" in report
    assert "- updated: missing-insight" not in report


def test_local_backend_reads_and_writes_insights_file_with_explicit_utf8(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    read_calls: list[dict[str, object]] = []
    write_calls: list[dict[str, object]] = []
    original_read_text = Path.read_text
    original_write_text = Path.write_text

    def spy_read_text(self: Path, *args: object, **kwargs: object) -> str:
        read_calls.append(kwargs)
        return original_read_text(self, *args, **kwargs)

    def spy_write_text(self: Path, *args: object, **kwargs: object) -> int:
        write_calls.append(kwargs)
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", spy_read_text)
    monkeypatch.setattr(Path, "write_text", spy_write_text)

    backend = LocalAnalystBackend(client=SimpleNamespace(), path=tmp_path / "insights.yaml")  # type: ignore[arg-type]
    backend._write_records([])
    backend._read_records()

    assert write_calls[-1].get("encoding") == "utf-8"
    assert read_calls[-1].get("encoding") == "utf-8"


def test_merge_eval_filter_pins_evaluation_id() -> None:
    assert _merge_eval_filter({"agent_name": "a"}, evaluation_id="run-1") == {
        "agent_name": "a",
        "evaluation_id": "run-1",
    }


def test_merge_eval_filter_none_is_noop() -> None:
    assert _merge_eval_filter({"agent_name": "a"}, evaluation_id=None) == {"agent_name": "a"}
    assert _merge_eval_filter(None, evaluation_id=None) is None


def test_merge_eval_filter_overwrites_model_supplied_scope() -> None:
    assert _merge_eval_filter({"evaluation_id": "sneaky"}, evaluation_id="run-1") == {
        "evaluation_id": "run-1",
    }


class _SpanGroups:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def list(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(
            data=[SpanGroup(group={"session_id": "session-1"}, span_count=3)],
            pagination=SimpleNamespace(total_results=7),
        )


class _SpanGroupClient:
    def __init__(self) -> None:
        self.intake = SimpleNamespace(
            spans=SimpleNamespace(groups=_SpanGroups()),
        )


@pytest.mark.asyncio
async def test_count_agent_sessions_uses_server_side_session_groups() -> None:
    since = datetime(2026, 6, 4, 12, tzinfo=timezone.utc)
    backend = RemoteAnalystBackend(_SpanGroupClient())  # type: ignore[arg-type]

    count = await backend.count_agent_sessions(
        agent="research-agent",
        workspace="default",
        since=since,
    )

    assert count == 7
    assert backend.client.intake.spans.groups.calls == [
        {
            "workspace": "default",
            "by": "session_id",
            "page": 1,
            "page_size": 1,
            "filter": {
                "agent_name": "research-agent",
                "started_at": {"gte": "2026-06-04T12:00:00+00:00"},
            },
            "sort": "-span_count",
        }
    ]


class _SpanGroupsPaged:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def list(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(
            data=[
                SpanGroup(group={"session_id": "session-1"}, span_count=12),
                SpanGroup(group={"session_id": "session-2"}, span_count=5),
            ],
            pagination=SimpleNamespace(total_results=37),
        )


class _GroupsBackendClient:
    def __init__(self, groups: _SpanGroupsPaged) -> None:
        self.intake = SimpleNamespace(spans=SimpleNamespace(groups=groups))


@pytest.mark.asyncio
async def test_list_span_groups_fans_out_over_sessions() -> None:
    since = datetime(2026, 6, 4, 12, tzinfo=timezone.utc)
    groups = _SpanGroupsPaged()
    backend = RemoteAnalystBackend(_GroupsBackendClient(groups))  # type: ignore[arg-type]

    result = await backend.list_span_groups(
        workspace="default",
        filter={"agent_name": "research-agent"},
        group_by="session_id",
        limit=100,
        since=since,
    )

    assert result == {
        "groups": [
            {"group": {"session_id": "session-1"}, "span_count": 12},
            {"group": {"session_id": "session-2"}, "span_count": 5},
        ],
        "grouped_by": "session_id",
        "count": 2,
        "total": 37,
        "truncated": True,
    }
    assert groups.calls == [
        {
            "workspace": "default",
            "by": "session_id",
            "page": 1,
            "page_size": 100,
            "filter": {
                "agent_name": "research-agent",
                "started_at": {"gte": "2026-06-04T12:00:00+00:00"},
            },
            "sort": "-span_count",
        }
    ]


@pytest.mark.asyncio
async def test_count_agent_sessions_pins_evaluation_id() -> None:
    backend = RemoteAnalystBackend(_SpanGroupClient())  # type: ignore[arg-type]

    await backend.count_agent_sessions(
        agent="research-agent",
        workspace="default",
        evaluation_id="run-1",
    )

    assert backend.client.intake.spans.groups.calls == [
        {
            "workspace": "default",
            "by": "session_id",
            "page": 1,
            "page_size": 1,
            "filter": {"agent_name": "research-agent", "evaluation_id": "run-1"},
            "sort": "-span_count",
        }
    ]


@pytest.mark.asyncio
async def test_list_span_groups_pins_evaluation_id() -> None:
    groups = _SpanGroupsPaged()
    backend = RemoteAnalystBackend(_GroupsBackendClient(groups))  # type: ignore[arg-type]

    await backend.list_span_groups(
        workspace="default",
        filter={"agent_name": "research-agent"},
        group_by="session_id",
        limit=100,
        evaluation_id="run-1",
    )

    assert groups.calls[0]["filter"] == {
        "agent_name": "research-agent",
        "evaluation_id": "run-1",
    }


_DENVER = ZoneInfo("America/Denver")


def test_previous_scheduled_daily_converts_local_hour_to_utc() -> None:
    # During MDT (UTC-6), 02:00 Denver local is 08:00 UTC.
    now = datetime(2026, 6, 10, 12, tzinfo=timezone.utc)

    scheduled = previous_scheduled(
        now,
        frequency=Frequency.DAILY,
        run_at_hour=2,
        run_on_weekday=int(Weekday.MONDAY),
        tz=_DENVER,
    )

    assert scheduled == datetime(2026, 6, 10, 8, tzinfo=timezone.utc)


def test_previous_scheduled_daily_rolls_back_when_hour_not_reached() -> None:
    # 03:00 UTC on 2026-06-10 is 21:00 Denver on 2026-06-09, before 02:00 local,
    # so the most recent 02:00-local run was the prior day.
    now = datetime(2026, 6, 10, 3, tzinfo=timezone.utc)

    scheduled = previous_scheduled(
        now,
        frequency=Frequency.DAILY,
        run_at_hour=2,
        run_on_weekday=int(Weekday.MONDAY),
        tz=_DENVER,
    )

    assert scheduled == datetime(2026, 6, 9, 8, tzinfo=timezone.utc)


def test_previous_scheduled_weekly_lands_on_configured_weekday() -> None:
    # 2026-06-10 is a Wednesday; the prior Monday 02:00 Denver is 2026-06-08.
    now = datetime(2026, 6, 10, 12, tzinfo=timezone.utc)

    scheduled = previous_scheduled(
        now,
        frequency=Frequency.WEEKLY,
        run_at_hour=2,
        run_on_weekday=int(Weekday.MONDAY),
        tz=_DENVER,
    )

    assert scheduled == datetime(2026, 6, 8, 8, tzinfo=timezone.utc)
    assert scheduled.astimezone(_DENVER).weekday() == int(Weekday.MONDAY)


def test_is_due_true_when_no_prior_run() -> None:
    now = datetime(2026, 6, 10, 12, tzinfo=timezone.utc)

    assert is_due(
        now,
        None,
        frequency=Frequency.DAILY,
        run_at_hour=2,
        run_on_weekday=int(Weekday.MONDAY),
        tz=_DENVER,
    )


def test_is_due_false_when_run_after_last_scheduled() -> None:
    now = datetime(2026, 6, 10, 12, tzinfo=timezone.utc)
    anchor = datetime(2026, 6, 10, 9, tzinfo=timezone.utc)  # after 08:00 UTC slot

    assert not is_due(
        now,
        anchor,
        frequency=Frequency.DAILY,
        run_at_hour=2,
        run_on_weekday=int(Weekday.MONDAY),
        tz=_DENVER,
    )


def test_is_due_true_when_run_before_last_scheduled() -> None:
    now = datetime(2026, 6, 10, 12, tzinfo=timezone.utc)
    anchor = datetime(2026, 6, 9, 9, tzinfo=timezone.utc)  # prior day's run

    assert is_due(
        now,
        anchor,
        frequency=Frequency.DAILY,
        run_at_hour=2,
        run_on_weekday=int(Weekday.MONDAY),
        tz=_DENVER,
    )


def test_is_due_treats_naive_anchor_as_utc() -> None:
    now = datetime(2026, 6, 10, 12, tzinfo=timezone.utc)
    anchor = datetime(2026, 6, 10, 9)  # naive, after the 08:00 UTC slot

    assert not is_due(
        now,
        anchor,
        frequency=Frequency.DAILY,
        run_at_hour=2,
        run_on_weekday=int(Weekday.MONDAY),
        tz=_DENVER,
    )


def test_weekly_not_due_until_configured_weekday() -> None:
    # Sunday 2026-06-07 12:00 UTC; the upcoming Monday slot has not passed, so
    # the most recent scheduled run is the previous Monday (2026-06-01).
    now = datetime(2026, 6, 7, 12, tzinfo=timezone.utc)
    anchor = datetime(2026, 6, 2, tzinfo=timezone.utc)  # after 2026-06-01 slot

    assert not is_due(
        now,
        anchor,
        frequency=Frequency.WEEKLY,
        run_at_hour=2,
        run_on_weekday=int(Weekday.MONDAY),
        tz=_DENVER,
    )


def test_config_accepts_weekday_name() -> None:
    config = AnalystSchedulerConfig(run_on_weekday="friday")

    assert config.run_on_weekday is Weekday.FRIDAY


def test_config_rejects_unknown_timezone() -> None:
    with pytest.raises(ValidationError):
        AnalystSchedulerConfig(timezone="Mars/Olympus_Mons")


class _Artifact:
    def __init__(self, name: str, path: Path) -> None:
        self.name = name
        self.path = path

    def model_dump(self) -> dict[str, str]:
        return {"name": self.name, "path": str(self.path)}


class _Results:
    def __init__(self) -> None:
        self.saved: list[tuple[str, Path]] = []

    def save(self, name: str, path: Path, **_: object) -> _Artifact:
        self.saved.append((name, path))
        return _Artifact(name, path)


class _SyncAnalysisRunStatuses:
    def __init__(self) -> None:
        self.updates: list[dict[str, object]] = []

    def update(self, **kwargs: object) -> AnalysisRunStatus:
        self.updates.append(kwargs)
        return AnalysisRunStatus(
            name=str(kwargs["agent"]),
            workspace=str(kwargs["workspace"]),
            agent=str(kwargs["agent"]),
        )


class _SyncSdk:
    def __init__(self) -> None:
        self.insights = SimpleNamespace(analysis_run_statuses=_SyncAnalysisRunStatuses())


def _ctx(tmp_path: Path) -> JobContext:
    persistent = tmp_path / "persistent"
    ephemeral = tmp_path / "ephemeral"
    persistent.mkdir()
    ephemeral.mkdir()
    return JobContext(
        workspace="default",
        storage=StoragePaths(ephemeral=ephemeral, persistent=persistent),
        results=_Results(),
        job_id="insights-job-1",
    )


def test_analyze_job_records_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    async def fake_run_analyst(**_: object) -> str:
        return "analysis report"

    monkeypatch.setattr("nemo_insights_plugin.jobs.analyze.run_analyst", fake_run_analyst)
    sdk = _SyncSdk()

    result = AnalyzeJob().run(
        AnalyzeSpec(agent="research-agent").model_dump(mode="json"),
        ctx=_ctx(tmp_path),
        sdk=sdk,
    )

    assert result["status"] == "completed"
    assert result["artifact"] == {
        "name": "analysis-report",
        "path": str(tmp_path / "persistent" / "analysis-report.txt"),
    }
    updates = sdk.insights.analysis_run_statuses.updates
    assert [u["status"] for u in updates] == [
        AnalysisConfigStatus.RUNNING,
        AnalysisConfigStatus.IDLE,
    ]
    assert updates[-1]["last_submitted_job"] == "insights-job-1"
    assert (tmp_path / "persistent" / "analysis-report.txt").read_text() == "analysis report"


@pytest.mark.asyncio
async def test_analyze_job_compile_requests_persistent_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("INFERENCE_API_KEY", raising=False)
    platform_spec = await AnalyzeJob.compile(
        workspace="default",
        spec=AnalyzeSpec(agent="research-agent"),
        entity_client=object(),
        job_name="opt-analyze-default-research-agent-20260608204901",
        async_sdk=object(),
    )

    step = platform_spec["steps"][0]
    assert step["environment"] == [
        {
            "name": PERSISTENT_JOB_STORAGE_PATH_ENVVAR,
            "value": DEFAULT_JOB_STORAGE_PATH,
        },
    ]


@pytest.mark.asyncio
async def test_analyze_job_compile_can_reference_inference_secret() -> None:
    platform_spec = await AnalyzeJob.compile(
        workspace="default",
        spec=AnalyzeSpec(
            agent="calculator-agent",
            inference_api_key_secret_name="insights-inference-api-key",
        ),
        entity_client=object(),
        job_name="opt-analyze-default-calculator-agent-20260608210807",
        async_sdk=object(),
    )

    step = platform_spec["steps"][0]
    assert step["environment"] == [
        {
            "name": PERSISTENT_JOB_STORAGE_PATH_ENVVAR,
            "value": DEFAULT_JOB_STORAGE_PATH,
        },
        {
            "name": "INFERENCE_API_KEY",
            "from_secret": {"name": "insights-inference-api-key"},
        },
    ]


@pytest.mark.asyncio
async def test_analyze_job_compile_can_forward_local_inference_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INFERENCE_API_KEY", "test-key")

    platform_spec = await AnalyzeJob.compile(
        workspace="default",
        spec=AnalyzeSpec(agent="calculator-agent"),
        entity_client=object(),
        job_name="opt-analyze-default-calculator-agent-20260608210807",
        async_sdk=object(),
    )

    step = platform_spec["steps"][0]
    assert step["environment"] == [
        {
            "name": PERSISTENT_JOB_STORAGE_PATH_ENVVAR,
            "value": DEFAULT_JOB_STORAGE_PATH,
        },
        {"name": "INFERENCE_API_KEY", "value": "test-key"},
    ]


class _AsyncJobList:
    def __init__(self, jobs: list[SimpleNamespace]) -> None:
        self.jobs = jobs

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        for job in self.jobs:
            yield job


class _AsyncJobs:
    def __init__(self, jobs: list[SimpleNamespace] | None = None) -> None:
        self.created: list[dict[str, object]] = []
        self.jobs = list(jobs or [])

    async def create(self, **kwargs: object) -> SimpleNamespace:
        self.created.append(kwargs)
        return SimpleNamespace(name=kwargs.get("name"))

    def list(self, **_: object) -> _AsyncJobList:
        return _AsyncJobList(self.jobs)


class _AsyncSdk:
    def __init__(self, jobs: list[SimpleNamespace] | None = None) -> None:
        self.jobs = _AsyncJobs(jobs=jobs)


class _Entities:
    def __init__(self, run_status: AnalysisRunStatus | None = None) -> None:
        self.updated: list[AnalysisConfig] = []
        self.run_status = run_status

    async def get(self, entity_type: type, *, name: str, workspace: str) -> AnalysisRunStatus:
        del name, workspace
        if entity_type is AnalysisRunStatus and self.run_status is not None:
            return self.run_status
        raise NemoEntityNotFoundError("missing")

    async def update(self, config: AnalysisConfig) -> AnalysisConfig:
        self.updated.append(config)
        return config


def _controller(
    *,
    jobs: list[SimpleNamespace] | None = None,
    run_status: AnalysisRunStatus | None = None,
) -> InsightsAnalysisController:
    controller = InsightsAnalysisController()
    controller._config = InsightsConfig(
        analyst=AnalystSchedulerConfig(
            frequency=Frequency.DAILY,
            run_at_hour=0,
            job_profile="test-profile",
        )
    )
    controller._sdk = _AsyncSdk(jobs=jobs)
    controller._entities = _Entities(run_status=run_status)
    return controller


def test_generated_job_name_fits_derived_fileset_name_limit() -> None:
    config = AnalysisConfig(
        name="research-agent-with-a-very-long-name",
        workspace="default",
        agent="research-agent-with-a-very-long-name",
    )

    name = _job_name(config, datetime(2026, 6, 8, 20, 31, 22, tzinfo=timezone.utc))

    assert name.startswith("opt-analyze-default-")
    assert len(name) <= 63 - len("job-fileset-")
    assert len(f"job-fileset-{name}") <= 63


@pytest.mark.asyncio
async def test_controller_submits_due_job(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = _controller()
    config = AnalysisConfig(name="research-agent", workspace="default", agent="research-agent")

    async def fake_compile_job_spec(**_: object) -> dict[str, list[object]]:
        return {"steps": []}

    monkeypatch.setattr(controller, "_compile_job_spec", fake_compile_job_spec)
    await controller._reconcile_config(config)

    assert len(controller.sdk.jobs.created) == 1
    created = controller.sdk.jobs.created[0]
    assert created["source"] == "insights"
    assert created["spec"]["agent"] == "research-agent"
    assert created["spec"]["since"] is None
    assert controller.entities.updated == []


@pytest.mark.asyncio
async def test_controller_skips_active_job(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = _controller(
        jobs=[
            SimpleNamespace(
                status="active",
                custom_fields={"insights_analysis_agent": "research-agent"},
            )
        ]
    )
    config = AnalysisConfig(
        name="research-agent",
        workspace="default",
        agent="research-agent",
    )

    async def fake_compile_job_spec(**_: object) -> dict[str, list[object]]:
        return {"steps": []}

    monkeypatch.setattr(controller, "_compile_job_spec", fake_compile_job_spec)
    await controller._reconcile_config(config)

    assert controller.sdk.jobs.created == []
