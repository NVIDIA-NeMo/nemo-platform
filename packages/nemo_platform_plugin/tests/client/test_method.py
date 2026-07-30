# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the ``method()`` descriptor that binds endpoints onto client classes.

Instance-level dispatch is exercised throughout the client and Models suites. What
is pinned here is *class*-level access, which nothing else touches and which every
introspection tool performs: ``Mock(spec=SomeClient)``, ``help()``, ``pydoc``,
autodoc, and anything walking ``dir()``.
"""

from __future__ import annotations

import inspect
import pydoc
from unittest.mock import MagicMock, create_autospec

import pytest
from nemo_platform_plugin.client.method import EndpointMethod
from nemo_platform_plugin.models.client import AsyncModelsClient, ModelsClient

BASE = "http://test:8000"


def _descriptor(name: str) -> EndpointMethod:
    return inspect.getattr_static(AsyncModelsClient, name)


# ---------------------------------------------------------------------------
# Class-level access
# ---------------------------------------------------------------------------


def test_class_level_access_returns_the_descriptor() -> None:
    """``__get__`` with no instance hands back the descriptor, per the protocol.

    It used to assert ``obj is not None``, so every one of these raised.
    """
    assert isinstance(ModelsClient.create_model, EndpointMethod)
    assert isinstance(AsyncModelsClient.create_model, EndpointMethod)
    assert ModelsClient.create_model is inspect.getattr_static(ModelsClient, "create_model")


def test_mock_spec_against_a_client_class_builds() -> None:
    """``Mock(spec=...)`` reads every attribute off the class to classify it.

    This is the failure that surfaced the bug: the models controller test suite
    could not spec a mock against its own client.
    """
    mock = MagicMock(spec=AsyncModelsClient)

    assert callable(mock.create_model)
    with pytest.raises(AttributeError):
        mock.create_modle  # noqa: B018  a typo must not be silently mockable


def test_pydoc_lists_endpoints_with_their_docstrings() -> None:
    """Endpoint docs reach help() through the copied ``__doc__``.

    pydoc swallows per-member errors, so this does not discriminate the
    class-access fix; what it pins is the attribute copying.
    """
    # plain() strips pydoc's backspace-overstrike bolding.
    rendered = pydoc.plain(pydoc.render_doc(ModelsClient))

    assert "delete_deployment" in rendered
    assert "Delete a deployment" in rendered


def test_create_autospec_does_not_raise() -> None:
    """autospec also walks the class.

    The resulting endpoint stubs are *not* callable, because the descriptor is not.
    That is a real limitation of this design and is pinned here so it is a
    deliberate trade-off rather than a surprise: use ``spec=`` for client mocks.
    """
    auto = create_autospec(AsyncModelsClient)

    assert not callable(auto.create_model)


# ---------------------------------------------------------------------------
# Identity carried from the endpoint
# ---------------------------------------------------------------------------


def test_descriptor_carries_endpoint_identity() -> None:
    descriptor = _descriptor("delete_deployment")

    assert descriptor.__name__ == "delete_deployment"
    assert descriptor.__doc__ == descriptor.endpoint.__doc__
    assert descriptor.__doc__  # the endpoint really does carry one
    assert descriptor.__wrapped__ is descriptor.endpoint


def test_signature_is_reachable_by_unwrapping_at_class_level() -> None:
    """``inspect.signature`` rejects the descriptor; ``unwrap`` gets past it.

    Pinned because the obvious reading of ``__wrapped__`` is that ``signature()``
    follows it. It does not: it refuses a non-callable before ever looking.
    """
    # Both calls are typed as taking a callable; passing the descriptor is the
    # behaviour under test, hence the suppressions rather than a cast.
    with pytest.raises(TypeError):
        inspect.signature(AsyncModelsClient.create_model)  # ty: ignore[invalid-argument-type]

    signature = inspect.signature(inspect.unwrap(AsyncModelsClient.create_model))  # ty: ignore[invalid-argument-type]

    assert set(signature.parameters) == {"workspace", "body", "exist_ok"}
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in signature.parameters.values())


def test_descriptor_does_not_leak_the_endpoint_abstractmethod_marker() -> None:
    """Endpoints are ``@abstractmethod`` stubs; that marker must not ride along.

    ``functools.update_wrapper`` would copy ``__dict__`` and with it
    ``__isabstractmethod__``, which would make any ABCMeta-based client class
    uninstantiable. The attributes are copied one by one to avoid exactly that.
    """
    descriptor = _descriptor("create_model")

    assert getattr(descriptor.endpoint, "__isabstractmethod__", False) is True
    assert not getattr(descriptor, "__isabstractmethod__", False)
    assert not getattr(AsyncModelsClient, "__abstractmethods__", frozenset())
    ModelsClient(base_url=BASE, workspace="default")  # constructs


# ---------------------------------------------------------------------------
# Instance-level dispatch (unchanged, but nothing states it outright)
# ---------------------------------------------------------------------------


def test_sync_client_binds_a_plain_callable() -> None:
    bound = ModelsClient(base_url=BASE, workspace="default").create_model

    assert callable(bound)
    assert not inspect.iscoroutinefunction(bound)


def test_async_client_binds_a_coroutine_function() -> None:
    bound = AsyncModelsClient(base_url=BASE, workspace="default").create_model

    assert inspect.iscoroutinefunction(bound)


def test_bound_method_exposes_the_real_signature() -> None:
    """Instance access hands back the wrapped function, so signature() works there."""
    signature = inspect.signature(ModelsClient(base_url=BASE, workspace="default").get_model)

    assert set(signature.parameters) == {"workspace", "name", "query_params"}
