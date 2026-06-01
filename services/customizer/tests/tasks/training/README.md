# Training Task Tests

This directory contains tests for the Customizer training task code.

## Testing Strategy

Tests follow the platform pattern of **heavy mocking at boundaries**:

1. **CPU-safe code**: Direct unit tests (no mocking needed)
2. **Code that uses GPU libs conditionally**: Structure imports to be conditional, mock in tests  
3. **Code that must use GPU libs**: Use `@pytest.mark.gpu_integration` marker, run in GPU container

## Test Categories

### Unit Tests (run in regular CI)

These tests have no GPU library dependencies and run in the standard CI environment:

| Test File | Description |
|-----------|-------------|
| `test_distributed.py` | Tests for `DistributedContext` file-based barriers |
| `test_schemas.py` | Tests for Pydantic schemas (if added) |
| `test_chat_templates.py` | Tests for chat template resolution (if added) |
| `test_runner.py` | Tests for `TrainingRunner` with mocked backend (if added) |

**How they work:**
- Auto-marked as `unit` by `conftest.py` (no explicit marker needed)
- Run automatically in CI via `make test-unit` or `make test-unit-ci`

### GPU Integration Tests (run in GPU container)

These tests require GPU libraries and are marked with `@pytest.mark.gpu_integration`:

| Test File | Description |
|-----------|-------------|
| `test_checkpoints_integration.py` | Tests for checkpoint processing with real transformers (if added) |
| `test_finetune_integration.py` | Tests for training recipe wrappers (if added) |

**How they work:**
- Marked explicitly with `@pytest.mark.gpu_integration`
- Run in GPU containers via `make test-gpu-integration EXTRA=cu129`
- Excluded from regular CI unit tests

## Running Tests

### Run unit tests (regular CI):

```bash
# Run all training unit tests
uv run pytest services/customizer/tests/tasks/training/ -v -m unit

# Run specific test file
uv run pytest services/customizer/tests/tasks/training/test_distributed.py -v
```

### Run GPU integration tests (requires GPU container):

```bash
# Run GPU integration tests
make test-gpu-integration EXTRA=cu129
```

## Writing New Tests

### For CPU-safe code (no mocking needed):

```python
"""Tests for distributed module (CPU-safe, no GPU dependencies)."""

from nmp.customizer.tasks.training.distributed import DistributedContext


class TestDistributedContext:
    """No marker needed - auto-marked as 'unit' by conftest.py."""

    def test_something(self, tmp_path):
        ctx = DistributedContext.from_env(tmp_path / "barriers")
        assert ctx.is_coordinator
```

### For code with conditional GPU imports (mock the imports):

```python
"""Tests for runner module (mocks GPU-dependent backend)."""

from unittest.mock import MagicMock, patch

from nmp.customizer.tasks.training.runner import TrainingRunner


class TestTrainingRunner:
    """Test runner with mocked backend via dependency injection."""

    def test_run_with_mocked_backend(self, tmp_path):
        # Create a mock backend
        mock_backend = MagicMock()
        mock_backend.compile_config.return_value = {"key": "value"}
        mock_backend.execute_training.return_value = TrainingMetrics(...)
        
        # Inject the mock backend
        runner = TrainingRunner(backend=mock_backend)
        # ... test runner logic
```

### For GPU-dependent integration tests:

```python
"""GPU integration tests for checkpoint processing.

These tests require transformers/torch and run in GPU containers.
"""

import pytest


@pytest.mark.gpu_integration
class TestCheckpointProcessing:
    """Tests that require actual GPU libraries."""

    def test_merge_lora_adapter(self, tmp_path):
        from transformers import AutoTokenizer
        # ... test with real transformers
```

## Module Classification

| Module | GPU Dependencies | Testing Approach |
|--------|-----------------|------------------|
| `distributed.py` | None | Direct unit tests ✅ |
| `protocol.py` | None | Direct unit tests ✅ |
| `schemas.py` | None | Direct unit tests ✅ |
| `progress.py` | None (uses nmp_common) | Direct unit tests ✅ |
| `chat_templates.py` | None | Direct unit tests ✅ |
| `datasets.py` | None | Direct unit tests ✅ |
| `sequence_packing.py` | None | Direct unit tests ✅ |
| `runner.py` | Conditional (in `_load_backend()`) | Mock backend via DI |
| `utils.py` | `torch` (conditional in function) | Mock `torch` imports |
| `backends/automodel/backend.py` | None (uses subprocess) | Mock subprocess |
| `backends/automodel/config.py` | None | Direct unit tests ✅ |
| `backends/automodel/finetune.py` | `nemo_automodel` (module-level) | GPU integration only |
| `backends/automodel/checkpoints.py` | `torch`, `peft` (in function) | Mock or GPU integration |
| `backends/automodel/callbacks.py` | None | Direct unit tests ✅ |

## Key Design Principles

1. **Defer GPU imports**: Import GPU-heavy libraries inside functions, not at module level
2. **Dependency injection**: Use constructor parameters (like `TrainingRunner(backend=...)`) to inject mocks
3. **Mock at boundaries**: Mock HTTP calls, subprocess, file I/O - not internal logic
4. **Use existing markers**: `gpu_integration` for GPU tests, no custom markers needed
