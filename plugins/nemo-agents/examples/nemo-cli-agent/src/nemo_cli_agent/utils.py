# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Generic NAT-compatible LangGraph wrapper.

Why this exists
---------------
``nvidia-nat-langchain``'s built-in ``langgraph_wrapper`` is a generic adapter
that wraps any compiled LangGraph as a NAT ``Function``. In NAT 1.6.0 it has
two limitations that block our use case end-to-end:

1. **Input schema is too narrow.** ``LanggraphWrapperInput`` declares
   ``messages: list[...] | PromptValue`` as required. ``nvidia-nat-eval``'s
   remote workflow client (used when ``nemo agents evaluate run`` is invoked
   with ``--agent <name>``) POSTs ``{"input_message": "..."}`` to the
   ``/generate/full`` route. FastAPI builds a ``TypeAdapter`` from
   ``LanggraphWrapperInput`` per route, validates the body against it, and
   rejects with **422 Unprocessable Entity** before the agent ever runs.

2. **Stream output schema is too narrow.** ``LanggraphWrapperOutput.messages``
   is required, and the wrapper validates *every* per-node state delta that
   ``LangGraph.astream()`` yields against it. Deep-agent graphs (and any graph
   whose state schema is wider than ``{messages: [...]}``) emit deltas like
   ``{"skills_metadata": []}`` that don't carry ``messages``; the resulting
   ``ValidationError`` aborts the whole stream before the final,
   ``messages``-bearing chunk arrives, surfacing as a 500 to the caller.

We can't fix (1) by monkey-patching ``cls.__pydantic_validator__`` because
FastAPI uses ``TypeAdapter`` per param, which builds its own validator from
the model's frozen core schema and bypasses ``cls.__pydantic_validator__``
entirely. The only reliable in-process fix is to register a *different*
NAT workflow type with permissive schemas. That's this module.

How it works
------------
* ``NatCompatibleLangGraphWrapperConfig`` registers
  ``_type: nat_compatible_langgraph_wrapper`` with NAT via ``register_function``
  at import time.
* ``NatCompatibleLangGraphWrapperInput`` accepts **either** ``messages`` (native LangGraph
  state shape) **or** ``input_message`` (the eval client's shape) and
  normalizes the latter to a single ``user`` message via a
  ``model_validator(mode="after")`` that participates in the Pydantic core
  schema (so it survives FastAPI's TypeAdapter path).
* ``NatCompatibleLangGraphWrapperOutput.messages`` defaults to an empty list, so streaming
  chunks without ``messages`` validate cleanly.
* ``NatCompatibleLangGraphWrapperFunction`` is a ``Function`` parametrized over those
  schemas. ``_ainvoke`` and ``_astream`` build a ``{"messages": [...]}`` state
  for the graph, run it, and coerce each output (or chunk) into
  ``NatCompatibleLangGraphWrapperOutput`` via ``_parse``.
* ``_parse`` extracts ``messages`` from the outer dict, from a single-keyed
  node-update wrapper, or — if neither shape applies — yields an empty
  placeholder. This is the key behavioral difference from
  ``LanggraphWrapperFunction._parse_stream_output``: we never raise on a
  state delta that lacks ``messages``.
* The graph itself comes from the ``graph`` factory path configured in YAML.

Use it via ``_type: nat_compatible_langgraph_wrapper`` and a ``graph`` field in
workflow YAML. Once the upstream NAT limitations are fixed, users should be
able to revert to NAT's stock ``langgraph_wrapper``.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncGenerator
from contextlib import contextmanager
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, MessageLikeRepresentation, ToolMessage
from langchain_core.messages.utils import convert_to_messages
from langchain_core.prompt_values import PromptValue
from langchain_core.runnables import RunnableConfig
from nat.builder.builder import Builder
from nat.builder.framework_enum import LLMFrameworkEnum
from nat.builder.function import Function
from nat.cli.register_workflow import register_function
from nat.data_models.api_server import ChatRequest, ChatResponse, ChatResponseChunk, Usage
from nat.data_models.function import FunctionBaseConfig
from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

logger = logging.getLogger(__name__)
console = Console()

os.environ.setdefault("NAT_TELEMETRY_ENABLED", "false")
# TODO: This is a hard local-PoC unblocker. Replace it with a scoped, supported
# NAT/local invoke quiet mode once the wrapper behavior is proven.
logging.disable(logging.CRITICAL)

_QUIET_LOGGERS = (
    "httpx",
    "nat.builder.intermediate_step_manager",
    "nat.observability",
    "nat.runtime.session",
)

_EMPTY_FINAL_CONTINUATION_PROMPT = """Your previous assistant response was empty, so the task is not complete.

Continue from the current tool history and finish every remaining requirement in the original user instruction. Do not stop after partial progress. Before returning, verify the requested final state with tools when possible. If every requirement is already complete, respond with a concise completion summary."""


@contextmanager
def _quiet_local_run_logs():
    previous = {name: logging.getLogger(name).level for name in _QUIET_LOGGERS}
    try:
        for name in _QUIET_LOGGERS:
            logging.getLogger(name).setLevel(logging.ERROR)
        yield
    finally:
        for name, level in previous.items():
            logging.getLogger(name).setLevel(level)


def _final_message_text(output: Any) -> str:
    if not isinstance(output, dict):
        return ""
    messages = output.get("messages")
    if not isinstance(messages, list) or not messages:
        return ""
    last = messages[-1]
    if isinstance(last, BaseMessage):
        return last.text
    if isinstance(last, dict):
        content = last.get("content", "")
        return content if isinstance(content, str) else ""
    return ""


def _extract_messages(output: Any) -> list[Any]:
    if not isinstance(output, dict):
        return []
    messages = output.get("messages")
    if isinstance(messages, list):
        return messages
    for inner in output.values():
        if isinstance(inner, dict) and isinstance(inner.get("messages"), list):
            return inner["messages"]
    return []


def _message_id(message: Any, fallback: str) -> str:
    if isinstance(message, BaseMessage) and message.id:
        return message.id
    if isinstance(message, dict) and isinstance(message.get("id"), str):
        return message["id"]
    return fallback


def _message_text(message: Any) -> str:
    if isinstance(message, BaseMessage):
        return message.text
    if isinstance(message, dict):
        content = message.get("content", "")
        return content if isinstance(content, str) else ""
    return ""


def _tool_calls(message: Any) -> list[dict[str, Any]]:
    if isinstance(message, AIMessage):
        return list(message.tool_calls or [])
    if not isinstance(message, dict):
        return []
    raw_calls = message.get("tool_calls") or message.get("additional_kwargs", {}).get("tool_calls")
    return raw_calls if isinstance(raw_calls, list) else []


def _parse_tool_args(call: dict[str, Any]) -> Any:
    args = call.get("args") or call.get("function", {}).get("arguments") or ""
    if isinstance(args, str):
        try:
            return json.loads(args)
        except json.JSONDecodeError:
            return args
    return args


def _skill_read_target(call: dict[str, Any]) -> tuple[str, str] | None:
    """Return ``(skill_name, path)`` when a tool call reads a ``SKILL.md`` file.

    The DeepAgents ``SkillsMiddleware`` injects skill paths into the system
    prompt and the agent picks them up through the built-in ``read_file``
    tool; matching here lets us render those reads as proof the agent is
    actually consulting the installed skills.
    """
    name = call.get("name") or call.get("function", {}).get("name")
    if name not in {"read_file", "read"}:
        return None
    parsed = _parse_tool_args(call)
    if not isinstance(parsed, dict):
        return None
    path = parsed.get("path") or parsed.get("file_path")
    if not isinstance(path, str) or not path.endswith("SKILL.md"):
        return None
    parent = path.rsplit("/", 2)
    skill_name = parent[-2] if len(parent) >= 2 else path
    return skill_name, path


def _file_read_target(call: dict[str, Any]) -> str | None:
    """Return the target path when a tool call reads a local file."""
    name = call.get("name") or call.get("function", {}).get("name")
    if name not in {"read_file", "read"}:
        return None
    parsed = _parse_tool_args(call)
    if not isinstance(parsed, dict):
        return None
    path = parsed.get("path") or parsed.get("file_path")
    return path if isinstance(path, str) else None


def _tool_call_display(call: dict[str, Any]) -> str:
    name = call.get("name") or call.get("function", {}).get("name") or "tool"
    args = call.get("args") or call.get("function", {}).get("arguments") or ""
    if name == "nemo_cli":
        parsed_args = _parse_tool_args(call)
        if isinstance(parsed_args, dict) and isinstance(parsed_args.get("command"), str):
            return parsed_args["command"]
    return f"{name} {args}".strip()


def _tool_result(message: Any) -> tuple[str, str] | None:
    if isinstance(message, ToolMessage):
        return message.tool_call_id or _message_id(message, "tool"), message.text
    if not isinstance(message, dict):
        return None
    role = message.get("role") or message.get("type")
    if role != "tool":
        return None
    tool_call_id = message.get("tool_call_id") or message.get("id") or "tool"
    content = message.get("content", "")
    return str(tool_call_id), content if isinstance(content, str) else str(content)


def _print_line(text: str) -> None:
    if text:
        console.print(text)


def _print_tool_call(command: str) -> None:
    console.print()
    console.print(Text(f"$ {command}", style="bold cyan"))


def _print_skill_read(skill_name: str, path: str) -> None:
    # The full path is intentionally elided; it's noisy and the skill
    # name alone is enough to verify the agent consulted the right one.
    del path
    console.print()
    console.print(Text(f"read skill: {skill_name}", style="bold magenta"))


def _print_file_read(path: str) -> None:
    console.print()
    console.print(Text(f"read file: {path}", style="bold magenta"))


def _print_tool_output(output: str) -> None:
    console.print(Panel(output or "(no output)", title="output", border_style="cyan", expand=False))


def _print_final_answer(text: str) -> None:
    console.print()
    console.print(text)


def list_installed_skills(skills_dir: Path) -> list[str]:
    """Return sorted skill folder names found under ``skills_dir``.

    The folders are the units the DeepAgents ``SkillsMiddleware``
    enumerates, so listing them gives a reliable preview of what will
    be exposed to the model without having to parse every ``SKILL.md``
    ourselves.
    """
    if not skills_dir.is_dir():
        return []
    return sorted(p.name for p in skills_dir.iterdir() if (p / "SKILL.md").is_file())


def print_loaded_skills(skills_dir: Path) -> None:
    """Print a one-line summary of the skills installed in ``skills_dir``."""
    skills = list_installed_skills(skills_dir)
    if not skills:
        print(f"No skills found under {skills_dir}.", flush=True)
        return
    preview = ", ".join(skills[:6])
    suffix = f", ... (+{len(skills) - 6} more)" if len(skills) > 6 else ""
    print(f"Loaded {len(skills)} skills from {skills_dir}: {preview}{suffix}", flush=True)


class _StreamSafeGraph:
    """Wrap a compiled graph so ``astream()`` yields final state for NAT parsing.

    Some graph implementations emit intermediate stream chunks that do not carry
    ``messages``. This adapter delegates streaming to ``ainvoke`` so the wrapper
    sees the single fully resolved state.
    """

    def __init__(self, graph: Any) -> None:
        self._graph = graph
        self._printed_calls: set[str] = set()
        self._printed_results: set[str] = set()
        self._printed_result_texts: set[str] = set()
        self._printed_messages: set[str] = set()
        self._suppressed_output_call_ids: set[str] = set()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._graph, name)

    def _print_chunk_activity(self, chunk: Any) -> None:
        for index, message in enumerate(_extract_messages(chunk)):
            if isinstance(message, HumanMessage) or (isinstance(message, dict) and message.get("role") == "user"):
                continue
            message_key = _message_id(message, f"message-{index}")
            for call_index, call in enumerate(_tool_calls(message)):
                call_id = str(call.get("id") or f"{message_key}-tool-{call_index}")
                if call_id in self._printed_calls:
                    continue
                self._printed_calls.add(call_id)
                skill_target = _skill_read_target(call)
                if skill_target is not None:
                    self._suppressed_output_call_ids.add(call_id)
                    _print_skill_read(*skill_target)
                else:
                    file_read_target = _file_read_target(call)
                    if file_read_target is not None:
                        self._suppressed_output_call_ids.add(call_id)
                        _print_file_read(file_read_target)
                    else:
                        _print_tool_call(_tool_call_display(call))

            tool_result = _tool_result(message)
            if tool_result is not None:
                result_id, content = tool_result
                stripped_content = content.strip()
                if result_id not in self._printed_results:
                    self._printed_results.add(result_id)
                    if stripped_content:
                        self._printed_result_texts.add(stripped_content)
                    # File reads can return thousands of lines; the concise
                    # ``read ...`` line above is the verifiable evidence that
                    # the agent fetched the file, so skip the content panel.
                    if result_id not in self._suppressed_output_call_ids:
                        _print_tool_output(stripped_content)
                continue

            text = _message_text(message).strip()
            if (
                text
                and text not in self._printed_result_texts
                and not _tool_calls(message)
                and message_key not in self._printed_messages
            ):
                self._printed_messages.add(message_key)
                _print_final_answer(text)

    async def ainvoke(self, input_data: Any, config: RunnableConfig | None = None, **kwargs: Any) -> Any:
        latest: Any = None
        stream_kwargs = dict(kwargs)
        stream_kwargs.setdefault("stream_mode", "values")
        with _quiet_local_run_logs():
            async for chunk in self._graph.astream(input_data, config=config, **stream_kwargs):
                latest = chunk
                self._print_chunk_activity(chunk)
        if latest is not None:
            return latest
        with _quiet_local_run_logs():
            result = await self._graph.ainvoke(input_data, config=config, **kwargs)
        self._print_chunk_activity(result)
        return result

    async def astream(self, input_data: Any, config: RunnableConfig | None = None, **kwargs: Any):
        stream_kwargs = dict(kwargs)
        stream_kwargs.setdefault("stream_mode", "values")
        with _quiet_local_run_logs():
            async for chunk in self._graph.astream(input_data, config=config, **stream_kwargs):
                self._print_chunk_activity(chunk)
                yield chunk

    async def astream_events(self, *args: Any, **kwargs: Any):
        with _quiet_local_run_logs():
            async for event in self._graph.astream_events(*args, **kwargs):
                yield event


def _attach_langchain_profiler(graph: Any) -> Any:
    """Attach NAT's LangChain callback handler to graph invocations."""
    from nat.plugins.langchain.callback_handler import LangchainProfilerHandler

    original_ainvoke = graph.ainvoke
    original_astream = graph.astream

    def _merge(config: RunnableConfig | None) -> RunnableConfig:
        cfg: dict[str, Any] = {}
        if config is not None:
            for key, value in config.items():
                cfg[key] = value
        raw_callbacks = cfg.get("callbacks")
        callbacks = list(raw_callbacks) if isinstance(raw_callbacks, list) else []
        if raw_callbacks is not None and not isinstance(raw_callbacks, list):
            callbacks.append(raw_callbacks)
        callbacks.append(LangchainProfilerHandler())
        cfg["callbacks"] = callbacks
        return cast(RunnableConfig, cfg)

    async def ainvoke(input_data: Any, config: RunnableConfig | None = None, **kwargs: Any):
        return await original_ainvoke(input_data, config=_merge(config), **kwargs)

    async def astream(input_data: Any, config: RunnableConfig | None = None, **kwargs: Any):
        async for chunk in original_astream(input_data, config=_merge(config), **kwargs):
            yield chunk

    graph.ainvoke = ainvoke
    graph.astream = astream
    return graph


def _prepare_graph_for_nat(graph: Any) -> Any:
    return _StreamSafeGraph(_attach_langchain_profiler(graph))


class NatCompatibleLangGraphWrapperConfig(FunctionBaseConfig, name="nat_compatible_langgraph_wrapper"):
    """Configuration for a NAT-compatible LangGraph workflow.

    The ``graph`` field points to a callable that returns the compiled graph.
    The callable is invoked with ``RunnableConfig()`` for compatibility with
    existing graph factories.

        workflow:
          _type: nat_compatible_langgraph_wrapper
          graph: package.module:create_graph
          description: Agent description
    """

    model_config = ConfigDict(extra="forbid")

    graph: str
    description: str = ""


class NatCompatibleLangGraphWrapperInput(BaseModel):
    """Input schema accepted by the wrapper's ``/generate*`` routes.

    Accepts either:

    * ``{"messages": [...]}`` — native LangGraph state shape, used by chat
      clients (``nemo agents invoke``, the Studio UI, direct ``curl``).
    * ``{"input_message": "..."}`` — the shape that ``nvidia-nat-eval``'s
      ``remote_workflow.py`` POSTs to ``/generate/full`` when running an
      eval with ``--endpoint`` (i.e. ``nemo agents evaluate run --agent``).

    The ``model_validator`` below normalizes the second form to the first
    so the rest of the pipeline only ever sees ``messages``. Because the
    validator is declared on the class, it's part of the Pydantic core
    schema and survives FastAPI's per-route ``TypeAdapter`` path —
    something a runtime monkey-patch on ``__pydantic_validator__`` would
    not achieve.

    ``extra="allow"`` so callers (or NAT itself) can attach unrelated
    metadata fields without rejection.
    """

    model_config = ConfigDict(extra="allow")

    messages: list[MessageLikeRepresentation] | PromptValue | None = None
    input_message: str | None = None

    @model_validator(mode="after")
    def _ensure_messages(self) -> "NatCompatibleLangGraphWrapperInput":
        if self.messages is not None:
            return self
        if self.input_message is not None:
            self.messages = [{"role": "user", "content": self.input_message}]
            return self
        raise ValueError("Either 'messages' or 'input_message' is required")


class NatCompatibleLangGraphWrapperOutput(BaseModel):
    """Output schema for chunks and final results.

    ``messages`` defaults to an empty list (vs. required in
    ``LanggraphWrapperOutput``) because LangGraph's per-node state deltas
    aren't guaranteed to include it — deep agents emit chunks like
    ``{"skills_metadata": []}`` that contain no messages at all, and we
    don't want those to crash the stream. Consumers that need the final
    answer keep accumulating from the last non-empty chunk; the chunk
    that emits the assistant's reply will populate ``messages``
    naturally.

    The ``value`` computed field exposes the last message's text directly
    so ``nvidia-nat-eval``'s ``remote_workflow.py`` can consume it. That
    client extracts the answer via ``chunk_data.get("value")`` from each
    streamed ``data:`` line; without this field every line would parse as
    ``{"messages": [...]}`` only and the eval would record an empty answer
    (and therefore a 0 score) regardless of the agent's actual reply.
    Empty / non-list ``messages`` produce ``value == ""``, which is falsy
    on the eval client side so it won't clobber a previously captured
    non-empty answer.

    ``extra="allow"`` lets the rest of the deep-agent state ride along
    in the response without being silently dropped.
    """

    model_config = ConfigDict(extra="allow")

    messages: list[BaseMessage] = Field(default_factory=list)

    @computed_field
    @property
    def value(self) -> str:
        # We use ``model_construct`` in ``_parse`` to skip validation on
        # streaming chunks (so graph state deltas don't error out),
        # which means ``self.messages`` may be a ``list[dict]`` (raw graph
        # output) or even a non-list (e.g. a langgraph add-messages
        # operator wrapper like ``{"value": [...]}``) instead of the
        # declared ``list[BaseMessage]``. Handle each shape explicitly.
        msgs = self.messages
        if not isinstance(msgs, list) or not msgs:
            return ""
        last = msgs[-1]
        if isinstance(last, BaseMessage):
            return last.text
        if isinstance(last, dict):
            content = last.get("content", "")
            return content if isinstance(content, str) else ""
        return ""


class NatCompatibleLangGraphWrapperFunction(
    Function[
        NatCompatibleLangGraphWrapperInput,
        NatCompatibleLangGraphWrapperOutput,
        NatCompatibleLangGraphWrapperOutput,
    ]
):
    """NAT ``Function`` wrapping a compiled LangGraph.

    Behavior mirrors ``LanggraphWrapperFunction`` (so the same converters
    work for both the chat-completions route and the raw generate routes),
    with two differences:

    * **Input normalization** happens via ``NatCompatibleLangGraphWrapperInput``'s
      validator, before this class is reached.
    * **Stream chunks** that lack ``messages`` are coerced to an empty
      output instead of raising — see :meth:`_parse`.
    """

    def __init__(self, *, config: NatCompatibleLangGraphWrapperConfig, graph: Any) -> None:
        super().__init__(
            config=config,
            description=config.description,
            converters=[
                NatCompatibleLangGraphWrapperFunction.convert_to_str,
                NatCompatibleLangGraphWrapperFunction.convert_chat_request,
                NatCompatibleLangGraphWrapperFunction.convert_str,
                NatCompatibleLangGraphWrapperFunction.convert_to_chat_response,
                NatCompatibleLangGraphWrapperFunction.convert_to_chat_response_chunk,
            ],
        )
        self._graph = graph

    @staticmethod
    def _build_state(value: NatCompatibleLangGraphWrapperInput) -> dict[str, Any]:
        """Project the validated input down to the LangGraph state shape.

        We deliberately forward only ``messages`` — that's all the deep
        agent's state schema accepts as a top-level input. ``input_message``
        is a synthetic field for HTTP callers and would not be a valid
        LangGraph state key.
        """
        messages = value.messages if value.messages is not None else []
        return {"messages": convert_to_messages(messages)}

    @staticmethod
    def _has_tool_calls(message: AIMessage | dict[str, Any]) -> bool:
        if isinstance(message, AIMessage):
            if message.tool_calls:
                return True
            tool_calls = message.additional_kwargs.get("tool_calls")
            return isinstance(tool_calls, list) and bool(tool_calls)

        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list) and tool_calls:
            return True
        additional_kwargs = message.get("additional_kwargs")
        if isinstance(additional_kwargs, dict):
            nested_tool_calls = additional_kwargs.get("tool_calls")
            return isinstance(nested_tool_calls, list) and bool(nested_tool_calls)
        return False

    @staticmethod
    def _is_empty_assistant_message(message: Any) -> bool:
        if isinstance(message, AIMessage):
            return not message.text.strip() and not NatCompatibleLangGraphWrapperFunction._has_tool_calls(message)
        if not isinstance(message, dict):
            return False
        role = message.get("role") or message.get("type")
        if role not in {"assistant", "ai"}:
            return False
        content = message.get("content", "")
        if isinstance(content, str):
            return not content.strip() and not NatCompatibleLangGraphWrapperFunction._has_tool_calls(message)
        if content in (None, []):
            return not NatCompatibleLangGraphWrapperFunction._has_tool_calls(message)
        return False

    @staticmethod
    def _drop_trailing_empty_assistant_messages(messages: list[Any]) -> list[Any]:
        sanitized = list(messages)
        while sanitized and NatCompatibleLangGraphWrapperFunction._is_empty_assistant_message(sanitized[-1]):
            sanitized.pop()
        return sanitized

    async def _ainvoke_with_empty_response_retry(self, state: dict[str, Any]) -> NatCompatibleLangGraphWrapperOutput:
        """Retry once when the graph silently stops with an empty final answer.

        Random-routed weaker models can occasionally emit an empty ``stop``
        response after successful tool calls. LangGraph treats that as a valid
        final state, but user requests can still have remaining requirements. A
        short continuation prompt preserves the prior tool history and gives the
        agent a chance to complete the task instead of ending silently.
        """
        output = await self._graph.ainvoke(state)
        parsed = self._parse(output)
        if parsed.value.strip():
            return parsed

        logger.warning("nat_compatible_langgraph_wrapper received empty final response; prompting graph to continue")
        messages = parsed.messages if parsed.messages else state.get("messages", [])
        messages = self._drop_trailing_empty_assistant_messages(messages)
        if not messages:
            messages = list(state.get("messages", []))
        # _parse preserves dict-backed messages as-is, so normalize before
        # handing back to the graph — otherwise we can mix BaseMessage and
        # raw dicts in the retry state, which some graphs reject.
        retry_messages = convert_to_messages([*messages, HumanMessage(content=_EMPTY_FINAL_CONTINUATION_PROMPT)])
        retry_state = {
            **state,
            "messages": retry_messages,
        }
        return self._parse(await self._graph.ainvoke(retry_state))

    async def _ainvoke(self, value: NatCompatibleLangGraphWrapperInput) -> NatCompatibleLangGraphWrapperOutput:
        try:
            return await self._ainvoke_with_empty_response_retry(self._build_state(value))
        except Exception as e:
            logger.exception("nat_compatible_langgraph_wrapper _ainvoke failed")
            raise RuntimeError(f"Error in nat_compatible_langgraph_wrapper workflow: {e}") from e

    async def _astream(
        self, value: NatCompatibleLangGraphWrapperInput
    ) -> AsyncGenerator[NatCompatibleLangGraphWrapperOutput, None]:
        # Streaming consumers receive graph chunks as they arrive; the
        # empty-final-response retry lives only on the non-streaming
        # ``_ainvoke`` path because it requires having the full final state.
        try:
            async for chunk in self._graph.astream(self._build_state(value)):
                yield self._parse(chunk)
        except Exception as e:
            logger.exception("nat_compatible_langgraph_wrapper _astream failed")
            raise RuntimeError(f"Error in nat_compatible_langgraph_wrapper workflow: {e}") from e

    @staticmethod
    def _parse(output: Any) -> NatCompatibleLangGraphWrapperOutput:
        """Coerce any LangGraph output (final state OR stream chunk) into our output type.

        ``LangGraph.astream()`` yields different shapes depending on stream
        mode and node fan-out:

        * ``{"messages": [...]}`` — full-state shape (``stream_mode="values"``)
          or a node update that happens to write ``messages``.
        * ``{<node_name>: {<state_delta>}}`` — the default
          ``stream_mode="updates"`` shape, where ``<state_delta>`` is just
          the keys that node modified. May or may not contain ``messages``.
        * Anything else (e.g. ``{"skills_metadata": []}`` from a deep-agent
          subagent state node) — neither carries messages.

        We extract ``messages`` if it appears at either nesting level, and
        otherwise emit an empty ``NatCompatibleLangGraphWrapperOutput``. ``model_construct``
        bypasses validation since we've already chosen the data ourselves.
        """
        if isinstance(output, dict):
            if "messages" in output:
                payload = {"messages": output["messages"], **{k: v for k, v in output.items() if k != "messages"}}
                return NatCompatibleLangGraphWrapperOutput.model_construct(**payload)
            # Scan all node deltas (not just the single-key shape): under
            # ``stream_mode="updates"`` LangGraph can fan out and emit a chunk
            # like ``{"agent": {"messages": [...]}, "tools": {...}}``. We pick
            # the first node delta that carries ``messages``; if multiple do,
            # the one that wrote the most recent assistant message will be
            # surfaced again in a later chunk anyway.
            for inner in output.values():
                if isinstance(inner, dict) and "messages" in inner:
                    payload = {"messages": inner["messages"], **{k: v for k, v in inner.items() if k != "messages"}}
                    return NatCompatibleLangGraphWrapperOutput.model_construct(**payload)
        return NatCompatibleLangGraphWrapperOutput.model_construct(messages=[])

    # Converters — called by NAT to translate between this Function's
    # native types and the chat-completions / string shapes that NAT's
    # route handlers expose. Behavior matches ``LanggraphWrapperFunction``;
    # the only delta is the output type they return is our wider one.

    @staticmethod
    def convert_to_str(value: NatCompatibleLangGraphWrapperOutput) -> str:
        if not value.messages:
            return ""
        return value.messages[-1].text

    @staticmethod
    def _extract_usage(value: NatCompatibleLangGraphWrapperOutput) -> Usage:
        """Best-effort token usage extraction from the final assistant message."""
        candidates: list[dict[str, Any]] = []
        extras = getattr(value, "__pydantic_extra__", None)
        if isinstance(extras, dict):
            for key in ("usage", "usage_metadata", "response_metadata"):
                extra_val = extras.get(key)
                if isinstance(extra_val, dict):
                    candidates.append(extra_val)

        if value.messages:
            last = value.messages[-1]
            if isinstance(last, BaseMessage):
                usage_metadata = getattr(last, "usage_metadata", None)
                response_metadata = getattr(last, "response_metadata", None)
                if isinstance(usage_metadata, dict):
                    candidates.append(usage_metadata)
                if isinstance(response_metadata, dict):
                    candidates.append(response_metadata)
            elif isinstance(last, dict):
                usage_metadata = last.get("usage_metadata")
                response_metadata = last.get("response_metadata")
                usage = last.get("usage")
                if isinstance(usage_metadata, dict):
                    candidates.append(usage_metadata)
                if isinstance(response_metadata, dict):
                    candidates.append(response_metadata)
                if isinstance(usage, dict):
                    candidates.append(usage)

        prompt_tokens: int | None = None
        completion_tokens: int | None = None
        total_tokens: int | None = None

        # BFS over candidate dicts so a nested ``token_usage`` can contribute
        # without mutating the list we're iterating.
        queue: list[dict[str, Any]] = list(candidates)
        seen: set[int] = set()
        while queue:
            candidate = queue.pop(0)
            ident = id(candidate)
            if ident in seen:
                continue
            seen.add(ident)

            token_usage = candidate.get("token_usage")
            if isinstance(token_usage, dict):
                queue.append(token_usage)

            if prompt_tokens is None:
                raw_prompt = candidate.get("prompt_tokens", candidate.get("input_tokens"))
                if isinstance(raw_prompt, int):
                    prompt_tokens = raw_prompt
            if completion_tokens is None:
                raw_completion = candidate.get("completion_tokens", candidate.get("output_tokens"))
                if isinstance(raw_completion, int):
                    completion_tokens = raw_completion
            if total_tokens is None:
                raw_total = candidate.get("total_tokens")
                if isinstance(raw_total, int):
                    total_tokens = raw_total

        if total_tokens is None and isinstance(prompt_tokens, int) and isinstance(completion_tokens, int):
            total_tokens = prompt_tokens + completion_tokens
        return Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    @staticmethod
    def convert_chat_request(value: ChatRequest) -> NatCompatibleLangGraphWrapperInput:
        """Translate NAT's ``ChatRequest`` (chat-completions route body) to our input.

        NAT's chat-completions handler hands us a ``ChatRequest`` per call;
        converting it to ``NatCompatibleLangGraphWrapperInput.messages`` is what lets the
        ``/chat/completions`` and ``/generate/full`` routes share a single
        downstream graph invocation. We unpack the role enum and any
        ``model_dump``-able content parts so the LangGraph state ends up with
        plain JSON-able dicts.
        """
        message_dicts: list[MessageLikeRepresentation] = []
        for message in value.messages:
            role = message.role.value if hasattr(message.role, "value") else str(message.role)
            content: Any = message.content
            if isinstance(content, list):
                content = [part.model_dump() if hasattr(part, "model_dump") else part for part in content]
            message_dicts.append({"role": role, "content": content})
        return NatCompatibleLangGraphWrapperInput(messages=message_dicts)

    @staticmethod
    def convert_str(value: str) -> NatCompatibleLangGraphWrapperInput:
        """Translate the ``/generate`` route body (a bare string) to our input.

        NAT's ``/generate`` route accepts a plain string and asks each
        registered ``str`` converter to lift it into the workflow's input
        type. We populate ``input_message`` (rather than ``messages``) so the
        ``model_validator`` on :class:`NatCompatibleLangGraphWrapperInput` can take the
        canonical eval-client path that ``nvidia-nat-eval``'s
        ``remote_workflow.py`` uses against ``/generate/full`` — see the
        module docstring for the FastAPI/TypeAdapter rationale.
        """
        return NatCompatibleLangGraphWrapperInput(input_message=value)

    @staticmethod
    def convert_to_chat_response(value: NatCompatibleLangGraphWrapperOutput) -> ChatResponse:
        # ``value.value`` already handles dict-backed messages from
        # ``model_construct`` (see NatCompatibleLangGraphWrapperOutput.value), so we don't
        # have to reach into ``messages[-1].text`` here and risk
        # ``AttributeError`` when streaming chunks contain raw graph dicts.
        return ChatResponse.from_string(value.value, usage=NatCompatibleLangGraphWrapperFunction._extract_usage(value))

    @staticmethod
    def convert_to_chat_response_chunk(value: NatCompatibleLangGraphWrapperOutput) -> ChatResponseChunk:
        return ChatResponseChunk.from_string(value.value)


def _load_graph_factory(path: str):
    module_name, sep, attr_name = path.partition(":")
    if not sep or not module_name or not attr_name:
        raise ValueError("graph must be in 'module:callable' format")
    module = import_module(module_name)
    factory = getattr(module, attr_name)
    if not callable(factory):
        raise TypeError(f"Configured graph factory is not callable: {path}")
    return factory


@register_function(config_type=NatCompatibleLangGraphWrapperConfig, framework_wrappers=[LLMFrameworkEnum.LANGCHAIN])
async def register(config: NatCompatibleLangGraphWrapperConfig, b: Builder):
    """Build the configured graph and yield a NAT-callable wrapper.

    NAT calls this once per workflow build and yields the function
    instance to the runtime; ``_ainvoke`` / ``_astream`` are then driven
    per request by the FastAPI route handlers.
    """
    graph = _prepare_graph_for_nat(_load_graph_factory(config.graph)(RunnableConfig()))
    yield NatCompatibleLangGraphWrapperFunction(config=config, graph=graph)
