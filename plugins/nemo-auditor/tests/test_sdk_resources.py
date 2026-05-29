# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the auditor plugin SDK CRUD sub-resources and ``run`` helper.

Each CRUD test stubs ``platform._client`` with a ``MagicMock(spec=httpx.Client)``
(or ``AsyncMock(spec=httpx.AsyncClient)``) so we can assert on the URL and
JSON body the SDK actually sends — same pattern the evaluator plugin uses in
``plugins/nemo-evaluator/tests/test_sdk.py``.

``test_run_*`` patches ``nemo_auditor.sdk.NemoJobScheduler`` so the test never
actually shells out to garak; we just verify the SDK builds the right
``AuditInputSpec`` payload and forwards it to ``scheduler.run_local``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from nemo_auditor.entities import (
    AuditConfig,
    AuditPluginsData,
    AuditReportData,
    AuditRunData,
    AuditSystemData,
    AuditTarget,
)
from nemo_auditor.sdk import AsyncAuditorPluginResource, AuditorPluginResource
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform

NOW = datetime.now(timezone.utc)


class _SyncPlatform:
    def __init__(self) -> None:
        self.base_url = "http://test:8000"
        self._client = MagicMock(spec=httpx.Client)


class _AsyncPlatform:
    def __init__(self) -> None:
        self.base_url = "http://test:8000"
        self._client = AsyncMock(spec=httpx.AsyncClient)


def _config_payload(name: str = "cfg-1", workspace: str = "default", **overrides: Any) -> dict:
    """Return the wire shape the FastAPI route returns for an AuditConfig."""
    base = {
        "id": f"auditor-audit-config-{name}-id",
        "name": name,
        "workspace": workspace,
        "entity_type": "auditor_audit_config",
        "created_at": NOW.isoformat(),
        "updated_at": NOW.isoformat(),
        "description": None,
        "system": AuditSystemData().model_dump(mode="json"),
        "run": AuditRunData().model_dump(mode="json"),
        "plugins": AuditPluginsData().model_dump(mode="json"),
        "reporting": AuditReportData().model_dump(mode="json"),
    }
    base.update(overrides)
    return base


def _target_payload(name: str = "tgt-1", workspace: str = "default", **overrides: Any) -> dict:
    base = {
        "id": f"auditor-audit-target-{name}-id",
        "name": name,
        "workspace": workspace,
        "entity_type": "auditor_audit_target",
        "created_at": NOW.isoformat(),
        "updated_at": NOW.isoformat(),
        "description": None,
        "type": "nim",
        "model": "meta/llama-3.1-8b-instruct",
        "options": {},
    }
    base.update(overrides)
    return base


def _ok_response(payload: dict, *, status_code: int = 200) -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


# ---------------------------------------------------------------------------
# Sync CRUD: configs
# ---------------------------------------------------------------------------


class TestSyncConfigs:
    def test_create_posts_to_workspace_route_with_full_body(self) -> None:
        platform = _SyncPlatform()
        platform._client.post.return_value = _ok_response(_config_payload(name="cfg-1"), status_code=201)
        resource = AuditorPluginResource(cast(NeMoPlatform, platform))

        cfg = resource.configs.create(
            workspace="default",
            name="cfg-1",
            description="hello",
            system=AuditSystemData(lite=True, parallel_attempts=4),
            run=AuditRunData(generations=3),
        )

        assert isinstance(cfg, AuditConfig)
        assert cfg.name == "cfg-1"
        assert cfg.workspace == "default"
        platform._client.post.assert_called_once()
        url, kwargs = platform._client.post.call_args[0], platform._client.post.call_args.kwargs
        assert url == ("http://test:8000/apis/auditor/v2/workspaces/default/configs",)
        body = kwargs["json"]
        assert body["name"] == "cfg-1"
        assert body["description"] == "hello"
        assert body["system"]["lite"] is True
        assert body["system"]["parallel_attempts"] == 4
        assert body["run"]["generations"] == 3

    def test_create_fills_default_subblocks_when_omitted(self) -> None:
        platform = _SyncPlatform()
        platform._client.post.return_value = _ok_response(_config_payload(), status_code=201)
        resource = AuditorPluginResource(cast(NeMoPlatform, platform))

        resource.configs.create(workspace="default", name="cfg-1")

        body = platform._client.post.call_args.kwargs["json"]
        # CreateAuditConfigRequest defaults must round-trip even when caller omits everything.
        assert body["system"] == AuditSystemData().model_dump(mode="json")
        assert body["run"] == AuditRunData().model_dump(mode="json")
        assert body["plugins"] == AuditPluginsData().model_dump(mode="json")
        assert body["reporting"] == AuditReportData().model_dump(mode="json")

    def test_list_forwards_pagination_params(self) -> None:
        platform = _SyncPlatform()
        platform._client.get.return_value = _ok_response(
            {
                "data": [],
                "pagination": {"page": 2, "page_size": 5, "total_pages": 0, "total_results": 0},
                "sort": "name",
            }
        )
        resource = AuditorPluginResource(cast(NeMoPlatform, platform))

        body = resource.configs.list(workspace="prod", page=2, page_size=5, sort="name")

        assert body["pagination"]["page"] == 2
        url = platform._client.get.call_args.args[0]
        params = platform._client.get.call_args.kwargs["params"]
        assert url == "http://test:8000/apis/auditor/v2/workspaces/prod/configs"
        assert params == {"page": 2, "page_size": 5, "sort": "name"}

    def test_get_hits_named_route_and_returns_entity(self) -> None:
        platform = _SyncPlatform()
        platform._client.get.return_value = _ok_response(_config_payload(name="cfg-1"))
        resource = AuditorPluginResource(cast(NeMoPlatform, platform))

        cfg = resource.configs.get(workspace="default", name="cfg-1")

        assert isinstance(cfg, AuditConfig)
        assert cfg.name == "cfg-1"
        platform._client.get.assert_called_once_with(
            "http://test:8000/apis/auditor/v2/workspaces/default/configs/cfg-1",
        )

    def test_update_puts_full_body(self) -> None:
        platform = _SyncPlatform()
        platform._client.put.return_value = _ok_response(_config_payload(name="cfg-1", description="new"))
        resource = AuditorPluginResource(cast(NeMoPlatform, platform))

        cfg = resource.configs.update(workspace="default", name="cfg-1", description="new")

        assert cfg.description == "new"
        url = platform._client.put.call_args.args[0]
        body = platform._client.put.call_args.kwargs["json"]
        assert url == "http://test:8000/apis/auditor/v2/workspaces/default/configs/cfg-1"
        assert body["description"] == "new"

    def test_delete_hits_named_route(self) -> None:
        platform = _SyncPlatform()
        response = MagicMock(spec=httpx.Response)
        response.status_code = 204
        response.raise_for_status.return_value = None
        platform._client.delete.return_value = response
        resource = AuditorPluginResource(cast(NeMoPlatform, platform))

        result = resource.configs.delete(workspace="default", name="cfg-1")

        assert result is None
        platform._client.delete.assert_called_once_with(
            "http://test:8000/apis/auditor/v2/workspaces/default/configs/cfg-1",
        )


# ---------------------------------------------------------------------------
# Sync CRUD: targets
# ---------------------------------------------------------------------------


class TestSyncTargets:
    def test_create_posts_to_workspace_route(self) -> None:
        platform = _SyncPlatform()
        platform._client.post.return_value = _ok_response(_target_payload(name="tgt-1"), status_code=201)
        resource = AuditorPluginResource(cast(NeMoPlatform, platform))

        tgt = resource.targets.create(
            workspace="default",
            name="tgt-1",
            type="nim",
            model="meta/llama-3.1-8b-instruct",
            options={"uri": "http://localhost:9000/v1"},
            description="local nim",
        )

        assert isinstance(tgt, AuditTarget)
        assert tgt.name == "tgt-1"
        platform._client.post.assert_called_once()
        url = platform._client.post.call_args.args[0]
        body = platform._client.post.call_args.kwargs["json"]
        assert url == "http://test:8000/apis/auditor/v2/workspaces/default/targets"
        assert body == {
            "name": "tgt-1",
            "description": "local nim",
            "type": "nim",
            "model": "meta/llama-3.1-8b-instruct",
            "options": {"uri": "http://localhost:9000/v1"},
        }

    def test_get_and_delete_hit_named_route(self) -> None:
        platform = _SyncPlatform()
        platform._client.get.return_value = _ok_response(_target_payload(name="tgt-1"))
        delete_response = MagicMock(spec=httpx.Response)
        delete_response.status_code = 204
        delete_response.raise_for_status.return_value = None
        platform._client.delete.return_value = delete_response
        resource = AuditorPluginResource(cast(NeMoPlatform, platform))

        tgt = resource.targets.get(workspace="default", name="tgt-1")
        resource.targets.delete(workspace="default", name="tgt-1")

        assert isinstance(tgt, AuditTarget)
        platform._client.get.assert_called_once_with(
            "http://test:8000/apis/auditor/v2/workspaces/default/targets/tgt-1",
        )
        platform._client.delete.assert_called_once_with(
            "http://test:8000/apis/auditor/v2/workspaces/default/targets/tgt-1",
        )

    def test_list_and_update_round_trip(self) -> None:
        platform = _SyncPlatform()
        platform._client.get.return_value = _ok_response(
            {"data": [_target_payload(name="a"), _target_payload(name="b")], "pagination": None, "sort": "-created_at"}
        )
        platform._client.put.return_value = _ok_response(_target_payload(name="tgt-1", model="new-model"))
        resource = AuditorPluginResource(cast(NeMoPlatform, platform))

        listed = resource.targets.list(workspace="default")
        assert [t["name"] for t in listed["data"]] == ["a", "b"]

        updated = resource.targets.update(
            workspace="default",
            name="tgt-1",
            type="nim",
            model="new-model",
        )
        assert updated.model == "new-model"


# ---------------------------------------------------------------------------
# Sub-resource caching
# ---------------------------------------------------------------------------


def test_configs_and_targets_properties_are_cached() -> None:
    platform = _SyncPlatform()
    resource = AuditorPluginResource(cast(NeMoPlatform, platform))

    cached_configs = resource.configs
    cached_targets = resource.targets
    assert resource.configs is cached_configs
    assert resource.targets is cached_targets


# ---------------------------------------------------------------------------
# Sync run()
# ---------------------------------------------------------------------------


@patch("nemo_auditor.sdk.NemoJobScheduler")
class TestSyncRun:
    def test_resolves_name_strings_via_get_then_calls_scheduler(self, scheduler_cls: MagicMock) -> None:
        platform = _SyncPlatform()
        platform._client.get.side_effect = [
            _ok_response(_config_payload(name="my-cfg", workspace="default")),
            _ok_response(_target_payload(name="my-tgt", workspace="default")),
        ]
        scheduler = MagicMock()
        scheduler.run_local.return_value = {"status": "completed", "returncode": 0, "results": {}}
        scheduler_cls.return_value = scheduler

        resource = AuditorPluginResource(cast(NeMoPlatform, platform))
        result = resource.run(config="my-cfg", target="my-tgt", workspace="default")

        assert result["status"] == "completed"
        # Resolved both entities via two sync GETs.
        assert platform._client.get.call_count == 2
        platform._client.get.assert_any_call(
            "http://test:8000/apis/auditor/v2/workspaces/default/configs/my-cfg",
        )
        platform._client.get.assert_any_call(
            "http://test:8000/apis/auditor/v2/workspaces/default/targets/my-tgt",
        )

        # Spec handed to the scheduler must carry inline entities (not strings).
        scheduler.run_local.assert_called_once()
        args, kwargs = scheduler.run_local.call_args
        job_cls, spec_dict = args
        assert job_cls.__name__ == "AuditJob"
        assert isinstance(spec_dict["config"], dict)
        assert spec_dict["config"]["name"] == "my-cfg"
        assert isinstance(spec_dict["target"], dict)
        assert spec_dict["target"]["name"] == "my-tgt"
        assert kwargs["workspace"] == "default"
        assert kwargs["sdk"] is platform

    def test_inline_entities_skip_http_resolution(self, scheduler_cls: MagicMock) -> None:
        platform = _SyncPlatform()
        scheduler = MagicMock()
        scheduler.run_local.return_value = {"status": "completed", "returncode": 0, "results": {}}
        scheduler_cls.return_value = scheduler

        inline_config = AuditConfig(name="inline-cfg", workspace="default")
        inline_target = AuditTarget(name="inline-tgt", workspace="default", type="nim", model="m")

        resource = AuditorPluginResource(cast(NeMoPlatform, platform))
        resource.run(config=inline_config, target=inline_target)

        # No HTTP roundtrip — inline entities go straight to the scheduler.
        platform._client.get.assert_not_called()
        spec_dict = scheduler.run_local.call_args.args[1]
        assert spec_dict["config"]["name"] == "inline-cfg"
        assert spec_dict["target"]["name"] == "inline-tgt"
        # Defaults to "default" workspace when caller omits it.
        assert scheduler.run_local.call_args.kwargs["workspace"] == "default"

    def test_workspace_qualified_name_parses_workspace_from_string(self, scheduler_cls: MagicMock) -> None:
        platform = _SyncPlatform()
        platform._client.get.side_effect = [
            _ok_response(_config_payload(name="cfg-1", workspace="prod")),
            _ok_response(_target_payload(name="tgt-1", workspace="staging")),
        ]
        scheduler = MagicMock()
        scheduler.run_local.return_value = {"status": "completed", "returncode": 0, "results": {}}
        scheduler_cls.return_value = scheduler

        resource = AuditorPluginResource(cast(NeMoPlatform, platform))
        resource.run(config="prod/cfg-1", target="staging/tgt-1", workspace="default")

        # GETs must use the workspace from the qualified name, not the default.
        platform._client.get.assert_any_call(
            "http://test:8000/apis/auditor/v2/workspaces/prod/configs/cfg-1",
        )
        platform._client.get.assert_any_call(
            "http://test:8000/apis/auditor/v2/workspaces/staging/targets/tgt-1",
        )
        # The run workspace (used by JobContext) still comes from the kwarg.
        assert scheduler.run_local.call_args.kwargs["workspace"] == "default"


# ---------------------------------------------------------------------------
# Async smoke tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_configs_create_posts_to_workspace_route() -> None:
    platform = _AsyncPlatform()
    platform._client.post.return_value = _ok_response(_config_payload(name="cfg-1"), status_code=201)
    resource = AsyncAuditorPluginResource(cast(AsyncNeMoPlatform, platform))

    cfg = await resource.configs.create(workspace="default", name="cfg-1", description="hi")

    assert isinstance(cfg, AuditConfig)
    assert cfg.name == "cfg-1"
    platform._client.post.assert_called_once()
    url = platform._client.post.call_args.args[0]
    assert url == "http://test:8000/apis/auditor/v2/workspaces/default/configs"


@pytest.mark.asyncio
async def test_async_run_resolves_names_and_calls_scheduler_in_thread() -> None:
    platform = _AsyncPlatform()
    platform._client.get.side_effect = [
        _ok_response(_config_payload(name="my-cfg")),
        _ok_response(_target_payload(name="my-tgt")),
    ]
    scheduler = MagicMock()
    scheduler.run_local.return_value = {"status": "completed", "returncode": 0, "results": {}}

    with (
        patch("nemo_auditor.sdk.NemoJobScheduler", return_value=scheduler) as scheduler_cls,
        patch(
            "nemo_auditor.sdk.asyncio.to_thread", new=AsyncMock(return_value=scheduler.run_local.return_value)
        ) as to_thread,
    ):
        resource = AsyncAuditorPluginResource(cast(AsyncNeMoPlatform, platform))
        result = await resource.run(config="my-cfg", target="my-tgt", workspace="default")

    assert result["status"] == "completed"
    scheduler_cls.assert_called_once_with()
    # Scheduler call is dispatched via asyncio.to_thread so the caller's loop stays free.
    to_thread.assert_awaited_once()
    call = to_thread.await_args
    assert call is not None
    assert call.args[0] is scheduler.run_local
    # job_cls is the second positional arg to to_thread (the first arg to run_local).
    assert call.args[1].__name__ == "AuditJob"
    spec_dict = call.args[2]
    assert spec_dict["config"]["name"] == "my-cfg"
    assert spec_dict["target"]["name"] == "my-tgt"
    assert call.kwargs["workspace"] == "default"
    assert call.kwargs["async_sdk"] is platform
