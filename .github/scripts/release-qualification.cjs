// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

async function requireReleaseQualification({
  github,
  repository,
  sourceSha,
  releaseBranch,
  version,
}) {
  const [owner, repo, extra] = repository.split("/");
  if (!owner || !repo || extra) {
    throw new Error("Release qualification repository is not configured.");
  }

  let deployments;
  try {
    deployments = await github.paginate(github.rest.repos.listDeployments, {
      owner,
      repo,
      environment: "release-qualified",
      per_page: 100,
    });
  } catch {
    throw new Error(
      "Unable to verify release qualification. Ensure the release token has Deployments read access.",
    );
  }

  const deployment = deployments.find(
    ({ payload }) =>
      payload?.platform_ref === sourceSha &&
      payload?.release_branch === releaseBranch &&
      payload?.release_version === version,
  );

  if (deployment) {
    try {
      const statuses = await github.paginate(
        github.rest.repos.listDeploymentStatuses,
        {
          owner,
          repo,
          deployment_id: deployment.id,
          per_page: 100,
        },
      );
      const latestStatus = [...statuses]
        .sort(
          (left, right) =>
            left.created_at.localeCompare(right.created_at) ||
            left.id - right.id,
        )
        .at(-1);
      if (latestStatus?.state === "success") {
        return;
      }
    } catch {
      throw new Error(
        "Unable to verify release qualification. Ensure the release token has Deployments read access.",
      );
    }
  }

  throw new Error(
    `Source SHA ${sourceSha} is not release-qualified for ${releaseBranch} version ${version}. ` +
      "Wait for the release-branch container build, nSpect registration, and NGC publishing MR update to succeed, then retry.",
  );
}

module.exports = { requireReleaseQualification };
