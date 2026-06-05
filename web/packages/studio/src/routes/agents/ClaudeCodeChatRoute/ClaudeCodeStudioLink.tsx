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

const isStudioRoute = (pathname: string): boolean =>
  pathname.startsWith('/workspaces/') || pathname === '/models' || pathname.startsWith('/models/');

const getStudioPathname = (pathname: string): string => {
  const baseUrl = getNormalizedBaseUrl();
  return baseUrl && pathname.startsWith(`${baseUrl}/`) ? pathname.slice(baseUrl.length) : pathname;
};

const rewriteWorkspacePath = (pathname: string, currentWorkspace: string | undefined): string => {
  if (!currentWorkspace || !pathname.startsWith('/workspaces/')) return pathname;

  const [, remainder] = pathname.match(/^\/workspaces\/[^/]+(\/.*)?$/) ?? [];
  return `/workspaces/${encodeURIComponent(currentWorkspace)}${remainder ?? ''}`;
};

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

  const pathname = getStudioPathname(url.pathname);

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
