# Vendored Codex agent adapter

Snapshot of `examples/experimental/codex_agent_adapter` from
[NVIDIA/NeMo-Agent-Toolkit](https://github.com/NVIDIA/NeMo-Agent-Toolkit) at commit
[`7f9c8a4a674ed2e9e14cf870cb6b7955ee00042f`](https://github.com/NVIDIA/NeMo-Agent-Toolkit/commit/7f9c8a4a674ed2e9e14cf870cb6b7955ee00042f)
("Forward-merge release/1.8 into develop (#2055)", 2026-06-24).

Copied upstream files:

- `LICENSE.md`
- `src/nat_codex_agent_adapter/`

Generated files and local development artifacts from the upstream example are
intentionally omitted, including `.DS_Store`, `uv.lock`, and
`src/nat_codex_agent_adapter.egg-info/`.

The vendored adapter registers the NAT workflow type `_type: codex_agent`.
Runtime use still requires external `codex` and `nemo-relay` commands to be
installed and configured in the environment that launches NAT.

To refresh this snapshot, copy the same included files from the new upstream
commit, preserve SPDX headers, and update this file with the new commit hash and
summary.
