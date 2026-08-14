<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

## NOTE This prompt is a low frequency prompt for use when updating the flows. Probably I should create a skill.

Under tests/agentic-use/agentic_flows, I've listed all the flows we're trying to cover with CLI and MCP tests across many markdown files. Under tests/agentic-use, there are a large numbe of evals already present.

Your task is:

1) Examine all the agentic flows that do not have evals, and compare against the current set of evals. Each eval has a README.md and an instruction.md that outlines what it does.
2) Update the agentic_flows markdowns to match the current set of implemented evals. DO NOT ADD NEW FLOWS, just mark which flows are covered.
3) Examine the tickets to be sure all the status there appear correct. Mark any that should be done as done.

Then, output a list of every change you've found, including:

1) New evals added.
2) Evals removed.
3) Evals that don't appear to match an agentic flow.
4) Ticket statuses that were incorrect.

Again: make sure the agentic flow are updated to match the evals added, and the tickets are updated.
