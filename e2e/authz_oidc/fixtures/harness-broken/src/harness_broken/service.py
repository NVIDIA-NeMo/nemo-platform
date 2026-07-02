# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unenumerable fixture plugin for the authz OIDC E2E harness.

The import fails on purpose, so authz derivation enumerates zero endpoints
for this plugin. The bundle must fence the whole
``/apis/harness-broken`` namespace (including the bare prefix) with an
explicit deny for every caller kind — service principals included, which is
the no-match-bypass hole the fence exists to close. The platform runner's
fault-isolated ``discover()`` skips the plugin, so the platform itself keeps
running.
"""

raise RuntimeError("harness-broken: deliberate import failure for authz fence verification")


class BrokenService:  # pragma: no cover - unreachable past the raise above
    name = "harness-broken"
