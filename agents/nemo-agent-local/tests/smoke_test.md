# NeMo Agent Smoke Test

Covers all changes from the follow-up PR: fallback removal, SyncBuilder-only
model resolution, and the `_StreamSafeGraph` Studio streaming fix.

## Prerequisites

- `NVIDIA_API_KEY` from https://inference.nvidia.com (Profile > Key Management)
- macOS: use `http://127.0.0.1:8080`, not `localhost` (IPv6 issue)

---

## Part 1: Unit Tests

Run from the worktree root. All tests should pass.

```bash
uv run --frozen pytest plugins/nemo-agents/builtin_agents/nemo-agent/tests/test_nemo_agent.py -v
```

Verify specifically:

- [ ] `TestGetModel::test_returns_llm_from_builder` — passes (SyncBuilder mock path works)
- [ ] `TestGetModel::test_raises_without_builder_context` — passes (ValueError propagates)
- [ ] `TestAgentGraph::test_create_agent_returns_stream_safe_graph` — passes (returns `_StreamSafeGraph`, not raw `CompiledStateGraph`)
- [ ] `TestAgentGraph::test_stream_safe_graph_delegates_attribute_access` — passes
- [ ] `TestAgentGraph::test_agent_has_expected_tools` — passes with exactly `nemo_api` and `check_status`
- [ ] No test imports `langchain_openai` or references `NVIDIA_API_KEY`

## Part 2: Fallback and CLI Tool Removal Verification

Confirm the ChatOpenAI fallback and subprocess-based CLI tool are gone:

```bash
# Should find zero matches in the runtime source.
rg -n 'ChatOpenAI|NVIDIA_API_KEY|langchain_openai|nemo_cli|subprocess' \
    plugins/nemo-agents/builtin_agents/nemo-agent/src/nemo_agent/register.py
```

Expected: no output.

## Part 3: Platform Boot + Agent Deploy

```bash
export NVIDIA_API_KEY='your-key-here'
export NMP_BASE_URL='http://127.0.0.1:8080'
nemo setup --auto --start-services --install-skills --deploy-agent
```

Wait for setup to complete.

```bash
# Agent should be deployed and running
nemo agents deployments list
```

- [ ] Deployment exists with status `running`

## Part 4: Agent Invocation

These test that the agent works end-to-end through NAT's `langgraph_wrapper`
with the real SyncBuilder and API-only platform tools.

```bash
# nemo_api tool — workspace CRUD
nemo agents invoke --agent nemo-agent \
    --input "List all workspaces on the platform"

# nemo_api tool — model and provider discovery
nemo agents invoke --agent nemo-agent \
    --input "List the available models and inference providers using the platform API."

# Multi-step with nemo_api — create + verify
nemo agents invoke --agent nemo-agent \
    --input "Create a workspace called 'smoke-test' with description 'PR follow-up smoke test', then list workspaces to confirm it exists"
```

- [ ] All three return coherent responses (no `RuntimeError` about missing builder context)
- [ ] The workspace `smoke-test` actually exists: `nemo workspaces list`

## Part 5: Studio Streaming (the main fix)

This validates that `_StreamSafeGraph` makes agent chat work in the Studio UI.

1. Open Studio in your browser:

   ```
   http://127.0.0.1:8080/studio
   ```

2. Navigate to **Agents** in the left sidebar.

3. Click the **nemo-agent** row to open the agent panel.

4. Switch to the **Chat Playground** tab.

5. Select the running deployment from the deployment dropdown (if not auto-selected).

6. Send a simple message:

   ```
   List all workspaces
   ```

7. Verify:

   - [ ] The chat shows a loading/thinking indicator (stream starts)
   - [ ] A response appears with workspace data (not empty, not an error)
   - [ ] The response text is **not garbled or duplicated** (this was the pre-fix bug — NAT's chunk validation failure or full-text concatenation produced gibberish)
   - [ ] No JavaScript console errors related to `choices`, `delta`, or stream parsing

8. Send a multi-step message to exercise tool calls:

   ```
   Create a secret called 'studio-test-key' with value 'sk-test-456' in the default workspace, then list all secrets to confirm it was created
   ```

9. Verify:

   - [ ] Response eventually appears (may take 15-30s for multi-tool agent turns)
   - [ ] Response mentions the created secret and lists secrets
   - [ ] No stream errors or broken UI state

### What "broken" looks like (for reference)

Without the `_StreamSafeGraph` fix, you would see one of:
- **Empty response** — NAT's `_parse_stream_output` throws on a chunk missing `messages`, the stream dies, Studio gets no `choices[0]` and renders nothing
- **Duplicated/garbled text** — each LangGraph state snapshot contains the full message list; NAT converts `messages[-1].text` to a `ChatResponseChunk`; Studio's reducer appends `delta.content` to the running string, so the same text appears 2-5x

## Part 6: Cleanup

```bash
nemo agents undeploy --agent nemo-agent
nemo agents delete nemo-agent
nemo workspaces delete smoke-test 2>/dev/null
nemo secrets delete studio-test-key 2>/dev/null
# Ctrl-C the nemo services run process
```
