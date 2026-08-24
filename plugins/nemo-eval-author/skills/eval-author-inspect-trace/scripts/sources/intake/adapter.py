# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Adapt an Intake trace to the generic inspection bundle."""

import argparse
from typing import Any, NoReturn

from sources.intake._http import IntakeClient, IntakeError
from sources.intake.reader import read_trace


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError(f"Intake source arguments are invalid: {message}")


def read_source(trace_ref: str, arguments: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read one Intake trace and return its source identity and evidence."""
    parser = _ArgumentParser(add_help=False)
    parser.add_argument("--workspace", required=True)
    args = parser.parse_args(arguments)

    try:
        client = IntakeClient.from_env(args.workspace)
        trace = read_trace(client, trace_ref)
    except IntakeError as exc:
        raise ValueError(str(exc)) from exc

    source = {
        "kind": "intake",
        "trace_ref": trace["trace_ref"],
        "context": {
            "platform_origin": client.base_url,
            "workspace": client.workspace,
        },
    }
    return source, trace
