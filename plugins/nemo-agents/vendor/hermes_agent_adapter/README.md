# Vendored Hermes agent adapter

Snapshot of `examples/experimental/hermes_agent_adapter` from
[NVIDIA/NeMo-Agent-Toolkit](https://github.com/NVIDIA/NeMo-Agent-Toolkit) at commit
[`d2f1c9c77b91fa28547e1526b9fe8c4fb7a09725`](https://github.com/NVIDIA/NeMo-Agent-Toolkit/commit/d2f1c9c77b91fa28547e1526b9fe8c4fb7a09725).

Copied upstream files:

- `src/nat_hermes_agent_adapter/`

Generated files, example configs, data files, and local development artifacts
from the upstream example are intentionally omitted, including `uv.lock`.

The vendored adapter registers the NAT workflow type `_type: hermes_agent`.
Runtime use still requires external `uvx` and `nemo-relay` commands to be
installed and configured in the environment that launches NAT. The default
config uses `uvx --from hermes-agent hermes` to run Hermes Agent.

To refresh this snapshot, copy the same included files from the new upstream
commit, preserve SPDX headers, and update this file with the new commit hash and
summary.
