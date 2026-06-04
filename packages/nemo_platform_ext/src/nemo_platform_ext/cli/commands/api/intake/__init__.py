# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# NOTE: This file is auto-generated
from __future__ import annotations

from nemo_platform_ext.cli.commands.api.intake import annotations, evaluator_results, ingest, spans, traces
from nemo_platform_ext.cli.core.help_formatter import create_typer_app

app = create_typer_app(name="intake", help="Intake operations")

app.add_typer(annotations.app, name="annotations")
app.add_typer(evaluator_results.app, name="evaluator-results")
app.add_typer(ingest.app, name="ingest")
app.add_typer(spans.app, name="spans")
app.add_typer(traces.app, name="traces")
