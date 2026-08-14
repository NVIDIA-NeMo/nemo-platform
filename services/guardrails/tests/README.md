<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Guardrails Service Tests

## Running Tests

### Basic Commands

```bash
# From guardrails service directory
cd services/guardrails

# Run all Guardrails service tests
uv run pytest

# Run tests in specific folder
uv run pytest tests/workflow/
```

### Common Scenarios

**Run specific test file:**
```bash
uv run pytest tests/workflow/test_chat_completions.py
```

**Run specific test class or function:**
```bash
uv run pytest tests/workflow/test_chat_completions.py::TestChatCompletionsCommon
uv run pytest tests/workflow/test_chat_completions.py::TestChatCompletionsCommon::test_chat_completions_safe_request
```

**Run tests with verbose output (-v) and logging (-s):**
```bash
uv run pytest tests/workflow/ -v -s
```

### Workflow Tests
The "workflow" tests are a hybrid of unit and integration tests. These tests instantiate a FastAPI app and test a full workflow, but only mock the underlying network calls to LLMs. This type of testing is helpful for Guardrails because much of the business logic and actual inference calls are handled by the underlying SDK. Unit tests mock these dependencies, and e2e tests are expensive to write and maintain, so the surface area of scenarios they can cover may not be as large. Workflow tests are a good middle ground: they're quick to write and run, can be easily parameterized to test a variety of scenarios, and are executed as part of the test step in CI.

### E2E Tests
The `RUN_E2E_TESTS=true` environment variable must be set to run e2e tests. There are several other envrionment variables you can use to configure the behavior of these tests - see the `BaseGuardrailsE2ETest` class in `tests/e2e/base_e2e_test.py` for a comprehensive list.

If running these tests manually, you'll most likely want to run them against a locally-deployed instance of Guardrails.

To run against a locally-deployed instance of Guardrails, using NIMs deployed at a central URL: use the following command:
```bash
RUN_E2E_TESTS=True GUARDRAILS_URL=<YOUR_GUARDRAILS_URL> MODEL_ID=meta/llama-3.3-70b-instruct NIM_URL=<NIM_URL> NIM_INTERNAL_URL=<NIM_URL> uv run --frozen pytest
```
A few notes:
- You can use any deployed model for `MODEL_ID`.
- `NIM_INTERNAL_URL` is used as the base URL for guardrail models. When using your locally-deployed Guardrails, this should be the NIM Proxy external URL (since your deployment can't access the internal service URL).
