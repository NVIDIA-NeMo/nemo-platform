# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the auditor plugin SDK CRUD sub-resources and ``run`` helper.

Each CRUD test stubs ``platform._client`` with a ``MagicMock(spec=httpx.Client)``
(or ``AsyncMock(spec=httpx.AsyncClient)``) so we can assert on the URL and
JSON body the SDK actually sends — same pattern the evaluator plugin uses in
``plugins/nemo-evaluator/tests/test_sdk.py``.

``test_run_*`` verifies the SDK builds the right ``AuditInputSpec`` payload
and submits it to the auditor plugin service.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

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


def _ok_response(payload: object, *, status_code: int = 200) -> MagicMock:
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


class TestSyncRun:
    def test_posts_name_refs_to_job_submission_route(self) -> None:
        platform = _SyncPlatform()
        platform._client.post.return_value = _ok_response({"name": "audit-job", "status": "created"}, status_code=201)

        resource = AuditorPluginResource(cast(NeMoPlatform, platform))
        result = resource.run(config="my-cfg", target="my-tgt", workspace="default")

        assert result == {"name": "audit-job", "status": "created"}
        platform._client.get.assert_not_called()
        platform._client.post.assert_called_once_with(
            "http://test:8000/apis/auditor/v2/workspaces/default/jobs/audit",
            json={"spec": {"config": "my-cfg", "target": "my-tgt"}},
        )

    def test_inline_entities_are_serialized_in_job_spec(self) -> None:
        platform = _SyncPlatform()
        platform._client.post.return_value = _ok_response({"name": "audit-job", "status": "created"}, status_code=201)

        inline_config = AuditConfig(name="inline-cfg", workspace="default")
        inline_target = AuditTarget(name="inline-tgt", workspace="default", type="nim", model="m")

        resource = AuditorPluginResource(cast(NeMoPlatform, platform))
        resource.run(config=inline_config, target=inline_target)

        spec_dict = platform._client.post.call_args.kwargs["json"]["spec"]
        assert spec_dict["config"]["name"] == "inline-cfg"
        assert spec_dict["target"]["name"] == "inline-tgt"

    def test_omitted_workspace_defaults_to_default(self) -> None:
        platform = _SyncPlatform()
        platform._client.post.return_value = _ok_response({"name": "audit-job", "status": "created"}, status_code=201)

        resource = AuditorPluginResource(cast(NeMoPlatform, platform))
        resource.run(config="cfg-1", target="tgt-1")

        assert (
            platform._client.post.call_args.args[0] == "http://test:8000/apis/auditor/v2/workspaces/default/jobs/audit"
        )

    def test_rejects_non_object_submission_response(self) -> None:
        platform = _SyncPlatform()
        platform._client.post.return_value = _ok_response(["bad"], status_code=201)
        resource = AuditorPluginResource(cast(NeMoPlatform, platform))

        with pytest.raises(TypeError, match="JSON object"):
            resource.run(config="cfg-1", target="tgt-1")


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
async def test_async_run_posts_job_submission() -> None:
    platform = _AsyncPlatform()
    platform._client.post.return_value = _ok_response({"name": "audit-job", "status": "created"}, status_code=201)

    resource = AsyncAuditorPluginResource(cast(AsyncNeMoPlatform, platform))
    result = await resource.run(config="my-cfg", target="my-tgt", workspace="default")

    assert result == {"name": "audit-job", "status": "created"}
    platform._client.post.assert_awaited_once_with(
        "http://test:8000/apis/auditor/v2/workspaces/default/jobs/audit",
        json={"spec": {"config": "my-cfg", "target": "my-tgt"}},
    )
