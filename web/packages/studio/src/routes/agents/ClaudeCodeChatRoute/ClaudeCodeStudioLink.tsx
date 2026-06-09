// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Anchor } from '@nvidia/foundations-react-core';
import { BASE_URL } from '@studio/constants/environment';
import { useWorkspaceFromPathIfExists } from '@studio/hooks/useWorkspaceFromPath';
import { ArrowRight } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

interface ClaudeCodeStudioLinkProps {
  children?: ReactNode;
  href?: string;
}

const getNormalizedBaseUrl = (): string => {
  const normalized = BASE_URL.replace(/\/+$/, '');
  return normalized === '/' ? '' : normalized;
};

const LEGACY_STUDIO_BASE_PATH = '/studio';

const isStudioRoute = (pathname: string): boolean =>
  pathname.startsWith('/workspaces/') || pathname === '/models' || pathname.startsWith('/models/');

const canonicalizeStudioPathname = (pathname: string): string => {
  const dashboardEvaluationPath = pathname.match(
    /^\/workspaces\/([^/]+)\/dashboard\/evaluations?(\/.*)?$/
  );
  if (dashboardEvaluationPath) {
    const [, workspace, remainder = ''] = dashboardEvaluationPath;
    return `/workspaces/${workspace}/evaluation${remainder}`;
  }

  const pluralEvaluationPath = pathname.match(/^\/workspaces\/([^/]+)\/evaluations(\/.*)?$/);
  if (pluralEvaluationPath) {
    const [, workspace, remainder = ''] = pluralEvaluationPath;
    return `/workspaces/${workspace}/evaluation${remainder}`;
  }

  return pathname;
};

const getStudioPathname = (pathname: string): string => {
  const baseUrl = getNormalizedBaseUrl();
  const pathWithoutBaseUrl =
    baseUrl && (pathname === baseUrl || pathname.startsWith(`${baseUrl}/`))
      ? pathname.slice(baseUrl.length) || '/'
      : pathname;

  if (pathWithoutBaseUrl === LEGACY_STUDIO_BASE_PATH) return '/';
  if (pathWithoutBaseUrl.startsWith(`${LEGACY_STUDIO_BASE_PATH}/`)) {
    return pathWithoutBaseUrl.slice(LEGACY_STUDIO_BASE_PATH.length);
  }

  return pathWithoutBaseUrl;
};

const rewriteWorkspacePath = (pathname: string, currentWorkspace: string | undefined): string => {
  if (!currentWorkspace || !pathname.startsWith('/workspaces/')) return pathname;

  const [, remainder] = pathname.match(/^\/workspaces\/[^/]+(\/.*)?$/) ?? [];
  return `/workspaces/${encodeURIComponent(currentWorkspace)}${remainder ?? ''}`;
};

const getWorkspaceDashboardPath = (currentWorkspace: string | undefined): string | undefined =>
  currentWorkspace ? `/workspaces/${encodeURIComponent(currentWorkspace)}/dashboard` : undefined;

export const getStudioInternalLinkTarget = (
  href: string | undefined,
  origin = window.location.origin,
  currentWorkspace?: string
): string | undefined => {
  if (!href) return undefined;

  let url: URL;
  try {
    url = new URL(href, origin);
  } catch {
    return undefined;
  }

  const pathname = canonicalizeStudioPathname(getStudioPathname(url.pathname));

  if (pathname === '/' || pathname === '') {
    const workspaceDashboardPath = getWorkspaceDashboardPath(currentWorkspace);
    return workspaceDashboardPath ? `${workspaceDashboardPath}${url.search}${url.hash}` : undefined;
  }

  if (!isStudioRoute(pathname)) return undefined;

  return `${rewriteWorkspacePath(pathname, currentWorkspace)}${url.search}${url.hash}`;
};

export const ClaudeCodeStudioLink = ({ href, children }: ClaudeCodeStudioLinkProps) => {
  const workspace = useWorkspaceFromPathIfExists();
  const target = getStudioInternalLinkTarget(href, window.location.origin, workspace);

  if (!target) {
    return <span>{children}</span>;
  }

  return (
    <Anchor asChild>
      <Link
        className="inline-flex min-h-7 max-w-full items-center gap-density-xs rounded border border-base bg-[linear-gradient(135deg,var(--background-color-accent-green-subtle),var(--background-color-accent-teal-subtle)_58%,var(--background-color-interaction-base))] px-density-sm py-density-xs align-baseline text-sm font-medium leading-none no-underline shadow-sm transition-[background,box-shadow] hover:bg-[linear-gradient(135deg,var(--background-color-accent-green-subtle-hover),var(--background-color-accent-teal-subtle-hover)_58%,var(--background-color-interaction-hover))] hover:shadow"
        to={target}
      >
        <span className="truncate">{children}</span>
        <ArrowRight aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
      </Link>
    </Anchor>
  );
};
