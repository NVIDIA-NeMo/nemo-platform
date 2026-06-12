// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  Anchor,
  Banner,
  Button,
  Card,
  Flex,
  SegmentedControl,
  Skeleton,
  Stack,
  Text,
  Tooltip,
} from '@nvidia/foundations-react-core';
import { Empty } from '@studio/components/Empty';
import { useWorkspaceFromPathIfExists } from '@studio/hooks/useWorkspaceFromPath';
import {
  CLAUDE_CODE_HISTORY_SESSIONS_QUERY_KEY,
  CLAUDE_CODE_SKILLS_QUERY_KEY,
  listClaudeCodeHistorySessions,
  listClaudeCodeSkills,
} from '@studio/routes/agents/ClaudeCodeChatRoute/api';
import { cleanClaudeCodeArtifactText } from '@studio/routes/agents/ClaudeCodeChatRoute/artifacts';
import { CLAUDE_CODE_STUDIO_LINK_CLASS } from '@studio/routes/agents/ClaudeCodeChatRoute/ClaudeCodeStudioLink';
import { getStudioInternalLinkTarget } from '@studio/routes/agents/ClaudeCodeChatRoute/ClaudeCodeStudioLinkTarget';
import type {
  ClaudeCodeChatArtifacts,
  ClaudeCodeChatFileArtifact,
  ClaudeCodeChatLinkArtifact,
  ClaudeCodeChatSelectionArtifact,
  ClaudeCodeHistorySession,
  ClaudeCodeSkill,
} from '@studio/routes/agents/ClaudeCodeChatRoute/types';
import { getSkillDisplayName } from '@studio/routes/DashboardLandingRoute/skillDisplayName';
import { useLocalStorage } from '@studio/util/hooks/useLocalStorage';
import { CLAUDE_CODE_HISTORY_OPEN_KEY, CLAUDE_CODE_PANEL_TAB_KEY } from '@studio/util/localStorage';
import { useQuery } from '@tanstack/react-query';
import cn from 'classnames';
import {
  ArrowRight,
  Bot,
  BookOpen,
  Boxes,
  Cpu,
  FileCode2,
  History,
  Link2,
  MessageSquare,
  MessageSquarePlus,
  PanelRightClose,
  PanelRightOpen,
  RefreshCw,
  Sparkles,
  Wrench,
} from 'lucide-react';
import { type FC, type ReactNode } from 'react';
import { Link } from 'react-router-dom';

interface ClaudeCodeHistoryPanelProps {
  activeSessionId?: string;
  artifacts?: ClaudeCodeChatArtifacts;
  onNewChat: () => void;
  onSelectSession: (sessionId: string) => void;
}

type ClaudeCodePanelTab = 'history' | 'skills';

const isClaudeCodePanelTab = (value: string): value is ClaudeCodePanelTab =>
  value === 'history' || value === 'skills';

const PANEL_TAB_ITEMS = [
  {
    value: 'history',
    children: (
      <Flex align="center" gap="density-xs">
        <History size={16} />
        History
      </Flex>
    ),
  },
  {
    value: 'skills',
    children: (
      <Flex align="center" gap="density-xs">
        <BookOpen size={16} />
        Skills
      </Flex>
    ),
  },
];

const getCompactRelativeTime = (mtime: number): string => {
  const elapsedMs = Math.max(Date.now() - mtime * 1000, 0);
  const minuteMs = 60 * 1000;
  const hourMs = 60 * minuteMs;
  const dayMs = 24 * hourMs;

  if (elapsedMs < minuteMs) return 'now';
  if (elapsedMs < hourMs) return `${Math.floor(elapsedMs / minuteMs)}m`;
  if (elapsedMs < dayMs) return `${Math.floor(elapsedMs / hourMs)}h`;

  const days = Math.floor(elapsedMs / dayMs);
  if (days < 31) return `${days}d`;

  return new Date(mtime * 1000).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
  });
};

const HistoryPanelSkeleton = () => (
  <Stack gap="density-sm" padding="density-md">
    <Skeleton className="h-16 w-full" />
    <Skeleton className="h-16 w-full" />
    <Skeleton className="h-16 w-full" />
  </Stack>
);

const SkillsPanelSkeleton = () => (
  <Stack gap="density-sm" padding="density-md">
    <Skeleton className="h-24 w-full" />
    <Skeleton className="h-24 w-full" />
    <Skeleton className="h-24 w-full" />
  </Stack>
);

const ToolCallSummary = ({ toolCalls }: { toolCalls: string[] }) => {
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

const ArtifactChip = ({ children }: { children: ReactNode }) => {
  const content = typeof children === 'string' ? cleanClaudeCodeArtifactText(children) : children;

  return (
    <span className="inline-flex min-w-0 max-w-full items-center rounded-full border border-accent/30 bg-accent/10 px-2 py-0.5 text-accent">
      <Text kind="label/bold/sm" className="truncate">
        {content}
      </Text>
    </span>
  );
};

const ArtifactRow = ({
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

const ArtifactSection = ({
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

const getFileLabel = (file: ClaudeCodeChatFileArtifact): string => {
  const parts = file.path.split('/');
  return parts[parts.length - 1] || file.path;
};

const FileArtifacts = ({ files }: { files: ClaudeCodeChatFileArtifact[] }) => {
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

const LinkArtifacts = ({ links }: { links: ClaudeCodeChatLinkArtifact[] }) => {
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

const SelectionArtifacts = ({ selections }: { selections: ClaudeCodeChatSelectionArtifact[] }) => {
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

const ToolArtifacts = ({ tools }: { tools: string[] }) => {
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

const getSelectedArtifactModel = (artifacts: ClaudeCodeChatArtifacts): string | undefined =>
  artifacts.model_source === 'selection' || artifacts.model_source === 'spec'
    ? artifacts.model
    : undefined;

const hasArtifacts = (artifacts?: ClaudeCodeChatArtifacts): artifacts is ClaudeCodeChatArtifacts =>
  !!artifacts &&
  !!(
    artifacts.agent ||
    getSelectedArtifactModel(artifacts) ||
    artifacts.workspace ||
    artifacts.selections.length ||
    artifacts.files.length ||
    artifacts.links.length ||
    artifacts.tools.length
  );

const ClaudeCodeArtifactsPane = ({
  artifacts,
  collapseLabel,
  onCollapse,
}: {
  artifacts?: ClaudeCodeChatArtifacts;
  collapseLabel: string;
  onCollapse: () => void;
}) => {
  const selectedModel = artifacts ? getSelectedArtifactModel(artifacts) : undefined;

  return (
    <section className="flex min-h-0 basis-1/2 flex-col border-b border-base">
      <Flex
        align="center"
        justify="between"
        gap="density-sm"
        className="border-b border-base px-density-md py-density-sm"
      >
        <Flex align="center" gap="density-sm" className="min-w-0">
          <Sparkles size={18} className="shrink-0 text-secondary" />
          <Text kind="label/bold/md" className="truncate">
            Chat artifacts
          </Text>
        </Flex>
        <Tooltip slotContent={collapseLabel} side="left">
          <Button
            aria-label={collapseLabel}
            kind="tertiary"
            size="small"
            type="button"
            onClick={onCollapse}
          >
            <PanelRightClose size={18} />
          </Button>
        </Tooltip>
      </Flex>
      {hasArtifacts(artifacts) ? (
        <Stack gap="density-md" padding="density-md" className="min-h-0 flex-1 overflow-y-auto">
          <Stack gap="density-sm" className="min-w-0">
            <ArtifactRow icon={<Bot size={14} />} label="Agent" value={artifacts.agent} />
            <ArtifactRow icon={<Cpu size={14} />} label="Model" value={selectedModel} />
            <ArtifactRow icon={<Boxes size={14} />} label="Workspace" value={artifacts.workspace} />
          </Stack>
          <SelectionArtifacts selections={artifacts.selections} />
          <FileArtifacts files={artifacts.files} />
          <LinkArtifacts links={artifacts.links} />
          <ToolArtifacts tools={artifacts.tools} />
        </Stack>
      ) : (
        <Flex className="min-h-0 flex-1 px-density-md" align="center" justify="center">
          <Empty title="No artifacts yet" description="Selections and outputs will appear here." />
        </Flex>
      )}
    </section>
  );
};

const HistorySessionButton = ({
  active,
  onSelect,
  session,
}: {
  active: boolean;
  onSelect: () => void;
  session: ClaudeCodeHistorySession;
}) => (
  <button
    type="button"
    aria-current={active ? 'page' : undefined}
    title={new Date(session.mtime * 1000).toLocaleString()}
    className={cn(
      'w-full cursor-pointer border-b border-base px-density-md py-density-sm text-left transition-colors hover:bg-surface-sunken focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent',
      active && 'bg-surface-sunken'
    )}
    onClick={onSelect}
  >
    <Stack gap="density-xs">
      <Flex align="center" gap="density-sm">
        <span
          className={cn(
            'flex size-6 shrink-0 items-center justify-center text-secondary',
            active && 'text-accent'
          )}
        >
          <MessageSquare size={12} />
        </span>
        <Flex align="center" justify="between" gap="density-sm" className="min-w-0 flex-1">
          <Text kind="body/regular/sm" className="min-w-0 flex-1 line-clamp-2">
            {session.first_prompt || 'Claude Code session'}
          </Text>
          <Text kind="body/regular/sm" color="secondary" className="shrink-0 whitespace-nowrap">
            {getCompactRelativeTime(session.mtime)}
          </Text>
        </Flex>
      </Flex>
      {session.tool_calls.length > 0 && (
        <div className="pl-8">
          <ToolCallSummary toolCalls={session.tool_calls} />
        </div>
      )}
    </Stack>
  </button>
);

const SkillCard = ({ skill }: { skill: ClaudeCodeSkill }) => (
  <Card
    className="h-auto shadow-none [&_.nv-card-content]:p-density-md"
    attributes={{ CardContent: { className: 'min-h-0' } }}
  >
    <Stack gap="density-sm" className="min-w-0">
      <Flex align="start" gap="density-sm" className="min-w-0">
        <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded bg-surface-sunken text-secondary">
          <BookOpen size={14} />
        </span>
        <Stack gap="density-xxs" className="min-w-0">
          <Text kind="body/semibold/sm" className="truncate" title={skill.name}>
            {getSkillDisplayName(skill)}
          </Text>
          <Text kind="body/regular/xs" color="secondary" className="truncate">
            {skill.claude_name}
          </Text>
        </Stack>
      </Flex>
      <Text kind="body/regular/sm" color="secondary" className="break-words">
        {skill.description || 'No description'}
      </Text>
    </Stack>
  </Card>
);

const HistoryPanelContents = ({
  activeSessionId,
  onNewChat,
  onSelectSession,
}: ClaudeCodeHistoryPanelProps) => {
  const {
    data: sessions = [],
    error,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: CLAUDE_CODE_HISTORY_SESSIONS_QUERY_KEY,
    queryFn: listClaudeCodeHistorySessions,
    refetchOnMount: 'always',
  });

  return (
    <>
      <div className="border-b border-base px-density-md py-density-sm">
        <Flex align="center" gap="density-xs">
          <Button
            color="neutral"
            kind="secondary"
            size="small"
            type="button"
            className="min-w-0 flex-1"
            onClick={onNewChat}
          >
            <MessageSquarePlus size={16} />
            <Text kind="label/bold/md">New chat</Text>
          </Button>
          <Tooltip slotContent="Refresh history">
            <Button
              aria-label="Refresh history"
              kind="tertiary"
              size="small"
              type="button"
              disabled={isLoading}
              onClick={() => void refetch()}
            >
              <RefreshCw size={16} />
            </Button>
          </Tooltip>
        </Flex>
      </div>
      {error && (
        <div className="px-density-md py-density-sm">
          <Banner kind="inline" status="error">
            Could not load Claude history.
          </Banner>
        </div>
      )}
      {isLoading ? (
        <HistoryPanelSkeleton />
      ) : sessions.length ? (
        <div className="min-h-0 flex-1 overflow-y-auto">
          {sessions.map((session) => (
            <HistorySessionButton
              key={session.session_id}
              active={session.session_id === activeSessionId}
              session={session}
              onSelect={() => onSelectSession(session.session_id)}
            />
          ))}
        </div>
      ) : !error ? (
        <Flex className="min-h-0 flex-1" align="center" justify="center">
          <Empty title="No chats yet" description="Claude Code sessions will appear here." />
        </Flex>
      ) : null}
    </>
  );
};

const SkillsPanelContents = () => {
  const {
    data: skills = [],
    error,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: CLAUDE_CODE_SKILLS_QUERY_KEY,
    queryFn: listClaudeCodeSkills,
  });

  return (
    <>
      <Flex
        align="center"
        justify="between"
        gap="density-sm"
        className="border-b border-base px-density-md py-density-sm"
      >
        <Text kind="body/regular/sm" color="secondary">
          {skills.length} skills
        </Text>
        <Tooltip slotContent="Refresh skills">
          <Button
            aria-label="Refresh skills"
            kind="tertiary"
            size="small"
            type="button"
            disabled={isLoading}
            onClick={() => void refetch()}
          >
            <RefreshCw size={16} />
          </Button>
        </Tooltip>
      </Flex>
      {error && (
        <div className="px-density-md py-density-sm">
          <Banner kind="inline" status="error">
            Could not load Claude skills.
          </Banner>
        </div>
      )}
      {isLoading ? (
        <SkillsPanelSkeleton />
      ) : skills.length ? (
        <div className="min-h-0 flex-1 overflow-y-auto p-density-sm">
          <Stack gap="density-md">
            {skills.map((skill) => (
              <SkillCard key={skill.claude_name} skill={skill} />
            ))}
          </Stack>
        </div>
      ) : !error ? (
        <Flex className="min-h-0 flex-1" align="center" justify="center">
          <Empty title="No skills found" description="Claude Code skills will appear here." />
        </Flex>
      ) : null}
    </>
  );
};

export const ClaudeCodeHistoryPanel: FC<ClaudeCodeHistoryPanelProps> = (props) => {
  const [historyOpen, setHistoryOpen] = useLocalStorage(CLAUDE_CODE_HISTORY_OPEN_KEY, 'true');
  const [panelTab, setPanelTab] = useLocalStorage(CLAUDE_CODE_PANEL_TAB_KEY, 'history');
  const isOpen = historyOpen !== 'false';
  const selectedTab =
    typeof panelTab === 'string' && isClaudeCodePanelTab(panelTab) ? panelTab : 'history';
  const toggleLabel = isOpen ? 'Collapse Claude history' : 'Expand Claude history';
  const handleTabChange = (value: string) => {
    if (isClaudeCodePanelTab(value)) setPanelTab(value);
  };

  if (!isOpen) {
    return (
      <aside className="flex shrink-0 justify-center border-t border-base bg-surface-base p-density-xs lg:w-14 lg:border-l lg:border-t-0">
        <Tooltip slotContent={toggleLabel} side="left">
          <Button
            aria-label={toggleLabel}
            kind="tertiary"
            size="small"
            type="button"
            onClick={() => setHistoryOpen('true')}
          >
            <PanelRightOpen size={18} />
          </Button>
        </Tooltip>
      </aside>
    );
  }

  return (
    <aside className="flex min-h-80 w-full shrink-0 flex-col border-t border-base bg-surface-base lg:w-[30rem] lg:border-l lg:border-t-0 xl:w-[32rem]">
      <ClaudeCodeArtifactsPane
        artifacts={props.artifacts}
        collapseLabel={toggleLabel}
        onCollapse={() => setHistoryOpen('false')}
      />
      <section className="flex min-h-0 basis-1/2 flex-col">
        <Flex
          align="center"
          justify="between"
          gap="density-sm"
          className="border-b border-base px-density-md py-density-sm"
        >
          <SegmentedControl
            size="tiny"
            value={selectedTab}
            onValueChange={handleTabChange}
            items={PANEL_TAB_ITEMS}
            className="min-w-0 flex-1"
          />
        </Flex>
        <div className="flex min-h-0 flex-1 flex-col">
          {selectedTab === 'history' ? (
            <HistoryPanelContents {...props} />
          ) : (
            <SkillsPanelContents />
          )}
        </div>
      </section>
    </aside>
  );
};
