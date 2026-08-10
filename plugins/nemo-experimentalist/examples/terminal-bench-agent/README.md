# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Terminal-Bench LangChain agent

This deliberately small agent runs directly in each canonical Harbor task
container. Harbor uploads a static `uv` binary, installs uv-managed Python
3.12, synchronizes the locked dependencies, and invokes `python -m main` with
`/app` as the working directory.

The agent has one LangChain tool: execute a bounded shell command in `/app`.
It calls the NVIDIA Inference Gateway using `INFERENCE_API_KEY` and writes
OpenInference spans in OTLP JSONL format under `/app/traces`; the wrapper also
publishes them to `/logs/artifacts/traces` for task-authored evaluators.

No Docker socket, sidecar container, system Python, package manager, `curl`, or
task-definition modification is required.
