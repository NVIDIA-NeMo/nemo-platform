// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

export const DEFAULT_GITHUB_TOKEN_HOSTS = [
  'github.com',
  'api.github.com',
  'raw.githubusercontent.com',
];

const parseAllowedHosts = (hosts?: string): Set<string> =>
  new Set(
    (hosts ?? DEFAULT_GITHUB_TOKEN_HOSTS.join(','))
      .split(',')
      .map((host) => host.trim().toLowerCase())
      .filter(Boolean)
  );

export const getGithubTokenHeaders = (
  url: URL,
  githubToken: string | undefined,
  allowedHosts = process.env.GITHUB_TOKEN_HOSTS
): Record<string, string> | undefined => {
  if (!githubToken || !parseAllowedHosts(allowedHosts).has(url.host.toLowerCase())) {
    return undefined;
  }

  return { Authorization: `Bearer ${githubToken}` };
};
