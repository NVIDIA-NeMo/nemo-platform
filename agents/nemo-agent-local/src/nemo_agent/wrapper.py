# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""NeMo agent wrapper — a NAT workflow type for the built-in nemo-agent.

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
* ``NemoAgentWrapperConfig`` registers ``_type: nemo_agent_wrapper`` with
  NAT via ``register_function`` at import time.
* ``NemoAgentWrapperInput`` accepts **either** ``messages`` (native LangGraph
  state shape) **or** ``input_message`` (the eval client's shape) and
  normalizes the latter to a single ``user`` message via a
  ``model_validator(mode="after")`` that participates in the Pydantic core
  schema (so it survives FastAPI's TypeAdapter path).
* ``NemoAgentWrapperOutput.messages`` defaults to an empty list, so streaming
  chunks without ``messages`` validate cleanly.
* ``NemoAgentWrapperFunction`` is a ``Function`` parametrized over those
  schemas. ``_ainvoke`` and ``_astream`` build a ``{"messages": [...]}`` state
  for the graph, run it, and coerce each output (or chunk) into
  ``NemoAgentWrapperOutput`` via ``_parse``.
* ``_parse`` extracts ``messages`` from the outer dict, from a single-keyed
  node-update wrapper, or — if neither shape applies — yields an empty
  placeholder. This is the key behavioral difference from
  ``LanggraphWrapperFunction._parse_stream_output``: we never raise on a
  state delta that lacks ``messages``.
* The graph itself comes from :func:`nemo_agent.register.create_nemo_agent`.
  No ``graph:`` field on the config: this wrapper is single-purpose.

Use it via ``_type: nemo_agent_wrapper`` in ``nemo-agent.yml`` /
``nemo-eval.yml``. Once the upstream NAT bugs are fixed we can drop this
module and revert to ``langgraph_wrapper``.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, MessageLikeRepresentation
from langchain_core.messages.utils import convert_to_messages
from langchain_core.prompt_values import PromptValue
from langchain_core.runnables import RunnableConfig
from nat.builder.builder import Builder
from nat.builder.framework_enum import LLMFrameworkEnum
from nat.builder.function import Function
from nat.cli.register_workflow import register_function
from nat.data_models.api_server import ChatRequest, ChatResponse, ChatResponseChunk, Usage
from nat.data_models.function import FunctionBaseConfig
from nemo_agent.register import create_nemo_agent
from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

logger = logging.getLogger(__name__)

_EMPTY_FINAL_CONTINUATION_PROMPT = """Your previous assistant response was empty, so the task is not complete.

Continue from the current tool history and finish every remaining requirement in the original user instruction. Do not stop after partial progress. Before returning, verify the requested final state with tools when possible. If every requirement is already complete, respond with a concise completion summary."""

_RATE_LIMIT_MESSAGE = (
    "The model service is temporarily rate-limited (HTTP 429), so I couldn't complete that request. "
    "Please try again shortly."
)
_TIMEOUT_MESSAGE = "The model service timed out before it could complete that request. Please try again."
_MODEL_ERROR_MESSAGE = "The model service returned an error before I could complete that request. Please try again."


class NemoAgentWrapperConfig(FunctionBaseConfig, name="nemo_agent_wrapper"):
    """Configuration for the nemo-agent NAT workflow.

    Unlike ``langgraph_wrapper`` there is no ``graph`` field — the graph is
    fixed (the built-in nemo-agent deep-agent), so the YAML is just::

        workflow:
          _type: nemo_agent_wrapper
          description: NeMo Platform assistant using LangChain Deep Agents
    """

    model_config = ConfigDict(extra="forbid")

    description: str = ""


class NemoAgentWrapperInput(BaseModel):
    """Input schema accepted by the nemo-agent ``/generate*`` routes.

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
    studio_session_id: UUID | None = None

    @model_validator(mode="after")
    def _ensure_messages(self) -> "NemoAgentWrapperInput":
        if self.messages is not None:
            return self
        if self.input_message is not None:
            self.messages = [{"role": "user", "content": self.input_message}]
            return self
        raise ValueError("Either 'messages' or 'input_message' is required")


class NemoAgentWrapperOutput(BaseModel):
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
        # streaming chunks (so deep-agent state deltas don't error out),
        # which means ``self.messages`` may be a ``list[dict]`` (raw graph
        # output) or even a non-list (e.g. a langgraph add-messages
        # operator wrapper like ``{"value": [...]}``) instead of the
        # declared ``list[BaseMessage]``. Handle each shape explicitly.
        msgs = self.messages
        if not isinstance(msgs, list) or not msgs:
            return ""
        last = msgs[-1]
        if isinstance(last, AIMessage):
            return last.text
        if isinstance(last, dict):
            role = last.get("role") or last.get("type")
            if role not in {"assistant", "ai"}:
                return ""
            content = last.get("content", "")
            return content if isinstance(content, str) else ""
        return ""


class NemoAgentWrapperFunction(Function[NemoAgentWrapperInput, NemoAgentWrapperOutput, NemoAgentWrapperOutput]):
    """NAT ``Function`` wrapping the nemo-agent compiled LangGraph.

    Behavior mirrors ``LanggraphWrapperFunction`` (so the same converters
    work for both the chat-completions route and the raw generate routes),
    with two differences:

    * **Input normalization** happens via ``NemoAgentWrapperInput``'s
      validator, before this class is reached.
    * **Stream chunks** that lack ``messages`` are coerced to an empty
      output instead of raising — see :meth:`_parse`.
    """

    def __init__(self, *, config: NemoAgentWrapperConfig, graph: Any) -> None:
        super().__init__(
            config=config,
            description=config.description,
            converters=[
                NemoAgentWrapperFunction.convert_to_str,
                NemoAgentWrapperFunction.convert_chat_request,
                NemoAgentWrapperFunction.convert_str,
                NemoAgentWrapperFunction.convert_to_chat_response,
                NemoAgentWrapperFunction.convert_to_chat_response_chunk,
            ],
        )
        self._graph = graph

    @staticmethod
    def _build_state(value: NemoAgentWrapperInput) -> dict[str, Any]:
        """Project the validated input down to the LangGraph state shape.

        We deliberately forward only ``messages`` — that's all the deep
        agent's state schema accepts as a top-level input. ``input_message``
        is a synthetic field for HTTP callers and would not be a valid
        LangGraph state key.
        """
        messages = value.messages if value.messages is not None else []
        return {"messages": convert_to_messages(messages)}

    @staticmethod
    def _invocation_config(value: NemoAgentWrapperInput) -> RunnableConfig:
        if value.studio_session_id is None:
            return {}
        return {
            "configurable": {
                "studio_session_id": str(value.studio_session_id),
            }
        }

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
            return not message.text.strip() and not NemoAgentWrapperFunction._has_tool_calls(message)
        if not isinstance(message, dict):
            return False
        role = message.get("role") or message.get("type")
        if role not in {"assistant", "ai"}:
            return False
        content = message.get("content", "")
        if isinstance(content, str):
            return not content.strip() and not NemoAgentWrapperFunction._has_tool_calls(message)
        if content in (None, []):
            return not NemoAgentWrapperFunction._has_tool_calls(message)
        return False

    @staticmethod
    def _drop_trailing_empty_assistant_messages(messages: list[Any]) -> list[Any]:
        sanitized = list(messages)
        while sanitized and NemoAgentWrapperFunction._is_empty_assistant_message(sanitized[-1]):
            sanitized.pop()
        return sanitized

    async def _ainvoke_with_empty_response_retry(
        self,
        state: dict[str, Any],
        config: RunnableConfig | None = None,
    ) -> NemoAgentWrapperOutput:
        """Retry once when the graph silently stops with an empty final answer.

        Random-routed weaker models can occasionally emit an empty ``stop``
        response after successful tool calls. LangGraph treats that as a valid
        final state, but benchmark tasks still have remaining requirements. A
        short continuation prompt preserves the prior tool history and gives the
        agent a chance to complete the task instead of ending silently.
        """
        output = await self._graph.ainvoke(state, config=config)
        parsed = self._parse(output)
        if parsed.value.strip():
            return parsed

        logger.warning("nemo_agent_wrapper received empty final response; prompting agent to continue")
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
        return self._parse(await self._graph.ainvoke(retry_state, config=config))

    async def _ainvoke(self, value: NemoAgentWrapperInput) -> NemoAgentWrapperOutput:
        try:
            return await self._ainvoke_with_empty_response_retry(
                self._build_state(value),
                self._invocation_config(value),
            )
        except Exception as e:
            logger.exception("nemo_agent_wrapper _ainvoke failed")
            return self._error_output(e)

    async def _astream(self, value: NemoAgentWrapperInput) -> AsyncGenerator[NemoAgentWrapperOutput, None]:
        # Streaming consumers receive graph chunks as they arrive; the
        # empty-final-response retry lives only on the non-streaming
        # ``_ainvoke`` path because it requires having the full final state.
        try:
            async for chunk in self._graph.astream(
                self._build_state(value),
                config=self._invocation_config(value),
            ):
                yield self._parse(chunk)
        except Exception as e:
            logger.exception("nemo_agent_wrapper _astream failed")
            # The route has already sent HTTP 200 by the time a streaming
            # model call fails. Re-raising closes the stream without a final
            # chunk, which Studio renders as a silent agent.
            yield self._error_output(e)

    @staticmethod
    def _error_output(error: Exception) -> NemoAgentWrapperOutput:
        """Turn model transport failures into a safe, visible assistant reply."""
        error_chain: list[str] = []
        current: BaseException | None = error
        seen: set[int] = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            error_chain.append(f"{type(current).__name__}: {current}".lower())
            current = current.__cause__ or current.__context__
        detail = " ".join(error_chain)

        if "429" in detail or "rate limit" in detail or "too many requests" in detail:
            message = _RATE_LIMIT_MESSAGE
        elif "timeout" in detail or "timed out" in detail:
            message = _TIMEOUT_MESSAGE
        else:
            message = _MODEL_ERROR_MESSAGE
        return NemoAgentWrapperOutput(messages=[AIMessage(content=message)])

    @staticmethod
    def _parse(output: Any) -> NemoAgentWrapperOutput:
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
        otherwise emit an empty ``NemoAgentWrapperOutput``. ``model_construct``
        bypasses validation since we've already chosen the data ourselves.
        """
        if isinstance(output, dict):
            if "messages" in output:
                payload = {"messages": output["messages"], **{k: v for k, v in output.items() if k != "messages"}}
                return NemoAgentWrapperOutput.model_construct(**payload)
            # Scan all node deltas (not just the single-key shape): under
            # ``stream_mode="updates"`` LangGraph can fan out and emit a chunk
            # like ``{"agent": {"messages": [...]}, "tools": {...}}``. We pick
            # the first node delta that carries ``messages``; if multiple do,
            # the one that wrote the most recent assistant message will be
            # surfaced again in a later chunk anyway.
            for inner in output.values():
                if isinstance(inner, dict) and "messages" in inner:
                    payload = {"messages": inner["messages"], **{k: v for k, v in inner.items() if k != "messages"}}
                    return NemoAgentWrapperOutput.model_construct(**payload)
        return NemoAgentWrapperOutput.model_construct(messages=[])

    # Converters — called by NAT to translate between this Function's
    # native types and the chat-completions / string shapes that NAT's
    # route handlers expose. Behavior matches ``LanggraphWrapperFunction``;
    # the only delta is the output type they return is our wider one.

    @staticmethod
    def convert_to_str(value: NemoAgentWrapperOutput) -> str:
        if not value.messages:
            return ""
        return value.value

    @staticmethod
    def _extract_usage(value: NemoAgentWrapperOutput) -> Usage:
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
    def convert_chat_request(value: ChatRequest) -> NemoAgentWrapperInput:
        """Translate NAT's ``ChatRequest`` (chat-completions route body) to our input.

        NAT's chat-completions handler hands us a ``ChatRequest`` per call;
        converting it to ``NemoAgentWrapperInput.messages`` is what lets the
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
        extras = value.model_extra or {}
        return NemoAgentWrapperInput(
            messages=message_dicts,
            studio_session_id=extras.get("studio_session_id"),
        )

    @staticmethod
    def convert_str(value: str) -> NemoAgentWrapperInput:
        """Translate the ``/generate`` route body (a bare string) to our input.

        NAT's ``/generate`` route accepts a plain string and asks each
        registered ``str`` converter to lift it into the workflow's input
        type. We populate ``input_message`` (rather than ``messages``) so the
        ``model_validator`` on :class:`NemoAgentWrapperInput` can take the
        canonical eval-client path that ``nvidia-nat-eval``'s
        ``remote_workflow.py`` uses against ``/generate/full`` — see the
        module docstring for the FastAPI/TypeAdapter rationale.
        """
        return NemoAgentWrapperInput(input_message=value)

    @staticmethod
    def convert_to_chat_response(value: NemoAgentWrapperOutput) -> ChatResponse:
        # ``value.value`` already handles dict-backed messages from
        # ``model_construct`` (see NemoAgentWrapperOutput.value), so we don't
        # have to reach into ``messages[-1].text`` here and risk
        # ``AttributeError`` when streaming chunks contain raw graph dicts.
        return ChatResponse.from_string(value.value, usage=NemoAgentWrapperFunction._extract_usage(value))

    @staticmethod
    def convert_to_chat_response_chunk(value: NemoAgentWrapperOutput) -> ChatResponseChunk:
        return ChatResponseChunk.from_string(value.value)


@register_function(config_type=NemoAgentWrapperConfig, framework_wrappers=[LLMFrameworkEnum.LANGCHAIN])
async def register(config: NemoAgentWrapperConfig, b: Builder):
    """Build the nemo-agent graph and yield a NAT-callable wrapper.

    The graph factory in ``register.create_nemo_agent`` constructs the
    Deep Agent graph. We hand it directly to ``NemoAgentWrapperFunction``.

    NAT calls this once per workflow build and yields the function
    instance to the runtime; ``_ainvoke`` / ``_astream`` are then driven
    per request by the FastAPI route handlers.
    """
    graph = create_nemo_agent()
    yield NemoAgentWrapperFunction(config=config, graph=graph)
