# Fabric Config Boundary

This package contains the Platform-side config and translation helpers for
Fabric-backed NeMo Agents.

NeMo Platform owns the persisted agent contract. A Fabric-backed agent is stored
using the Platform-owned `nemo-agents-spec-v1` config shape, authored as
`agent.yaml` in the agent spec fileset and represented in code as `AgentConfig`.

Fabric is an execution dependency, not the persisted Platform contract. Before
calling Fabric SDK APIs, NeMo Agents translates the Platform-owned config into a
typed in-memory `FabricConfig`.

```text
Platform agent.yaml -> AgentConfig -> FabricConfig
```

`agent.yaml` is not treated as a Fabric SDK file-backed config or profile. The
Platform config may keep product concepts, defaults, and artifact references in
the shape NeMo Platform needs, while the Fabric translator owns the mapping into
Fabric's runtime fields such as harness adapter, model, environment, and
telemetry config.
