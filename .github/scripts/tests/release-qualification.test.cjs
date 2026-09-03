// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

const assert = require("node:assert/strict");
const test = require("node:test");

const { requireReleaseQualification } = require("../release-qualification.cjs");

const SOURCE_SHA = "a".repeat(40);
const REQUEST = {
  repository: "private-owner/private-repo",
  sourceSha: SOURCE_SHA,
  releaseBranch: "release/0.5",
  version: "0.5.1",
};

function githubClient(deployments, statuses = [{ state: "success" }]) {
  return {
    paginate: async (_method, request) => {
      assert.equal(request.environment, "release-qualified");
      return deployments;
    },
    rest: {
      repos: {
        listDeployments: () => {},
        listDeploymentStatuses: async (request) => {
          assert.equal(request.deployment_id, 42);
          return { data: statuses };
        },
      },
    },
  };
}

test("accepts the exact successful release qualification", async () => {
  await requireReleaseQualification({
    ...REQUEST,
    github: githubClient([
      {
        id: 42,
        payload: {
          platform_ref: SOURCE_SHA,
          release_branch: "release/0.5",
          release_version: "0.5.1",
        },
      },
    ]),
  });
});

test("rejects a missing release qualification", async () => {
  await assert.rejects(
    requireReleaseQualification({
      ...REQUEST,
      github: githubClient([]),
    }),
    /is not release-qualified/,
  );
});

for (const [name, payload] of [
  ["SHA", { platform_ref: "b".repeat(40) }],
  ["branch", { release_branch: "release/0.6" }],
  ["version", { release_version: "0.5.0" }],
]) {
  test(`rejects a qualification with the wrong ${name}`, async () => {
    await assert.rejects(
      requireReleaseQualification({
        ...REQUEST,
        github: githubClient([
          {
            id: 42,
            payload: {
              platform_ref: SOURCE_SHA,
              release_branch: "release/0.5",
              release_version: "0.5.1",
              ...payload,
            },
          },
        ]),
      }),
      /is not release-qualified/,
    );
  });
}

test("rejects a non-success qualification", async () => {
  await assert.rejects(
    requireReleaseQualification({
      ...REQUEST,
      github: githubClient(
        [
          {
            id: 42,
            payload: {
              platform_ref: SOURCE_SHA,
              release_branch: "release/0.5",
              release_version: "0.5.1",
            },
          },
        ],
        [{ state: "inactive" }],
      ),
    }),
    /is not release-qualified/,
  );
});

test("sanitizes private API failures", async () => {
  const github = githubClient([]);
  github.paginate = async () => {
    throw new Error("private-owner/private-repo is forbidden");
  };

  await assert.rejects(
    requireReleaseQualification({ ...REQUEST, github }),
    (error) => {
      assert.match(error.message, /Deployments read access/);
      assert.doesNotMatch(error.message, /private-owner|private-repo/);
      return true;
    },
  );
});
