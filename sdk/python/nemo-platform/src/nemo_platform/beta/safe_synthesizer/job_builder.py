# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
import random
import string
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pandas as pd
from nemo_platform.types.safe_synthesizer import SafeSynthesizerJobConfigParam
from typing_extensions import Self

from .job import SafeSynthesizerJob

if TYPE_CHECKING:
    from nemo_platform import NeMoPlatform

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Type alias for the config inputs accepted by each with_* method:
# a Pydantic model, a plain dict, or None (use service-side defaults).
_ConfigInput = Any


def _to_dict(config: _ConfigInput) -> dict:
    """Coerce a Pydantic model, dict, or None to a plain dict."""
    if config is None:
        return {}
    if hasattr(config, "model_dump"):
        return config.model_dump()
    if isinstance(config, dict):
        return config.copy()
    raise ValueError(f"Config must be a dict, a Pydantic model, or None; got {type(config)!r}")


def _merge_config(config: _ConfigInput, kwargs: dict) -> dict:
    base = _to_dict(config)
    base.update(kwargs)
    return base


class SafeSynthesizerJobBuilder:
    """Builder for Safe Synthesizer Jobs ran with the NeMo Platform.

    This class provides a fluent interface for building Safe Synthesizer configurations.
    It allows you to configure all the parameters needed to create and run a Safe Synthesizer
    job. Each method returns the builder instance to allow method chaining.

    Examples:
        >>> from nemo_platform import NeMoPlatform
        >>> from nemo_platform.beta.safe_synthesizer.job_builder import SafeSynthesizerJobBuilder
        >>> client = NeMoPlatform(base_url=..., inference_base_url=...)
        >>> builder = (
        ...     SafeSynthesizerJobBuilder(client)
        ...     .with_data_source(your_dataframe)
        ...     .with_replace_pii()
        ...     .synthesize()
        ...     .with_train(learning_rate=0.0001)
        ...     .with_generate(num_records=10000)
        ...     .with_evaluate(enable=False)
        ... )
        >>> job = builder.create_job()
    """

    def __init__(self, client: NeMoPlatform, workspace: str = "default"):
        self._client = client
        self._workspace = workspace

        # Job-level fields
        self._hf_token_secret: str | None = None
        self._classify_model_provider: str | None = None
        self._data_source: pd.DataFrame | str | None = None
        self._data_source_path: str | None = None

        # Enable flags
        self._enable_synthesis: bool = False
        self._enable_replace_pii: bool = False

        # Per-section config dicts (populated by with_* methods)
        self._data_config: dict = {}
        self._training_config: dict = {}
        self._generation_config: dict = {}
        self._evaluation_config: dict = {}
        self._privacy_config: dict | None = None
        self._time_series_config: dict = {}
        self._replace_pii_config: dict = {}

    # ------------------------------------------------------------------
    # Data source
    # ------------------------------------------------------------------

    def with_data_source(self, df_source: pd.DataFrame | str) -> Self:
        """Set the data source for synthetic data generation.

        Args:
            df_source: Training dataset as a pandas DataFrame or a fetchable URL.

        Returns:
            The builder instance for method chaining.
        """
        self._data_source = df_source
        self._data_source_path = None  # invalidate any cached upload
        return self

    # ------------------------------------------------------------------
    # Mode flags
    # ------------------------------------------------------------------

    def synthesize(self) -> Self:
        """Enable data synthesis for the job run."""
        self._enable_synthesis = True
        return self

    # ------------------------------------------------------------------
    # Section configs
    # ------------------------------------------------------------------

    def with_data(self, config: _ConfigInput = None, **kwargs) -> Self:
        """Configure data parameters."""
        self._data_config = _merge_config(config, kwargs)
        return self

    def with_train(self, config: _ConfigInput = None, **kwargs) -> Self:
        """Configure training hyperparameters.

        Calling this method also enables synthesis.
        """
        self._training_config = _merge_config(config, kwargs)
        self._enable_synthesis = True
        return self

    def with_generate(self, config: _ConfigInput = None, **kwargs) -> Self:
        """Configure generation parameters.

        Calling this method also enables synthesis.
        """
        self._generation_config = _merge_config(config, kwargs)
        self._enable_synthesis = True
        return self

    def with_evaluate(self, config: _ConfigInput = None, **kwargs) -> Self:
        """Configure evaluation parameters."""
        self._evaluation_config = _merge_config(config, kwargs)
        return self

    def with_differential_privacy(self, config: _ConfigInput = None, **kwargs) -> Self:
        """Configure differential privacy parameters."""
        self._privacy_config = _merge_config(config, kwargs)
        return self

    def with_time_series(self, config: _ConfigInput = None, **kwargs) -> Self:
        """Configure time-series parameters."""
        self._time_series_config = _merge_config(config, kwargs)
        return self

    def with_replace_pii(self, config: _ConfigInput = None, **kwargs) -> Self:
        """Configure PII replacement.

        Calling this method enables PII replacement for the job. If no config is
        provided the service will use its own defaults.

        Args:
            config: PII replacement config as a dict or Pydantic model, or None to
                use service-side defaults.
            **kwargs: Individual PII replacement parameters to override.

        Returns:
            The builder instance for method chaining.
        """
        self._replace_pii_config = _merge_config(config, kwargs)
        self._enable_replace_pii = True
        return self

    # ------------------------------------------------------------------
    # Classify model provider
    # ------------------------------------------------------------------

    def with_classify_model_provider(self, provider_name: str) -> Self:
        """Configure column classification using an Inference Gateway model provider.

        The model provider should be configured to serve an LLM suitable for column
        classification tasks.

        Args:
            provider_name: Name of the model provider. Provide just the name to use a
                provider in the current workspace (e.g. ``"my-classify-llm"``), or a
                fully-qualified ``workspace/provider_name`` reference to use a provider
                from a different workspace.

        Returns:
            The builder instance for method chaining.
        """
        if "/" in provider_name:
            self._classify_model_provider = provider_name
        else:
            self._classify_model_provider = f"{self._workspace}/{provider_name}"
        logger.info(f"Configured classify model provider: {self._classify_model_provider}")
        return self

    # ------------------------------------------------------------------
    # HuggingFace token
    # ------------------------------------------------------------------

    def with_hf_token_secret(self, secret_name: str) -> Self:
        """Configure HuggingFace authentication using a platform secret.

        The secret must exist in the same workspace as the job and should contain
        a valid HuggingFace token.

        Args:
            secret_name: Name of the platform secret containing the HuggingFace token.

        Returns:
            The builder instance for method chaining.
        """
        self._hf_token_secret = secret_name
        return self

    # ------------------------------------------------------------------
    # Internal resolution
    # ------------------------------------------------------------------

    def _resolve_datasource(self, **kwargs) -> None:
        if self._data_source_path is not None:
            return  # already uploaded; reuse the cached result
        if isinstance(self._data_source, pd.DataFrame):
            df = self._data_source
        elif isinstance(self._data_source, str):
            df = pd.read_csv(self._data_source, **kwargs)
        else:
            raise ValueError("Data source must be a pandas DataFrame or a URL")

        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="w+", suffix=".csv", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            df.to_csv(tmp_path, index=False)
            file_name = f"dataset{self._generate_random_string()}.csv"
            self._data_source_path = self._upload_to_fileset(
                dataset_path=tmp_path,
                filename=file_name,
                fileset_name="safe-synthesizer-inputs",
            )
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)

    def _build_job_spec(self) -> dict:
        """Assemble the final job spec dict to send to the API."""
        if not self._enable_replace_pii and not self._enable_synthesis:
            raise ValueError("Data synthesis and/or replace PII must be enabled")
        if not self._data_source_path:
            raise ValueError("No data source path found after uploading dataset")

        pii_config: dict | None = None
        if self._enable_replace_pii:
            pii_config = self._replace_pii_config.copy()
            if self._classify_model_provider:
                globals_cfg = pii_config.setdefault("globals", {})
                classify_cfg = globals_cfg.setdefault("classify", {})
                classify_cfg["classify_model_provider"] = self._classify_model_provider
                logger.debug(f"Injected classify model provider: {self._classify_model_provider}")

        nss_config: dict = {
            "enable_synthesis": self._enable_synthesis,
            "enable_replace_pii": self._enable_replace_pii,
            "data": self._data_config,
            "training": self._training_config,
            "generation": self._generation_config,
            "evaluation": self._evaluation_config,
            "time_series": self._time_series_config,
        }
        if self._privacy_config is not None:
            nss_config["privacy"] = self._privacy_config
        if pii_config is not None:
            nss_config["replace_pii"] = pii_config

        return {
            "data_source": self._data_source_path,
            "config": nss_config,
            "hf_token_secret": self._hf_token_secret,
        }

    def resolve_job_config(self) -> Self:
        """Resolve and validate the final job configuration without submitting.

        Returns:
            The builder instance for method chaining.
        """
        self._resolve_datasource()
        # _build_job_spec validates; call it just for the side-effect of early error detection.
        self._build_job_spec()
        return self

    def create_job(self, **kwargs) -> SafeSynthesizerJob:
        """Upload the dataset and submit the job.

        Args:
            **kwargs: Additional job creation parameters passed to the API.

        Returns:
            A :class:`SafeSynthesizerJob` for monitoring and retrieving results.
        """
        self._resolve_datasource()
        spec = self._build_job_spec()
        response = self._client.safe_synthesizer.jobs.create(
            workspace=self._workspace,
            spec=cast(SafeSynthesizerJobConfigParam, spec),
            **kwargs,
        )
        return SafeSynthesizerJob(response.name, self._client, workspace=self._workspace)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _generate_random_string(self, length: int = 6) -> str:
        characters = string.ascii_uppercase + string.digits
        return "".join(random.choice(characters) for _ in range(length))

    def _upload_to_fileset(
        self,
        dataset_path: str | Path,
        filename: str,
        fileset_name: str,
    ) -> str:
        """Upload a dataset file to a fileset.

        Returns:
            The fileset:// URL of the uploaded file.
        """
        dataset_path = self._validate_dataset_path(dataset_path)
        self._client.files.upload(
            local_path=str(dataset_path),
            remote_path=filename,
            fileset=fileset_name,
            workspace=self._workspace,
            fileset_auto_create=True,
        )
        return f"{self._workspace}/{fileset_name}#{filename}"

    @staticmethod
    def _validate_dataset_path(dataset_path: str | Path) -> Path:
        if not Path(dataset_path).is_file():
            raise ValueError("🛑 To upload a dataset, you must provide a valid file path.")
        if not Path(dataset_path).name.endswith((".parquet", ".csv", ".json", ".jsonl")):
            raise ValueError(
                "🛑 Dataset files must be in `parquet`, `csv`, or `json` (orient='records', lines=True) format."
            )
        return Path(dataset_path)
