# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Friendly ``nemo data-designer retrieval`` command group."""

from __future__ import annotations

import json
from enum import Enum

import typer
from nemo_data_designer_plugin.jobs.retrieval_spec import RetrievalGenerateJobConfig, RetrievalPrepareJobConfig


class ProfileChoice(str, Enum):
    """Model-default profiles from the Nemotron embed/rerank recipes."""

    embed = "embed"
    rerank = "rerank"


retrieval_app = typer.Typer(
    name="retrieval",
    help="Nemotron retrieval SDG (Stage 0 generate, Stage 1 prepare).",
    no_args_is_help=True,
)


@retrieval_app.command("generate")
def retrieval_generate(
    corpus: str = typer.Option(..., "--corpus", help="Fileset ref, local path, or hf:// URI."),
    provider: str = typer.Option(..., "--provider", help="Inference Gateway provider (workspace/name)."),
    profile: ProfileChoice = typer.Option(ProfileChoice.embed, "--profile", help="embed or rerank model defaults."),
    workspace: str = typer.Option("default", "--workspace", "-w"),
    spec_out: bool = typer.Option(False, "--print-spec", help="Print JSON spec instead of submitting."),
) -> None:
    """Build a retrieval-generate spec. Auto CLI: ``nemo data-designer retrieval-generate``."""
    spec = RetrievalGenerateJobConfig(corpus=corpus, provider=provider, profile=profile.value)
    payload = json.dumps(spec.model_dump(mode="json"), indent=2)
    if spec_out:
        typer.echo(payload)
        return
    typer.echo("Submit with:")
    typer.echo(
        f"  nemo data-designer retrieval-generate --workspace {workspace} --spec '{json.dumps(spec.model_dump(mode='json'))}'"
    )


@retrieval_app.command("prepare")
def retrieval_prepare(
    sdg_input: str | None = typer.Option(
        None, "--sdg-input", help="Stage 0 fileset, generation_result.json, or hf:// URI."
    ),
    train_input_file: str | None = typer.Option(None, "--train-input-file"),
    enable_mining: bool = typer.Option(
        False,
        "--mine/--no-mine",
        help="Run GPU hard-negative mining after conversion. Conversion-only is the default.",
    ),
    workspace: str = typer.Option("default", "--workspace", "-w"),
) -> None:
    """Build a retrieval-prepare spec. Auto CLI: ``nemo data-designer retrieval-prepare``."""
    spec = RetrievalPrepareJobConfig(
        sdg_input=sdg_input,
        train_input_file=train_input_file,
        enable_mining=enable_mining,
    )
    typer.echo("Submit with:")
    typer.echo(
        f"  nemo data-designer retrieval-prepare --workspace {workspace} --spec '{json.dumps(spec.model_dump(mode='json'))}'"
    )


@retrieval_app.command("preview")
def retrieval_preview(
    corpus: str = typer.Option(..., "--corpus"),
    provider: str = typer.Option(..., "--provider"),
    profile: ProfileChoice = typer.Option(ProfileChoice.embed, "--profile"),
    workspace: str = typer.Option("default", "--workspace", "-w"),
) -> None:
    """Build a retrieval-preview spec. Auto CLI: ``nemo data-designer retrieval-preview``."""
    generate = RetrievalGenerateJobConfig(corpus=corpus, provider=provider, profile=profile.value)
    spec = {"generate": generate.model_dump(mode="json"), "num_records": 1}
    typer.echo("Submit with:")
    typer.echo(f"  nemo data-designer retrieval-preview --workspace {workspace} --spec '{json.dumps(spec)}'")
