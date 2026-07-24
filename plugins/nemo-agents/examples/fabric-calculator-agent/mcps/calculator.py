# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""A toy calculator exposed as an MCP stdio server."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("fabric-calculator")


@mcp.tool()
def add(numbers: list[float]) -> float:
    """Add two or more numbers."""
    if len(numbers) < 2:
        raise ValueError("add requires at least two numbers")
    return sum(numbers)


@mcp.tool()
def subtract(left: float, right: float) -> float:
    """Subtract right from left."""
    return left - right


@mcp.tool()
def multiply(numbers: list[float]) -> float:
    """Multiply two or more numbers."""
    if len(numbers) < 2:
        raise ValueError("multiply requires at least two numbers")
    result = 1.0
    for number in numbers:
        result *= number
    return result


@mcp.tool()
def divide(dividend: float, divisor: float) -> float:
    """Divide dividend by divisor."""
    if divisor == 0:
        raise ValueError("cannot divide by zero")
    return dividend / divisor


@mcp.tool()
def compare(left: float, right: float) -> str:
    """Compare two numbers."""
    if left > right:
        relation = "greater than"
    elif left < right:
        relation = "less than"
    else:
        relation = "equal to"
    return f"{left:g} is {relation} {right:g}"


def main() -> None:
    """Run the calculator MCP server over stdio."""
    mcp.run(transport="stdio")
