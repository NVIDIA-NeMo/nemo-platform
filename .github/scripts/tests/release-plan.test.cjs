// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Unit tests for release plan parsing.
const assert = require("node:assert/strict");
const test = require("node:test");

const { resolveReleasePlan } = require("../release-plan.cjs");

const WHEELS = [
  {
    id: "nemo-platform",
    package: "nemo-platform",
    path: "packages/nemo_platform",
  },
  {
    id: "nemo-sandboxed-gym",
    package: "nemo-sandboxed-gym",
    path: "packages/sandboxed_gym",
    independent: true,
    tagPrefix: "nemo-sandboxed-gym-v",
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
      "source-sha": SHA.toUpperCase(),
      version: "1.2.3",
      "helm-version": "1.2.3-rc.1+build.9",
    }),
    getCommit: async () =>
      assert.fail("stable releases do not resolve a default branch commit"),
  });

  assert.equal(plan.sourceSha, SHA);
  assert.equal(plan.releaseLabel, "1.2.3");
  assert.equal(plan.includeHelm, true);
  assert.deepEqual(plan.wheelIds, []);
  assert.deepEqual(plan.containerIds, []);
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

test("bulk scopes leave an independent wheel alone", async () => {
  // The failure this guards is silent: a scheduled or whole-platform release quietly publishing
  // a version of nemo-sandboxed-gym that nothing pinned, on the platform's version line.
  for (const scope of ["all", "wheels"]) {
    const plan = await resolveReleasePlan({
      env: environment(),
      context: manualContext({
        "release-type": "stable",
        "release-scope": scope,
        "source-sha": SHA,
        version: "1.2.3",
      }),
      getCommit: async () => ({ data: { sha: SHA } }),
    });

    assert.deepEqual(plan.wheelIds, ["nemo-platform"]);
  }
});

test("an independent wheel is still selectable by id", async () => {
  const plan = await resolveReleasePlan({
    env: environment(),
    context: manualContext({
      "release-type": "stable",
      "release-scope": "custom",
      "wheel-ids": "nemo-sandboxed-gym",
      "source-sha": SHA,
      version: "0.1.0",
    }),
    getCommit: async () => ({ data: { sha: SHA } }),
  });

  // Alone: releasing it must not drag the platform wheels along.
  assert.deepEqual(plan.wheelIds, ["nemo-sandboxed-gym"]);
});

test("a pre-release version is accepted and flagged", async () => {
  const plan = await resolveReleasePlan({
    env: environment(),
    context: manualContext({
      "release-type": "stable",
      "release-scope": "custom",
      "wheel-ids": "nemo-sandboxed-gym",
      "source-sha": SHA,
      version: "0.1.0-rc0",
    }),
    getCommit: async () => assert.fail("stable releases pin their source"),
  });

  assert.equal(plan.isPrerelease, true);
  assert.equal(plan.releaseLabel, "0.1.0-rc0");
  assert.deepEqual(plan.wheelIds, ["nemo-sandboxed-gym"]);
});

test("a finished release is not flagged as a pre-release", async () => {
  const plan = await resolveReleasePlan({
    env: environment(),
    context: manualContext({
      "release-type": "stable",
      "release-scope": "wheels",
      "source-sha": SHA,
      version: "1.2.3",
    }),
    getCommit: async () => assert.fail("stable releases pin their source"),
  });

  assert.equal(plan.isPrerelease, false);
});

test("rejects a version whose pre-release suffix is not PEP 440 spellable", async () => {
  for (const version of [
    "1.2.3-alpha1",
    "1.2.3-rc",
    "1.2.3-rc0.1",
    "1.2.3rc0",
  ]) {
    await assert.rejects(
      resolveReleasePlan({
        env: environment(),
        context: manualContext({
          "release-type": "stable",
          "release-scope": "wheels",
          "source-sha": SHA,
          version,
        }),
        getCommit: async () => assert.fail("stable releases pin their source"),
      }),
      /MAJOR\.MINOR\.PATCH/,
      `expected ${version} to be rejected`,
    );
  }
});

test("an independent wheel cannot ride along with other artifacts", async () => {
  const selections = [
    { "wheel-ids": "nemo-platform,nemo-sandboxed-gym" },
    { "wheel-ids": "nemo-sandboxed-gym", "container-ids": "nmp-api" },
    { "wheel-ids": "nemo-sandboxed-gym", "include-helm": "true" },
  ];
  for (const extra of selections) {
    await assert.rejects(
      resolveReleasePlan({
        env: environment(),
        context: manualContext({
          "release-type": "stable",
          "release-scope": "custom",
          "source-sha": SHA,
          version: "1.2.3",
          ...extra,
        }),
        getCommit: async () => assert.fail("stable releases pin their source"),
      }),
      /independent wheel must be released on its own/,
      `expected ${JSON.stringify(extra)} to be rejected`,
    );
  }
});

test("an independent wheel alone is still a valid release", async () => {
  const plan = await resolveReleasePlan({
    env: environment(),
    context: manualContext({
      "release-type": "stable",
      "release-scope": "custom",
      "wheel-ids": "nemo-sandboxed-gym",
      "source-sha": SHA,
      version: "0.1.0-rc0",
    }),
    getCommit: async () => assert.fail("stable releases pin their source"),
  });

  assert.deepEqual(plan.wheelIds, ["nemo-sandboxed-gym"]);
  assert.equal(plan.isPrerelease, true);
});

test("an independent wheel tags under its own prefix", async () => {
  const plan = await resolveReleasePlan({
    env: environment(),
    context: manualContext({
      "release-type": "stable",
      "release-scope": "custom",
      "wheel-ids": "nemo-sandboxed-gym",
      "source-sha": SHA,
      version: "0.1.0-rc0",
    }),
    getCommit: async () => assert.fail("stable releases pin their source"),
  });

  // Not `0.1.0-rc0`: the platform already owns tags in that namespace, and the package's
  // dynamic versioning reads this prefix.
  assert.equal(plan.releaseTag, "nemo-sandboxed-gym-v0.1.0-rc0");
  assert.equal(plan.tagPrefix, "nemo-sandboxed-gym-v");
});

test("a platform release still tags unprefixed", async () => {
  const plan = await resolveReleasePlan({
    env: environment(),
    context: manualContext({
      "release-type": "stable",
      "release-scope": "wheels",
      "source-sha": SHA,
      version: "1.2.3",
    }),
    getCommit: async () => assert.fail("stable releases pin their source"),
  });

  assert.equal(plan.releaseTag, "1.2.3");
  assert.equal(plan.tagPrefix, "");
});

test("an independent wheel cannot be released as a nightly", async () => {
  await assert.rejects(
    resolveReleasePlan({
      env: environment(),
      context: manualContext({
        "release-type": "nightly",
        "release-scope": "custom",
        "wheel-ids": "nemo-sandboxed-gym",
        "dry-run": "true",
      }),
      getCommit: async () => assert.fail("dry runs use the workflow SHA"),
    }),
    /versioned from its own tags/,
  );
});
