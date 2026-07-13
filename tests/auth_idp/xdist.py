# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0


def append_xdist_group_suffix(nodeid: str, groups: set[str]) -> str:
    if not groups:
        return nodeid
    if nodeid.rfind("@") > nodeid.rfind("]"):
        return nodeid
    return f"{nodeid}@{'_'.join(sorted(groups))}"
