# `demos/` — runnable entry points

Run these via the Makefile from the reference root (`make spike` / `make fabric`) —
they need `PYTHONPATH` set to the root so they can import `relay_guardrails`, which
the Makefile does. Both need `INFERENCE_API_KEY`.

- **`run_spike.py`** (`make spike`) — drives the tools **directly** (no agent, no
  Fabric), so all four tools / six checks are exercised **deterministically** every
  run. The fast regression loop for iterating on `guardrails_config/prompts.yml`.
- **`fabric_demo.py`** (`make fabric`) — the **deployment shape**: the agent through
  Fabric's deepagents harness, tools via the MCP server, guardrails via config + the
  custom adapter. Real end-to-end. Passes the reference root as Fabric's `base_dir`
  (so `adapters/` is discovered).
