# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Bidirectional render between :class:`AgentSpec` and its on-disk markdown form.

The on-disk file at ``agents/<name>.spec.md`` is the human-editable artifact
the developer and coding agent collaborate on. The :class:`AgentSpec`
Pydantic model is the typed contract everything else reads. This module is
the only place that knows how to convert between the two.

Format:

* YAML front matter for the small primitive fields (``name``, ``eval_command``).
* One ``## <Section>`` header per body field, in the order declared on the
  :class:`AgentSpec` model.
* Structured nested types (``Harness``, ``ModelChoice``, ``ChangeScope``, ``Scope``)
  render as labeled bullet lists that are still hand-editable.

Round-trip guarantee: ``parse_spec(render_spec(spec)) == spec``. We assert
this property in the unit tests for every valid sample.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

import yaml
from nemo_agents_plugin.spec import (
    AgentSpec,
    ChangeScope,
    Framework,
    FrameworkResolution,
    Harness,
    ModelChoice,
    Scope,
)

# Order matters: it defines the on-disk section order. Keep aligned with the
# field order on :class:`AgentSpec`.
_BODY_SECTIONS: tuple[tuple[str, str], ...] = (
    ("role", "Role"),
    ("purpose", "Purpose"),
    ("scope", "Scope"),
    ("tools", "Tools"),
    ("model", "Model"),
    ("framework", "Framework"),
    ("harness", "Harness"),
    ("behavior", "Behavior"),
    ("success_criteria", "Success Criteria"),
    ("evaluation_setup", "Evaluation Setup"),
    ("change_scope", "Change Scope"),
    ("signals", "Signals"),
    ("unresolved_questions", "Unresolved Questions"),
)

# Header rendered for each ChangeScope boolean. Order is fixed so the
# round-trip is deterministic.
_CHANGE_SCOPE_LABELS: tuple[tuple[str, str], ...] = (
    ("system_prompt", "System prompt"),
    ("tools", "Tools"),
    ("middleware", "Middleware"),
    ("inference_params", "Inference params"),
    ("model_swap_within_mode", "Model swap (within mode)"),
    ("skills", "Skills"),
    ("fine_tuning", "Fine-tuning"),
)
_LABEL_TO_CHANGE_SCOPE_FIELD: dict[str, str] = {label.lower(): attr for attr, label in _CHANGE_SCOPE_LABELS}


class SpecRenderError(ValueError):
    """Raised when the markdown cannot be parsed back into an :class:`AgentSpec`.

    Validation errors from the Pydantic model itself are still raised as
    ``pydantic.ValidationError``; this class is for failures in the markdown
    structure that happen before the model sees the data (missing section,
    duplicate section, malformed labeled bullet, etc.).
    """


# ---------------------------------------------------------------------------
# Render: AgentSpec -> markdown
# ---------------------------------------------------------------------------


def render_spec(spec: AgentSpec) -> str:
    """Render an :class:`AgentSpec` as the canonical on-disk markdown."""

    front_matter = {"name": spec.name}
    if spec.eval_command is not None:
        front_matter["eval_command"] = spec.eval_command
    front = yaml.safe_dump(front_matter, sort_keys=False).rstrip()

    parts: list[str] = [f"---\n{front}\n---", "", f"# Agent Spec: {spec.name}", ""]
    for attr, header in _BODY_SECTIONS:
        parts.append(f"## {header}")
        parts.append("")
        parts.append(_render_field(attr, getattr(spec, attr)))
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def _render_field(attr: str, value: object) -> str:
    if attr in {"role", "purpose", "tools", "behavior", "success_criteria", "evaluation_setup"}:
        assert isinstance(value, str)
        return value
    if attr == "signals":
        return value if isinstance(value, str) else "_(none)_"
    if attr == "unresolved_questions":
        assert isinstance(value, list)
        if not value:
            return "_(none)_"
        return "\n".join(f"- {item}" for item in value)
    if attr == "scope":
        assert isinstance(value, Scope)
        lines = [
            f"- Audience: {value.audience}",
            f"- Categories: {_render_inline_list(value.categories)}",
            f"- In scope: {_render_inline_list(value.in_scope)}",
            f"- Out of scope: {_render_inline_list(value.out_of_scope)}",
        ]
        return "\n".join(lines)
    if attr == "model":
        assert isinstance(value, ModelChoice)
        return f"- Mode: {value.mode}\n- Family: {value.family}"
    if attr == "framework":
        assert isinstance(value, Framework)
        lines = [f"- Resolution: {value.resolution.value}"]
        if value.source_framework is not None:
            lines.append(f"- Source framework: {value.source_framework}")
        if value.notes is not None:
            lines.append(f"- Notes: {value.notes}")
        return "\n".join(lines)
    if attr == "harness":
        if value is None:
            return "_(none)_"
        assert isinstance(value, Harness)
        lines = [f"- Description: {value.description}"]
        if value.agent_loop is not None:
            lines.append(f"- Agent loop: {value.agent_loop}")
        if value.tool_dispatch is not None:
            lines.append(f"- Tool dispatch: {value.tool_dispatch}")
        if value.context_management is not None:
            lines.append(f"- Context management: {value.context_management}")
        if value.state_management is not None:
            lines.append(f"- State management: {value.state_management}")
        if value.guardrails is not None:
            lines.append(f"- Guardrails: {value.guardrails}")
        if value.observability is not None:
            lines.append(f"- Observability: {value.observability}")
        if value.verification is not None:
            lines.append(f"- Verification: {value.verification}")
        if value.runtime is not None:
            lines.append(f"- Runtime: {value.runtime}")
        if value.notes is not None:
            lines.append(f"- Notes: {value.notes}")
        return "\n".join(lines)
    if attr == "change_scope":
        assert isinstance(value, ChangeScope)
        lines = [f"- {label}: {'yes' if getattr(value, field) else 'no'}" for field, label in _CHANGE_SCOPE_LABELS]
        if value.notes is not None:
            lines.append(f"- Notes: {value.notes}")
        return "\n".join(lines)
    raise SpecRenderError(f"unknown field {attr!r}")


def _render_inline_list(items: list[str]) -> str:
    """Render a short list inside one labeled bullet."""

    return "; ".join(items) if items else "_(none)_"


# ---------------------------------------------------------------------------
# Parse: markdown -> AgentSpec
# ---------------------------------------------------------------------------

_FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_SECTION_RE = re.compile(r"^## +(.+?)\s*$", re.MULTILINE)
# ``- label: value`` — label may contain letters, spaces, and parenthesised
# clarifications. value is everything after the first colon.
_LABELED_BULLET_RE = re.compile(r"^- +([^:]+?)\s*:\s*(.*)$")


def parse_spec(markdown: str) -> AgentSpec:
    """Parse the on-disk markdown form back into an :class:`AgentSpec`.

    Validation errors against the Pydantic schema are raised as
    ``pydantic.ValidationError`` from :class:`AgentSpec` construction.
    Structural errors (missing section, unknown section, malformed bullet)
    are raised as :class:`SpecRenderError`.
    """

    front_match = _FRONT_MATTER_RE.match(markdown)
    if front_match is None:
        raise SpecRenderError("missing YAML front matter")
    front = yaml.safe_load(front_match.group(1)) or {}
    if not isinstance(front, dict):
        raise SpecRenderError("YAML front matter must be a mapping")

    body = markdown[front_match.end() :]
    sections = _split_sections(body)

    expected = {header for _, header in _BODY_SECTIONS}
    unknown = set(sections) - expected
    if unknown:
        raise SpecRenderError(f"unknown section(s): {sorted(unknown)}")

    kwargs: dict[str, Any] = {}
    if "name" in front:
        kwargs["name"] = front["name"]
    if "eval_command" in front:
        kwargs["eval_command"] = front["eval_command"]

    for attr, header in _BODY_SECTIONS:
        if header not in sections:
            raise SpecRenderError(f"missing section: ## {header}")
        parsed = _parse_field(attr, sections[header])
        if parsed is not _OMIT:
            kwargs[attr] = parsed

    return AgentSpec(**kwargs)


# Sentinel for "this section was empty / placeholder — let the model default
# apply instead of passing an empty value".
class _Omit:
    pass


_OMIT = _Omit()


def _split_sections(body: str) -> dict[str, str]:
    """Split the markdown body into ``{section_header: section_body}``.

    Anything before the first ``## `` (e.g. the ``# Agent Spec`` title) is
    dropped. Duplicate sections raise.
    """

    sections: dict[str, str] = {}
    parts: list[tuple[str, int]] = [(m.group(1).strip(), m.end()) for m in _SECTION_RE.finditer(body)]
    for i, (header, start) in enumerate(parts):
        end = parts[i + 1][1] - len(f"## {parts[i + 1][0]}") - 1 if i + 1 < len(parts) else len(body)
        # Step back over the ``## `` marker of the next section.
        if i + 1 < len(parts):
            next_match = list(_SECTION_RE.finditer(body))[i + 1]
            end = next_match.start()
        chunk = body[start:end].strip("\n")
        if header in sections:
            raise SpecRenderError(f"duplicate section: ## {header}")
        sections[header] = chunk
    return sections


def _parse_field(attr: str, raw: str) -> object:
    stripped = raw.strip()
    placeholder = stripped == "_(none)_"

    if attr in {"role", "purpose", "tools", "behavior", "success_criteria", "evaluation_setup"}:
        return stripped
    if attr == "signals":
        return None if placeholder or not stripped else stripped
    if attr == "unresolved_questions":
        if placeholder or not stripped:
            return _OMIT
        return list(_parse_bullet_list(stripped))
    if attr == "scope":
        labels = _parse_labeled_bullets(stripped)
        try:
            return Scope(
                audience=labels["audience"],
                categories=_parse_inline_list(labels["categories"]),
                in_scope=_parse_inline_list(labels.get("in scope", "_(none)_")),
                out_of_scope=_parse_inline_list(labels.get("out of scope", "_(none)_")),
            )
        except KeyError as exc:
            raise SpecRenderError(f"scope section missing key {exc.args[0]!r}") from exc
    if attr == "model":
        labels = _parse_labeled_bullets(stripped)
        try:
            return ModelChoice(mode=labels["mode"], family=labels["family"])  # type: ignore[arg-type]
        except KeyError as exc:
            raise SpecRenderError(f"model section missing key {exc.args[0]!r}") from exc
    if attr == "framework":
        labels = _parse_labeled_bullets(stripped)
        if "resolution" not in labels:
            raise SpecRenderError("framework section missing 'Resolution'")
        try:
            resolution = FrameworkResolution(labels["resolution"])
        except ValueError as exc:
            raise SpecRenderError(f"unknown framework resolution: {labels['resolution']!r}") from exc
        return Framework(
            resolution=resolution,
            source_framework=labels.get("source framework"),
            notes=labels.get("notes"),
        )
    if attr == "harness":
        if placeholder or not stripped:
            return _OMIT
        labels = _parse_labeled_bullets(stripped)
        if "description" not in labels:
            raise SpecRenderError("harness section missing 'Description'")
        return Harness(
            description=labels["description"],
            agent_loop=labels.get("agent loop"),
            tool_dispatch=labels.get("tool dispatch"),
            context_management=labels.get("context management"),
            state_management=labels.get("state management"),
            guardrails=labels.get("guardrails"),
            observability=labels.get("observability"),
            verification=labels.get("verification"),
            runtime=labels.get("runtime"),
            notes=labels.get("notes"),
        )
    if attr == "change_scope":
        labels = _parse_labeled_bullets(stripped)
        notes = labels.pop("notes", None)
        fields: dict[str, object] = {}
        for raw_label, value in labels.items():
            field_name = _LABEL_TO_CHANGE_SCOPE_FIELD.get(raw_label)
            if field_name is None:
                raise SpecRenderError(f"unknown change-scope label: {raw_label!r}")
            fields[field_name] = _parse_bool(value, raw_label)
        if notes is not None:
            fields["notes"] = notes
        return ChangeScope(**fields)  # type: ignore[arg-type]
    raise SpecRenderError(f"unknown field {attr!r}")


def _parse_bullet_list(block: str) -> Iterator[str]:
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if not stripped.startswith("- "):
            raise SpecRenderError(f"expected bullet, got: {line!r}")
        yield stripped[2:].strip()


def _parse_labeled_bullets(block: str) -> dict[str, str]:
    """Parse ``- Label: value`` lines into ``{label.lower(): value}``."""

    out: dict[str, str] = {}
    for line in block.splitlines():
        if not line.strip():
            continue
        match = _LABELED_BULLET_RE.match(line)
        if match is None:
            raise SpecRenderError(f"expected '- Label: value' bullet, got: {line!r}")
        label = match.group(1).strip().lower()
        value = match.group(2).strip()
        if label in out:
            raise SpecRenderError(f"duplicate label: {label!r}")
        out[label] = value
    return out


def _parse_inline_list(value: str) -> list[str]:
    stripped = value.strip()
    if not stripped or stripped == "_(none)_":
        return []
    return [item.strip() for item in stripped.split(";") if item.strip()]


def _parse_bool(value: str, label: str) -> bool:
    low = value.strip().lower()
    if low in {"yes", "true", "on"}:
        return True
    if low in {"no", "false", "off"}:
        return False
    raise SpecRenderError(f"expected yes/no for {label!r}, got: {value!r}")
