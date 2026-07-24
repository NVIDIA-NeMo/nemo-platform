# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministic calculator CLI used by the Fabric calculator example."""

from __future__ import annotations

import argparse
import math
from collections.abc import Sequence
from decimal import Decimal


def calculate(operation: str, numbers: Sequence[Decimal]) -> str:
    """Apply a calculator operation and return its display value."""
    if operation in {"add", "multiply"} and len(numbers) < 2:
        raise ValueError(f"{operation} requires at least two numbers")
    if operation in {"subtract", "divide", "compare"} and len(numbers) != 2:
        raise ValueError(f"{operation} requires exactly two numbers")

    if operation == "add":
        return _format_decimal(sum(numbers, start=Decimal(0)))
    if operation == "subtract":
        return _format_decimal(numbers[0] - numbers[1])
    if operation == "multiply":
        return _format_decimal(math.prod(numbers, start=Decimal(1)))
    if operation == "divide":
        if numbers[1] == 0:
            raise ValueError("cannot divide by zero")
        return _format_decimal(numbers[0] / numbers[1])
    if operation == "compare":
        if numbers[0] > numbers[1]:
            relation = "greater than"
        elif numbers[0] < numbers[1]:
            relation = "less than"
        else:
            relation = "equal to"
        return f"{_format_decimal(numbers[0])} is {relation} {_format_decimal(numbers[1])}"

    raise ValueError(f"unsupported operation: {operation}")


def _format_decimal(value: Decimal) -> str:
    normalized = format(value, "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return "0" if normalized in {"-0", ""} else normalized


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Perform a calculator operation.")
    parser.add_argument("operation", choices=("add", "subtract", "multiply", "divide", "compare"))
    parser.add_argument("numbers", nargs="+", type=Decimal)
    return parser


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    try:
        result = calculate(args.operation, args.numbers)
    except ValueError as error:
        parser.error(str(error))
    print(result)


if __name__ == "__main__":
    main()
