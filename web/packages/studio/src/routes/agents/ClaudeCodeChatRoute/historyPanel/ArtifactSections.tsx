// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Anchor, Flex, Stack, Text } from '@nvidia/foundations-react-core';
import { useWorkspaceFromPathIfExists } from '@studio/hooks/useWorkspaceFromPath';
import { cleanClaudeCodeArtifactText } from '@studio/routes/agents/ClaudeCodeChatRoute/artifacts';
import { CLAUDE_CODE_STUDIO_LINK_CLASS } from '@studio/routes/agents/ClaudeCodeChatRoute/ClaudeCodeStudioLink';
import { getStudioInternalLinkTarget } from '@studio/routes/agents/ClaudeCodeChatRoute/ClaudeCodeStudioLinkTarget';
import { getFileLabel } from '@studio/routes/agents/ClaudeCodeChatRoute/historyPanel/helpers';
import type {
  ClaudeCodeChatFileArtifact,
  ClaudeCodeChatJobArtifact,
  ClaudeCodeChatLinkArtifact,
  ClaudeCodeChatSelectionArtifact,
} from '@studio/routes/agents/ClaudeCodeChatRoute/types';
import { getJobProgressDetailRoute } from '@studio/routes/agents/ClaudeCodeChatRoute/utils/jobProgress';
import cn from 'classnames';
import { ArrowRight, Boxes, Briefcase, FileCode2, Link2, Sparkles, Wrench } from 'lucide-react';
import { type ReactNode } from 'react';
import { Link } from 'react-router-dom';

export const ToolCallSummary = ({ toolCalls }: { toolCalls: string[] }) => {
  if (!toolCalls.length) return null;

  return (
    <Flex className="min-w-0 text-secondary" align="center" gap="density-xs">
      <Wrench size={12} className="shrink-0" />
      <Text kind="body/regular/sm" className="truncate">
        {toolCalls.join(', ')}
      </Text>
    </Flex>
  );
};

export const ArtifactChip = ({ children }: { children: ReactNode }) => {
  const content = typeof children === 'string' ? cleanClaudeCodeArtifactText(children) : children;

  return (
    <span className="inline-flex min-w-0 max-w-full items-center rounded-full border border-accent/30 bg-accent/10 px-2 py-0.5 text-accent">
      <Text kind="label/bold/sm" className="truncate">
        {content}
      </Text>
    </span>
  );
};

export const ArtifactRow = ({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value?: string;
}) => {
  if (!value) return null;

  return (
    <Flex align="start" gap="density-sm" className="min-w-0">
      <span className="mt-1 flex size-5 shrink-0 items-center justify-center text-secondary">
        {icon}
      </span>
      <Flex align="center" gap="density-xs" className="min-w-0 flex-1 flex-wrap">
        <Text kind="label/bold/sm" color="secondary" className="shrink-0">
          {label}:
        </Text>
        <ArtifactChip>{value}</ArtifactChip>
      </Flex>
    </Flex>
  );
};

export const ArtifactSection = ({
  background,
  children,
  icon,
  title,
}: {
  background?: boolean;
  children: ReactNode;
  icon: ReactNode;
  title: string;
}) => (
  <Stack
    gap="density-xs"
    className={cn(
      'min-w-0',
      background && 'rounded border border-base bg-surface-sunken px-density-sm py-density-sm'
    )}
  >
    <Flex align="center" gap="density-xs" className="text-secondary">
      {icon}
      <Text kind="label/bold/sm" color="secondary">
        {title}
      </Text>
    </Flex>
    {children}
  </Stack>
);

export const FileArtifacts = ({ files }: { files: ClaudeCodeChatFileArtifact[] }) => {
  if (!files.length) return null;

  return (
    <ArtifactSection icon={<FileCode2 size={14} />} title="Files">
      <Stack gap="density-xs">
        {files.slice(0, 6).map((file) => (
          <Flex
            key={`${file.action}-${file.path}`}
            align="center"
            gap="density-xs"
            className="min-w-0 rounded border border-base bg-surface-sunken px-density-sm py-density-xs"
            title={file.path}
          >
            <Text kind="label/bold/sm" className="shrink-0">
              {file.action}
            </Text>
            <Text kind="body/regular/sm" className="min-w-0 flex-1 truncate font-mono">
              {getFileLabel(file)}
            </Text>
          </Flex>
        ))}
      </Stack>
    </ArtifactSection>
  );
};

export const LinkArtifacts = ({ links }: { links: ClaudeCodeChatLinkArtifact[] }) => {
  const workspace = useWorkspaceFromPathIfExists();

  if (!links.length) return null;

  return (
    <ArtifactSection icon={<Link2 size={14} />} title="Studio links">
      <Flex gap="density-xs" className="min-w-0 flex-wrap">
        {links.slice(0, 6).map((link) => {
          const target = getStudioInternalLinkTarget(
            link.href ?? link.destination,
            window.location.origin,
            workspace
          );
          const label = cleanClaudeCodeArtifactText(link.label);
          const key = `${link.label}-${link.destination ?? link.href ?? 'link'}`;

          return target ? (
            <Anchor asChild key={key}>
              <Link className={CLAUDE_CODE_STUDIO_LINK_CLASS} to={target}>
                <span className="truncate">{label}</span>
                <ArrowRight aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
              </Link>
            </Anchor>
          ) : (
            <ArtifactChip key={key}>{label}</ArtifactChip>
          );
        })}
      </Flex>
    </ArtifactSection>
  );
};

const getJobArtifactHref = (
  job: ClaudeCodeChatJobArtifact,
  workspace: string | undefined
): string | undefined => {
  if (job.href) return job.href;
  if (!workspace) return undefined;

  return getJobProgressDetailRoute({
    jobName: job.name,
    jobType: job.job_type,
    source: job.source,
    workspace,
  });
};

export const JobArtifacts = ({
  jobs,
  workspace: artifactWorkspace,
}: {
  jobs: ClaudeCodeChatJobArtifact[];
  workspace?: string;
}) => {
  const currentWorkspace = useWorkspaceFromPathIfExists();
  const workspace = currentWorkspace ?? artifactWorkspace;

  if (!jobs.length) return null;

  return (
    <ArtifactSection icon={<Briefcase size={14} />} title="Jobs">
      <Flex gap="density-xs" className="min-w-0 flex-wrap">
        {jobs.slice(0, 6).map((job) => {
          const target = getStudioInternalLinkTarget(
            getJobArtifactHref(job, workspace),
            window.location.origin,
            workspace
          );
          const label = cleanClaudeCodeArtifactText(job.name);

          return target ? (
            <Anchor asChild key={job.name}>
              <Link className={CLAUDE_CODE_STUDIO_LINK_CLASS} to={target}>
                <span className="truncate">{label}</span>
                <ArrowRight aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
              </Link>
            </Anchor>
          ) : (
            <ArtifactChip key={job.name}>{label}</ArtifactChip>
          );
        })}
      </Flex>
    </ArtifactSection>
  );
};

export const SelectionArtifacts = ({
  selections,
}: {
  selections: ClaudeCodeChatSelectionArtifact[];
}) => {
  if (!selections.length) return null;

  return (
    <ArtifactSection background icon={<Boxes size={14} />} title="Selections">
      <Stack gap="density-xs">
        {selections.slice(0, 6).map((selection) => (
          <ArtifactRow
            key={selection.label}
            icon={<Sparkles size={14} />}
            label={selection.label}
            value={selection.value}
          />
        ))}
      </Stack>
    </ArtifactSection>
  );
};

export const ToolArtifacts = ({ tools }: { tools: string[] }) => {
  if (!tools.length) return null;

  return (
    <ArtifactSection background icon={<Wrench size={14} />} title="Tools">
      <Flex gap="density-xs" className="min-w-0 flex-wrap">
        {tools.slice(0, 8).map((tool) => (
          <ArtifactChip key={tool}>{tool}</ArtifactChip>
        ))}
      </Flex>
    </ArtifactSection>
  );
};
