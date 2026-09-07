# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Prompt mutation and recombination interfaces for GA optimization."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any, Protocol


class PromptTransformError(RuntimeError):
    """Raised when a prompt transform cannot be produced."""


class PromptTransformer(Protocol):
    """Generate prompt variants for GA operators."""

    def mutate(
        self,
        *,
        prompt_name: str,
        prompt: str,
        purpose: str,
        prompt_format: str | None,
        feedback: str | None,
    ) -> str:
        """Return one mutated prompt."""
        ...

    def recombine(
        self,
        *,
        prompt_name: str,
        parent_a: str,
        parent_b: str,
        purpose: str,
        prompt_format: str | None,
        feedback: str | None,
    ) -> str:
        """Return one child prompt from two parent prompts."""
        ...


class ModelPromptTransformer:
    """Direct OpenAI-compatible model caller used by the prompt GA backend.

    This adapter intentionally supports only model declarations with a direct
    ``url``/``base_url`` and optional ``api_key_env``. It does not resolve
    platform secret references; unsupported Fabric model shapes fail before the
    first mutation instead of falling back to guessed credentials.
    """

    def __init__(
        self,
        *,
        payload: Mapping[str, Any],
        model_name: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout_s: float | None = None,
    ) -> None:
        model_config = _model_config(payload, model_name)
        settings = _model_settings(model_config, model_name)
        self._model_name = str(model_config.get("model") or model_config.get("model_name") or model_name)
        self._base_url = _chat_completions_url(model_config, model_name)
        self._api_key = _api_key(model_config)
        self._temperature = _float_setting(
            settings,
            "temperature",
            default=0.7 if temperature is None else temperature,
        )
        self._max_tokens = _int_setting(
            settings,
            "max_tokens",
            default=2048 if max_tokens is None else max_tokens,
        )
        self._timeout_s = _float_setting(
            settings,
            "timeout_s",
            default=60.0 if timeout_s is None else timeout_s,
        )

    def mutate(
        self,
        *,
        prompt_name: str,
        prompt: str,
        purpose: str,
        prompt_format: str | None,
        feedback: str | None,
    ) -> str:
        user_prompt = _mutation_user_prompt(
            prompt_name=prompt_name,
            prompt=prompt,
            purpose=purpose,
            prompt_format=prompt_format,
            feedback=feedback,
        )
        return self._complete(user_prompt)

    def recombine(
        self,
        *,
        prompt_name: str,
        parent_a: str,
        parent_b: str,
        purpose: str,
        prompt_format: str | None,
        feedback: str | None,
    ) -> str:
        user_prompt = _recombination_user_prompt(
            prompt_name=prompt_name,
            parent_a=parent_a,
            parent_b=parent_b,
            purpose=purpose,
            prompt_format=prompt_format,
            feedback=feedback,
        )
        return self._complete(user_prompt)

    def _complete(self, user_prompt: str) -> str:
        body = {
            "model": self._model_name,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are optimizing an agent prompt. Return only the revised prompt text, "
                        "with no markdown fences, commentary, or scoring rationale."
                    ),
                },
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        request = urllib.request.Request(
            self._base_url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_s) as response:  # noqa: S310
                response_payload = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise PromptTransformError(f"Prompt optimizer model call failed: {exc}") from exc

        content = _extract_chat_content(response_payload)
        if not content:
            raise PromptTransformError("Prompt optimizer model returned an empty prompt.")
        return content


def _model_config(payload: Mapping[str, Any], model_name: str) -> Mapping[str, Any]:
    models = payload.get("models")
    if not isinstance(models, Mapping):
        raise PromptTransformError("Fabric payload must declare models for prompt GA optimization.")
    model_config = models.get(model_name)
    if not isinstance(model_config, Mapping):
        raise PromptTransformError(f"Prompt optimizer model {model_name!r} not found under payload.models.")
    provider = str(model_config.get("provider") or "openai").strip().lower().replace("-", "_")
    supported = {"openai", "openai_compatible", "nvidia", "nim", "nvidia_nim"}
    if provider not in supported:
        raise PromptTransformError(
            f"Prompt optimizer model {model_name!r} has unsupported provider {provider!r}; "
            "the GA direct adapter currently supports OpenAI-compatible providers with url/base_url."
        )
    return model_config


def _model_settings(model_config: Mapping[str, Any], model_name: str) -> Mapping[str, Any]:
    settings = model_config.get("settings")
    if settings is None:
        return {}
    if not isinstance(settings, Mapping):
        raise PromptTransformError(f"Prompt optimizer model {model_name!r} settings must be a mapping.")
    return settings


def _chat_completions_url(model_config: Mapping[str, Any], model_name: str) -> str:
    raw_url = model_config.get("url") or model_config.get("base_url")
    if not isinstance(raw_url, str) or not raw_url.strip():
        raise PromptTransformError(f"Prompt optimizer model {model_name!r} must declare 'url' or 'base_url'.")
    url = raw_url.strip().rstrip("/")
    if url.endswith("/chat/completions"):
        return url
    if url.endswith("/v1"):
        return f"{url}/chat/completions"
    return f"{url}/v1/chat/completions"


def _api_key(model_config: Mapping[str, Any]) -> str | None:
    if model_config.get("api_key_secret") is not None and model_config.get("api_key_env") is None:
        raise PromptTransformError(
            "Prompt GA direct model adapter supports api_key_env, not api_key_secret; "
            "use an environment-backed model declaration for prompt optimization."
        )
    env_name = model_config.get("api_key_env")
    if not isinstance(env_name, str) or not env_name.strip():
        return None
    value = os.getenv(env_name.strip())
    if value is None:
        raise PromptTransformError(f"Prompt optimizer model api_key_env {env_name!r} is not set.")
    return value


def _float_setting(settings: Mapping[str, Any], key: str, *, default: float) -> float:
    value = settings.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PromptTransformError(f"Prompt optimizer model setting {key!r} must be a number.")
    return float(value)


def _int_setting(settings: Mapping[str, Any], key: str, *, default: int) -> int:
    value = settings.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PromptTransformError(f"Prompt optimizer model setting {key!r} must be a positive integer.")
    return value


def _extract_chat_content(payload: Mapping[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, Mapping):
        return ""
    message = first.get("message")
    content: Any
    if isinstance(message, Mapping):
        content = message.get("content")
    else:
        content = first.get("text")
    if not isinstance(content, str):
        return ""
    return _strip_prompt_wrapper(content)


def _strip_prompt_wrapper(content: str) -> str:
    stripped = content.strip()
    fenced = re.fullmatch(r"```(?:[A-Za-z0-9_-]+)?\s*(.*?)\s*```", stripped, flags=re.DOTALL)
    if fenced:
        stripped = fenced.group(1).strip()
    return stripped


def _mutation_user_prompt(
    *,
    prompt_name: str,
    prompt: str,
    purpose: str,
    prompt_format: str | None,
    feedback: str | None,
) -> str:
    sections = [
        f"Prompt dimension: {prompt_name}",
        f"Purpose: {purpose}",
        f"Required format: {prompt_format or 'Preserve the current prompt format.'}",
        "Current prompt:",
        prompt,
    ]
    if feedback:
        sections.extend(["Evaluation feedback to address:", feedback])
    sections.append("Rewrite the prompt to improve the objective while preserving the agent's role and constraints.")
    return "\n\n".join(sections)


def _recombination_user_prompt(
    *,
    prompt_name: str,
    parent_a: str,
    parent_b: str,
    purpose: str,
    prompt_format: str | None,
    feedback: str | None,
) -> str:
    sections = [
        f"Prompt dimension: {prompt_name}",
        f"Purpose: {purpose}",
        f"Required format: {prompt_format or 'Preserve the current prompt format.'}",
        "Parent prompt A:",
        parent_a,
        "Parent prompt B:",
        parent_b,
    ]
    if feedback:
        sections.extend(["Evaluation feedback to address:", feedback])
    sections.append("Combine the strongest parts of both parents into one improved prompt.")
    return "\n\n".join(sections)


__all__ = [
    "ModelPromptTransformer",
    "PromptTransformError",
    "PromptTransformer",
]
