# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Endpoint transport resolution: which address the platform dials for an Endpoint URL."""

from __future__ import annotations

from typing import Any

import pytest
from nemo_deployments_plugin.config import DeploymentsConfig, ExecutorConfigEntry
from nemo_deployments_plugin.endpoint_transport import DIRECT, EndpointTransport, endpoint_transport

MINTED = "https://default--nmp-abc--http.openshell.localhost:8080/v1/chat/completions?stream=true"


def _config(monkeypatch: pytest.MonkeyPatch, *entries: dict[str, Any], default: str | None = None) -> None:
    cfg = DeploymentsConfig(executors=[ExecutorConfigEntry(**e) for e in entries], default_executor=default)
    monkeypatch.setattr(DeploymentsConfig, "get", classmethod(lambda cls: cfg))


def test_direct_transport_leaves_the_url_alone() -> None:
    url, headers = DIRECT.target(MINTED)
    assert url == MINTED
    assert headers == {}
    assert DIRECT.client_kwargs() == {}


def test_connect_base_swaps_netloc_and_carries_the_minted_host() -> None:
    transport = EndpointTransport(connect_base="https://openshell.openshell.svc.cluster.local:8080")
    url, headers = transport.target(MINTED)
    assert url == "https://openshell.openshell.svc.cluster.local:8080/v1/chat/completions?stream=true"
    assert headers == {"Host": "default--nmp-abc--http.openshell.localhost:8080"}


def test_client_kwargs_only_carry_non_default_tls() -> None:
    assert EndpointTransport(connect_base="http://gw:17670").client_kwargs() == {}
    assert EndpointTransport(verify="/etc/ca.crt", cert=("/etc/tls.crt", "/etc/tls.key")).client_kwargs() == {
        "verify": "/etc/ca.crt",
        "cert": ("/etc/tls.crt", "/etc/tls.key"),
    }


def test_openshell_executor_dials_the_gateway_with_its_tls_material(monkeypatch: pytest.MonkeyPatch) -> None:
    _config(
        monkeypatch,
        {"name": "local-k8s", "backend": "k8s"},
        {
            "name": "openshell",
            "backend": "openshell",
            "config": {
                "gateway_endpoint": "https://openshell.openshell.svc.cluster.local:8080",
                "tls": {
                    "ca_cert_path": "/etc/openshell-tls/client/ca.crt",
                    "client_cert_path": "/etc/openshell-tls/client/tls.crt",
                    "client_key_path": "/etc/openshell-tls/client/tls.key",
                },
            },
        },
    )
    transport = endpoint_transport("openshell")
    assert transport == EndpointTransport(
        connect_base="https://openshell.openshell.svc.cluster.local:8080",
        verify="/etc/openshell-tls/client/ca.crt",
        cert=("/etc/openshell-tls/client/tls.crt", "/etc/openshell-tls/client/tls.key"),
    )


def test_plaintext_openshell_executor_dials_http_with_no_tls_material(monkeypatch: pytest.MonkeyPatch) -> None:
    """A gateway installed with server.disableTls=true is reached over plain http, minted host preserved."""
    _config(
        monkeypatch,
        {
            "name": "openshell",
            "backend": "openshell",
            "config": {"gateway_endpoint": "http://openshell.openshell.svc.cluster.local:8080"},
        },
    )
    transport = endpoint_transport("openshell")
    url, headers = transport.target("http://default--nmp-abc--http.openshell.localhost:8080/health")
    assert url == "http://openshell.openshell.svc.cluster.local:8080/health"
    assert headers == {"Host": "default--nmp-abc--http.openshell.localhost:8080"}
    assert transport.client_kwargs() == {}


def test_unset_executor_resolves_the_default_like_the_reconciler(monkeypatch: pytest.MonkeyPatch) -> None:
    _config(
        monkeypatch,
        {"name": "openshell", "backend": "openshell", "config": {"gateway_endpoint": "http://127.0.0.1:17670"}},
        default="openshell",
    )
    assert endpoint_transport(None).connect_base == "http://127.0.0.1:17670"


@pytest.mark.parametrize("executor", ["local-k8s", "local-docker", "missing", None])
def test_non_openshell_and_unknown_executors_dial_directly(
    monkeypatch: pytest.MonkeyPatch, executor: str | None
) -> None:
    _config(
        monkeypatch,
        {"name": "local-k8s", "backend": "k8s"},
        {"name": "local-docker", "backend": "docker"},
        default="local-docker",
    )
    assert endpoint_transport(executor) is DIRECT
