# NeMo Studio Copilot Fabric smoke test

The copilot is a `nemo-agents-spec-v1` Fabric agent using the preinstalled
Deep Agents adapter. Its platform and Studio tools are exposed by the packaged
`nemo-studio-copilot-mcp` stdio server.

## Static and unit validation

From the repository root:

```bash
PYTHONPATH=agents/nemo-studio-copilot/src \
  uv run --frozen pytest agents/nemo-studio-copilot/tests/test_nemo_studio_copilot.py -v
uv run ruff check agents/nemo-studio-copilot/src agents/nemo-studio-copilot/tests
uv run ruff format --check agents/nemo-studio-copilot/src agents/nemo-studio-copilot/tests
uv run --frozen ty check
```

The tests validate Fabric translation, the Deep Agents adapter, all packaged
skills, the MCP tool surface, SDK serialization, session validation, and
approval gating for mutations.

## Register, package, and deploy

These commands change platform state and should be run independently so each
result can be verified:

```bash
export NMP_BASE_URL=http://127.0.0.1:8080
nemo agents create --name nemo-studio-copilot \
  --agent-config agents/nemo-studio-copilot-spec/agent.yaml
nemo agents package \
  --agent agents/nemo-studio-copilot/agent.yaml \
  --pyproject agents/nemo-studio-copilot/pyproject.toml \
  --tag nemo-studio-copilot:fabric-local
nemo agents deploy --agent nemo-studio-copilot \
  --name nemo-studio-copilot-fabric-deployment \
  --mode docker --image nemo-studio-copilot:fabric-local
nemo agents deployments wait nemo-studio-copilot-fabric-deployment
```

The generated image must use the Fabric server entrypoint, not `nat serve`.

## Invocation

```bash
nemo agents invoke --agent-deployment nemo-studio-copilot-fabric-deployment \
  --input "List all workspaces on the platform"
nemo agents invoke --agent-deployment nemo-studio-copilot-fabric-deployment \
  --input "List the available models and inference providers using the platform API."
```

For mutation approval, invoke through Studio and ask the copilot to create a
workspace named `nemo-studio-copilot-smoke-test`. Verify that Studio renders an
approval prompt before the SDK call, and that declining leaves platform state
unchanged.

## Studio streaming

Open `http://127.0.0.1:8080/studio`, select the copilot deployment, and send
`List all workspaces`. Verify incremental, nonduplicated text and a terminal
success or error. Then exercise a selector and an approved mutation to verify
the callback MCP tools.

## Cleanup

After verification, remove the temporary workspace, then undeploy and delete
the agent so another smoke-test run starts cleanly:

```bash
nemo workspaces delete nemo-studio-copilot-smoke-test
nemo agents undeploy nemo-studio-copilot-fabric-deployment --yes
nemo agents delete nemo-studio-copilot --yes
```

## Automated evaluation coverage

The former NAT `/generate/full` evaluation YAML remains removed. Each case in
`src/nemo_studio_copilot/nemo-studio-copilot-eval-data.json` now has
deterministic unit coverage for its required `nemo_api` tool path in
`test_nemo_studio_copilot.py`. Root pytest discovery includes these unit tests,
so `make test-unit-ci` runs them in CI without a live model endpoint.
