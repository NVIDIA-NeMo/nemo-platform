# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest
from data_designer_nemo.errors import (
    NDDError,
    NDDInternalError,
    NDDInvalidConfigError,
    raise_if_errors,
)


class TestErrorHierarchy:
    def test_invalid_config_error_is_an_ndd_error(self) -> None:
        assert issubclass(NDDInvalidConfigError, NDDError)

    def test_internal_error_is_an_ndd_error(self) -> None:
        assert issubclass(NDDInternalError, NDDError)

    def test_invalid_config_and_internal_are_distinct(self) -> None:
        assert not issubclass(NDDInvalidConfigError, NDDInternalError)
        assert not issubclass(NDDInternalError, NDDInvalidConfigError)


class TestRaiseIfErrors:
    def test_empty_list_is_a_no_op(self) -> None:
        # Must not raise.
        raise_if_errors([])

    def test_single_config_error_raises_invalid_config(self) -> None:
        with pytest.raises(NDDInvalidConfigError) as exc_info:
            raise_if_errors([NDDInvalidConfigError("bad config")])
        assert "bad config" in str(exc_info.value)

    def test_single_internal_error_raises_internal(self) -> None:
        with pytest.raises(NDDInternalError) as exc_info:
            raise_if_errors([NDDInternalError("oops")])
        assert "oops" in str(exc_info.value)

    def test_any_config_error_wins_over_internal(self) -> None:
        """The 422 path takes precedence over the 500 path when both are present."""
        with pytest.raises(NDDInvalidConfigError) as exc_info:
            raise_if_errors(
                [
                    NDDInternalError("internal"),
                    NDDInvalidConfigError("config"),
                ]
            )
        # Both messages must surface in the aggregated body — the exception
        # class only reflects whose fault it primarily is.
        message = str(exc_info.value)
        assert "internal" in message
        assert "config" in message

    def test_only_internal_errors_raise_internal(self) -> None:
        with pytest.raises(NDDInternalError) as exc_info:
            raise_if_errors(
                [
                    NDDInternalError("first"),
                    NDDInternalError("second"),
                ]
            )
        message = str(exc_info.value)
        assert "first" in message
        assert "second" in message

    def test_multiple_config_errors_aggregate(self) -> None:
        with pytest.raises(NDDInvalidConfigError) as exc_info:
            raise_if_errors(
                [
                    NDDInvalidConfigError("first"),
                    NDDInvalidConfigError("second"),
                ]
            )
        message = str(exc_info.value)
        assert "first" in message
        assert "second" in message
