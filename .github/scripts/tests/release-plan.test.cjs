// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Unit tests for release plan parsing.
const assert = require("node:assert/strict");
const test = require("node:test");

const {
  deriveNextReleaseVersion,
  resolveReleasePlan,
} = require("../release-plan.cjs");

const WHEELS = [
  {
    id: "nemo-platform",
    package: "nemo-platform",
    path: "packages/nemo_platform",
  },
];
const CONTAINERS = [{ id: "nmp-api", target: "nmp-api-docker" }];
const SHA = "a".repeat(40);

function environment() {
  return {
    RELEASE_WHEELS_JSON: JSON.stringify(WHEELS),
    RELEASE_CONTAINERS_JSON: JSON.stringify(CONTAINERS),
  };
}

function manualContext(inputs) {
  return {
    eventName: "workflow_dispatch",
    sha: "b".repeat(40),
    payload: { inputs, repository: { default_branch: "main" } },
  };
}

test("resolves a stable Helm-only release", async () => {
  const plan = await resolveReleasePlan({
    env: environment(),
    context: manualContext({
      "release-type": "stable",
      "release-scope": "helm",
      "release-series": "1.2",
      "source-sha": SHA.toUpperCase(),
      "helm-version": "1.2.3-rc.1+build.9",
    }),
    getCommit: async () =>
      assert.fail("stable releases do not resolve a default branch commit"),
    getTags: async () => ["1.2.0", "1.2.1", "1.2.2", "2.0.0-rc1"],
    sourceBelongsToBranch: async (sha, branch) => {
      assert.equal(sha, SHA);
      assert.equal(branch, "release/1.2");
      return true;
    },
  });

  assert.equal(plan.sourceSha, SHA);
  assert.equal(plan.releaseSeries, "1.2");
  assert.equal(plan.releaseBranch, "release/1.2");
  assert.equal(plan.releaseLabel, "1.2.3");
  assert.equal(plan.includeHelm, true);
  assert.deepEqual(plan.wheelIds, []);
  assert.deepEqual(plan.containerIds, []);
});

test("derives the first patch in a release series", () => {
  assert.equal(
    deriveNextReleaseVersion("0.5", ["0.4.9", "0.5.0-rc1", "v0.5.0"]),
    "0.5.0",
  );
});

test("derives the patch after the latest stable tag", () => {
  assert.equal(
    deriveNextReleaseVersion("0.5", ["0.5.1", "1.5.9", "0.5.7", "0.5.3"]),
    "0.5.8",
  );
});

test("rejects an invalid release series", () => {
  assert.throws(
    () => deriveNextReleaseVersion("0.5.1", []),
    /MAJOR.MINOR release series/,
  );
});

test("rejects a stable source outside the release branch", async () => {
  await assert.rejects(
    resolveReleasePlan({
      env: environment(),
      context: manualContext({
        "release-type": "stable",
        "release-scope": "containers",
        "release-series": "0.5",
        "source-sha": SHA,
      }),
      getCommit: async () => assert.fail("stable releases use an exact SHA"),
      getTags: async () => [],
      sourceBelongsToBranch: async () => false,
    }),
    new RegExp(`Source SHA ${SHA} does not belong to release/0.5`),
  );
});

test("resolves a custom nightly release and uses the supplied clock", async () => {
  const plan = await resolveReleasePlan({
    env: environment(),
    context: manualContext({
      "release-type": "nightly",
      "release-scope": "custom",
      "wheel-ids": "nemo-platform",
      "container-ids": "nmp-api",
      "include-helm": "false",
      "dry-run": "true",
    }),
    getCommit: async () => assert.fail("dry runs use the workflow SHA"),
    now: () => new Date("2026-08-27T12:34:56.789Z"),
  });

  assert.equal(plan.sourceSha, "b".repeat(40));
  assert.equal(plan.releaseLabel, "nightly-20260827123456");
  assert.deepEqual(plan.wheelIds, ["nemo-platform"]);
  assert.deepEqual(plan.containerIds, ["nmp-api"]);
});

test("rejects duplicate custom artifact IDs", async () => {
  await assert.rejects(
    resolveReleasePlan({
      env: environment(),
      context: manualContext({
        "release-type": "nightly",
        "release-scope": "custom",
        "wheel-ids": "nemo-platform,nemo-platform",
      }),
      getCommit: async () => SHA,
    }),
    /wheel-ids contains duplicate entries/,
  );
});
