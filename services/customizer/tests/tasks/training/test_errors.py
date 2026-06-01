# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Tests for Customizer training error handling.

Tests the error mapping framework integration with Customizer:
- Exception classes and EXCEPTION_REGISTRY
- Error rules loading from YAML
- Exception conversion for Automodel errors via create_error_details()
- Subprocess error parsing (parse_error_from_output)
- End-to-end subprocess→parser→converter flow for NeMo-RL errors
- Error details generation for Jobs service reporting
"""

import subprocess
from collections import deque

from nmp.customizer.tasks.training.errors.converter import (
    ErrorDetails,
    create_error_details,
    get_error_converter,
)
from nmp.customizer.tasks.training.errors.exceptions import (
    EXCEPTION_REGISTRY,
    CheckpointError,
    CudaError,
    CustomizerTrainingError,
    DatasetFormatError,
    DistributedError,
    InternalError,
    ModelLoadError,
    TrainingConfigError,
    TrainingTimeoutError,
    default_exception_handler,
)
from nmp.customizer.tasks.training.errors.parser import (
    ParsedError,
    parse_error_from_output,
)

# =============================================================================
# EXCEPTION CLASS TESTS
# =============================================================================


class TestCustomizerTrainingError:
    """Tests for CustomizerTrainingError base class."""

    def test_exception_with_message_only(self):
        """Test creating exception with just a message."""
        exc = CustomizerTrainingError(message="Test error")
        assert exc.message == "Test error"
        assert exc.detail is None
        assert str(exc) == "Test error"

    def test_exception_with_message_and_detail(self):
        """Test creating exception with message and detail."""
        exc = CustomizerTrainingError(message="Test error", detail="Technical details")
        assert exc.message == "Test error"
        assert exc.detail == "Technical details"

    def test_to_error_details(self):
        """Test converting exception to error details dict."""
        exc = DatasetFormatError(message="Invalid role", detail="Got 'invalid'")
        details = exc.to_error_details()

        assert details["message"] == "Invalid role"
        assert details["type"] == "DatasetFormatError"
        assert details["detail"] == "Got 'invalid'"


class TestExceptionSubclasses:
    """Tests for CustomizerTrainingError subclasses."""

    def test_all_subclasses_have_user_message(self):
        """All subclasses should have a user_message class attribute."""
        subclasses = [
            DatasetFormatError,
            TrainingConfigError,
            ModelLoadError,
            CheckpointError,
            CudaError,
            DistributedError,
            TrainingTimeoutError,
            InternalError,
        ]
        for cls in subclasses:
            assert hasattr(cls, "user_message"), f"{cls.__name__} missing user_message"
            assert cls.user_message, f"{cls.__name__}.user_message is empty"


class TestExceptionRegistry:
    """Tests for EXCEPTION_REGISTRY."""

    def test_registry_contains_all_exceptions(self):
        """Registry should contain all exception classes."""
        expected = [
            "CustomizerTrainingError",
            "DatasetFormatError",
            "TrainingConfigError",
            "ModelLoadError",
            "CheckpointError",
            "CudaError",
            "DistributedError",
            "TrainingTimeoutError",
            "InternalError",
        ]
        for name in expected:
            assert name in EXCEPTION_REGISTRY
            assert issubclass(EXCEPTION_REGISTRY[name], Exception)


# =============================================================================
# DEFAULT HANDLER TESTS
# =============================================================================


class TestDefaultExceptionHandler:
    """Tests for default_exception_handler."""

    def test_creates_customizer_exception_with_details(self):
        """Handler should create exception with error_details as message."""
        original = ValueError("Original error")
        result = default_exception_handler(DatasetFormatError, original, "Custom user message")

        assert isinstance(result, DatasetFormatError)
        assert result.message == "Custom user message"
        assert result.detail == "ValueError: Original error"

    def test_creates_customizer_exception_without_details(self):
        """Handler should use class default message when no error_details."""
        original = ValueError("Original error")
        result = default_exception_handler(DatasetFormatError, original, None)

        assert isinstance(result, DatasetFormatError)
        assert result.message == DatasetFormatError.user_message
        assert result.detail == "ValueError: Original error"


# =============================================================================
# ERROR CONVERTER TESTS
# =============================================================================


class TestGetErrorConverter:
    """Tests for get_error_converter."""

    def test_returns_converter(self):
        """Should return a configured ExceptionConverter."""
        converter = get_error_converter()
        assert converter is not None
        assert converter.rule_count > 0

    def test_returns_same_instance(self):
        """Should return the same singleton instance."""
        converter1 = get_error_converter()
        converter2 = get_error_converter()
        assert converter1 is converter2


# =============================================================================
# AUTOMODEL ERROR CONVERSION TESTS (via create_error_details)
# =============================================================================


class TestAutomodelDatasetErrors:
    """Tests for Automodel dataset error conversion."""

    def test_unsupported_role_error(self):
        """Should convert unsupported role ValueError to DatasetFormatError."""
        original = ValueError("Unsupported role in messages: invalid_role")
        details = create_error_details(original)

        assert details["type"] == "DatasetFormatError"
        assert "invalid role" in details["message"].lower()

    def test_unrelated_value_error_uses_fallback(self):
        """Unrelated ValueError should use InternalError fallback."""
        original = ValueError("Something completely different")
        details = create_error_details(original)

        # Should fall back to InternalError
        assert details["type"] == "InternalError"


class TestAutomodelModelLoadErrors:
    """Tests for Automodel model load error conversion."""

    def test_weight_swap_failure(self):
        """Should convert weight swap RuntimeError to ModelLoadError."""
        original = RuntimeError("_apply(): Couldn't swap Linear.weight")
        details = create_error_details(original)

        assert details["type"] == "ModelLoadError"
        assert "weights could not be applied" in details["message"].lower()

    def test_patch_failure(self):
        """Should convert patch failure to ModelLoadError."""
        original = RuntimeError("Failed to patch model")
        details = create_error_details(original)

        assert details["type"] == "ModelLoadError"
        assert "optimizations" in details["message"].lower()

    def test_signature_mismatch(self):
        """Should convert signature mismatch to ModelLoadError."""
        original = AssertionError("Signature mismatch:\n  original: foo\n  patched : bar")
        details = create_error_details(original)

        assert details["type"] == "ModelLoadError"
        assert "signature" in details["message"].lower()

    def test_missing_lm_head(self):
        """Should convert missing lm_head to ModelLoadError."""
        original = ValueError("lm_head.weight not found in model")
        details = create_error_details(original)

        assert details["type"] == "ModelLoadError"
        assert "language model head" in details["message"].lower()


class TestAutomodelTrainingConfigErrors:
    """Tests for Automodel training config error conversion."""

    def test_tied_embeddings_error(self):
        """Should convert tied embeddings error to TrainingConfigError."""
        original = ValueError(
            "Model 'test-model' is not compatible with pipeline parallelism:\n\n"
            "1. tie_word_embeddings=True is not supported for pipelining."
        )
        details = create_error_details(original)

        assert details["type"] == "TrainingConfigError"
        assert "tied embeddings" in details["message"].lower()

    def test_encoder_decoder_error(self):
        """Should convert encoder-decoder error to TrainingConfigError."""
        original = ValueError(
            "Model 'test-model' is not compatible with pipeline parallelism:\n\n"
            "1. Encoder-Decoder models with cross-attention are not supported yet."
        )
        details = create_error_details(original)

        assert details["type"] == "TrainingConfigError"
        assert "encoder-decoder" in details["message"].lower()

    def test_pp_batch_size_error(self):
        """Should convert PP batch size error to TrainingConfigError."""
        original = AssertionError("pp_batch_size // pp_microbatch_size must be >= pp_size")
        details = create_error_details(original)

        assert details["type"] == "TrainingConfigError"
        assert "pipeline parallelism" in details["message"].lower()

    def test_sdpa_error(self):
        """Should convert SDPA error to TrainingConfigError."""
        original = ValueError("Model does not support SDPA required for context parallelism")
        details = create_error_details(original)

        assert details["type"] == "TrainingConfigError"
        assert "SDPA" in details["message"] or "context parallelism" in details["message"].lower()

    def test_triton_not_installed(self):
        """Should convert triton import error to TrainingConfigError."""
        original = ImportError("triton is not installed. Please install it.")
        details = create_error_details(original)

        assert details["type"] == "TrainingConfigError"
        assert "triton" in details["message"].lower()

    def test_lora_dimensions_mismatch(self):
        """Should convert LoRA dimensions error to TrainingConfigError."""
        original = AssertionError("Incompatible X and LoRA A dimensions")
        details = create_error_details(original)

        assert details["type"] == "TrainingConfigError"
        assert "LoRA" in details["message"]


class TestAutomodelCheckpointErrors:
    """Tests for Automodel checkpoint error conversion."""

    def test_checkpoint_directory_exists(self):
        """Should convert checkpoint exists error to CheckpointError."""
        original = AssertionError("Checkpoint directory /path/to/ckpt already exists")
        details = create_error_details(original)

        assert details["type"] == "CheckpointError"
        assert "already exists" in details["message"].lower()

    def test_global_plan_validation(self):
        """Should convert global plan error to CheckpointError."""
        original = ValueError("Failed to validate global plan")
        details = create_error_details(original)

        assert details["type"] == "CheckpointError"
        assert "validation failed" in details["message"].lower()

    def test_missing_checkpoint_key(self):
        """Should convert missing key error to CheckpointError."""
        original = RuntimeError("Missing key in checkpoint state_dict: model.layer.weight")
        details = create_error_details(original)

        assert details["type"] == "CheckpointError"
        assert "missing" in details["message"].lower()

    def test_moe_expert_weights_missing(self):
        """Should convert MoE expert weights error to CheckpointError."""
        original = RuntimeError("Expert weights missing from checkpoint for layer 0")
        details = create_error_details(original)

        assert details["type"] == "CheckpointError"
        assert "MoE" in details["message"] or "expert" in details["message"].lower()


class TestAutomodelCudaErrors:
    """Tests for Automodel CUDA error conversion."""

    def test_cuda_oom_message(self):
        """Should convert CUDA OOM message to CudaError."""
        original = RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB")
        details = create_error_details(original)

        assert details["type"] == "CudaError"
        assert "memory" in details["message"].lower()

    def test_out_of_memory_generic(self):
        """Should convert generic OOM to CudaError."""
        original = RuntimeError("out of memory")
        details = create_error_details(original)

        assert details["type"] == "CudaError"

    def test_cuda_error_generic(self):
        """Should convert generic CUDA error to CudaError."""
        original = RuntimeError("CUDA error: device-side assert triggered")
        details = create_error_details(original)

        assert details["type"] == "CudaError"


class TestAutomodelDistributedErrors:
    """Tests for Automodel distributed error conversion."""

    def test_distributed_not_available(self):
        """Should convert distributed not available to DistributedError."""
        original = RuntimeError("torch.distributed not available")
        details = create_error_details(original)

        assert details["type"] == "DistributedError"
        assert "not available" in details["message"].lower()

    def test_distributed_not_initialized(self):
        """Should convert not initialized to DistributedError."""
        original = RuntimeError("expected torch.distributed to be initialized")
        details = create_error_details(original)

        assert details["type"] == "DistributedError"
        assert "not properly initialized" in details["message"].lower()

    def test_nccl_error(self):
        """Should convert NCCL error to DistributedError."""
        original = RuntimeError("NCCL error in: ncclAllReduce")
        details = create_error_details(original)

        assert details["type"] == "DistributedError"
        assert "NCCL" in details["message"]

    def test_timeout_in_cause_chain(self):
        """Should convert exception with TimeoutError in cause chain to DistributedError."""
        # Create an exception chain: RuntimeError caused by TimeoutError
        timeout_exc = TimeoutError("Timed out waiting for worker")
        original = RuntimeError("Distributed operation failed")
        original.__cause__ = timeout_exc

        details = create_error_details(original)

        assert details["type"] == "DistributedError"
        assert "timed out" in details["message"].lower()

    def test_timeout_in_nested_cause_chain(self):
        """Should find TimeoutError recursively in nested cause chain."""
        # Create a deeper chain: RuntimeError -> ValueError -> TimeoutError
        timeout_exc = TimeoutError("Connection timed out")
        middle_exc = ValueError("Worker communication failed")
        middle_exc.__cause__ = timeout_exc
        original = RuntimeError("Training failed")
        original.__cause__ = middle_exc

        details = create_error_details(original)

        assert details["type"] == "DistributedError"
        assert "timed out" in details["message"].lower()


class TestAutomodelTimeoutError:
    """Tests for training timeout error conversion."""

    def test_subprocess_timeout(self):
        """Should convert subprocess.TimeoutExpired to TrainingTimeoutError."""
        original = subprocess.TimeoutExpired(cmd="torchrun", timeout=3600)
        details = create_error_details(original)

        assert details["type"] == "TrainingTimeoutError"
        assert "time limit" in details["message"].lower()


class TestAutomodelInternalErrors:
    """Tests for Automodel internal error conversion."""

    def test_pipeline_missing_inputs(self):
        """Should convert missing inputs to InternalError."""
        original = ValueError("You must provide either input_ids or inputs_embeds")
        details = create_error_details(original)

        assert details["type"] == "InternalError"
        assert "pipeline" in details["message"].lower()

    def test_pipeline_missing_embeddings(self):
        """Should convert missing embeddings to InternalError."""
        original = ValueError("inputs_embeds must be provided for pipeline stages without embed_tokens")
        details = create_error_details(original)

        assert details["type"] == "InternalError"
        assert "pipeline" in details["message"].lower()

    def test_moe_mesh_error(self):
        """Should convert MoE mesh error to ParallelismConfigError."""
        original = AssertionError("We only support 1D mesh for MoE")
        details = create_error_details(original)

        assert details["type"] == "ParallelismConfigError"
        assert "moe" in details["message"].lower()

    def test_dtensor_placement_error(self):
        """Should convert DTensor placement error to ParallelismConfigError."""
        original = ValueError("tensor has unsupported DTensor placement: Partial")
        details = create_error_details(original)

        assert details["type"] == "ParallelismConfigError"
        assert "moe" in details["message"].lower() or "expert" in details["message"].lower()

    def test_fused_loss_error(self):
        """Should convert fused loss error to InternalError."""
        original = ValueError("FusedLinearCrossEntropy requires the model to output hidden states")
        details = create_error_details(original)

        assert details["type"] == "InternalError"
        assert "hidden states" in details["message"].lower()


# =============================================================================
# SUBPROCESS ERROR PARSING TESTS
# =============================================================================


class TestParseErrorFromOutput:
    """Tests for parse_error_from_output with realistic subprocess output."""

    # -- basic extraction (single-line inputs) --------------------------------

    def test_extracts_type_and_message(self):
        result = parse_error_from_output(deque(["ValueError: invalid input"]), 1)
        assert result == ParsedError("ValueError", "invalid input")

    def test_empty_message_uses_type_as_message(self):
        """Exception with no message should use the type name as the message."""
        result = parse_error_from_output(deque(["ValueError:"]), 1)
        assert result == ParsedError("ValueError", "ValueError")

    def test_whitespace_only_message_uses_type_as_message(self):
        """Exception with whitespace-only message should use the type name."""
        result = parse_error_from_output(deque(["ValueError:   "]), 1)
        assert result == ParsedError("ValueError", "ValueError")

    def test_extracts_runtime_error(self):
        result = parse_error_from_output(
            deque(["RuntimeError: NCCL error in: ncclAllReduce"]),
            1,
        )
        assert result == ParsedError("RuntimeError", "NCCL error in: ncclAllReduce")

    def test_handles_rank_prefix(self):
        """Rank prefixes don't interfere with extraction."""
        result = parse_error_from_output(
            deque(["[rank0]: ValueError: invalid input"]),
            1,
        )
        assert result == ParsedError("ValueError", "invalid input")

    def test_handles_qualified_exception(self):
        """Should handle fully qualified names like torch.cuda.OutOfMemoryError."""
        result = parse_error_from_output(
            deque(["torch.cuda.OutOfMemoryError: CUDA OOM"]),
            1,
        )
        assert result == ParsedError("OutOfMemoryError", "CUDA OOM")

    def test_handles_timestamp_prefix(self):
        result = parse_error_from_output(
            deque(["2024-01-15 10:30:00 ERROR ValueError: bad value"]),
            1,
        )
        assert result == ParsedError("ValueError", "bad value")

    def test_non_exception_lines_fall_back(self):
        """Lines with no exception pattern should trigger the fallback."""
        result = parse_error_from_output(
            deque(["  File 'train.py', line 42", "Loading model weights..."]),
            1,
        )
        assert result.exception_type == "RuntimeError"

    def test_skips_wrapper_exception_lines(self):
        """Wrapper exceptions should be skipped to find the root cause."""
        result = parse_error_from_output(
            deque(
                [
                    "ValueError: the real error",
                    "ChildFailedError: worker 0 failed",
                ]
            ),
            1,
        )
        assert result == ParsedError("ValueError", "the real error")

    def test_preserves_colons_in_message(self):
        """Colons within the message body should be preserved."""
        result = parse_error_from_output(
            deque(["RuntimeError: CUDA error: device-side assert triggered"]),
            1,
        )
        assert result == ParsedError(
            "RuntimeError",
            "CUDA error: device-side assert triggered",
        )

    # -- multi-line / realistic output ----------------------------------------

    def test_empty_output(self):
        result = parse_error_from_output(deque(), returncode=1)
        assert result.exception_type == "RuntimeError"
        assert "exit code" in result.message

    def test_extracts_exception_from_traceback(self):
        """Should find the exception at the bottom of a Python traceback."""
        output = deque(
            [
                "Starting training...",
                "Traceback (most recent call last):",
                '  File "train.py", line 42, in <module>',
                "    validate_config(cfg)",
                '  File "config.py", line 10, in validate_config',
                "ValueError: text must be a string or a list of strings, got <class 'int'>",
            ]
        )
        result = parse_error_from_output(output, 1)
        assert result.exception_type == "ValueError"
        assert result.message == "text must be a string or a list of strings, got <class 'int'>"

    def test_takes_last_exception_not_first(self):
        """In distributed output, the last exception is usually the root cause."""
        output = deque(
            [
                "RuntimeError: Some wrapper error",
                "The above exception was the direct cause of the following exception:",
                "ValueError: the actual root cause message",
            ]
        )
        result = parse_error_from_output(output, 1)
        assert result.exception_type == "ValueError"
        assert result.message == "the actual root cause message"

    def test_deduplicates_distributed_output(self):
        """Distributed training often prints the same error from multiple ranks."""
        output = deque(
            [
                "[rank0]: ValueError: text must be a string",
                "[rank1]: ValueError: text must be a string",
                "[rank2]: ValueError: text must be a string",
            ]
        )
        result = parse_error_from_output(output, 1)
        assert result.exception_type == "ValueError"
        assert result.message == "text must be a string"

    def test_skips_wrapper_exceptions(self):
        """Should skip ChildFailedError wrappers and find the real error."""
        output = deque(
            [
                "RuntimeError: NCCL error in: ncclAllReduce",
                "ChildFailedError: worker 0 failed with exit code 1",
            ]
        )
        result = parse_error_from_output(output, 1)
        assert "NCCL error" in result.message

    def test_fallback_to_error_keywords(self):
        """When no exception line is found, fall back to error-keyword lines."""
        output = deque(
            [
                "Training step 100/1000",
                "CUDA out of memory trying to allocate 2.00 GiB",
                "Killed",
            ]
        )
        result = parse_error_from_output(output, 137)
        assert result.exception_type == "RuntimeError"
        assert "CUDA out of memory" in result.message or "Killed" in result.message

    def test_last_resort_returns_tail(self):
        """When nothing matches, return the last lines of output."""
        output = deque(
            [
                "some opaque binary garbage line 1",
                "some opaque binary garbage line 2",
            ]
        )
        result = parse_error_from_output(output, 1)
        assert result.exception_type == "RuntimeError"
        assert "exit code" in result.message or "garbage" in result.message

    # -- to_exception() -------------------------------------------------------

    def test_to_exception_preserves_type_name(self):
        """to_exception() should produce an exception whose __name__ is ValueError."""
        output = deque(["ValueError: bad input"])
        result = parse_error_from_output(output, 1)
        exc = result.to_exception()
        assert type(exc).__name__ == "ValueError"
        assert isinstance(exc, RuntimeError)
        assert str(exc) == "bad input"

    def test_to_exception_preserves_library_type_name(self):
        """Library-specific exception names should be preserved, not collapsed."""
        output = deque(["ResourceInsufficientError: Not enough GPUs"])
        result = parse_error_from_output(output, 1)
        exc = result.to_exception()
        assert type(exc).__name__ == "ResourceInsufficientError"
        assert isinstance(exc, RuntimeError)
        assert str(exc) == "Not enough GPUs"


# =============================================================================
# END-TO-END SUBPROCESS FLOW TESTS
#
# These simulate the real code path:
#   subprocess stdout → deque → parse_error_from_output → ParsedError
#   → to_exception() → runner except block → create_error_details → dict
# =============================================================================


def _simulate_subprocess_error(lines: list[str]) -> ErrorDetails:
    """Simulate the full subprocess error flow that both backends use.

    This mirrors backend.py:
        parsed = parse_error_from_output(bootstrap.driver_output, exit_code)
        raise parsed.to_exception()
    followed by runner.py:
        except Exception as e:
            error_details = create_error_details(e)
    """
    output = deque(lines, maxlen=500)
    parsed = parse_error_from_output(output, returncode=1)
    return create_error_details(parsed.to_exception())


class TestSubprocessErrorFlow:
    """End-to-end tests: subprocess output → parser → converter → error details.

    Each test verifies the full ErrorDetails dict:
      type    – correct CustomizerTrainingError subclass
      message – user-facing text from the matched YAML rule's error_details
      detail  – original exception message preserved through the pipeline
    """

    # -- dataset errors -------------------------------------------------------

    def test_text_type_error(self):
        details = _simulate_subprocess_error(
            [
                "ValueError: text must be a string or a list of strings, got <class 'int'>",
            ]
        )
        assert details == {
            "type": "DatasetFormatError",
            "message": "The 'text' field in your dataset has an invalid type. For NeMo-RL training (DPO/GRPO), the text field must be either a single string or a list of strings. Please check your dataset format and ensure the text field contains the correct data type.",
            "detail": "ValueError: text must be a string or a list of strings, got <class 'int'>",
        }

    def test_prompt_file_not_found(self):
        details = _simulate_subprocess_error(
            [
                "FileNotFoundError: Prompt file /data/prompts/template.txt not found",
            ]
        )
        assert details == {
            "type": "DatasetFormatError",
            "message": "The prompt template file specified in your training dataset configuration does not exist. Prompt templates define how your dataset samples are formatted for training. Please verify the prompt file path is correct and the file is accessible at the specified location.",
            "detail": "FileNotFoundError: Prompt file /data/prompts/template.txt not found",
        }

    # -- training config errors -----------------------------------------------

    def test_megatron_and_dtensor_both_enabled(self):
        details = _simulate_subprocess_error(
            [
                "ValueError: Configure either Megatron (policy.megatron_cfg.enabled=true) "
                "or DTensor (policy.dtensor_cfg.enabled=true), not both.",
            ]
        )
        assert details == {
            "type": "TrainingConfigError",
            "message": "Internal configuration error: both Megatron and DTensor training backends are enabled, but only one can be active at a time. This is an issue with the training environment setup, please contact the administrator.",
            "detail": "ValueError: Configure either Megatron (policy.megatron_cfg.enabled=true) or DTensor (policy.dtensor_cfg.enabled=true), not both.",
        }

    def test_world_size_insufficient(self):
        details = _simulate_subprocess_error(
            [
                "ValueError: World size (2) is insufficient for the parallelism configuration: "
                "PP=2, CP=1, TP=2 requires at least 4 GPUs.",
            ]
        )
        assert details == {
            "type": "TrainingConfigError",
            "message": "Not enough GPUs available for the requested parallelism settings. The total number of GPUs must be at least pipeline_parallel_size * context_parallel_size * tensor_parallel_size. Either reduce parallelism settings or request more GPUs.",
            "detail": "ValueError: World size (2) is insufficient for the parallelism configuration: PP=2, CP=1, TP=2 requires at least 4 GPUs.",
        }

    def test_world_size_not_divisible(self):
        details = _simulate_subprocess_error(
            [
                "ValueError: World size (5) must be divisible by PP * CP * TP (4) for correct parallelism.",
            ]
        )
        assert details == {
            "type": "TrainingConfigError",
            "message": "The total number of GPUs must be evenly divisible by (pipeline_parallel_size * context_parallel_size * tensor_parallel_size). For example, with PP=2, CP=1, TP=2, you need 4, 8, 12, etc. GPUs. Please adjust your parallelism settings or cluster size.",
            "detail": "ValueError: World size (5) must be divisible by PP * CP * TP (4) for correct parallelism.",
        }

    def test_dtensor_world_size_mismatch(self):
        details = _simulate_subprocess_error(
            [
                "AssertionError: World size(8) must equal to dp_size(2) * tp_size(2) * cp_size(1) to use DTensor",
            ]
        )
        assert details == {
            "type": "TrainingConfigError",
            "message": "The total number of GPUs (world_size) does not match the product of data_parallel_size * tensor_parallel_size * context_parallel_size for the DTensor backend. Please adjust your parallelism settings so they are consistent with the available GPU count.",
            "detail": "AssertionError: World size(8) must equal to dp_size(2) * tp_size(2) * cp_size(1) to use DTensor",
        }

    def test_dynamic_batching_pp(self):
        details = _simulate_subprocess_error(
            [
                "AssertionError: Dynamic batching is only supported for single pipeline parallel stage",
            ]
        )
        assert details == {
            "type": "TrainingConfigError",
            "message": "Dynamic batching is only supported when pipeline_parallel_size=1. With pipeline parallelism (PP > 1), the model is split across GPU stages which requires fixed batch sizes. Please either set pipeline_parallel_size=1 or disable dynamic batching.",
            "detail": "AssertionError: Dynamic batching is only supported for single pipeline parallel stage",
        }

    def test_dynamic_batching_exclusive_of_packing(self):
        details = _simulate_subprocess_error(
            [
                "AssertionError: Dynamic Batching is exclusive of Sequence Packing",
            ]
        )
        assert details == {
            "type": "TrainingConfigError",
            "message": "Dynamic batching and sequence packing cannot be used together. Please disable one of them: either set dynamic_batching=false or set sequence_packing_enabled=false.",
            "detail": "AssertionError: Dynamic Batching is exclusive of Sequence Packing",
        }

    def test_sequence_packing_vlm(self):
        details = _simulate_subprocess_error(
            [
                "AssertionError: Sequence packing is not supported for VLM models",
            ]
        )
        assert details == {
            "type": "TrainingConfigError",
            "message": "Sequence packing is not supported for Vision-Language Models (VLMs). Please set sequence_packing_enabled=false when training VLM models.",
            "detail": "AssertionError: Sequence packing is not supported for VLM models",
        }

    def test_context_parallel_gemma3(self):
        details = _simulate_subprocess_error(
            [
                "AssertionError: Context parallel is not supported for Gemma3ForCausalLM",
            ]
        )
        assert details == {
            "type": "TrainingConfigError",
            "message": "Context parallelism is not supported for Gemma3 models due to limitations in the PyTorch context parallel implementation. Please set context_parallel_size=1 when training Gemma3 models.",
            "detail": "AssertionError: Context parallel is not supported for Gemma3ForCausalLM",
        }

    def test_cp_requires_packing_megatron(self):
        details = _simulate_subprocess_error(
            [
                "RuntimeError: Context Parallelism (CP>1) requires sequence packing to be enabled.",
            ]
        )
        assert details == {
            "type": "TrainingConfigError",
            "message": "When using the Megatron backend with context_parallel_size > 1, sequence packing must be enabled. Please either enable sequence packing (sequence_packing_enabled=true) or reduce context_parallel_size to 1.",
            "detail": "RuntimeError: Context Parallelism (CP>1) requires sequence packing to be enabled.",
        }

    def test_grpo_generation_config(self):
        details = _simulate_subprocess_error(
            [
                "AssertionError: A generation config in the PolicyConfig is required for GRPO",
            ]
        )
        assert details == {
            "type": "TrainingConfigError",
            "message": "GRPO (Group Relative Policy Optimization) requires a generation configuration to produce responses during training. This is an internal configuration issue with the training environment, please contact the administrator.",
            "detail": "AssertionError: A generation config in the PolicyConfig is required for GRPO",
        }

    def test_validation_dataset_required(self):
        details = _simulate_subprocess_error(
            [
                "AssertionError: Validation dataset is required if validation is enabled",
            ]
        )
        assert details == {
            "type": "TrainingConfigError",
            "message": "Validation is enabled for this training job, but no validation dataset was provided. Please provide a validation dataset in your training request, or disable validation.",
            "detail": "AssertionError: Validation dataset is required if validation is enabled",
        }

    def test_async_grpo_requires_vllm_async(self):
        details = _simulate_subprocess_error(
            [
                "AssertionError: Async GRPO requires vLLM backend with "
                "vllm_cfg.async_engine=True. Please enable async engine.",
            ]
        )
        assert details == {
            "type": "TrainingConfigError",
            "message": "Async GRPO training requires the vLLM backend with async engine enabled, but the current configuration does not have this set. This is an internal configuration issue with the training environment, please contact the administrator.",
            "detail": "AssertionError: Async GRPO requires vLLM backend with vllm_cfg.async_engine=True. Please enable async engine.",
        }

    def test_batch_size_not_divisible_by_dp(self):
        details = _simulate_subprocess_error(
            [
                "AssertionError: Configuration error: (num_prompts_per_step * "
                "num_generations_per_prompt) = 32 must be divisible by "
                "data_parallel size 6.",
            ]
        )
        assert details == {
            "type": "TrainingConfigError",
            "message": "The effective batch size (num_prompts_per_step * num_generations_per_prompt) must be evenly divisible by the number of data parallel workers. Please adjust num_prompts_per_step or num_generations_per_prompt so their product divides evenly.",
            "detail": "AssertionError: Configuration error: (num_prompts_per_step * num_generations_per_prompt) = 32 must be divisible by data_parallel size 6.",
        }

    def test_top_k_sampling_threshold(self):
        details = _simulate_subprocess_error(
            [
                "ValueError: top_k sampling with values < 50 is not supported with vLLM V1 engine",
            ]
        )
        assert details == {
            "type": "TrainingConfigError",
            "message": "The top_k value is too low for the vLLM V1 engine. The vLLM V1 engine does not return logprobs after top_k filtering, so very low top_k values produce inaccurate logprob computations. Please increase top_k or remove the top_k constraint.",
            "detail": "ValueError: top_k sampling with values < 50 is not supported with vLLM V1 engine",
        }

    def test_sequence_too_long_for_packing(self):
        details = _simulate_subprocess_error(
            [
                "ValueError: Sequence length 4096 exceeds bin capacity 2048",
            ]
        )
        assert details == {
            "type": "TrainingConfigError",
            "message": "When sequence packing is enabled, one or more sequences in your dataset exceed the maximum sequence length (max_seq_length). Sequence packing combines multiple shorter sequences into a single training sample, but each individual sequence must fit within max_seq_length. Please either increase max_seq_length to accommodate longer sequences, or preprocess your dataset to truncate or remove sequences that are too long.",
            "detail": "ValueError: Sequence length 4096 exceeds bin capacity 2048",
        }

    def test_moe_aux_loss(self):
        details = _simulate_subprocess_error(
            [
                "AssertionError: MoE aux loss is currently not supported due to a known bug in Megatron-LM.",
            ]
        )
        assert details == {
            "type": "TrainingConfigError",
            "message": "Mixture-of-Experts (MoE) auxiliary loss is not currently supported due to a known bug in Megatron-LM. Please disable the MoE auxiliary loss in your training configuration.",
            "detail": "AssertionError: MoE aux loss is currently not supported due to a known bug in Megatron-LM.",
        }

    def test_dpo_dynamic_batching(self):
        details = _simulate_subprocess_error(
            [
                "AssertionError: Dynamic batching is currently not supported with DPO",
            ]
        )
        assert details == {
            "type": "TrainingConfigError",
            "message": "DPO (Direct Preference Optimization) training does not support dynamic batching. This is an internal configuration issue with the training environment, please contact the administrator.",
            "detail": "AssertionError: Dynamic batching is currently not supported with DPO",
        }

    # -- environment errors ---------------------------------------------------

    def test_incompatible_environment(self):
        details = _simulate_subprocess_error(
            [
                "ValueError: Unable to find compatible environment - my_custom_env",
            ]
        )
        assert details == {
            "type": "TrainingEnvironmentError",
            "message": "The specified GRPO environment name is not recognized. GRPO (Group Relative Policy Optimization) requires a valid environment that defines how to evaluate model responses. Please check the environment name in your training request and ensure it matches one of the supported environments for your use case.",
            "detail": "ValueError: Unable to find compatible environment - my_custom_env",
        }

    def test_environment_required(self):
        details = _simulate_subprocess_error(
            [
                "ValueError: hyperparameters.environment is required for GRPO, but it is not set",
            ]
        )
        assert details == {
            "type": "TrainingEnvironmentError",
            "message": "GRPO (Group Relative Policy Optimization) training requires an environment configuration to evaluate model responses and compute rewards. Please specify the environment in your training request's hyperparameters. The environment determines how the model's generated responses will be scored during reinforcement learning.",
            "detail": "ValueError: hyperparameters.environment is required for GRPO, but it is not set",
        }

    def test_no_environment_for_task(self):
        details = _simulate_subprocess_error(
            [
                "ValueError: No environment found for task type: unknown_task",
            ]
        )
        assert details == {
            "type": "TrainingEnvironmentError",
            "message": "No GRPO environment is registered for the specified task type. The environment defines how model responses are evaluated during reinforcement learning. This may indicate an unsupported task type or a misconfiguration. Please verify your task type is supported for GRPO training.",
            "detail": "ValueError: No environment found for task type: unknown_task",
        }

    # -- model load errors ----------------------------------------------------

    def test_vllm_not_installed(self):
        details = _simulate_subprocess_error(
            [
                "ImportError: vLLM is not installed. Please check that the py_executable is correct.",
            ]
        )
        assert details == {
            "type": "ModelLoadError",
            "message": "vLLM is not installed in the training environment. This is an issue with the training environment setup, please contact the administrator to raise an issue with the NeMo Platform team.",
            "detail": "ImportError: vLLM is not installed. Please check that the py_executable is correct.",
        }

    def test_missing_generation_output_keys(self):
        details = _simulate_subprocess_error(
            [
                "ValueError: Missing required keys for GenerationOutputSpec: logprobs, tokens",
            ]
        )
        assert details == {
            "type": "ModelLoadError",
            "message": "The base model's generation output is missing required fields. The base model may not be compatible with the selected training method (e.g., GRPO). Please verify you are using a supported model for this training type.",
            "detail": "ValueError: Missing required keys for GenerationOutputSpec: logprobs, tokens",
        }

    def test_pretrained_run_config_not_found(self):
        details = _simulate_subprocess_error(
            [
                "FileNotFoundError: Pretrained run config not found at /shared/converted/config.json on rank=1",
            ]
        )
        assert details == {
            "type": "ModelLoadError",
            "message": "The pretrained model configuration file was not found after Megatron checkpoint conversion. This usually means the HuggingFace-to-Megatron conversion on the head node saved to a directory not accessible by this worker node. This is an infrastructure issue - please ensure shared storage is properly mounted across all nodes, or contact your administrator.",
            "detail": "FileNotFoundError: Pretrained run config not found at /shared/converted/config.json on rank=1",
        }

    # -- checkpoint errors ----------------------------------------------------

    def test_distributed_process_group_not_initialized(self):
        details = _simulate_subprocess_error(
            [
                "RuntimeError: Distributed process group is not initialized. Cannot save checkpoint.",
            ]
        )
        assert details == {
            "type": "CheckpointError",
            "message": "Cannot save checkpoint because the distributed process group is not initialized. This typically occurs when the training cluster encountered communication issues before checkpoint saving could complete. This is a transient infrastructure issue - please try running your training job again.",
            "detail": "RuntimeError: Distributed process group is not initialized. Cannot save checkpoint.",
        }

    def test_megatron_state_not_initialized(self):
        details = _simulate_subprocess_error(
            [
                "RuntimeError: Megatron core state or model is not initialized. Cannot save checkpoint.",
            ]
        )
        assert details == {
            "type": "CheckpointError",
            "message": "Cannot save checkpoint because the Megatron model state is not initialized. This typically occurs when the model failed to load or initialize correctly before training could produce a checkpoint. Please verify the base model is valid and try again.",
            "detail": "RuntimeError: Megatron core state or model is not initialized. Cannot save checkpoint.",
        }

    def test_hf_checkpoint_already_exists(self):
        details = _simulate_subprocess_error(
            [
                "FileExistsError: HF checkpoint already exists at /output/hf_ckpt. "
                "Delete it to run or set overwrite=True.",
            ]
        )
        assert details == {
            "type": "CheckpointError",
            "message": "The HuggingFace checkpoint output directory already exists from a previous training run or conversion. This typically happens when a previous training job left partial output behind. Please use a clean output directory, or contact your administrator to remove the existing checkpoint.",
            "detail": "FileExistsError: HF checkpoint already exists at /output/hf_ckpt. Delete it to run or set overwrite=True.",
        }

    # -- distributed / Ray errors ---------------------------------------------

    def test_no_space_left_on_device(self):
        details = _simulate_subprocess_error(
            [
                "OSError: [Errno 28] No space left on device",
            ]
        )
        assert details == {
            "type": "DistributedError",
            "message": "Disk space exhausted on the node's ephemeral storage (/tmp). During reinforcement learning training (DPO/GRPO), Ray stores session logs and temporary files in /tmp/ray/ which can fill up the node's local disk. This is separate from the PVC used for checkpoints and datasets. This is typically a transient infrastructure issue - please try running your training job again, or contact your administrator to ensure adequate ephemeral storage is configured for the cluster nodes.",
            "detail": "OSError: [Errno 28] No space left on device",
        }

    def test_not_enough_gpus(self):
        details = _simulate_subprocess_error(
            [
                "ResourceInsufficientError: Not enough GPUs available. Requested 8 GPUs, but only 4 are available",
            ]
        )
        assert details == {
            "type": "DistributedError",
            "message": "The training cluster does not have enough GPUs available for your requested configuration. Your training job requires more GPUs than are currently available in the cluster. Try reducing the parallelism settings (tensor_parallel_size, pipeline_parallel_size) to require fewer GPUs.",
            "detail": "ResourceInsufficientError: Not enough GPUs available. Requested 8 GPUs, but only 4 are available",
        }

    def test_max_retries_reached(self):
        details = _simulate_subprocess_error(
            [
                "ResourceInsufficientError: Maximum number of retries reached (5). Cluster resources may be insufficient",
            ]
        )
        assert details == {
            "type": "DistributedError",
            "message": "Failed to allocate cluster resources after multiple retry attempts. This is typically a transient issue - please wait a few minutes and try submitting your training job again. If the problem persists, contact your administrator to check cluster health.",
            "detail": "ResourceInsufficientError: Maximum number of retries reached (5). Cluster resources may be insufficient",
        }

    def test_placement_group_timeout(self):
        details = _simulate_subprocess_error(
            [
                "TimeoutError: Timed out waiting for placement groups to be ready after 300s",
            ]
        )
        assert details == {
            "type": "DistributedError",
            "message": "Timed out while waiting for Ray placement groups to be allocated. Placement groups are used to co-locate GPU workers on the same nodes for efficient communication. This typically happens when the cluster is under heavy load and cannot allocate the required resources in time. Please try submitting your training job again. If the problem persists, contact your administrator.",
            "detail": "TimeoutError: Timed out waiting for placement groups to be ready after 300s",
        }

    def test_nccl_error_through_subprocess(self):
        details = _simulate_subprocess_error(
            [
                "[rank0]: RuntimeError: NCCL error in: ncclAllReduce",
            ]
        )
        assert details == {
            "type": "DistributedError",
            "message": "An NCCL (NVIDIA Collective Communications Library) error occurred during GPU-to-GPU communication. NCCL is used to synchronize data between GPUs during distributed training. Common causes include: 1) Network connectivity issues between GPU nodes, 2) GPU hardware problems, 3) Incompatible NCCL versions, or 4) Memory pressure on GPUs. This may be a transient issue - please try running your training job again. If the problem persists, contact your administrator.",
            "detail": "RuntimeError: NCCL error in: ncclAllReduce",
        }

    # -- generation errors ----------------------------------------------------

    def test_weight_update_failed_refit(self):
        details = _simulate_subprocess_error(
            [
                "RuntimeError: Updating weights for the generation policy failed during refit. Weight sync timed out.",
            ]
        )
        assert details == {
            "type": "GenerationError",
            "message": "Failed to update the vLLM generation model weights from the training policy during the 'refit' step. In GRPO training, the generation model periodically syncs weights from the training model. This failure may be caused by: 1) CUDA IPC (Inter-Process Communication) issues between training and generation workers, 2) NCCL communication errors, or 3) Memory pressure on GPUs. This is typically a transient issue - please try running your training job again.",
            "detail": "RuntimeError: Updating weights for the generation policy failed during refit. Weight sync timed out.",
        }

    def test_error_in_sample_rollout(self):
        details = _simulate_subprocess_error(
            [
                "RuntimeError: Error in sample 42 rollout: generation timed out",
            ]
        )
        assert details == {
            "type": "GenerationError",
            "message": "An error occurred while generating a response (rollout) for one of the training samples during GRPO training. Rollouts are the model-generated responses used to compute rewards and policy gradients. This may be caused by: 1) Invalid input data in the sample, 2) Generation parameters causing issues (e.g., max_tokens too low), or 3) vLLM backend errors. Check your dataset for problematic samples.",
            "detail": "RuntimeError: Error in sample 42 rollout: generation timed out",
        }

    def test_unable_to_allocate_worker_groups(self):
        details = _simulate_subprocess_error(
            [
                "RuntimeError: Unable to allocate any worker groups with the available resources",
            ]
        )
        assert details == {
            "type": "GenerationError",
            "message": "Could not allocate any vLLM worker groups with the available cluster resources. The generation component of DPO/GRPO training requires dedicated GPU resources for vLLM inference workers. Please ensure the cluster has enough GPUs, or reduce the generation parallelism settings.",
            "detail": "RuntimeError: Unable to allocate any worker groups with the available resources",
        }

    def test_no_output_received(self):
        details = _simulate_subprocess_error(
            [
                "RuntimeError: No output received for request abc-123-def",
            ]
        )
        assert details == {
            "type": "GenerationError",
            "message": "The vLLM async generation engine did not produce any output for a generation request. This can happen when: 1) The generation request timed out, 2) The vLLM worker encountered an internal error, or 3) GPU memory was exhausted during generation. This is typically a transient issue - please try running your training job again.",
            "detail": "RuntimeError: No output received for request abc-123-def",
        }

    # -- internal errors ------------------------------------------------------

    def test_stale_trajectories(self):
        details = _simulate_subprocess_error(
            [
                "ValueError: Found 15 trajectories older than min_valid_version 3",
            ]
        )
        assert details == {
            "type": "InternalError",
            "message": "The async GRPO replay buffer contains stale trajectories that are older than the minimum valid version. In async GRPO, trajectories are generated asynchronously and stored in a replay buffer. Stale trajectories can cause training instability because they were generated by an outdated policy. This indicates a synchronization issue between generation and training workers. Please contact the administrator.",
            "detail": "ValueError: Found 15 trajectories older than min_valid_version 3",
        }

    def test_tensor_dimension_mismatch(self):
        details = _simulate_subprocess_error(
            [
                "RuntimeError: tensors for key='input_ids' must have same number of dimensions",
            ]
        )
        assert details == {
            "type": "InternalError",
            "message": "Tensors being processed have mismatched dimensions during internal batching. This is an internal data processing issue that should not occur with valid datasets. Please contact the NeMo Platform team with your dataset format details.",
            "detail": "RuntimeError: tensors for key='input_ids' must have same number of dimensions",
        }

    def test_generic_training_failed_exit_code(self):
        details = _simulate_subprocess_error(
            [
                "Training failed with exit code: 1",
            ]
        )
        assert details == {
            "type": "InternalError",
            "message": "The training process exited with a non-zero exit code, but no specific error message could be extracted from the training logs. This is a generic failure that can have many causes. Please check the full training logs for more details, and contact the administrator if you cannot determine the cause.",
            "detail": "RuntimeError: Training failed with exit code: 1",
        }

    # -- realistic multi-line output ------------------------------------------

    def test_error_buried_in_traceback(self):
        """The parser should find the exception at the end of a full traceback."""
        details = _simulate_subprocess_error(
            [
                "[rank0]: Epoch 1/10, Step 50/100, Loss: 2.345",
                "[rank0]: Epoch 1/10, Step 51/100, Loss: 2.340",
                "[rank0]: Traceback (most recent call last):",
                '[rank0]:   File "/opt/nemo-rl/train.py", line 200, in train',
                "[rank0]:     policy_worker.step(batch)",
                '[rank0]:   File "/opt/nemo-rl/workers/megatron.py", line 85',
                "[rank0]:     self._validate_config(cfg)",
                (
                    "[rank0]: ValueError: World size (2) is insufficient for the "
                    "parallelism configuration: PP=2, CP=1, TP=2 requires at least 4 GPUs."
                ),
            ]
        )
        assert details == {
            "type": "TrainingConfigError",
            "message": "Not enough GPUs available for the requested parallelism settings. The total number of GPUs must be at least pipeline_parallel_size * context_parallel_size * tensor_parallel_size. Either reduce parallelism settings or request more GPUs.",
            "detail": "ValueError: World size (2) is insufficient for the parallelism configuration: PP=2, CP=1, TP=2 requires at least 4 GPUs.",
        }

    def test_distributed_error_repeated_across_ranks(self):
        """All ranks print the same error; should deduplicate and match."""
        details = _simulate_subprocess_error(
            [
                "[rank0]: RuntimeError: NCCL error in: ncclAllReduce",
                "[rank1]: RuntimeError: NCCL error in: ncclAllReduce",
                "[rank2]: RuntimeError: NCCL error in: ncclAllReduce",
                "[rank3]: RuntimeError: NCCL error in: ncclAllReduce",
            ]
        )
        assert details == {
            "type": "DistributedError",
            "message": "An NCCL (NVIDIA Collective Communications Library) error occurred during GPU-to-GPU communication. NCCL is used to synchronize data between GPUs during distributed training. Common causes include: 1) Network connectivity issues between GPU nodes, 2) GPU hardware problems, 3) Incompatible NCCL versions, or 4) Memory pressure on GPUs. This may be a transient issue - please try running your training job again. If the problem persists, contact your administrator.",
            "detail": "RuntimeError: NCCL error in: ncclAllReduce",
        }

    def test_wrapper_exception_skipped(self):
        """ChildFailedError wrapper should be skipped, real error extracted."""
        details = _simulate_subprocess_error(
            [
                "[rank0]: AssertionError: Dynamic Batching is exclusive of Sequence Packing",
                "[rank0]: ",
                "[rank0]: The above exception was the direct cause of:",
                "[rank0]: ChildFailedError: worker 0 failed",
            ]
        )
        assert details == {
            "type": "TrainingConfigError",
            "message": "Dynamic batching and sequence packing cannot be used together. Please disable one of them: either set dynamic_batching=false or set sequence_packing_enabled=false.",
            "detail": "AssertionError: Dynamic Batching is exclusive of Sequence Packing",
        }

    def test_head_node_exception_format(self):
        """Exceptions from _run_head_with_driver are formatted as 'Type: msg'."""
        details = _simulate_subprocess_error(
            [
                "[ray_bootstrap] Waiting for Ray to initialize...",
                "[ray_bootstrap] Waiting for workers to connect...",
                "ResourceInsufficientError: Not enough GPUs available. Requested 8 GPUs, but only 4 are available",
            ]
        )
        assert details == {
            "type": "DistributedError",
            "message": "The training cluster does not have enough GPUs available for your requested configuration. Your training job requires more GPUs than are currently available in the cluster. Try reducing the parallelism settings (tensor_parallel_size, pipeline_parallel_size) to require fewer GPUs.",
            "detail": "ResourceInsufficientError: Not enough GPUs available. Requested 8 GPUs, but only 4 are available",
        }

    def test_no_exception_line_falls_back(self):
        """When there's no exception line, falls back to InternalError."""
        details = _simulate_subprocess_error(
            [
                "Training step 1/100",
                "Training step 2/100",
                "Segmentation fault (core dumped)",
            ]
        )
        assert details["type"] == "InternalError"
        assert "Segmentation fault" in details["detail"]


# =============================================================================
# CREATE_ERROR_DETAILS EDGE CASES
# =============================================================================


class TestCreateErrorDetails:
    """Tests for create_error_details function edge cases."""

    def test_passes_through_customizer_error(self):
        """Should pass through CustomizerTrainingError directly."""
        exc = DatasetFormatError(message="Test message", detail="Test detail")
        details = create_error_details(exc)

        assert details["message"] == "Test message"
        assert details["type"] == "DatasetFormatError"
        assert details["detail"] == "Test detail"

    def test_unknown_error_uses_fallback(self):
        """Should use InternalError fallback for unknown errors."""
        original = Exception("Some completely unknown error")
        details = create_error_details(original)

        assert details["type"] == "InternalError"
        assert details["detail"] == "Exception: Some completely unknown error"
