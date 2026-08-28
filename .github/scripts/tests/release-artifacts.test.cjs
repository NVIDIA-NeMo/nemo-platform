// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Unit tests for release artifact validation.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { validateReleaseArtifacts } = require("../release-artifacts.cjs");

function createSourceTree() {
  const sourceRoot = fs.mkdtempSync(
    path.join(os.tmpdir(), "nemo-release-artifacts-"),
  );
  fs.mkdirSync(path.join(sourceRoot, "packages", "nemo_platform"), {
    recursive: true,
  });
  fs.mkdirSync(
    path.join(sourceRoot, ".github", "assets", "ngc", "containers"),
    { recursive: true },
  );
  fs.writeFileSync(
    path.join(sourceRoot, "packages", "nemo_platform", "pyproject.toml"),
    '[project]\nname = "nemo-platform"\n',
  );
  fs.writeFileSync(
    path.join(sourceRoot, "docker-bake.hcl"),
    'target "nmp-api-docker" {}\n',
  );
  fs.writeFileSync(
    path.join(
      sourceRoot,
      ".github",
      "assets",
      "ngc",
      "containers",
      "nmp-api.md",
    ),
    "# API\n",
  );
  return sourceRoot;
}

function selectedArtifacts() {
  return {
    wheels: [
      {
        id: "nemo-platform",
        package: "nemo-platform",
        path: "packages/nemo_platform",
      },
    ],
    containers: [{ id: "nmp-api", target: "nmp-api-docker" }],
  };
}

test("validates selected wheel and container artifacts", (t) => {
  const sourceRoot = createSourceTree();
  t.after(() => fs.rmSync(sourceRoot, { recursive: true, force: true }));

  assert.deepEqual(
    validateReleaseArtifacts({ ...selectedArtifacts(), sourceRoot }),
    {
      wheels: "nemo-platform",
      containers: "nmp-api",
    },
  );
});

test("rejects a wheel whose project name does not match the release catalog", (t) => {
  const sourceRoot = createSourceTree();
  t.after(() => fs.rmSync(sourceRoot, { recursive: true, force: true }));
  fs.writeFileSync(
    path.join(sourceRoot, "packages", "nemo_platform", "pyproject.toml"),
    '[project]\nname = "other-package"\n',
  );

  assert.throws(
    () => validateReleaseArtifacts({ ...selectedArtifacts(), sourceRoot }),
    /does not declare that project name/,
  );
});

test("rejects a container without matching NGC metadata", (t) => {
  const sourceRoot = createSourceTree();
  t.after(() => fs.rmSync(sourceRoot, { recursive: true, force: true }));
  fs.rmSync(
    path.join(
      sourceRoot,
      ".github",
      "assets",
      "ngc",
      "containers",
      "nmp-api.md",
    ),
  );

  assert.throws(
    () => validateReleaseArtifacts({ ...selectedArtifacts(), sourceRoot }),
    /missing matching NGC metadata/,
  );
});
