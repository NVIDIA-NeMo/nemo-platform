# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from nmp.platform_runner import run
from rich.console import Console


class PolicyWasmError(Exception):
    pass


PolicyWasmError.__module__ = "nmp.core.auth.app.embedded_pdp.policy_wasm"


def test_policy_wasm_error_is_expected_startup_error():
    assert run._is_policy_wasm_error(PolicyWasmError("boom"))
    assert not run._is_policy_wasm_error(RuntimeError("boom"))


def test_policy_wasm_error_renders_as_panel(tmp_path, monkeypatch):
    stderr = tmp_path / "stderr.txt"
    console = Console(file=stderr.open("w"), force_terminal=False, width=100)
    monkeypatch.setattr(run, "error_console", console)

    run._display_policy_wasm_error(
        PolicyWasmError(
            "Failed to build embedded auth PDP policy.wasm.\n\n"
            "Command:\n"
            "  script/build_policy_wasm.sh\n\n"
            "Offline options:\n"
            "  OPA_BIN=/path/to/opa ./script/build_policy_wasm.sh"
        )
    )

    output = stderr.read_text()
    assert "Embedded Auth Policy WASM Startup Failed" in output
    assert "script/build_policy_wasm.sh" in output
    assert "OPA_BIN=/path/to/opa" in output
