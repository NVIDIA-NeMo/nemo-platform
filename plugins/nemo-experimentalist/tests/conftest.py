# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Experimentalist test-wide state isolation."""

import os
from typing import cast

import litellm
import pytest
from nemo_platform_plugin.nooa_model_client import ConfiguredModelClients, ConfiguredModelRefs, activate_model_clients
from nooa.unifiedllm import CompletionClient, FakeLLMClient

# Some NVIDIA inference endpoint models reject the tool_choice parameter.
# Drop unsupported params silently so the CodeAct strategy can call tools.
litellm.drop_params = True


@pytest.fixture(autouse=True)
def _restore_environ():
    """Undo environment changes and activate hermetic agent models.

    The CLI loads a profile's .env straight into os.environ. When the variable was
    previously unset, monkeypatch has nothing recorded to restore, so the value
    survives the test and leaks into whatever else the xdist worker runs next.

    """
    snapshot = os.environ.copy()
    fake = FakeLLMClient()
    clients = ConfiguredModelClients(
        default=cast(CompletionClient, fake),
        fast=cast(CompletionClient, fake),
        refs=ConfiguredModelRefs(default="default/fake", fast="default/fake"),
    )
    with activate_model_clients(clients):
        yield
    os.environ.clear()
    os.environ.update(snapshot)
