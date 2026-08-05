# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the skills base module."""

from nemo_platform_ext.cli.commands.skills.base import Scope, installed_skill_name


def test_scope_enum_has_project_and_user():
    assert Scope.PROJECT.value == "project"
    assert Scope.USER.value == "user"


def test_scope_enum_members():
    assert set(Scope) == {Scope.PROJECT, Scope.USER}


def test_installed_skill_name_adds_nemo_prefix_once():
    assert installed_skill_name("inference") == "nemo-inference"
    assert installed_skill_name("nemo-files") == "nemo-files"
