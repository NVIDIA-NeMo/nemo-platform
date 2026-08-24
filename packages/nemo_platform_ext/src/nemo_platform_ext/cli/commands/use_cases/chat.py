# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""CLI commands for interactive chat."""

from __future__ import annotations

import json
import logging
import re
import select
import sys
from types import TracebackType
from typing import Annotated, Any, Callable, Iterator, Literal, Protocol, Self, TypedDict, cast

import click
import typer
class SSEDecoder:
    """Minimal SSE decoder — replaces nemo_platform._streaming.SSEDecoder."""
    def __init__(self):
        self._event = None
        self._data = []
    def decode(self, line: str):
        if not line: return
        if line.startswith("data: "): self._data.append(line[6:])
    def events(self):
        if self._data: yield {"data": "\n".join(self._data)}; self._data = []
from rich.align import Align
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from nemo_platform_ext.cli.core.api import build_kwargs, is_tty
from nemo_platform_ext.cli.core.autocomplete import autocomplete_model_entity
from nemo_platform_ext.cli.core.context import CLIContext
from nemo_platform_ext.cli.core.errors import handle_errors
from nemo_platform_ext.cli.core.help_formatter import _get_terminal_width
from nemo_platform_ext.cli.core.stdin_utils import is_stdin_available
from nemo_platform_ext.ui.prompts import is_interactive


class ChatMessage(TypedDict):
    """Type for chat messages."""

    role: Literal["system", "user", "assistant"]
    content: str


ChatOutputFormat = Literal["text", "json", "raw"]


class _StreamingResponse(Protocol):
    """Streaming response interface used by the generated SDK response wrapper."""

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None: ...

    def iter_bytes(self) -> Iterator[bytes]: ...


class _StreamingThinkingFilter:
    """Incrementally strips thinking tags while preserving visible content."""

    def __init__(self) -> None:
        self._pending = ""
        self._in_thinking = False

    def feed(self, text: str) -> str:
        """Return visible text that is safe to print immediately."""
        if not text:
            return ""

        data = self._pending + text
        self._pending = ""
        visible = ""

        while data:
            if self._in_thinking:
                close_index = data.find("</think>")
                if close_index >= 0:
                    data = data[close_index + len("</think>") :]
                    self._in_thinking = False
                    continue

                pending_length = _partial_tag_suffix_length(data, "</think>")
                self._pending = data[-pending_length:] if pending_length else ""
                break

            open_index = data.find("<think>")
            if open_index >= 0:
                chunk = data[:open_index]
                visible += chunk
                data = data[open_index + len("<think>") :]
                self._in_thinking = True
                continue

            pending_length = _partial_tag_suffix_length(data, "<think>")
            chunk = data[:-pending_length] if pending_length else data
            visible += chunk
            self._pending = data[-pending_length:] if pending_length else ""
            break

        return visible

    def finish(self) -> str:
        """Flush any buffered non-thinking text at the end of the stream."""
        if not self._pending:
            return ""

        pending = self._pending
        self._pending = ""
        if self._in_thinking:
            logging.debug("Dropping incomplete thinking content at end of streamed chat response")
            return ""

        return pending


def _partial_tag_suffix_length(text: str, tag: str) -> int:
    """Return the length of a text suffix that could start a tag."""
    max_length = min(len(text), len(tag) - 1)
    for length in range(max_length, 0, -1):
        if tag.startswith(text[-length:]):
            return length
    return 0


# Constants
USER_PANEL_WIDTH_RATIO = 0.8  # User messages take 80% width to leave right margin
ASSISTANT_PANEL_WIDTH_RATIO = 0.95  # Assistant uses more space for readability
LIVE_REFRESH_RATE = 20
ANSI_MOVE_UP_CLEAR_LINE = "\033[1A\033[2K"

# Regex patterns for thinking tag parsing
THINKING_TAG_PATTERN = r"<think>(.*?)</think>"  # Matches complete <think>...</think> pairs
THINKING_UNCLOSED_PATTERN = r"<think>(.*?)$"  # Matches unclosed <think> tag to end of string

# Create console with width limit
terminal_width = _get_terminal_width()
console = Console(width=terminal_width)


def _parse_model_and_workspace(
    model: str,
    workspace_flag: str | None,
    workspace_from_config: str | None,
) -> tuple[str, str]:
    """Parse model argument and resolve workspace for model entity routing.

    Args:
        model: Model argument, either "model-name" or "workspace/model-name"
        workspace_flag: Explicit --workspace flag value
        workspace_from_config: Workspace from client config

    Returns:
        Tuple of (workspace, model_entity_id) where model_entity_id is "workspace/model-name"

    Raises:
        click.UsageError: If workspace is specified both inline and via flag,
                          or if no workspace can be determined
    """
    inline_workspace = None
    model_name = model

    # Check for inline workspace (model entity names don't contain /)
    if "/" in model:
        inline_workspace, model_name = model.split("/", 1)

    # Validate no conflict between inline and flag
    if inline_workspace and workspace_flag:
        raise click.UsageError(
            f"Workspace specified both in model name ('{inline_workspace}') and "
            f"via --workspace flag ('{workspace_flag}'). Please use only one method."
        )

    # Resolve final workspace (flag > inline > config)
    final_workspace = workspace_flag or inline_workspace or workspace_from_config

    if not final_workspace:
        raise click.UsageError(
            "No workspace specified. Provide workspace via --workspace flag, "
            "include it in model name (workspace/model-name), or configure a default workspace."
        )

    # Return workspace and full model entity ID
    model_entity_id = f"{final_workspace}/{model_name}"
    return final_workspace, model_entity_id


def _is_interactive_chat_session() -> bool:
    """Return whether the process can safely run the Rich chat REPL."""
    return is_interactive() and is_tty()


def _resolve_chat_mode(prompt: str | None, interactive: bool) -> tuple[bool, str | None]:
    """Resolve whether chat should run once and the prompt to send."""
    can_run_interactive = _is_interactive_chat_session()

    if interactive:
        if not can_run_interactive:
            raise click.UsageError(
                "Interactive chat requires a terminal. Remove --interactive for one-shot mode or run in a TTY."
            )
        return False, prompt

    if prompt:
        return True, prompt

    stdin_prompt = _read_stdin_prompt()
    if stdin_prompt:
        return True, stdin_prompt

    return not can_run_interactive, None


def _read_stdin_prompt() -> str | None:
    """Read a prompt from stdin only when data is ready."""
    if not is_stdin_available() or not _stdin_has_data_ready():
        return None

    stdin_prompt = sys.stdin.read().strip()
    return stdin_prompt or None


def _stdin_has_data_ready() -> bool:
    """Return whether reading stdin should complete without blocking."""
    try:
        readable, _, _ = select.select([sys.stdin], [], [], 0)
    except (OSError, ValueError):
        # Some platforms cannot probe non-socket stdin. Keep piped stdin support
        # and rely on the non-TTY stream to provide data or EOF.
        return True
    return bool(readable)


def _resolve_chat_output_format(
    state: CLIContext,
    output_format: ChatOutputFormat | None,
) -> ChatOutputFormat:
    """Resolve the one-shot output format, respecting compatible global config.

    The chat command streams plain conversational text and picks its own JSON
    shape when asked, so the global non-TTY ``table -> json`` shortcut does not
    apply here — opt out of it via ``apply_non_tty_default=False``. Otherwise a
    piped or redirected ``nemo chat`` would silently switch from text to JSON
    and break shell pipelines that just want the model's reply on stdout.
    """
    if output_format is not None:
        return output_format

    configured = state.get_output_format(apply_non_tty_default=False)
    return configured if configured in ("json", "raw") else "text"


@handle_errors
def chat(
    ctx: typer.Context,
    model: Annotated[
        str,
        typer.Argument(
            help="Model entity name (from 'nemo models list') or model ID when using --provider",
            autocompletion=autocomplete_model_entity,
        ),
    ],
    prompt: Annotated[
        str | None,
        typer.Argument(
            help="Prompt for one-shot mode. Takes precedence over piped stdin.",
        ),
    ] = None,
    provider: Annotated[
        str | None,
        typer.Option(
            help="Provider name for direct provider routing (bypasses model entity routing)",
        ),
    ] = None,
    workspace: Annotated[str | None, typer.Option(help="Workspace name")] = None,
    interactive: Annotated[
        bool,
        typer.Option(
            "--interactive",
            help="Start the terminal chat UI; cannot be used with piped stdin. With PROMPT, send it first.",
            rich_help_panel="Chat Options",
        ),
    ] = False,
    output_format: Annotated[
        ChatOutputFormat | None,
        typer.Option(
            "--output-format",
            "--format",
            "-f",
            help="Output format for one-shot responses.",
            show_choices=True,
            rich_help_panel="Output Options",
        ),
    ] = None,
    temperature: Annotated[
        float | None,
        typer.Option(
            help="Sampling temperature (0.0 to 2.0)",
            rich_help_panel="Model Options",
        ),
    ] = None,
    max_tokens: Annotated[
        int | None,
        typer.Option(
            help="Maximum tokens to generate",
            rich_help_panel="Model Options",
        ),
    ] = None,
    system_message: Annotated[
        str | None,
        typer.Option(
            "--system-message",
            help="System message to set context for the conversation",
            rich_help_panel="Model Options",
        ),
    ] = None,
) -> None:
    """
    Start an interactive chat session with a model.

    By default, uses model entity routing where the model name should match
    what's shown in 'nemo models list'.

    Use --provider for direct provider routing, where the model argument is
    passed directly to the provider's API.

    Passing PROMPT sends one message and exits unless --interactive is set.
    Omitting PROMPT in a TTY starts the interactive chat UI. In non-TTY
    contexts, PROMPT may also be piped on stdin. Piped stdin is read in full
    before sending. If both PROMPT and piped stdin are provided, PROMPT takes
    precedence.

    Examples:
      nemo chat nvidia/llama-3.3-nemotron-super-49b-v1.5
      nemo chat nvidia/llama-3.3-nemotron-super-49b-v1.5 "What is machine learning?"
      nemo chat nvidia/llama-3.3-nemotron-super-49b-v1.5 "What is machine learning?" --interactive
      echo "What is machine learning?" | nemo chat nvidia/llama-3.3-nemotron-super-49b-v1.5
      nemo chat nvidia/llama-3.3-nemotron-super-49b-v1.5 "What is machine learning?" -f json
      nemo chat nvidia/llama-3.3-nemotron-super-49b-v1.5 --provider nvidia-build
    """
    state: CLIContext = ctx.obj
    run_once, effective_prompt = _resolve_chat_mode(prompt, interactive)
    if run_once and not effective_prompt:
        raise click.UsageError("One-shot chat requires a prompt. Provide PROMPT or pipe text on stdin.")
    client = state.get_client()
    chat_output_format = _resolve_chat_output_format(state, output_format) if run_once else "text"

    # Get workspace from client config if available
    try:
        workspace_from_config: str | None = client._get_workspace_path_param()
    except ValueError:
        workspace_from_config = None

    if provider:
        # Provider routing: pass model directly to the provider
        if "/" in provider:
            suggested = provider.split("/")[-1]
            raise click.UsageError(
                f"Invalid provider name '{provider}'. Provider names should not include a workspace prefix.\n"
                f"[yellow]Hint:[/] Use '--provider {suggested}' instead."
            )

        resolved_workspace = workspace or workspace_from_config

        if not resolved_workspace:
            raise click.UsageError(
                "No workspace specified. Provide workspace via --workspace flag or configure a default workspace."
            )

        def get_response(body: dict[str, Any]) -> _StreamingResponse:
            return client.inference.gateway.provider.with_streaming_response.post(
                trailing_uri="v1/chat/completions",
                workspace=resolved_workspace,
                name=provider,
                body=body,
            )

        model_for_body = model
        display_info = {"Provider": f"{resolved_workspace}/{provider}", "Model": model}
    else:
        # Model entity routing (default): use OpenAI-compatible gateway
        resolved_workspace, model_entity_id = _parse_model_and_workspace(model, workspace, workspace_from_config)

        def get_response(body: dict[str, Any]) -> _StreamingResponse:
            return client.inference.gateway.openai.with_streaming_response.post(
                trailing_uri="v1/chat/completions",
                workspace=resolved_workspace,
                body=body,
            )

        model_for_body = model_entity_id
        display_info = {"Model": model_for_body}

    if run_once:
        _run_one_shot(
            user_message=cast(str, effective_prompt),  # UsageError above guarantees non-None.
            model_for_body=model_for_body,
            get_response_func=get_response,
            temperature=temperature,
            max_tokens=max_tokens,
            system_message=system_message,
            output_format=chat_output_format,
        )
    else:
        _run_chat_session(
            model_for_body=model_for_body,
            get_response_func=get_response,
            temperature=temperature,
            max_tokens=max_tokens,
            system_message=system_message,
            user_message=effective_prompt,
            display_info=display_info,
        )


def _run_one_shot(
    user_message: str,
    model_for_body: str,
    get_response_func: Callable[[dict[str, Any]], _StreamingResponse],
    temperature: float | None,
    max_tokens: int | None,
    system_message: str | None,
    output_format: ChatOutputFormat,
) -> None:
    """Send one chat message and emit the response in the requested format."""
    history: list[ChatMessage] = []
    if system_message:
        history.append({"role": "system", "content": system_message})

    if output_format == "text":
        _stream_one_shot_text(user_message, history, model_for_body, get_response_func, temperature, max_tokens)
    else:
        result = _process_one_shot_message(
            user_message, history, model_for_body, get_response_func, temperature, max_tokens
        )
        _print_one_shot_response(result, model_for_body, output_format)


def _run_chat_session(
    model_for_body: str,
    get_response_func: Callable[[dict[str, Any]], _StreamingResponse],
    temperature: float | None,
    max_tokens: int | None,
    system_message: str | None,
    user_message: str | None,
    display_info: dict[str, str],
) -> None:
    """Run an interactive chat session."""
    root_logger = logging.getLogger()
    initial_level = root_logger.level
    try:
        # Disable logging during the chat session.
        root_logger.setLevel(logging.CRITICAL)

        history: list[ChatMessage] = []
        if system_message:
            history.append({"role": "system", "content": system_message})

        _print_welcome_header(display_info, temperature, max_tokens, system_message)

        last_thinking_content = ""
        thinking_displayed = False

        # Handle initial user message if provided
        if user_message:
            result = _process_user_message(
                user_message,
                history,
                model_for_body,
                get_response_func,
                temperature,
                max_tokens,
            )
            if result:
                _, last_thinking_content = result
                thinking_displayed = False

        while True:
            try:
                console.print()
                user_input = Prompt.ask("[bold cyan]You[/bold cyan]", console=console).strip()

                if not user_input:
                    continue

                if user_input.startswith("/"):
                    _clear_prompt_line()
                    new_thinking_state = _handle_special_command(user_input, last_thinking_content, thinking_displayed)
                    if new_thinking_state is not None:
                        thinking_displayed = new_thinking_state
                    continue

                _clear_prompt_line()

                result = _process_user_message(
                    user_input,
                    history,
                    model_for_body,
                    get_response_func,
                    temperature,
                    max_tokens,
                )
                if result:
                    _, last_thinking_content = result
                    thinking_displayed = False

            except (KeyboardInterrupt, EOFError):
                _exit_gracefully()

    finally:
        # Restore logging level
        root_logger.setLevel(initial_level)


def _create_one_shot_response(
    user_input: str,
    history: list[ChatMessage],
    model_for_body: str,
    get_response_func: Callable[[dict[str, Any]], _StreamingResponse],
    temperature: float | None,
    max_tokens: int | None,
) -> _StreamingResponse:
    """Build and send one chat request."""
    history.append({"role": "user", "content": user_input})
    body = build_kwargs(
        model=model_for_body,
        messages=history,
        stream=True,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    return get_response_func(body)


def _process_one_shot_message(
    user_input: str,
    history: list[ChatMessage],
    model_for_body: str,
    get_response_func: Callable[[dict[str, Any]], _StreamingResponse],
    temperature: float | None,
    max_tokens: int | None,
) -> dict[str, Any]:
    """Send one chat message and collect the streamed response without Rich UI."""
    response = _create_one_shot_response(
        user_input, history, model_for_body, get_response_func, temperature, max_tokens
    )

    raw_message, usage = _collect_stream_response(response)
    thinking_content, regular_content = _parse_thinking(raw_message)
    return {
        "content": regular_content,
        "thinking": thinking_content,
        "raw": raw_message,
        "usage": usage,
    }


def _iter_stream_deltas(response: _StreamingResponse) -> Iterator[dict[str, Any]]:
    """Yield parsed OpenAI-compatible streaming delta payloads."""
    with response as stream:
        for event in SSEDecoder().iter_bytes(stream.iter_bytes()):
            if event.event == "error":
                raise click.ClickException(_format_streaming_error(stream, event.data))
            if event.event is not None:
                # Match the Stainless Stream behavior: OpenAI chunks are
                # carried by unnamed data events; named non-error events are skipped.
                continue
            if not event.data:
                continue
            if event.data.startswith("[DONE]"):
                break

            try:
                yield json.loads(event.data)
            except json.JSONDecodeError:
                logging.debug(f"Failed to parse JSON stream event: {event.data}")


def _format_streaming_error(response: _StreamingResponse, data: str) -> str:
    """Build a helpful message for an SSE error frame."""
    if data:
        return f"Streaming chat request failed: {data}"

    status_code = _stream_status_code(response)
    if status_code is not None:
        return f"Streaming chat request failed (HTTP {status_code})"
    return "Streaming chat request failed"


def _stream_status_code(response: _StreamingResponse) -> int | None:
    """Return the HTTP status code from SDK streaming wrappers when available."""
    status_code = getattr(response, "status_code", None)
    return status_code if isinstance(status_code, int) else None


def _stream_delta_content(delta: dict[str, Any]) -> str:
    """Extract text content from a streaming delta payload."""
    choices = delta.get("choices", [])
    if not choices or not isinstance(choices[0], dict):
        return ""

    chunk_delta = choices[0].get("delta", {})
    if not isinstance(chunk_delta, dict):
        return ""

    content = chunk_delta.get("content")
    return content if isinstance(content, str) else ""


def _collect_stream_response(response: _StreamingResponse) -> tuple[str, Any | None]:
    """Collect content chunks from an OpenAI-compatible streaming response."""
    raw_message = ""
    usage = None

    for delta in _iter_stream_deltas(response):
        if delta.get("usage") is not None:
            usage = delta["usage"]

        content = _stream_delta_content(delta)
        if content:
            raw_message += content

    return raw_message, usage


def _stream_one_shot_text(
    user_input: str,
    history: list[ChatMessage],
    model_for_body: str,
    get_response_func: Callable[[dict[str, Any]], _StreamingResponse],
    temperature: float | None,
    max_tokens: int | None,
) -> None:
    """Send one chat message and stream plain text output."""
    response = _create_one_shot_response(
        user_input, history, model_for_body, get_response_func, temperature, max_tokens
    )
    _stream_text_response(response)


def _stream_text_response(response: _StreamingResponse) -> None:
    """Stream text chunks to stdout while hiding thinking markup."""
    thinking_filter = _StreamingThinkingFilter()

    for delta in _iter_stream_deltas(response):
        content = _stream_delta_content(delta)
        if not content:
            continue

        visible_content = thinking_filter.feed(content)
        if visible_content:
            typer.echo(visible_content, nl=False)
            sys.stdout.flush()

    trailing_content = thinking_filter.finish()
    if trailing_content:
        typer.echo(trailing_content, nl=False)
        sys.stdout.flush()
    typer.echo()


def _print_one_shot_response(
    result: dict[str, Any], model_for_body: str, output_format: Literal["json", "raw"]
) -> None:
    """Print a one-shot response in a script-friendly format."""
    if output_format == "json":
        payload = {
            "content": result["content"],
            "thinking": result["thinking"],
            "model": model_for_body,
            "usage": result["usage"],
        }
        typer.echo(json.dumps(payload, ensure_ascii=False))
        return

    typer.echo(result["raw"])


def _process_user_message(
    user_input: str,
    history: list[ChatMessage],
    model_for_body: str,
    get_response_func: Callable[[dict[str, Any]], _StreamingResponse],
    temperature: float | None,
    max_tokens: int | None,
) -> tuple[str, str] | None:
    """Display user message, send to API, stream response.

    Args:
        user_input: The user's message
        history: Chat history (will be modified in place)
        model_for_body: Model identifier for the request body
        get_response_func: Function to get streaming response
        temperature: Sampling temperature
        max_tokens: Max tokens to generate

    Returns:
        Tuple of (assistant_message, thinking_content) or None if empty response
    """
    # Display user message panel
    panel_width = int(terminal_width * USER_PANEL_WIDTH_RATIO)
    user_panel = Panel(
        user_input,
        title="[bold cyan]You[/bold cyan]",
        title_align="right",
        border_style="cyan",
        padding=(0, 1),
        width=panel_width,
    )
    console.print(Align.right(user_panel))

    # Add to history
    history.append({"role": "user", "content": user_input})

    # Build request body
    body = build_kwargs(
        model=model_for_body,
        messages=history,
        stream=True,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    # Make API call
    response = get_response_func(body)

    # Stream response
    assistant_message, thinking_content = _stream_response(response)

    if assistant_message:
        history.append({"role": "assistant", "content": assistant_message})
        return assistant_message, thinking_content
    else:
        logging.warning("Received empty response from API")
        console.print(Panel.fit("⚠ Received empty response from model", border_style="yellow", padding=(0, 1)))
        return None


def _clear_prompt_line() -> None:
    """Move cursor up one line and clear it."""
    console.file.write(ANSI_MOVE_UP_CLEAR_LINE)
    console.file.flush()


def _exit_gracefully() -> None:
    """Exit the chat session gracefully."""
    console.print("\n")
    console.print(Panel.fit("[bold]Chat session ended[/bold]", border_style="dim", padding=(0, 2)))
    sys.exit(0)


def _handle_special_command(command: str, last_thinking: str, thinking_displayed: bool) -> bool | None:
    """
    Handle special commands like /thinking, and /help.

    Returns:
        New thinking_displayed value for /thinking, None otherwise.
    """
    if command in {"/thinking", "/t"}:
        if not last_thinking:
            console.print(Panel.fit("No reasoning content in the last response", border_style="yellow", padding=(0, 1)))
            return None

        if thinking_displayed:
            console.print(Panel.fit("Reasoning already displayed above", border_style="yellow dim", padding=(0, 1)))
            return True  # Keep the state as displayed

        # Show the thinking content in an expanded panel
        thinking_panel = Panel(
            Markdown(last_thinking),
            title="[bold yellow]💭 Reasoning[/bold yellow]",
            title_align="left",
            border_style="yellow dim",
            padding=(0, 1),
        )
        console.print(thinking_panel)
        return True  # Indicate thinking was shown

    if command in {"/help", "/h"}:
        console.print(
            Panel(
                "[cyan]/thinking[/cyan] - Show/hide model reasoning from last response\n"
                "[cyan]/help[/cyan] - Show this help message\n"
                "[cyan]Ctrl+C[/cyan] - Exit the chat",
                title="[bold]Available Commands[/bold]",
                border_style="blue",
                padding=(0, 1),
            )
        )
        return None

    console.print(
        Panel.fit(
            f"Unknown command: {command}. Type /help for available commands.", border_style="yellow", padding=(0, 1)
        )
    )
    return None


def _print_welcome_header(
    display_info: dict[str, str],
    temperature: float | None,
    max_tokens: int | None,
    system_message: str | None,
) -> None:
    """Print a styled welcome header for the chat session."""
    config_lines = [f"[cyan]{key}:[/cyan] {value}" for key, value in display_info.items()]

    if temperature is not None:
        config_lines.append(f"[cyan]Temperature:[/cyan] {temperature}")
    if max_tokens is not None:
        config_lines.append(f"[cyan]Max Tokens:[/cyan] {max_tokens}")
    if system_message:
        config_lines.append(f"[cyan]System:[/cyan] {system_message}")

    config_text = "\n".join(config_lines)

    welcome_panel = Panel(
        config_text,
        title="[bold green]🤖 NeMo Platform Chat Session[/bold green]",
        subtitle="Press Ctrl+C to exit",
        border_style="green",
        padding=(1, 2),
    )

    console.print(welcome_panel)


def _is_inside_thinking_tag(message: str) -> bool:
    """Check if we're currently inside an unclosed <think> tag."""
    open_think_count = message.count("<think>")
    close_think_count = message.count("</think>")
    return open_think_count > close_think_count


def _create_thinking_preview(message: str) -> str:
    """Create a preview of the current thinking content.

    Args:
        message: Full message text containing unclosed <think> tag

    Returns:
        Formatted preview text for display
    """
    # Extract current thinking content (inside unclosed <think> tag)
    thinking_match = re.search(THINKING_UNCLOSED_PATTERN, message, re.DOTALL)
    current_thinking = thinking_match.group(1).strip() if thinking_match else ""

    if current_thinking:
        # Get last 150 characters, or last 2-3 lines (whichever is shorter)
        lines = current_thinking.split("\n")
        preview = "\n".join(lines[-3:]) if len(lines) > 1 else current_thinking
        if len(preview) > 150:
            preview = "..." + preview[-150:]
        return f"[dim italic]{preview}[/dim italic]"
    else:
        return "[dim]💭 Thinking...[/dim]"


def _extract_display_text(message: str, inside_thinking: bool) -> str:
    """Extract content outside of think tags for display.

    Args:
        message: Full message text
        inside_thinking: Whether we're currently inside a thinking tag

    Returns:
        Text to display (with thinking tags removed)
    """
    # Remove complete <think>...</think> pairs
    display_text = re.sub(THINKING_TAG_PATTERN, "", message, flags=re.DOTALL)
    # Remove any unclosed <think> tag and everything after it
    if inside_thinking:
        display_text = re.sub(THINKING_UNCLOSED_PATTERN, "", display_text, flags=re.DOTALL)
    return display_text.strip()


def _stream_response(response: _StreamingResponse) -> tuple[str, str]:
    """
    Stream and display the assistant's response with live updates in a panel.

    Parses out <think> tags and shows thinking separately.

    Args:
        response: Streaming response from the API (StreamingResponse from nemo_platform SDK)

    Returns:
        Tuple of (complete assistant message, thinking content)
    """
    full_message = ""
    panel_width = int(terminal_width * ASSISTANT_PANEL_WIDTH_RATIO)

    # TODO: this doesn't work well with very long outputs
    with Live("", console=console, refresh_per_second=LIVE_REFRESH_RATE) as live:
        for delta in _iter_stream_deltas(response):
            content = _stream_delta_content(delta)
            if not content:
                continue

            full_message += content

            # Check if we're currently inside a <think> tag
            inside_thinking = _is_inside_thinking_tag(full_message)

            # Extract content outside of think tags for display
            display_text = _extract_display_text(full_message, inside_thinking)

            # Show thinking indicator if model is currently reasoning
            if inside_thinking and not display_text:
                # Show preview of the thinking content
                thinking_preview = _create_thinking_preview(full_message)
                thinking_indicator = Panel(
                    thinking_preview,
                    title="[bold yellow dim]💭 Reasoning[/bold yellow dim]",
                    title_align="left",
                    border_style="yellow dim",
                    padding=(0, 1),
                    width=panel_width,
                )
                live.update(Align.left(thinking_indicator))
            else:
                # Show the main content (regular response)
                response_panel = Panel(
                    Markdown(display_text) if display_text else "",
                    title="[bold magenta]Assistant[/bold magenta]",
                    title_align="left",
                    border_style="magenta",
                    padding=(0, 1),
                    width=panel_width,
                )
                live.update(Align.left(response_panel))

    # Final parse to extract thinking
    thinking_content, regular_content = _parse_thinking(full_message)

    # Show collapsed thinking hint after streaming if there's thinking content
    if thinking_content:
        console.print("[dim]💭 Reasoning available! Type [dim cyan]/thinking[/] to view it[/]", markup=True)

    return regular_content or full_message, thinking_content


def _parse_thinking(text: str) -> tuple[str, str]:
    """
    Parse out <think> tags from text.

    Returns:
        Tuple of (thinking_content, regular_content)
    """
    # Match <think>...</think> tags (non-greedy)
    matches = re.findall(THINKING_TAG_PATTERN, text, re.DOTALL)
    regular_content = re.sub(THINKING_TAG_PATTERN, "", text, flags=re.DOTALL)
    thinking_parts = list(matches)

    unclosed_match = re.search(THINKING_UNCLOSED_PATTERN, regular_content, re.DOTALL)
    if unclosed_match:
        thinking_parts.append(unclosed_match.group(1))
        regular_content = re.sub(THINKING_UNCLOSED_PATTERN, "", regular_content, flags=re.DOTALL)

    if thinking_parts:
        return "\n\n".join(thinking_parts), regular_content.strip()

    return "", text
