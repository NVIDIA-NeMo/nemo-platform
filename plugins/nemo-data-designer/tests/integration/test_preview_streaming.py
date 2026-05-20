# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""End-to-end coverage of preview-stream error propagation.

This complements ``test_preview.py`` (happy-path streaming) by exercising
the worker-raised-an-exception path all the way from the in-process FastAPI
route through the NDJSON stream and SDK frame decoder back into a typed
``DataDesignerPreviewError``.
"""

import data_designer.config as dd
import nemo_data_designer_plugin.testing.utils as u
import pytest
from nemo_data_designer_plugin.functions import _preview_worker as worker_module
from nemo_data_designer_plugin.sdk.errors import DataDesignerPreviewError


@pytest.mark.integration
def test_preview_surfaces_worker_error_through_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the preview worker thread raises, the function emits a ``LogFrame`` and an
    ``Error`` frame instead of ``Done``; the SDK's ``_PreviewFrameCollector`` translates
    that ``Error`` into a typed ``DataDesignerPreviewError`` with the original message.
    """

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("forced worker failure")

    monkeypatch.setattr(worker_module, "make_preview_dataset", boom)

    builder = dd.DataDesignerConfigBuilder(model_configs=[u.make_model_config()])
    builder.add_column(
        column_config=dd.SamplerColumnConfig(
            name="foo",
            sampler_type=dd.SamplerType.CATEGORY,
            params=dd.CategorySamplerParams(values=["a"]),
        )
    )

    with u.make_mock_client_context() as client_context:
        dd_client = u.make_dd_client(client_context)
        with pytest.raises(DataDesignerPreviewError, match="forced worker failure"):
            dd_client.preview(builder, num_records=3)
