# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Import this module for its side effect: bridging ``AUTHOR_*`` credentials.

Transitional. This module exists only because Eval Author still reuses Experimentalist
agents, and it should be deleted along with the last ``nemo_experimentalist_plugin`` import
in this package. ``tests/test_plugin_boundary.py`` tracks what is left to remove.

``TraceAnalyzer`` and the other Experimentalist agents Eval Author reuses build their LLM
client in the class body, so they read ``EXPERIMENTALIST_*`` the moment their module is
first imported. A module that imports them therefore has to bridge *before* that import,
which no function call inside the module can do.

Importing this module is how Eval Author expresses that ordering. ``import
nemo_eval_author_plugin._env_bridge`` sorts ahead of every ``from ...`` line in the same
isort section, so the ordering is maintained by the linter rather than by an ``E402``
waiver and a comment asking future readers not to reshuffle the imports.
"""

from nemo_eval_author_plugin.model_config import bridge_author_env_to_experimentalist

bridge_author_env_to_experimentalist()
