# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Product CLI for importing a reusable Intake trace corpus."""

import json
import re
import subprocess
import sys
import tempfile
from importlib.util import find_spec
from pathlib import Path
from typing import ClassVar

import typer
from nemo_insights_plugin.contracts.profile import (
    ProfileError,
    discover_profile,
    load_env_file,
)
from nemo_insights_plugin.contracts.workflow_context import (
    WorkflowContext,
    resolve_context_base_url,
    write_workflow_context,
)
from nemo_insights_plugin.profile import load_profile
from nemo_platform_plugin.cli import NemoCLI

# The wheel force-includes the mature bundle importer as the ``testbed``
# namespace. Editable source installs leave it beside ``src/`` instead, so make
# that checkout-local namespace discoverable without changing global pytest
# configuration.
if find_spec("testbed") is None:
    plugin_root = Path(__file__).resolve().parents[2]
    if (plugin_root / "testbed").is_dir():
        sys.path.insert(0, str(plugin_root))

from testbed import reingest, release


def _resolve_platform_root(explicit: Path | None, profile_dir: Path) -> Path:
    """Find the source checkout from the profile/cwd before legacy fallbacks."""
    if explicit is not None:
        return explicit
    for start in (profile_dir.resolve(), Path.cwd().resolve()):
        for candidate in (start, *start.parents):
            if (candidate / reingest.CATALOG_RELPATH).is_file():
                return candidate
    return reingest.resolve_platform_root()


def _read_bundle_manifest(bundle: Path) -> dict:
    """Read and validate ``state/manifest.json`` without extracting the bundle."""
    if not bundle.is_file():
        raise ValueError(f"Trace bundle not found: {bundle}")
    listing = subprocess.run(
        ["tar", "--zstd", "-tf", str(bundle)],
        capture_output=True,
        text=True,
        check=False,
    )
    if listing.returncode != 0:
        reason = (listing.stderr.strip().splitlines() or ["tar failed"])[0]
        raise ValueError(f"Could not read trace bundle {bundle.name}: {reason}")
    if "state/manifest.json" not in listing.stdout.splitlines():
        raise ValueError(f"{bundle.name} is not a supported trace bundle (missing state/manifest.json)")
    manifest = subprocess.run(
        ["tar", "--zstd", "-xOf", str(bundle), "state/manifest.json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if manifest.returncode != 0:
        reason = (manifest.stderr.strip().splitlines() or ["tar failed"])[0]
        raise ValueError(f"Could not read trace bundle {bundle.name}: {reason}")
    try:
        payload = json.loads(manifest.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{bundle.name} has an invalid state/manifest.json: {exc}") from None
    if payload.get("kind") != "testbed-export":
        raise ValueError(
            f"{bundle.name} uses an unsupported legacy bundle format; "
            "re-export it with the current NeMo Insights testbed"
        )
    workspaces = payload.get("workspaces")
    if not isinstance(workspaces, list) or not workspaces:
        raise ValueError(f"{bundle.name} manifest has no workspaces")
    return payload


def _resolve_bundle(source: str, cache_dir: Path) -> tuple[Path, str]:
    candidate = Path(source).expanduser()
    if candidate.is_file():
        return candidate.resolve(), candidate.name
    if not re.fullmatch(r"state-v\d+", source):
        raise ValueError(f"Unknown trace source {source!r}; pass a published state-v<N> ref or a local .tar.zst bundle")
    typer.echo(f"Resolving trace corpus: {source}", err=True)
    return release.download_ref(source, cache_dir), source


def _import_bundle(
    bundle: Path,
    *,
    manifest: dict,
    workspace: str,
    base_url: str,
    platform_root: Path | None,
    scratch_root: Path,
) -> dict[str, dict]:
    """Extract and idempotently ingest a single-workspace bundle."""
    workspaces = [str(value) for value in manifest["workspaces"]]
    workspace_map = reingest.explicit_workspace_map(workspaces, workspace)
    catalog = reingest.load_catalog(reingest.resolve_platform_root(platform_root))
    scratch_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch_root) as temporary:
        extracted = Path(temporary)
        completed = subprocess.run(
            ["tar", "--zstd", "-xf", str(bundle), "-C", str(extracted)],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            reason = (completed.stderr.strip().splitlines() or ["tar failed"])[0]
            raise ValueError(f"Could not extract trace bundle {bundle.name}: {reason}")
        return reingest.ingest_bundle(
            base_url,
            extracted / "state" / "export",
            manifest,
            workspace_map=workspace_map,
            catalog=catalog,
            require_empty=False,
        )


class TracesCLI(NemoCLI):
    """``nemo traces ...`` commands."""

    name: ClassVar[str] = "traces"
    description: ClassVar[str] = "Import reusable agent trace corpora."

    def get_cli(self) -> typer.Typer:
        app = typer.Typer(help=self.description, no_args_is_help=True)

        @app.callback()
        def _root() -> None:
            """Force subcommand dispatch."""

        @app.command("import")
        def import_traces(
            source: str = typer.Argument(
                ...,
                help="Published state-v<N> ref or local .tar.zst trace bundle.",
            ),
            workspace: str | None = typer.Option(
                None,
                "--workspace",
                help="Target Intake workspace. Default: optimizer.yaml workspace.",
            ),
            base_url: str | None = typer.Option(
                None,
                "--base-url",
                help="Target NeMo Platform URL. Default: NMP_BASE_URL, then localhost.",
            ),
            profile_path: Path | None = typer.Option(
                None,
                "--profile",
                help="Path to optimizer.yaml. Default: discovered from cwd.",
                exists=True,
                dir_okay=False,
                readable=True,
            ),
            platform_root: Path | None = typer.Option(
                None,
                "--platform-root",
                help="NeMo Platform checkout root. Auto-detected in source checkouts.",
                exists=True,
                file_okay=False,
                readable=True,
            ),
        ) -> None:
            """Import a trace corpus and select it for the current agent profile."""
            try:
                found = profile_path or discover_profile()
                if found is None:
                    raise ProfileError("No optimizer.yaml found. Run from an agent directory or pass --profile.")
                profile = load_profile(found)
                load_env_file(profile.profile_dir / ".env")
                resolved_base_url = resolve_context_base_url(base_url, None)
                resolved_workspace = workspace or profile.workspace
                state_dir = profile.profile_dir / ".nemo-optimizer"
                bundle, source_label = _resolve_bundle(source, state_dir / "cache" / "traces")
                manifest = _read_bundle_manifest(bundle)
                outcome = _import_bundle(
                    bundle,
                    manifest=manifest,
                    workspace=resolved_workspace,
                    base_url=resolved_base_url,
                    platform_root=_resolve_platform_root(platform_root, profile.profile_dir),
                    scratch_root=state_dir / "tmp",
                )
                since = reingest.manifest_since(manifest)
                context = WorkflowContext(
                    agent=profile.agent,
                    workspace=resolved_workspace,
                    base_url=resolved_base_url,
                    trace_source=source_label,
                    trace_since=since,
                )
                context_file = write_workflow_context(profile.profile_dir, context)
            except (
                OSError,
                ProfileError,
                RuntimeError,
                subprocess.SubprocessError,
                ValueError,
            ) as exc:
                typer.echo(f"Error: {exc}", err=True)
                raise typer.Exit(code=1) from None

            ingested = sum(item["spans"]["ingested"] for item in outcome.values())
            skipped = sum(item["spans"]["skipped"] for item in outcome.values())
            typer.echo(
                f"Trace corpus ready: {resolved_workspace} ({ingested} spans ingested, {skipped} already present)"
            )
            typer.echo(f"Workflow context: {context_file}", err=True)

        return app
