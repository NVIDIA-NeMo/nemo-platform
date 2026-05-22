# AssistantChat

`AssistantChat` is an assistant-ui based chat surface for Studio consumers. It owns an assistant-ui `ExternalStoreRuntime` and calls the existing `useChatCompletion` hook, so it can use the same inference gateway routing as the current chat components without depending on the legacy `ChatProvider` state.

## Reference

### Basic Usage

```tsx
import { AssistantChat } from '@nemo/common/src/components/AssistantChat';

export const ChatPanel = () => (
  <AssistantChat
    model="meta/llama-3.1-8b-instruct"
    workspace="default"
    assistantName="Inference Gateway"
  />
);
```

Use `baseURL` instead of `workspace` when the caller already has an OpenAI-compatible chat completions endpoint:

```tsx
<AssistantChat
  model="meta/llama-3.1-8b-instruct"
  baseURL="https://example.test/v1"
  promptData={{
    system_prompt: 'Answer concisely.',
    inference_params: { temperature: 0.2, max_tokens: 512 },
  }}
/>
```

### Props

| Prop                  | Type                           | Required | Description                                                                                                                                                        |
| --------------------- | ------------------------------ | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `model`               | `string`                       | Yes      | Model name routed through inference gateway or sent to the explicit `baseURL`.                                                                                     |
| `workspace`           | `string`                       | No       | Workspace used by `useChatCompletion` to build the default inference gateway URL.                                                                                  |
| `baseURL`             | `string`                       | No       | Explicit OpenAI-compatible chat completions base URL.                                                                                                              |
| `promptData`          | `PromptData`                   | No       | Supplies `system_prompt`, `temperature`, and `max_tokens` defaults.                                                                                                |
| `tools`               | `readonly AssistantChatTool[]` | No       | Tool definitions for the request. OpenAI-compatible tool schemas are forwarded verbatim. Studio tools are executable client-side tools shown in the composer menu. |
| `defaultEnabledTools` | `readonly string[]`            | No       | Tool names enabled when the thread mounts. Users flip the rest via the composer options menu (per-thread, in-memory). Defaults to none enabled.                    |
| `assistantName`       | `string`                       | No       | Display name used in the composer placeholder.                                                                                                                     |
| `placeholder`         | `string`                       | No       | Overrides the composer placeholder text.                                                                                                                           |
| `disabled`            | `boolean`                      | No       | Disables assistant-ui input and runtime actions.                                                                                                                   |
| `className`           | `string`                       | No       | Additional class names for the chat container.                                                                                                                     |
| `initialMessages`     | `readonly ThreadMessageLike[]` | No       | Initial assistant-ui messages for the thread.                                                                                                                      |
| `onError`             | `(error: Error) => void`       | No       | Called when a completion request fails for a non-cancel reason.                                                                                                    |

### Runtime Integration

`AssistantChat` creates an assistant-ui `ExternalStoreRuntime` through `useAssistantChatRuntime`. Consumers pass props to `AssistantChat`; they do not need to instantiate the runtime directly. The runtime converts assistant-ui messages to OpenAI messages, calls `useChatCompletion`, streams deltas into the latest assistant message, executes any tool calls the model emits, appends the results, and re-issues the completion until the model produces a final text response (or hits the round cap).

Related documentation:

- [assistant-ui documentation](https://www.assistant-ui.com/docs)
- [AssistantChat stories](./AssistantChat.stories.tsx)

## Tools

Studio ships a registry of executable tools the model can call. Pass these through the `tools` prop. Each Studio tool exposes:

- `name` — the function name reported to the model.
- `parameters` — JSON Schema sent in the OpenAI `tools` payload.
- `execute` — async client-side function that receives parsed args and an `AbortSignal`.
- `Render` — optional component used to render the tool call in the chat surface.

### Default tools

- **`web_search`** — DuckDuckGo search via the Studio service's `POST /apis/studio/v1/web-search` endpoint. The endpoint calls DuckDuckGo's static HTML endpoint (`html.duckduckgo.com/html/`), parses results with BeautifulSoup, and returns structured `{ title, url, snippet }` items. The frontend provider is auto-installed when `web_search` is in the registry, and uses the user's bearer token from `react-oidc-context`. To plug a custom backend (e.g., a Playwright-driven crawler for resilience), override the provider:
  ```ts
  import { setWebSearchProvider } from '@nemo/common/src/components/AssistantChat';
  setWebSearchProvider({
    async search({ query, maxResults }, { signal }) {
      const response = await fetch(
        `/my-custom/search?q=${encodeURIComponent(query)}&n=${maxResults}`,
        { signal }
      );
      return response.json();
    },
  });
  ```

### Tool-call loop

Up to `MAX_TOOL_ROUNDS` (5) rounds. Each round:

1. Stream a completion. If `tool_calls` deltas arrive, accumulate them on the current assistant message as `tool-call` parts.
2. If no tool calls are present when the stream ends, finalize the assistant message and stop.
3. Otherwise execute each tool call in parallel, attaching the result (or error) to the matching `tool-call` part.
4. Re-issue the completion with the updated history (assistant message + `tool` messages) and without re-advertising executable tools, so the model produces a final user-facing response.

Cancellation propagates through to active tool executions and aborts the in-flight stream.

### Toggling tools

The composer's leading button (sliders icon) opens a popover listing every executable Studio tool in `tools`. Toggling a tool only affects this thread — state resets on `onReset`, page reload, or component remount.

## Common Patterns

- **Editing**: saving a user-message edit trims downstream messages and runs inference again from the edited prompt.
- **Regeneration**: reload removes the latest assistant response and re-runs inference with the preceding messages.
- **Stop**: cancel aborts the active request, the in-flight stream, and any running tool executions; marks the running assistant message as cancelled.
- **Reset**: reset aborts active work and clears the local thread.
- **Testing**: Storybook uses MSW handlers for streaming, indexed example responses, and a hanging stream that validates Stop behavior.

## Supported

- Text-only user prompts with Enter-to-send and Shift+Enter newlines.
- Streaming assistant responses through `useChatCompletion` with `model`, `workspace`, or explicit `baseURL`.
- Optional `PromptData` support for system prompt, temperature, and max tokens.
- Executable client-side tools via the `tools` prop — `web_search` (DuckDuckGo via the Studio service backend).
- Multi-round tool-call loop with a max-rounds cap and full cancel/stop propagation.
- Per-thread tool toggles via the composer options menu.
- User-message editing that re-runs inference from the edited prompt and drops stale downstream messages.
- Stop/cancel for an in-flight stream, regenerate for assistant responses, and reset for clearing the current thread.
- Streaming surface for assistant tool calls (tool name + accumulated args + result) with per-tool renderers and a generic fallback.
- Storybook MSW mocks for normal streaming, indexed example responses, and a hanging stream used to validate Stop behavior.

## Not Yet Supported

- File attachments and multimodal message parts.
- Persisted multi-thread history or server-backed thread management.
- Feedback/intake submission parity with the existing `Chat` component.
- Playwright-backed fallback for `web_search` (httpx → DDG static HTML ships today; a Playwright fallback is the next step if DDG starts fingerprinting plain HTTP clients).
- Persisting tool-toggle state across threads/reloads.
