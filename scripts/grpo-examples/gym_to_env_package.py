#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Package any NeMo Gym server directory as a `wheels-v1` or `native-v1` environment FileSet.

This is an **example helper**, not part of the customizer's functionality. Nothing in the
platform calls it: the supported contract is the environment FileSet layout itself, which
`nmp.rl.tasks.environment.validate` defines and which you can satisfy by hand. Use this to
get a working package quickly, or as a starting point for your own build.

    uv run scripts/grpo-examples/gym_to_env_package.py \\
        --gym-root ~/workspace/Gym \\
        --server resources_servers/math_with_judge \\
        --format wheels-v1 --arch x86_64 --out-dir /tmp/mwj-env

Then validate and upload:

    uv run --package nmp-rl pi-to-gym-conversion --validate-only /tmp/mwj-env
    nemo files filesets create my-env -w default --purpose environment --exist-ok
    nemo files upload /tmp/mwj-env/ my-env -w default

`native-v1` ships no wheels and resolves the server's requirements from a package index when
the job starts, so the cluster needs egress. `wheels-v1` vendors the closure and does not.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

GYM_REPO = "https://github.com/NVIDIA-NeMo/Gym"

# Matches the interpreter the training image builds Gym server venvs with.
TARGET_PYTHON_VERSION = "3.13"
# The training images are published for both linux/amd64 and linux/arm64, so wheel
# architecture is a property of the cluster's nodes. Several glibc floors are listed per arch
# because pip matches these tags literally rather than expanding a compatibility range.
WHEEL_ARCHES = ("x86_64", "aarch64")

SERVER_TYPES = ("resources_servers", "responses_api_agents", "responses_api_models")

# native-v1 requires every config_path under a Gym server prefix; wheels-v1 allows configs/.
POLICY_MODEL_RELPATH = {
    "wheels-v1": Path("configs") / "policy_model.yaml",
    "native-v1": Path("responses_api_models") / "vllm_model" / "configs" / "policy_model.yaml",
}

# validate_package_layout rejects any *.jsonl anywhere under the package, and prompts ship as
# their own dataset FileSet -- so a server's bundled data never travels with it.
SKIP_DIRS = {"data", "tests", "__pycache__", ".venv", ".pytest_cache"}


def resolve_gym_root(raw: str | None) -> Path:
    """Require an explicit Gym checkout and fail with instructions rather than a stack trace."""
    if not raw:
        raise SystemExit(
            "--gym-root is required.\n\n"
            "This script packages a server out of a NeMo Gym source tree, and Gym is not vendored\n"
            "in nemo-platform. Clone it first, then point --gym-root at the checkout:\n\n"
            f"    git clone {GYM_REPO} ~/workspace/Gym\n"
            "    --gym-root ~/workspace/Gym\n"
        )
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"--gym-root does not exist: {root}")
    if not any((root / t).is_dir() for t in SERVER_TYPES):
        raise SystemExit(
            f"{root} does not look like a NeMo Gym checkout -- expected at least one of "
            f"{', '.join(SERVER_TYPES)}/ inside it.\n"
            f"Clone it with: git clone {GYM_REPO} ~/workspace/Gym"
        )
    return root


def resolve_server(gym_root: Path, server: str) -> Path:
    """Validate ``<server_type>/<implementation>`` and return it as a relative path."""
    rel = Path(server.strip("/"))
    if len(rel.parts) != 2 or rel.parts[0] not in SERVER_TYPES:
        raise SystemExit(
            f"--server must be '<server_type>/<implementation>', with server_type one of "
            f"{', '.join(SERVER_TYPES)}. Got: {server!r}"
        )
    source = gym_root / rel
    if not (source / "app.py").is_file():
        raise SystemExit(f"no app.py under {source} -- is that the right --server?")
    # Gym only treats a directory as a server if it ships an install marker; without one it
    # silently falls back to a built-in of the same name in the image.
    if not ((source / "requirements.txt").is_file() or (source / "pyproject.toml").is_file()):
        raise SystemExit(
            f"{source} has neither requirements.txt nor pyproject.toml. Gym would not recognise "
            "it as a server, and would silently run a built-in of the same name instead."
        )
    return rel


def copy_server(gym_root: Path, out_dir: Path, rel: Path) -> Path:
    """Copy the server tree, dropping bundled data, tests and any stray JSONL."""
    target = out_dir / rel
    shutil.copytree(
        gym_root / rel,
        target,
        dirs_exist_ok=True,
        ignore=lambda d, names: [n for n in names if n in SKIP_DIRS or n.endswith(".jsonl")],
    )
    return target


def server_config_paths(pkg_server_dir: Path, out_dir: Path, impl: str, chosen: list[str] | None) -> list[str]:
    """Select the configs to load -- never all of them.

    A Gym server directory often ships several configs pairing it with different agents
    (math_with_judge alone, or with hermes/opencode/openclaw agents). Loading every one would
    start servers whose implementations this package does not carry. Gym's convention is that
    ``<impl>.yaml`` is the plain pairing, so that is the default; anything else is explicit.
    """
    available = sorted((pkg_server_dir / "configs").glob("*.yaml"))
    if not available:
        raise SystemExit(
            f"no configs/*.yaml under {pkg_server_dir}. An environment with no config starts no "
            "servers, so at least one is required."
        )
    names = {c.name: c for c in available}
    if chosen:
        missing = [c for c in chosen if c not in names]
        if missing:
            raise SystemExit(f"--config not found: {', '.join(missing)}. Available: {', '.join(sorted(names))}")
        picked = [names[c] for c in chosen]
    elif f"{impl}.yaml" in names:
        picked = [names[f"{impl}.yaml"]]
    else:
        raise SystemExit(
            f"no default config: expected {impl}.yaml under {pkg_server_dir}/configs. "
            f"Pass --config explicitly. Available: {', '.join(sorted(names))}"
        )
    return [c.relative_to(out_dir).as_posix() for c in picked]


def strip_inline_datasets(pkg_server_dir: Path) -> list[str]:
    """Drop ``datasets:`` blocks, which point at in-tree JSONL the package cannot carry."""
    touched = []
    for cfg in sorted((pkg_server_dir / "configs").glob("*.yaml")):
        doc = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
        changed = False
        for instance in doc.values():
            if not isinstance(instance, dict):
                continue
            for server_type, impls in instance.items():
                if server_type not in SERVER_TYPES or not isinstance(impls, dict):
                    continue
                for impl in impls.values():
                    if isinstance(impl, dict) and impl.pop("datasets", None) is not None:
                        changed = True
        if changed:
            cfg.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
            touched.append(cfg.name)
    return touched


def write_policy_model_config(out_dir: Path, fmt: str) -> Path:
    """Ship the ``policy_model`` server every config's refs resolve against.

    Reuses the platform's own builder so a hand-built package and pi-to-gym-conversion cannot
    drift on the interpolations, which resolve against the config NeMo-RL injects at spin-up.
    """
    from nmp.rl.tasks.environment.package import build_policy_model_yaml

    target = out_dir / POLICY_MODEL_RELPATH[fmt]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(build_policy_model_yaml(), sort_keys=False), encoding="utf-8")
    return target


def build_fork_wheel(gym_root: Path, wheels: Path, expect_version: str | None) -> Path:
    """Build nemo-gym from the checkout rather than taking it from an index.

    Gym pins each sub-venv to ``nemo-gym=={image version}``. If the cluster runs a fork, a
    same-versioned wheel from PyPI is upstream code, so build from source and check the version.
    """
    with tempfile.TemporaryDirectory(prefix="nemo-gym-build-") as tmp:
        subprocess.run(["uv", "build", "--wheel", "--out-dir", tmp, str(gym_root)], check=True)
        built = sorted(Path(tmp).glob("nemo_gym-*.whl"))
        if len(built) != 1:
            raise SystemExit(f"expected exactly one nemo_gym wheel, got {[p.name for p in built]}")
        version = built[0].name.split("-")[1]
        if expect_version is not None and version != expect_version:
            raise SystemExit(
                f"the checkout builds nemo-gym {version} but the image reports {expect_version}. "
                "Gym pins sub-venvs to the image's version, so this wheel would be ignored and uv "
                "would resolve from an index instead."
            )
        target = wheels / built[0].name
        shutil.copy2(built[0], target)
    return target


def vendor_wheels(
    out_dir: Path,
    gym_root: Path,
    pkg_server_dir: Path,
    arch: str,
    expect_version: str | None,
    ray_version: str,
    openai_version: str,
) -> Path:
    """Resolve the closure from nemo-gym, Gym's head-server deps, and the server's requirements.

    Gym appends ``ray[default]==`` and ``openai==`` (read from the Gym host process) to every
    per-server venv install, and the venv is created with ``uv venv --seed``, so nothing carries
    over from the image. Omitting them leaves the closure incomplete and the venv build reaches
    for an index -- which fails on a cluster with no egress, the case wheels-v1 exists for.
    """
    wheels = out_dir / "wheels"
    # Rebuild from empty: pip copies by filename, so a wheel from an earlier run survives
    # whenever the new resolution picks a different version, leaving two versions of one
    # distribution and no guarantee about which gets installed.
    if wheels.exists():
        shutil.rmtree(wheels)
    wheels.mkdir(parents=True)
    fork_wheel = build_fork_wheel(gym_root, wheels, expect_version)

    cmd = [
        sys.executable,
        "-m",
        "pip",
        "download",
        "--dest",
        str(wheels),
        "--no-cache-dir",
        "--only-binary",
        ":all:",
        "--python-version",
        TARGET_PYTHON_VERSION,
    ]
    for tag in (f"manylinux_2_39_{arch}", f"manylinux_2_28_{arch}", f"manylinux_2_17_{arch}", f"manylinux2014_{arch}"):
        cmd += ["--platform", tag]
    cmd += [str(fork_wheel), f"ray[default]=={ray_version}", f"openai=={openai_version}"]
    # The sub-venv is created with `uv venv --seed`, so everything the server imports must be
    # present. Its own requirements.txt names those; the editable nemo-gym line is not a real
    # requirement outside a checkout, and Gym rewrites it at spin-up.
    reqs = pkg_server_dir / "requirements.txt"
    if reqs.is_file():
        kept = [ln for ln in reqs.read_text(encoding="utf-8").splitlines() if ln.strip() and "../.." not in ln]
        if kept:
            with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
                fh.write("\n".join(kept) + "\n")
            cmd += ["-r", fh.name]
    print("Running:", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)

    stray = [p.name for p in wheels.iterdir() if p.is_file() and p.suffix != ".whl"]
    if stray:
        raise SystemExit(f"wheels/ must contain only .whl files, got: {stray}")
    return wheels


def write_manifest(out_dir: Path, fmt: str, config_paths: list[str], name: str, description: str) -> Path:
    manifest = out_dir / "nemo-environment.yaml"
    # policy_model first: it defines the server the other configs' refs resolve against.
    entries = "".join(f"  - {p}\n" for p in [POLICY_MODEL_RELPATH[fmt].as_posix(), *config_paths])
    body = f"format: {fmt}\nconfig_paths:\n{entries}metadata:\n  name: {name}\n"
    if description:
        body += f"  description: {description}\n"
    manifest.write_text(body, encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--gym-root",
        help=f"Local NeMo Gym checkout. Gym is not vendored here: git clone {GYM_REPO}",
    )
    parser.add_argument(
        "--server",
        required=True,
        help="Server to package, as '<server_type>/<implementation>', e.g. resources_servers/math_with_judge",
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--config",
        action="append",
        help="Config filename to load, repeatable (e.g. math_with_judge.yaml). Defaults to "
        "'<implementation>.yaml'. Other configs in the directory usually pair the server with an "
        "agent whose implementation this package does not carry, so they are not included by default.",
    )
    parser.add_argument(
        "--format",
        choices=tuple(POLICY_MODEL_RELPATH),
        default="wheels-v1",
        help="wheels-v1 vendors the closure and needs no egress at spin-up. native-v1 ships no "
        "wheels and resolves from a package index, so the cluster must allow internet.",
    )
    parser.add_argument(
        "--arch",
        choices=WHEEL_ARCHES,
        default="x86_64",
        help="Architecture of the nodes that run GRPO training (wheels-v1 only). Check with: "
        "kubectl get nodes -o jsonpath='{.items[*].status.nodeInfo.architecture}' "
        "-- amd64 maps to x86_64, arm64 to aarch64.",
    )
    parser.add_argument(
        "--expect-nemo-gym-version",
        help="Fail unless the checkout builds this exact version. Read the image's with: "
        "docker run --rm <image> sh -c 'PY=$(ls -d /opt/ray_venvs/*NemoGym*/bin/python | head -1); "
        '"${PY:-python}" -c \'import importlib.metadata as m; print(m.version("nemo-gym"))\'\'',
    )
    parser.add_argument(
        "--ray-version",
        help="ray version the training image runs (wheels-v1 only). Gym appends "
        "'ray[default]==<this>' to every per-server venv install.",
    )
    parser.add_argument(
        "--openai-version",
        help="openai version the training image runs (wheels-v1 only). Appended the same way.",
    )
    parser.add_argument("--name", help="metadata.name. Defaults to the implementation name.")
    parser.add_argument("--description", default="")
    args = parser.parse_args()

    if args.format == "wheels-v1":
        missing = [
            flag
            for flag, value in (
                ("--expect-nemo-gym-version", args.expect_nemo_gym_version),
                ("--ray-version", args.ray_version),
                ("--openai-version", args.openai_version),
            )
            if not value
        ]
        if missing:
            raise SystemExit(
                f"wheels-v1 needs {', '.join(missing)}.\n\n"
                "Gym pins each per-server venv to the training image's nemo-gym, ray and openai\n"
                "versions. A closure built against different ones is ignored and resolved from an\n"
                "index instead, which defeats the point of vendoring. Read them from the image:\n\n"
                "    docker run --rm <training-image> sh -c '\\\n"
                "      PY=$(ls -d /opt/ray_venvs/*NemoGym*/bin/python | head -1); \\\n"
                '      "${PY:-python}" -c \'import importlib.metadata as m; '
                'print(m.version("nemo-gym"), m.version("ray"), m.version("openai"))\'\'\n\n'
                "Use --format native-v1 if you do not need an offline closure.\n"
            )

    gym_root = resolve_gym_root(args.gym_root)
    rel = resolve_server(gym_root, args.server)
    name = args.name or rel.parts[1].replace("_", "-")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    pkg_server_dir = copy_server(gym_root, args.out_dir, rel)
    stripped = strip_inline_datasets(pkg_server_dir)
    config_paths = server_config_paths(pkg_server_dir, args.out_dir, rel.parts[1], args.config)
    policy_model = write_policy_model_config(args.out_dir, args.format)
    wheels = (
        vendor_wheels(
            args.out_dir,
            gym_root,
            pkg_server_dir,
            args.arch,
            args.expect_nemo_gym_version,
            args.ray_version,
            args.openai_version,
        )
        if args.format == "wheels-v1"
        else None
    )
    manifest = write_manifest(args.out_dir, args.format, config_paths, name, args.description)

    stray = [str(p.relative_to(args.out_dir)) for p in args.out_dir.rglob("*.jsonl")]
    if stray:
        raise SystemExit(f"validation rejects *.jsonl inside the package, found: {stray}")

    print(
        json.dumps(
            {
                "environment_root": str(args.out_dir),
                "format": args.format,
                "name": name,
                "server": rel.as_posix(),
                "manifest": str(manifest),
                "policy_model_config": str(policy_model),
                "config_paths": [POLICY_MODEL_RELPATH[args.format].as_posix(), *config_paths],
                "datasets_blocks_stripped": stripped,
                "arch": args.arch if wheels else None,
                "wheel_count": len(list(wheels.glob("*.whl"))) if wheels else 0,
                "next": [f"uv run --package nmp-rl pi-to-gym-conversion --validate-only {args.out_dir}"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
