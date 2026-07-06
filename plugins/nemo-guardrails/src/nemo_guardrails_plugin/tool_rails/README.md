# Tool Rails

This folder contains the built-in tool-call rail flows exposed by the
`nemo-guardrails` plugin. These flows let a GuardrailConfig apply deterministic
policy to OpenAI-style tool calls without requiring users to write custom Colang.

The plugin injects `flows.co` into each `LLMRails` instance and registers the
matching Python actions from `actions.py` at build time.

## Flow Surface

Use these flow names in `rails.tool_output.flows` or `rails.tool_input.flows`.

| Flow | Rail type | Purpose |
| --- | --- | --- |
| `check tool allowlist` | `tool_output`, `tool_input` | Allows only configured tool names. |
| `check tool arguments` | `tool_output` | Blocks configured argument values by keyword or maximum length. |
| `check tool schema` | `tool_output` | Validates tool-call arguments against the request's declared tool JSON schemas. |
| `check tool result linkage` | `tool_input` | Verifies `role: "tool"` results correspond to prior assistant tool calls. |

Each Colang flow calls its Python action and aborts with `bot refuse to respond`
when the action returns `False`.

## Configuration

Tool rail policy lives in `custom_data` on the GuardrailConfig.

```json
{
  "rails": {
    "tool_output": {
      "flows": [
        "check tool allowlist",
        "check tool arguments",
        "check tool schema"
      ]
    },
    "tool_input": {
      "flows": ["check tool result linkage"]
    }
  },
  "custom_data": {
    "tool_allowlist": {
      "allowed_tools": ["search_public_docs"]
    },
    "tool_arguments": {
      "query_db": {
        "query": {
          "blocked_keywords": ["DROP", "DELETE"],
          "max_length": 500
        }
      }
    }
  }
}
```

An absent or empty allowlist allows all tool names. Argument rules are applied
only to tools and argument names present in `custom_data.tool_arguments`.

## Runtime Context

The middleware provides the context consumed by these actions:

- `tool_calls`: assistant-proposed tool calls from a non-streaming response or a
  buffered streaming response.
- `declared_tools`: the original request's `tools` field, used by
  `check tool schema`.
- `messages`: the request messages, used by `check tool result linkage`.
- `tool_name`, `tool_message`, and `tool_call_id`: values set by the
  `nemoguardrails` tool-input flow while iterating tool results.

`tool_output` rails run after the model proposes tool calls and before an agent
executes them. `tool_input` rails run when tool results are sent back to the
model.

## Failure Behavior

The actions fail closed on unexpected errors. Malformed tool-call arguments,
undeclared schemas, and invalid result linkage return `False`, causing the
Colang flow to abort and the plugin to return a blocked response.
