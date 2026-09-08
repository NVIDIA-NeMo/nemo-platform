// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Release artifact validation is independent of the GitHub Actions runtime.
const fs = require("node:fs");
const path = require("node:path");

function requireFile(filePath, message) {
  if (!fs.existsSync(filePath)) {
    throw new Error(`${message}: ${filePath}`);
  }
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function validateWheel(wheel, sourceRoot) {
  const pyprojectPath = path.join(sourceRoot, wheel.path, "pyproject.toml");
  requireFile(
    pyprojectPath,
    `Wheel ${wheel.id} cannot be built because its package config is missing`,
  );
  const pyproject = fs.readFileSync(pyprojectPath, "utf8");
  const namePattern = new RegExp(
    `^\\s*name\\s*=\\s*["']${escapeRegExp(wheel.package)}["']\\s*$`,
    "m",
  );
  if (!namePattern.test(pyproject)) {
    throw new Error(
      `Wheel ${wheel.id} expects package ${wheel.package}, ` +
        `but ${pyprojectPath} does not declare that project name.`,
    );
  }
}

function readBakeTargets(sourceRoot) {
  const bakePath = path.join(sourceRoot, "docker-bake.hcl");
  requireFile(bakePath, "Container validation needs docker-bake.hcl");
  return new Set(
    [
      ...fs.readFileSync(bakePath, "utf8").matchAll(/^target\s+"([^"]+)"/gm),
    ].map((match) => match[1]),
  );
}

function validateContainer(container, sourceRoot, bakeTargets) {
  if (!bakeTargets.has(container.target)) {
    throw new Error(
      `Container ${container.id} cannot be built because bake target ` +
        `${container.target} is missing from docker-bake.hcl.`,
    );
  }
  requireFile(
    path.join(
      sourceRoot,
      ".github",
      "assets",
      "ngc",
      "containers",
      `${container.id}.md`,
    ),
    `Container ${container.id} is missing matching NGC metadata`,
  );
}

function artifactList(artifacts) {
  return artifacts.length === 0
    ? "(none)"
    : artifacts.map((artifact) => artifact.id).join(", ");
}

function validateReleaseArtifacts({ wheels, containers, sourceRoot = "." }) {
  const bakeTargets = readBakeTargets(sourceRoot);
  wheels.forEach((wheel) => validateWheel(wheel, sourceRoot));
  containers.forEach((container) =>
    validateContainer(container, sourceRoot, bakeTargets),
  );
  return {
    wheels: artifactList(wheels),
    containers: artifactList(containers),
  };
}

module.exports = { validateReleaseArtifacts };
