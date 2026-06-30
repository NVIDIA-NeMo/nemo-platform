# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Automodel training subprocess entry point.

Wraps nemo_automodel recipes with Jobs-service progress reporting (SFT, KD, embedding).
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from nemo_automodel.components.checkpoint.checkpointing import Checkpointer
from nemo_automodel.components.config._arg_parser import parse_args_and_load_config
from nemo_automodel.components.training.step_scheduler import StepScheduler
from nemo_automodel.recipes.llm.kd import KnowledgeDistillationRecipeForNextTokenPrediction
from nemo_automodel.recipes.llm.train_ft import TrainFinetuneRecipeForNextTokenPrediction
from nemo_automodel.recipes.retrieval.train_bi_encoder import TrainBiEncoderRecipe
from nmp.automodel.tasks.training.progress import JobsServiceProgressReporter
from nmp.customization_common.service.context import NMPJobContext
from nmp.customization_common.training.callbacks import TrainingProgressCallback

logger = logging.getLogger(__name__)


@runtime_checkable
class AutomodelRecipe(Protocol):
    """Protocol defining the interface we need from Automodel recipes.

    This makes the dependencies explicit and enables type checking, unlike
    the previous mixin approach that relied on implicit attributes.
    """

    cfg: Any
    step_scheduler: StepScheduler
    checkpointer: Checkpointer
    dist_env: Any

    def setup(self) -> None:
        """Build all components needed for training."""
        ...

    def run_train_validation_loop(self) -> None:
        """Run the main training/validation loop."""
        ...

    def log_train_metrics(self, log_data: Any) -> None:
        """Log training metrics."""
        ...

    def log_val_metrics(self, *args: Any, **kwargs: Any) -> None:
        """Log validation metrics.

        Note: Signature varies across Automodel recipes:
        - LLM/KD: (val_name, log_data, metric_logger=None)
        - VLM/biencoder/seq_cls: (log_data)
        """
        ...

    def save_checkpoint(
        self,
        epoch: int,
        step: int,
        train_loss: float,
        val_loss: dict[str, float] | None = None,
        best_metric_key: str = "default",
    ) -> None:
        """Save a checkpoint."""
        ...


class AutomodelRecipeWrapper:
    """Wraps an Automodel recipe with Jobs-service progress reporting."""

    def __init__(self, recipe: AutomodelRecipe, job_ctx: NMPJobContext | None = None):
        """Initialize the wrapper with an Automodel recipe.

        Args:
            recipe: Any recipe implementing the AutomodelRecipe protocol
                    (SFT, KD, biencoder, etc.).
            job_ctx: NeMo Platform job context for progress reporting (optional,
                     defaults to environment variables).
        """
        self._job_ctx = job_ctx or NMPJobContext.from_env()
        self._reporter = JobsServiceProgressReporter(self._job_ctx)
        self._reporter.report_running("automodel_recipe_setup")

        self._recipe = recipe
        self._recipe.setup()

        self.max_steps = getattr(self._recipe.step_scheduler, "max_steps", None) or 100
        self.num_epochs = getattr(self._recipe.step_scheduler, "num_epochs", None) or 1

        self.callback = TrainingProgressCallback(self._reporter)
        logger.info(f"Automodel recipe wrapper initialized: max_steps={self.max_steps}, num_epochs={self.num_epochs}")

        # Store original methods before patching
        self._original_log_train_metrics = recipe.log_train_metrics
        self._original_log_val_metrics = recipe.log_val_metrics
        self._original_save_checkpoint = recipe.save_checkpoint

        # Monkey-patch the recipe's methods to add our callbacks
        recipe.log_train_metrics = self._log_train_metrics  # type: ignore[method-assign]
        recipe.log_val_metrics = self._log_val_metrics  # type: ignore[method-assign]
        recipe.save_checkpoint = self._save_checkpoint  # type: ignore[method-assign]

    @property
    def recipe(self) -> AutomodelRecipe:
        """Access the underlying recipe."""
        return self._recipe

    def run_train_validation_loop(self) -> None:
        """Run training and close the progress callback."""
        try:
            self.callback.report_training_start(self.max_steps, self.num_epochs)
            self._recipe.run_train_validation_loop()
        finally:
            if self.callback:
                self.callback.close()
                logger.info("Training progress callback closed")

    def _log_train_metrics(self, log_data: Any) -> None:
        """Wrapped log_train_metrics with Jobs-service reporting."""
        self._original_log_train_metrics(log_data)
        if self.callback and log_data:
            try:
                metrics = getattr(log_data, "metrics", {})
                self.callback.report_train_step(
                    step=getattr(log_data, "step", 0) + 1,  # Convert to 1-based
                    epoch=getattr(log_data, "epoch", 0) + 1,  # Convert to 1-based
                    loss=metrics.get("loss", 0.0),
                    lr=metrics.get("lr"),
                    grad_norm=metrics.get("grad_norm"),
                )
            except Exception as e:
                logger.warning(f"Failed to report training progress: {e}")

            try:
                if self._recipe.step_scheduler.is_last_batch:
                    self.callback.report_epoch_end(
                        step=self._recipe.step_scheduler.step + 1,
                        epoch=self._recipe.step_scheduler.epoch + 1,
                    )
            except Exception as e:
                logger.warning(f"Failed to report epoch end: {e}")

    def _log_val_metrics(self, *args: Any, **kwargs: Any) -> None:
        """Wrapped log_val_metrics with Jobs-service reporting.

        Handles different Automodel recipe signatures:
        - LLM/KD: (val_name, log_data, metric_logger=None)
        - VLM/biencoder/seq_cls: (log_data)
        """
        # Call original method first with whatever args were passed
        self._original_log_val_metrics(*args, **kwargs)

        # Extract log_data from args (it's always the last positional arg before kwargs)
        # LLM signature: (val_name, log_data, metric_logger=None) -> log_data is args[1]
        # VLM/biencoder signature: (log_data) -> log_data is args[0]
        log_data = None
        if len(args) >= 2:
            # LLM/KD style: (val_name, log_data, ...)
            log_data = args[1]
        elif len(args) == 1:
            # VLM/biencoder style: (log_data)
            log_data = args[0]

        if self.callback and log_data:
            try:
                metrics = getattr(log_data, "metrics", {})
                self.callback.report_validation(
                    step=getattr(log_data, "step", 0) + 1,  # Convert to 1-based
                    epoch=getattr(log_data, "epoch", 0) + 1,  # Convert to 1-based
                    val_loss=metrics.get("val_loss", 0.0),
                )
            except Exception as e:
                logger.warning(f"Failed to report validation progress: {e}")

    def _save_checkpoint(
        self,
        epoch: int,
        step: int,
        train_loss: float,
        val_loss: dict[str, float] | None = None,
        best_metric_key: str = "default",
    ) -> None:
        """Wrapped save_checkpoint with Jobs-service reporting."""
        self._original_save_checkpoint(epoch, step, train_loss, val_loss, best_metric_key)
        if self.callback:
            try:
                checkpoint_dir = getattr(
                    getattr(self._recipe.checkpointer, "config", None),
                    "checkpoint_dir",
                    None,
                )
                self.callback.report_checkpoint_saved(
                    step=step + 1,  # Convert to 1-based
                    epoch=epoch + 1,  # Convert to 1-based
                    checkpoint_path=str(checkpoint_dir) if checkpoint_dir else None,
                )
            except Exception as e:
                logger.warning(f"Failed to report checkpoint save: {e}")


def _is_kd_config(cfg: Any) -> bool:
    """Check if config is for knowledge distillation."""
    return cfg.get("teacher_model") is not None or cfg.get("kd_ratio") is not None


def _is_biencoder_config(cfg: Any) -> bool:
    """Check if config is for biencoder/embedding model training.

    Detects biencoder configs by checking if model._target_ contains 'biencoder'.

    Note: ConfigNode automatically resolves _target_ to the actual function/class,
    so we check the function's __module__ or __qualname__ for 'biencoder'.
    """
    try:
        model_cfg = cfg.get("model", {})
        if model_cfg is None:
            return False

        target = model_cfg.get("_target_")
        if target is None:
            return False

        # target is resolved to the actual function/class by ConfigNode
        # Check its module path or qualified name
        module = getattr(target, "__module__", "") or ""
        qualname = getattr(target, "__qualname__", "") or ""
        return "biencoder" in module.lower() or "biencoder" in qualname.lower()
    except (AttributeError, TypeError):
        return False


def create_automodel_recipe(cfg: Any) -> AutomodelRecipeWrapper:
    """Create a progress-reporting wrapper for the recipe implied by *cfg*."""
    if _is_biencoder_config(cfg):
        logger.info("Detected biencoder config, using embedding model recipe")
        base_recipe = TrainBiEncoderRecipe(cfg)
    elif _is_kd_config(cfg):
        logger.info("Detected Knowledge Distillation config, using KD recipe")
        base_recipe = KnowledgeDistillationRecipeForNextTokenPrediction(cfg)
    else:
        logger.info("Using SFT fine-tuning recipe")
        base_recipe = TrainFinetuneRecipeForNextTokenPrediction(cfg)

    return AutomodelRecipeWrapper(base_recipe)


def main() -> None:
    cfg = parse_args_and_load_config()
    recipe = create_automodel_recipe(cfg)
    recipe.run_train_validation_loop()


if __name__ == "__main__":
    main()
