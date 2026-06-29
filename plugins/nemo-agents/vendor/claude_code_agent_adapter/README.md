# Vendored Claude Code agent adapter

Snapshot of `examples/experimental/claude_code_agent_adapter` from
[NVIDIA/NeMo-Agent-Toolkit](https://github.com/NVIDIA/NeMo-Agent-Toolkit) at commit
[`506575970c35420355263e445582c27b4f5f2d98`](https://github.com/NVIDIA/NeMo-Agent-Toolkit/commit/506575970c35420355263e445582c27b4f5f2d98).

Copied upstream files:

- `src/nat_claude_code_agent_adapter/`

Generated files, example configs, data files, and local development artifacts
from the upstream example are intentionally omitted, including `uv.lock`.

The vendored adapter registers the NAT workflow type `_type:
claude_code_agent`. Runtime use still requires external `claude` and
`nemo-relay` commands to be installed and configured in the environment that
launches NAT.

To refresh this snapshot, copy the same included files from the new upstream
commit, preserve SPDX headers, and update this file with the new commit hash and
summary.
