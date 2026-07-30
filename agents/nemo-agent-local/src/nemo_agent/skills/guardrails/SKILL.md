---
name: guardrails
description: NeMo guardrails self-check input config plus harmful-message check workflow through the platform SDK.
---
Guardrails tasks

- Build one valid self-check input config, then run one harmful-message check.
- Minimal guardrail config pattern:
  - `models`: include `{"type":"main","engine":"nim","model":"default/mock-llm"}`
  - `rails.input.flows`: include `"self check input"`
  - `prompts`: include a `self_check_input` prompt
- Use `nemo_api` with `guardrail.configs` for config CRUD.
- Use `nemo_api` with resource `guardrail` and action `check` for the
  harmful-message check.
- Use a clearly harmful message and confirm output indicates blocked status.
- Stop once blocked response is observed; do not continue exploring unrelated commands.
