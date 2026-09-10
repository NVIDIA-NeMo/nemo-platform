# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from typing import Annotated

import typer
from nemo_platform_sdk_tools.common.logging import setup_logging
from nemo_platform_sdk_tools.sdk.generate_cli import generate_cli
from nemo_platform_sdk_tools.sdk.post_generation_update import app as post_generation_update_app
from nemo_platform_sdk_tools.sdk.vendor.vendor_package import app as vendor_app

app = typer.Typer(help="Tools for managing NeMo Platform SDKs", no_args_is_help=True, rich_markup_mode="markdown")


@app.callback()
def callback(verbose: Annotated[bool, typer.Option(help="Verbose mode")] = False) -> None:
    """NeMo Platform SDK management commands."""
    setup_logging(verbose=verbose, show_path=True, enable_link_path=True, stderr=True)


app.add_typer(post_generation_update_app)
app.add_typer(vendor_app)
app.command()(generate_cli)
