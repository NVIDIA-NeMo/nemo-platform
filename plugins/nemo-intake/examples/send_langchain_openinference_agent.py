#!/usr/bin/env python
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Run a minimal LangChain agent and export OpenInference spans over OTLP/HTTP."""

from __future__ import annotations

import argparse
import json
import os
import warnings
from typing import Any

DEFAULT_ENDPOINT = "http://127.0.0.1:8000/apis/intake/v2/workspaces/default/ingest/otlp/v1/traces"
DEFAULT_OPENAI_MODEL = "openai/openai/gpt-5.5"
SESSION_ID = "langchain-openinference-smoke"
USER_ID = "local-user"
QUESTION = "What is 6 times 7? Use the multiply tool."


def multiply(a: int, b: int) -> int:
    """Multiply two integers."""
    return a * b


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    args = parser.parse_args()

    base_url = _normalize_base_url(os.getenv("OPENAI_BASE_URL"))
    model = os.getenv("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit(
            "Set OPENAI_API_KEY before running this script. "
            "For a local OpenAI-compatible server that ignores auth, set it to any non-empty value."
        )

    _suppress_langchain_warning()
    from langchain.agents import create_agent
    from langchain_openai import ChatOpenAI
    from openinference.instrumentation import using_attributes
    from openinference.instrumentation.langchain import LangChainInstrumentor
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": "intake-langchain-openinference-smoke",
                "service.version": "0.1.0",
            }
        )
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=args.endpoint)))
    trace.set_tracer_provider(provider)
    LangChainInstrumentor().instrument()

    llm_kwargs: dict[str, Any] = {
        "model": model,
        "api_key": api_key,
    }
    if base_url:
        llm_kwargs["base_url"] = base_url
    llm = ChatOpenAI(**llm_kwargs)
    agent = create_agent(
        model=llm,
        tools=[multiply],
        system_prompt="You are a terse calculator. Use tools for arithmetic.",
    )

    try:
        with using_attributes(
            session_id=SESSION_ID,
            user_id=USER_ID,
            metadata={"script": "plugins/nemo-intake/examples/send_langchain_openinference_agent.py"},
            tags=["intake-smoke", "langchain", "openinference"],
        ):
            result = agent.invoke({"messages": [{"role": "user", "content": QUESTION}]})

        print(_final_text(result))
        print(f"sent OpenInference OTLP spans to {args.endpoint}")
        print(f"session_id={SESSION_ID}")
    except AttributeError as exc:
        if "'str' object has no attribute 'model_dump'" not in str(exc):
            raise
        raise SystemExit(
            "The OpenAI-compatible model endpoint returned a top-level string instead of a chat completion "
            "object. Check that OPENAI_BASE_URL points at an OpenAI API base, normally "
            "http://host:port/v1 for LiteLLM proxy, and that the selected model is served by "
            "/chat/completions."
        ) from None
    finally:
        provider.force_flush()
        provider.shutdown()


def _final_text(result: Any) -> str:
    if isinstance(result, dict):
        messages = result.get("messages")
        if isinstance(messages, list) and messages:
            return _message_content(messages[-1])
    return json.dumps(result, default=str)


def _suppress_langchain_warning() -> None:
    from langchain_core._api.deprecation import LangChainPendingDeprecationWarning

    warnings.filterwarnings(
        "ignore",
        message=r"The default value of `allowed_objects` will change.*",
        category=LangChainPendingDeprecationWarning,
        module=r"langgraph\.checkpoint\.serde\.encrypted",
    )


def _normalize_base_url(base_url: str | None) -> str | None:
    if not base_url:
        return None
    return base_url.rstrip("/")


def _message_content(message: Any) -> str:
    content = message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
    if isinstance(content, str):
        return content
    return json.dumps(content, default=str)


if __name__ == "__main__":
    main()
