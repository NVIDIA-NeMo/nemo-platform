# Iron Swarm × Relay guardrails — self-contained setup + runs.
#
# Two venvs, both local to this directory:
#   .venv         driver — nemo-relay + nemo-fabric[deepagents] + mcp
#   .worker-venv  worker — nemoguardrails==0.22.0 (the guardrails plugin spawns it)
#
# Usage:
#   make setup          # create both venvs
#   export INFERENCE_API_KEY=...
#   make spike          # all six guardrails, driven directly (real judge)
#   make fabric         # the full deployment demo through Fabric (real judge)

PYPI_NVIDIA := https://pypi.nvidia.com
DRIVER_PY   := $(CURDIR)/.venv/bin/python
WORKER_PY   := $(CURDIR)/.worker-venv/bin/python
# PATH: local .venv first, so Fabric resolves THIS venv's adapter.
# PYTHONPATH: this dir, so the adapter subprocess (python -m
#   relay_guardrails.fabric_adapter) can import our custom adapter module.
# Both are inherited by the adapter subprocess. Worker + MCP server use absolute
# interpreters, so they're unaffected.
RUN_ENV     := PATH="$(CURDIR)/.venv/bin:$$PATH" PYTHONPATH="$(CURDIR):$$PYTHONPATH" IRON_SWARM_WORKER_PYTHON=$(WORKER_PY)

.PHONY: setup setup-driver setup-worker spike fabric check-key clean

setup: setup-worker setup-driver
	@echo ""
	@echo "Setup complete. Next:  export INFERENCE_API_KEY=...  then  make spike"

# Driver venv. Two installs: public-PyPI deps first (so `mcp` is the real MCP SDK,
# not an NVIDIA-internal package), then nemo-fabric from the NVIDIA index.
setup-driver:
	uv venv .venv
	uv pip install --python $(DRIVER_PY) -r requirements-driver.txt
	uv pip install --python $(DRIVER_PY) --index $(PYPI_NVIDIA) --prerelease=allow \
		"nemo-fabric[deepagents,runtime]"

# Worker venv: pinned nemoguardrails runtime the plugin spawns.
setup-worker:
	uv venv --python 3.12 .worker-venv
	uv pip install --python $(WORKER_PY) -r requirements-worker.txt

# All six guardrails, driven directly (deterministic tool calls), real judge.
spike: check-key
	$(RUN_ENV) OPENAI_API_KEY=$$INFERENCE_API_KEY $(DRIVER_PY) demos/run_spike.py

# The deployment demo: four tools through Fabric, real judge.
fabric: check-key
	$(RUN_ENV) OPENAI_API_KEY=$$INFERENCE_API_KEY $(DRIVER_PY) demos/fabric_demo.py

check-key:
	@test -n "$$INFERENCE_API_KEY" || { echo "Set INFERENCE_API_KEY first (export INFERENCE_API_KEY=...)"; exit 1; }

clean:
	rm -rf .venv .worker-venv artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
