# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The ``run_analyst`` client injection contract."""

import pytest
from nemo_insights_plugin.analyst import run as run_module


class FakeClient:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class FakeBackend:
    async def persist_result(self, *, workspace: str, agent: str, result: object) -> str:
        return "REPORT"


def _stub_pipeline(monkeypatch: pytest.MonkeyPatch, seen: dict[str, object]) -> None:
    def fake_make_backend(*, client: FakeClient, insights_output: str | None) -> FakeBackend:
        seen["backend_client"] = client
        return FakeBackend()

    async def fake_run_agent(analyst: object, deps: object, *, verbose: bool) -> object:
        return object()

    monkeypatch.setattr(run_module, "make_analyst_backend", fake_make_backend)
    monkeypatch.setattr(run_module, "build_analyst_agent", lambda **kwargs: object())
    monkeypatch.setattr(run_module, "_run_agent", fake_run_agent)


async def test_injected_client_is_used_and_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    seen: dict[str, object] = {}
    _stub_pipeline(monkeypatch, seen)

    report = await run_module.run_analyst(
        agent="agent",
        agent_spec=None,
        workspace="workspace",
        base_url="https://platform",
        client=client,  # type: ignore[arg-type]
    )

    assert report == "REPORT"
    assert seen["backend_client"] is client
    assert client.closed


async def test_client_closed_when_backend_construction_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()

    def raising_backend(*, client: FakeClient, insights_output: str | None) -> FakeBackend:
        raise RuntimeError("backend failed")

    monkeypatch.setattr(run_module, "make_analyst_backend", raising_backend)

    with pytest.raises(RuntimeError, match="backend failed"):
        await run_module.run_analyst(
            agent="agent",
            agent_spec=None,
            workspace="workspace",
            base_url="https://platform",
            client=client,  # type: ignore[arg-type]
        )

    assert client.closed
