# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest
from harbor_nemo.names import NameMappingError, from_entity_name, to_entity_name


def test_org_is_folded_into_the_entity_name():
    assert to_entity_name("nvidia", "my-task") == "nvidia.my-task"


def test_round_trips_a_package_name_containing_dots():
    """The decode splits on the *first* dot, so dots in the package name survive."""
    assert from_entity_name(to_entity_name("nvidia", "my.task")) == ("nvidia", "my.task")


def test_rejects_a_dotted_org_rather_than_mis_splitting_it():
    with pytest.raises(NameMappingError, match="contains a '.'"):
        to_entity_name("nvidia.labs", "my-task")


def test_rejects_a_name_over_the_entity_store_limit():
    # 63 is the store's cap, and it is stricter than the evaluator route's own 255 — a name
    # that passes the route can still be rejected by the store, late and opaquely.
    with pytest.raises(NameMappingError, match="63-character"):
        to_entity_name("nvidia", "x" * 60)


def test_rejects_names_the_entity_store_charset_forbids():
    for org, name in [
        ("NVIDIA", "my-task"),  # must start lowercase
        ("9nvidia", "my-task"),  # must start with a letter
        ("nvidia", "my--task"),  # no consecutive hyphens
        ("nvidia", "my-task-"),  # no trailing hyphen
        ("nvidia", "my task"),  # charset
    ]:
        with pytest.raises(NameMappingError):
            to_entity_name(org, name)


def test_name_mapping_error_is_a_value_error():
    """The read path relies on this: a reference NeMo could never have stored is a
    reference NeMo does not have, and `package_type` tells absent from broken by ValueError."""
    assert issubclass(NameMappingError, ValueError)


def test_entity_name_without_a_separator_is_rejected():
    with pytest.raises(NameMappingError, match="no '.'"):
        from_entity_name("plain-name")
