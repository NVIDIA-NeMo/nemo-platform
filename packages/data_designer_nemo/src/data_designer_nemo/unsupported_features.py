# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from typing import Any

import data_designer.config as dd
from data_designer_nemo.errors import NDDInvalidConfigError

_SUPPORTED_SEED_TYPES = {"hf", "nmp"}
_UNSUPPORTED_SEED_TYPES_MESSAGE = (
    "The NeMo Platform Data Designer service only supports seed data from HuggingFace "
    "(seed_type=hf) or the Files service (seed_type=nmp)."
)
_DATAFRAME_SEED_TYPE = "df"
_DATAFRAME_SEED_TYPE_MESSAGE = (
    "Dataframe seed sources (seed_type=df) are not supported on the NeMo Platform. "
    "Use a serializable seed source such as a local file, directory, HuggingFace, or the Files service."
)


def validate_no_tool_configs(config: dd.DataDesignerConfig) -> None:
    if config.tool_configs and len(config.tool_configs) > 0:
        raise NDDInvalidConfigError("Tool configs are not supported in the NeMo Platform Data Designer service.")


def validate_remote_seed_type(seed_type: str) -> None:
    """Raises if a seed source type is unsupported for remote execution."""
    _validate_seed_type_for_execution_context(seed_type, is_local=False)


def validate_seed_config_for_execution_context(config: dd.DataDesignerConfig, *, is_local: bool) -> None:
    """Raises if a parsed config uses a seed source unsupported in this execution context."""
    seed_type = _get_config_seed_type(config)
    if seed_type is not None:
        _validate_seed_type_for_execution_context(seed_type, is_local=is_local)


def validate_seed_source_for_execution_context(data: Any, *, is_local: bool) -> None:
    """Raises if a raw request seed source is unsupported for the execution context.

    This function is used in Pydantic validators defined on the preview and job request models,
    both of which carry a `config: dd.DataDesignerConfig` field.

    This function is used in "before"-style Pydantic validators, where the data argument is typed
    as Any. We run in the before context to preempt less-useful error messages from the DD library:
    - missing dataframe field (we don't serialize dataframes over the wire)
    - file does not exist (the client's local fs != the service's local fs)

    The validators using this function only care about preventing unsupported seed types. All the
    other standard Pydantic validation will get applied by FastAPI parsing the request; this does
    not bypass that. So, we can safely ignore all Exceptions (most commonly KeyError, on requests
    that don't include a seed_config at all) and index our way straight to the deeply nested field
    we care about for this particular validation.

    Per the Pydantic v2 contract, "before"-mode validators may raise ``ValueError``,
    ``AssertionError``, or ``PydanticCustomError`` — anything else (including our
    ``NDDInvalidConfigError``) propagates raw out of ``model_validate`` and is not wrapped in
    ``pydantic.ValidationError``. That breaks ``except ValidationError`` clauses in CLI / framework
    code that turn validation problems into clean user-facing messages. To keep those code paths
    working *and* keep ``NDDInvalidConfigError`` as the canonical error class for non-Pydantic
    callers, we translate at this boundary: catch the plugin's error class and re-raise as a
    ``ValueError`` carrying the same message.
    """
    seed_type = _get_raw_seed_type(data)
    if seed_type is None:
        return

    try:
        _validate_seed_type_for_execution_context(seed_type, is_local=is_local)
    except NDDInvalidConfigError as exc:
        raise ValueError(str(exc)) from exc


def _validate_seed_type_for_execution_context(seed_type: str, *, is_local: bool) -> None:
    """Raises if a seed source type is unsupported in this execution context."""
    if is_local:
        if seed_type == _DATAFRAME_SEED_TYPE:
            raise NDDInvalidConfigError(_DATAFRAME_SEED_TYPE_MESSAGE)
        return

    if seed_type not in _SUPPORTED_SEED_TYPES:
        raise NDDInvalidConfigError(_UNSUPPORTED_SEED_TYPES_MESSAGE)


def _get_config_seed_type(config: dd.DataDesignerConfig) -> str | None:
    if config.seed_config is None:
        return None

    return config.seed_config.source.seed_type


def _get_raw_seed_type(data: Any) -> str | None:
    try:
        seed_type = data["config"]["seed_config"]["source"]["seed_type"]
    except Exception:
        return None

    return seed_type if isinstance(seed_type, str) else None
