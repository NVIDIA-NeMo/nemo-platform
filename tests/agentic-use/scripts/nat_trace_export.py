#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Run NAT agents and export evaluator-ready ATIF trajectories."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, JsonValue]


def _json_object_array(values: Sequence[JsonObject]) -> list[JsonValue]:
    return [value for value in values]


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_final_message(output_dir: Path, final_result: JsonValue) -> None:
    final_payload = final_result if isinstance(final_result, dict) else {"result": final_result}
    _write_json(output_dir / "final_message.json", final_payload)
    if isinstance(final_result, str):
        (output_dir / "final_message.txt").write_text(final_result.strip() + "\n", encoding="utf-8")


def _trajectory_to_json_dict(trajectory) -> JsonObject:
    return trajectory.model_dump(mode="json", exclude_none=True)


def _write_atif_trajectory(path: Path, trajectory) -> None:
    from nat.atif import ATIFTrajectory

    payload = _trajectory_to_json_dict(trajectory)
    ATIFTrajectory.model_validate(payload)
    _write_json(path, payload)


def _read_jsonl(path: Path) -> list[JsonObject]:
    events: list[JsonObject] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            logger.debug("Skipping non-JSON line %d in %s", line_number, path)
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def _load_instruction(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace").strip()


def _read_final_message(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return ""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text
    extracted = _extract_text(payload)
    return extracted or text


def _write_final_message_artifact(path: Path | None, final_message: str) -> None:
    if path is None or not final_message.strip():
        return
    if path.suffix == ".json":
        _write_json(path, {"result": final_message.strip()})
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(final_message.strip() + "\n", encoding="utf-8")


def _extract_text(value: JsonValue) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, int | float | bool):
        return str(value)
    if isinstance(value, list):
        parts = [_extract_text(item) for item in value]
        return "\n".join(part for part in parts if part).strip()
    if not isinstance(value, dict):
        return ""

    for key in ("text", "content", "message", "result", "response", "output", "summary", "final_summary"):
        text = _extract_text(value.get(key))
        if text:
            return text

    choices = value.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            text = _extract_text(choice)
            if text:
                return text
    return ""


def _compact_payload(value: JsonValue, *, max_chars: int = 4000) -> str:
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, sort_keys=True)
    return text if len(text) <= max_chars else text[:max_chars] + "...[truncated]"


def _arguments_from_value(value: JsonValue) -> JsonObject:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            payload = json.loads(value)
        except json.JSONDecodeError:
            return {"value": value}
        return payload if isinstance(payload, dict) else {"value": payload}
    if value is None:
        return {}
    return {"value": value}


def _event_type(event: JsonObject) -> str:
    for key in ("type", "event", "event_type", "kind"):
        value = event.get(key)
        if isinstance(value, str):
            return value
    return "unknown"


def _iso_now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


class _DirectATIFBuilder:
    def __init__(self, *, agent_name: str, instruction: str = "", source_file: str | None = None) -> None:
        self._agent_name = agent_name
        self._source_file = source_file
        self._steps: list[JsonObject] = []
        self._pending_tool_step: dict[str, JsonObject] = {}
        self._next_step_id = 1
        self._next_tool_id = 1
        if instruction.strip():
            self.add_user_step(instruction.strip())

    def add_user_step(self, message: str) -> None:
        self._steps.append(
            {
                "step_id": self._allocate_step_id(),
                "source": "user",
                "message": message,
                "timestamp": _iso_now(),
                "extra": self._extra("instruction"),
            }
        )

    def add_agent_step(
        self,
        *,
        message: str = "",
        tool_calls: list[JsonObject] | None = None,
        observations: list[JsonObject] | None = None,
        extra: JsonObject | None = None,
    ) -> JsonObject:
        step: JsonObject = {
            "step_id": self._allocate_step_id(),
            "source": "agent",
            "message": message,
            "timestamp": _iso_now(),
            "extra": self._extra("agent", extra),
        }
        if tool_calls:
            step["tool_calls"] = _json_object_array(tool_calls)
        if observations:
            step["observation"] = {"results": _json_object_array(observations)}
        self._steps.append(step)
        for call in tool_calls or []:
            call_id = call.get("tool_call_id")
            if isinstance(call_id, str):
                self._pending_tool_step[call_id] = step
        return step

    def add_tool_call(
        self,
        *,
        tool_call_id: str | None,
        function_name: str,
        arguments: JsonObject | None = None,
        message: str = "",
        extra: JsonObject | None = None,
    ) -> str:
        call_id = tool_call_id or self._allocate_tool_call_id()
        tool_call: JsonObject = {
            "tool_call_id": call_id,
            "function_name": function_name or "unknown_tool",
            "arguments": arguments or {},
        }
        if extra:
            tool_call["extra"] = extra
        self.add_agent_step(message=message, tool_calls=[tool_call], extra=extra)
        return call_id

    def add_observation(self, *, tool_call_id: str | None, content: str, extra: JsonObject | None = None) -> None:
        observation: JsonObject = {
            "source_call_id": tool_call_id,
            "content": content,
        }
        if extra:
            observation["extra"] = extra
        target = self._pending_tool_step.get(tool_call_id or "")
        if target is None:
            self.add_agent_step(observations=[observation], extra=extra)
            return
        existing = target.get("observation")
        if not isinstance(existing, dict):
            target["observation"] = {"results": _json_object_array([observation])}
            return
        results = existing.get("results")
        if isinstance(results, list):
            results.append(observation)
        else:
            existing["results"] = _json_object_array([observation])

    def finalize(self, *, final_message: str = "") -> JsonObject:
        if final_message.strip():
            last_agent = next((step for step in reversed(self._steps) if step.get("source") == "agent"), None)
            if not isinstance(last_agent, dict) or _extract_text(last_agent.get("message")) != final_message.strip():
                self.add_agent_step(message=final_message.strip(), extra={"event_type": "final_message"})
        trajectory: JsonObject = {
            "agent": {"name": self._agent_name, "version": "0.0.0"},
            "session_id": str(uuid.uuid4()),
            "steps": _json_object_array(self._steps),
        }
        from nat.atif import ATIFTrajectory

        return _trajectory_to_json_dict(ATIFTrajectory.model_validate(trajectory))

    def _allocate_step_id(self) -> int:
        step_id = self._next_step_id
        self._next_step_id += 1
        return step_id

    def _allocate_tool_call_id(self) -> str:
        tool_call_id = f"call_{self._next_tool_id}"
        self._next_tool_id += 1
        return tool_call_id

    def _extra(self, event_type: str, extra: JsonObject | None = None) -> JsonObject:
        payload: JsonObject = {"event_type": event_type, "backend": self._agent_name}
        if self._source_file:
            payload["source_file"] = self._source_file
        if extra:
            payload.update(extra)
        return payload


def _convert_intermediate_steps_jsonl(input_path: Path, output_path: Path, session_id: str) -> int:
    from nat.data_models.intermediate_step import IntermediateStep
    from nat.utils.atif_converter import IntermediateStepToATIFConverter

    steps: list[IntermediateStep] = []
    for line_number, line in enumerate(input_path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid IntermediateStep JSON on line {line_number} of {input_path}") from exc
        steps.append(IntermediateStep.model_validate(payload))

    trajectory = IntermediateStepToATIFConverter().convert(steps, session_id=session_id)
    _write_atif_trajectory(output_path, trajectory)
    print(f"ATIF trajectory written to {output_path} from {len(steps)} IntermediateStep events")
    return 0


def _latest_jsonl(projects_dir: Path) -> Path:
    files = [path for path in projects_dir.rglob("*.jsonl") if path.is_file()]
    if not files:
        raise FileNotFoundError(f"No session JSONL files found under {projects_dir}")
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return files[0]


def _raw_event_extra(event: JsonObject) -> JsonObject:
    return {
        "event_type": _event_type(event),
        "raw_event": _compact_payload(event),
    }


def _message_content(event: JsonObject) -> JsonValue:
    message = event.get("message")
    if isinstance(message, dict):
        return message.get("content")
    return event.get("content")


def _content_blocks(event: JsonObject) -> list[JsonObject]:
    content = _message_content(event)
    if not isinstance(content, list):
        return []
    return [item for item in content if isinstance(item, dict)]


def _tool_name(block: JsonObject) -> str:
    for key in ("name", "tool_name", "function_name", "function", "tool"):
        value = block.get(key)
        if isinstance(value, str) and value:
            return value
    return "unknown_tool"


def _tool_call_id(block: JsonObject) -> str | None:
    for key in ("id", "tool_call_id", "call_id", "tool_use_id"):
        value = block.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _handle_message_event(builder: _DirectATIFBuilder, event: JsonObject) -> bool:
    event_type = _event_type(event)
    blocks = _content_blocks(event)
    if blocks:
        text_parts: list[str] = []
        tool_calls: list[JsonObject] = []
        observations: list[JsonObject] = []
        for block in blocks:
            block_type = _event_type(block)
            if block_type == "text":
                text = _extract_text(block)
                if text:
                    text_parts.append(text)
            elif block_type in {"tool_use", "tool_call", "function_call"}:
                call_id = _tool_call_id(block) or builder._allocate_tool_call_id()
                tool_calls.append(
                    {
                        "tool_call_id": call_id,
                        "function_name": _tool_name(block),
                        "arguments": _arguments_from_value(block.get("input") or block.get("arguments")),
                        "extra": {"event_type": block_type, "raw_event": _compact_payload(block)},
                    }
                )
            elif block_type == "tool_result":
                observations.append(
                    {
                        "source_call_id": _tool_call_id(block),
                        "content": _extract_text(block) or _compact_payload(block),
                        "extra": {"event_type": block_type, "is_error": bool(block.get("is_error"))},
                    }
                )
        if event_type == "user":
            text_parts = []
        if tool_calls or text_parts:
            builder.add_agent_step(
                message="\n".join(text_parts),
                tool_calls=tool_calls or None,
                extra=_raw_event_extra(event),
            )
        for observation in observations:
            source_call_id = observation.get("source_call_id")
            observation_extra = observation.get("extra")
            builder.add_observation(
                tool_call_id=source_call_id if isinstance(source_call_id, str) else None,
                content=str(observation.get("content") or ""),
                extra=observation_extra if isinstance(observation_extra, dict) else None,
            )
        return bool(tool_calls or observations or text_parts)

    message_text = _extract_text(_message_content(event))
    if event_type in {"assistant", "agent_message", "message"} and message_text:
        builder.add_agent_step(message=message_text, extra=_raw_event_extra(event))
        return True
    return False


def _item_id(item: JsonObject) -> str | None:
    for key in ("id", "item_id", "call_id", "tool_call_id"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _item_kind(item: JsonObject) -> str:
    for key in ("type", "item_type", "kind"):
        value = item.get(key)
        if isinstance(value, str):
            return value
    return ""


def _item_tool_name(item: JsonObject) -> str:
    name = _tool_name(item)
    if name != "unknown_tool":
        return name
    kind = _item_kind(item)
    if "command" in kind:
        return "shell"
    return kind or "unknown_tool"


def _item_arguments(item: JsonObject) -> JsonObject:
    command = item.get("command")
    if isinstance(command, str) and command:
        return {"command": command}
    return _arguments_from_value(item.get("arguments") or item.get("input"))


def _item_output(item: JsonObject) -> str:
    for key in ("aggregated_output", "output", "result", "stdout", "stderr"):
        value = item.get(key)
        text = _extract_text(value)
        if text:
            return text
    exit_code = item.get("exit_code")
    if isinstance(exit_code, int):
        return f"exit code {exit_code}"
    return ""


def _cursor_tool_payload(event: JsonObject) -> JsonObject | None:
    tool_call = event.get("tool_call")
    if not isinstance(tool_call, dict):
        return None
    for value in tool_call.values():
        if isinstance(value, dict):
            return value
    return tool_call


def _cursor_tool_name(event: JsonObject, tool_payload: JsonObject) -> str:
    tool_call = event.get("tool_call")
    if isinstance(tool_call, dict):
        for key in tool_call:
            if key == "shellToolCall":
                return "shell"
            if key.endswith("ToolCall"):
                return key.removesuffix("ToolCall")
    return _tool_name(tool_payload)


def _cursor_tool_arguments(tool_payload: JsonObject) -> JsonObject:
    args = tool_payload.get("args")
    if isinstance(args, dict):
        return args
    return _arguments_from_value(tool_payload.get("arguments") or tool_payload.get("input"))


def _cursor_tool_result(tool_payload: JsonObject) -> str:
    result = tool_payload.get("result")
    if result is None:
        return ""
    return _extract_text(result) or _compact_payload(result)


def _handle_top_level_tool_call_event(builder: _DirectATIFBuilder, event: JsonObject) -> bool:
    if _event_type(event) != "tool_call":
        return False
    tool_payload = _cursor_tool_payload(event)
    if tool_payload is None:
        return False
    call_id = event.get("call_id")
    if not isinstance(call_id, str):
        call_id = _tool_call_id(tool_payload)
    subtype = event.get("subtype")
    if subtype == "started":
        builder.add_tool_call(
            tool_call_id=call_id,
            function_name=_cursor_tool_name(event, tool_payload),
            arguments=_cursor_tool_arguments(tool_payload),
            extra=_raw_event_extra(event),
        )
        return True
    if subtype == "completed":
        if call_id not in builder._pending_tool_step:
            call_id = builder.add_tool_call(
                tool_call_id=call_id,
                function_name=_cursor_tool_name(event, tool_payload),
                arguments=_cursor_tool_arguments(tool_payload),
                extra=_raw_event_extra(event),
            )
        builder.add_observation(
            tool_call_id=call_id,
            content=_cursor_tool_result(tool_payload) or _compact_payload(tool_payload),
            extra=_raw_event_extra(event),
        )
        return True
    return False


def _handle_item_event(builder: _DirectATIFBuilder, event: JsonObject) -> bool:
    item = event.get("item")
    if not isinstance(item, dict):
        return False
    event_type = _event_type(event)
    item_kind = _item_kind(item)
    looks_tool = any(marker in item_kind for marker in ("tool", "command", "function")) or isinstance(
        item.get("command"), str
    )
    if not looks_tool:
        text = _extract_text(item)
        if text and (
            event_type in {"agent_message", "item_completed", "item.completed", "message"}
            or item_kind == "agent_message"
        ):
            builder.add_agent_step(message=text, extra=_raw_event_extra(event))
            return True
        return False

    call_id = _item_id(item)
    if any(marker in event_type for marker in ("started", "created", "begin")):
        builder.add_tool_call(
            tool_call_id=call_id,
            function_name=_item_tool_name(item),
            arguments=_item_arguments(item),
            extra=_raw_event_extra(event),
        )
        return True

    if any(marker in event_type for marker in ("completed", "finished", "end")):
        if call_id not in builder._pending_tool_step:
            call_id = builder.add_tool_call(
                tool_call_id=call_id,
                function_name=_item_tool_name(item),
                arguments=_item_arguments(item),
                extra=_raw_event_extra(event),
            )
        output = _item_output(item) or _compact_payload(item)
        extra = _raw_event_extra(event)
        exit_code = item.get("exit_code")
        if isinstance(exit_code, int):
            extra["exit_code"] = exit_code
        builder.add_observation(tool_call_id=call_id, content=output, extra=extra)
        return True

    return False


def _final_message_from_events(events: Sequence[JsonObject]) -> str:
    for event in reversed(events):
        event_type = _event_type(event)
        if event_type in {"result", "final", "agent_message", "assistant", "message", "turn_completed"}:
            text = _extract_text(event)
            if text:
                return text
        item = event.get("item")
        if isinstance(item, dict) and _item_kind(item) == "agent_message":
            text = _extract_text(item)
            if text:
                return text
    return ""


def _convert_claude_session(
    *,
    projects_dir: Path,
    output_path: Path,
    instruction_path: Path | None,
    final_message_path: Path | None,
) -> int:
    session_path = _latest_jsonl(projects_dir)
    events = _read_jsonl(session_path)
    if not events:
        raise ValueError(f"Claude session file contains no JSON events: {session_path}")
    instruction = _load_instruction(instruction_path)
    if not instruction:
        for event in events:
            if _event_type(event) == "user":
                text = _extract_text(_message_content(event))
                if text:
                    instruction = text
                    break
    builder = _DirectATIFBuilder(agent_name="claude-code", instruction=instruction, source_file=str(session_path))
    for event in events:
        _handle_message_event(builder, event)
    final_message = _read_final_message(final_message_path) or _final_message_from_events(events)
    _write_json(output_path, builder.finalize(final_message=final_message))
    print(f"ATIF trajectory written to {output_path} from Claude session {session_path}")
    return 0


def _convert_agent_jsonl(
    *,
    input_path: Path,
    output_path: Path,
    instruction_path: Path | None,
    final_message_path: Path | None,
    agent_name: str,
    write_final_message: bool = False,
) -> int:
    events = _read_jsonl(input_path)
    if not events:
        raise ValueError(f"Agent log contains no JSON events: {input_path}")
    builder = _DirectATIFBuilder(
        agent_name=agent_name,
        instruction=_load_instruction(instruction_path),
        source_file=str(input_path),
    )
    handled = False
    for event in events:
        handled = (
            _handle_message_event(builder, event)
            or _handle_top_level_tool_call_event(builder, event)
            or _handle_item_event(builder, event)
            or handled
        )
    final_message = _read_final_message(final_message_path) or _final_message_from_events(events)
    if write_final_message:
        _write_final_message_artifact(final_message_path, final_message)
    if not handled and not final_message:
        raise ValueError(f"No convertible {agent_name} events found in {input_path}")
    _write_json(output_path, builder.finalize(final_message=final_message))
    print(f"ATIF trajectory written to {output_path} from {agent_name} events in {input_path}")
    return 0


def _read_http_response(url: str, payload: bytes, timeout: int) -> str:
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _iter_sse_data(text: str) -> Sequence[str]:
    events: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            if current:
                events.append("\n".join(current))
                current = []
            continue
        if line.startswith("data:"):
            current.append(line.removeprefix("data:").strip())
    if current:
        events.append("\n".join(current))
    if not events and text.strip():
        events.append(text.strip())
    return events


def _decode_json_event(raw_event: str) -> JsonValue:
    try:
        return json.loads(raw_event)
    except json.JSONDecodeError:
        return raw_event


def _assemble_atif_stream(events: Sequence[JsonValue]) -> tuple[JsonObject | None, JsonValue]:
    from nat.atif import ATIFTrajectory

    # TODO: If /generate/atif starts emitting raw IntermediateStep events, replace
    # this assembler with nat.utils.atif_converter.ATIFStreamConverter.
    steps: list[JsonObject] = []
    summary: JsonObject | None = None
    final_result: JsonValue = ""

    for event in events:
        if not isinstance(event, dict):
            if event not in ("", None):
                final_result = event
            continue
        if "code" in event and event.get("code") == "workflow_error":
            raise RuntimeError(str(event))
        if "step_id" in event and "source" in event:
            steps.append(event)
            continue
        if "schema_version" in event and "session_id" in event and "agent" in event:
            summary = event
            continue
        final_result = event

    if summary is None:
        return None, final_result

    trajectory: JsonObject = {
        "schema_version": summary["schema_version"],
        "session_id": summary["session_id"],
        "agent": summary["agent"],
        "steps": _json_object_array(steps),
    }
    final_metrics = summary.get("final_metrics")
    if final_metrics is not None:
        trajectory["final_metrics"] = final_metrics

    validated = ATIFTrajectory.model_validate(trajectory)
    return _trajectory_to_json_dict(validated), final_result


def _invoke_aut(endpoint: str, instruction: str, output_dir: Path, timeout: int) -> int:
    payload = json.dumps({"input_message": instruction}).encode("utf-8")
    base_endpoint = endpoint.rstrip("/")
    output_dir.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None

    atif_url = f"{base_endpoint}/generate/atif"
    for attempt in range(3):
        try:
            response_text = _read_http_response(atif_url, payload, timeout)
            events = [_decode_json_event(raw_event) for raw_event in _iter_sse_data(response_text)]
            trajectory, final_result = _assemble_atif_stream(events)
            if trajectory is not None:
                _write_json(output_dir / "trajectory.json", trajectory)
            _write_json(output_dir / "atif_stream_events.json", events)
            _write_final_message(output_dir, final_result)
            print(json.dumps({"result": final_result}))
            return 0
        except urllib.error.HTTPError as err:
            last_error = err
            if err.code in {404, 422}:
                break
            raise
        except urllib.error.URLError as err:
            last_error = err
            if attempt < 2:
                time.sleep(1.0)
                continue
            raise

    for suffix in ("/generate/full?filter_steps=none", "/generate"):
        fallback_url = urllib.parse.urljoin(f"{base_endpoint}/", suffix.removeprefix("/"))
        try:
            response_text = _read_http_response(fallback_url, payload, timeout)
            print(response_text)
            try:
                _write_final_message(output_dir, json.loads(response_text))
            except json.JSONDecodeError:
                _write_final_message(output_dir, response_text.strip())
            return 0
        except urllib.error.HTTPError as err:
            last_error = err
            if err.code in {404, 422}:
                continue
            raise

    if last_error is not None:
        raise last_error
    raise RuntimeError("AUT invocation failed: no endpoint variants succeeded")


def _convert_jsonl_command(args: argparse.Namespace) -> int:
    return _convert_intermediate_steps_jsonl(
        input_path=Path(args.input),
        output_path=Path(args.output),
        session_id=args.session_id or str(uuid.uuid4()),
    )


def _convert_claude_session_command(args: argparse.Namespace) -> int:
    return _convert_claude_session(
        projects_dir=Path(args.projects_dir),
        output_path=Path(args.output),
        instruction_path=Path(args.instruction) if args.instruction else None,
        final_message_path=Path(args.final_message) if args.final_message else None,
    )


def _convert_codex_jsonl_command(args: argparse.Namespace) -> int:
    return _convert_agent_jsonl(
        input_path=Path(args.input),
        output_path=Path(args.output),
        instruction_path=Path(args.instruction) if args.instruction else None,
        final_message_path=Path(args.final_message) if args.final_message else None,
        agent_name="codex",
    )


def _convert_cursor_jsonl_command(args: argparse.Namespace) -> int:
    return _convert_agent_jsonl(
        input_path=Path(args.input),
        output_path=Path(args.output),
        instruction_path=Path(args.instruction) if args.instruction else None,
        final_message_path=Path(args.final_message) if args.final_message else None,
        agent_name="cursor-agent",
        write_final_message=True,
    )


def _invoke_aut_command(args: argparse.Namespace) -> int:
    instruction = Path(args.instruction).read_text(encoding="utf-8")
    return _invoke_aut(
        endpoint=args.endpoint,
        instruction=instruction,
        output_dir=Path(args.output_dir),
        timeout=args.timeout,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    convert_jsonl = subparsers.add_parser("convert-jsonl", help="Convert NAT IntermediateStep JSONL to ATIF JSON.")
    convert_jsonl.add_argument("--input", required=True)
    convert_jsonl.add_argument("--output", required=True)
    convert_jsonl.add_argument("--session-id")
    convert_jsonl.set_defaults(func=_convert_jsonl_command)

    claude_session = subparsers.add_parser(
        "convert-claude-session",
        help="Convert the newest Claude Code session JSONL to ATIF JSON.",
    )
    claude_session.add_argument("--projects-dir", required=True)
    claude_session.add_argument("--output", required=True)
    claude_session.add_argument("--instruction")
    claude_session.add_argument("--final-message")
    claude_session.set_defaults(func=_convert_claude_session_command)

    codex_jsonl = subparsers.add_parser("convert-codex-jsonl", help="Convert Codex exec JSONL to ATIF JSON.")
    codex_jsonl.add_argument("--input", required=True)
    codex_jsonl.add_argument("--output", required=True)
    codex_jsonl.add_argument("--instruction")
    codex_jsonl.add_argument("--final-message")
    codex_jsonl.set_defaults(func=_convert_codex_jsonl_command)

    cursor_jsonl = subparsers.add_parser(
        "convert-cursor-jsonl",
        help="Convert Cursor Agent stream-json output to ATIF JSON.",
    )
    cursor_jsonl.add_argument("--input", required=True)
    cursor_jsonl.add_argument("--output", required=True)
    cursor_jsonl.add_argument("--instruction")
    cursor_jsonl.add_argument("--final-message")
    cursor_jsonl.set_defaults(func=_convert_cursor_jsonl_command)

    aut = subparsers.add_parser("invoke-aut", help="Invoke a deployed NAT AUT and export ATIF artifacts.")
    aut.add_argument("--endpoint", required=True)
    aut.add_argument("--instruction", required=True)
    aut.add_argument("--output-dir", required=True)
    aut.add_argument("--timeout", type=int, default=600)
    aut.set_defaults(func=_invoke_aut_command)
    return parser


def main() -> int:
    logging.basicConfig(level=logging.WARNING)
    args = _build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
