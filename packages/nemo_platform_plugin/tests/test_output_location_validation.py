# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Syntactic validation of the ``output_location`` job-request field."""

from __future__ import annotations

import pytest
from nemo_platform_plugin.jobs.api_factory import BaseJobRequest
from pydantic import BaseModel, ValidationError


class _Spec(BaseModel):
    pass


def _request(output_location: str | None) -> BaseJobRequest[_Spec]:
    return BaseJobRequest[_Spec](spec=_Spec(), output_location=output_location)


def test_bare_fileset_name_is_accepted() -> None:
    assert _request("my-eval-fileset").output_location == "my-eval-fileset"


def test_value_is_stripped() -> None:
    assert _request("  my-fileset  ").output_location == "my-fileset"


def test_none_is_allowed() -> None:
    assert _request(None).output_location is None


@pytest.mark.parametrize("value", ["", "   "])
def test_empty_is_rejected(value: str) -> None:
    with pytest.raises(ValidationError, match="must not be empty"):
        _request(value)


def test_subpath_is_rejected() -> None:
    with pytest.raises(ValidationError, match="subpath in output_location is not yet supported"):
        _request("my-fileset#runs/2026")


def test_workspace_qualified_name_is_rejected() -> None:
    with pytest.raises(ValidationError, match="bare fileset name"):
        _request("default/my-fileset")
