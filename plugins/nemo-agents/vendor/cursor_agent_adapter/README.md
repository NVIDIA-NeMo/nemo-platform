# Vendored Cursor agent adapter

Snapshot of `examples/experimental/cursor_agent_adapter` from
[NVIDIA/NeMo-Agent-Toolkit](https://github.com/NVIDIA/NeMo-Agent-Toolkit) at commit
[`ffa626e512e0b9bdb973f3ebe4f4122272092499`](https://github.com/NVIDIA/NeMo-Agent-Toolkit/commit/ffa626e512e0b9bdb973f3ebe4f4122272092499).

Copied upstream files:

- `src/nat_cursor_agent_adapter/`

Generated files, example configs, data files, and local development artifacts
from the upstream example are intentionally omitted, including `uv.lock`.

The vendored adapter registers the NAT workflow type `_type: cursor_agent`.
Runtime use still requires external `cursor-agent` and `nemo-relay` commands to
be installed and configured in the environment that launches NAT.

To refresh this snapshot, copy the same included files from the new upstream
commit, preserve SPDX headers, and update this file with the new commit hash and
summary.
