# `adapters/` — custom Fabric adapter

`quill-relay/fabric-adapter.json` registers a custom Fabric adapter
(`iron_swarm.fabric.deepagents.guardrails`) whose `runner.module` is
`relay_guardrails.fabric_adapter`. Fabric discovers it by scanning
`<base_dir>/adapters/`, so `demos/fabric_demo.py` passes the reference root as
`base_dir`.

Why it exists: Fabric runs the deepagents adapter in a **separate subprocess**, so
the context workaround registered in the driver never reaches it. This adapter runs
that registration **inside the subprocess**, then serves the stock `DeepAgentsRuntime`.

**Workaround** — needed only because Relay does not yet carry conversation context
across Fabric's process boundary to the tool-boundary judge. The longer-term fix is
native context support in Relay, after which this adapter is removed (see the
feature requests in the top-level README).
