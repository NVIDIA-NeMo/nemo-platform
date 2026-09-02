# `relay_guardrails/` — Relay wiring + the context workaround

- **`context.py`** — the workaround: three Relay intercepts that **capture** the user
  turn off the model call, **inject** it into the tool args, and **strip** it before
  the tool runs — so the tool-boundary judge can see conversation context Relay
  doesn't natively carry there.
- **`fabric_adapter.py`** — a custom Fabric adapter that registers the workaround
  **inside** Fabric's adapter subprocess (the driver process can't reach it), then
  serves the stock `DeepAgentsRuntime` unchanged.
- **`component.py`** — builds the `nemo_guardrails` Relay component (the judge).

`context.py` and `fabric_adapter.py` are **workarounds** for a current Relay gap —
conversation context is not carried to the tool boundary. The longer-term fix is
native context support in Relay, after which both are removed (see the top-level
README's feature requests). `component.py` stays.
