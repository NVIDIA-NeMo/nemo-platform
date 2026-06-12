// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { GradientBackground } from '@nemo/common/src/components/GradientBackground';
import { Button, Flex, Text, TextArea, Tooltip } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import {
  CLAUDE_CODE_SKILLS_QUERY_KEY,
  listClaudeCodeSkills,
} from '@studio/routes/agents/ClaudeCodeChatRoute/api';
import { ClaudeCodeLayout } from '@studio/routes/agents/ClaudeCodeChatRoute/ClaudeCodeLayout';
import type { ClaudeCodeChatRouteState } from '@studio/routes/agents/ClaudeCodeChatRoute/types';
import {
  SkillActionSection,
  type SkillActionCard,
} from '@studio/routes/DashboardLandingRoute/SkillActionSection';
import { getSkillActionSuggestions } from '@studio/routes/DashboardLandingRoute/skillActionSuggestions';
import { getClaudeCodeChatRoute } from '@studio/routes/utils';
import { useQuery } from '@tanstack/react-query';
import { GitBranch, Hammer, Search, Send, Terminal } from 'lucide-react';
import {
  type ChangeEvent,
  type FC,
  type FormEvent,
  type KeyboardEvent,
  useCallback,
  useMemo,
  useState,
} from 'react';
import { useNavigate } from 'react-router-dom';

const LandingComposer = ({
  input,
  onChange,
  onSubmit,
}: {
  input: string;
  onChange: (value: string) => void;
  onSubmit: (prompt: string) => void;
}) => {
  const submitInput = () => {
    const prompt = input.trim();
    if (!prompt) return;

    onSubmit(prompt);
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    submitInput();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return;

    event.preventDefault();
    submitInput();
  };

  return (
    <form
      data-testid="dashboard-landing-composer"
      onSubmit={handleSubmit}
      className="w-full rounded-lg border border-base bg-surface-base p-2 shadow-xl"
    >
      <TextArea
        aria-label="Message Claude"
        value={input}
        onChange={(event: ChangeEvent<HTMLTextAreaElement>) => onChange(event.target.value)}
        placeholder="Message Claude"
        rows={3}
        resizeable="auto"
        className="max-h-56 w-full border-0 bg-transparent shadow-none focus-within:outline-none focus-within:ring-0 [&:has(:focus-visible)]:outline-none [&:has(:focus-visible)]:ring-0"
        attributes={{
          TextAreaElement: {
            className:
              '[&&]:focus:outline-none [&&]:focus:ring-0 [&&]:focus-visible:outline-none [&&]:focus-visible:ring-0',
            onKeyDown: handleKeyDown,
          },
        }}
      />
      <Flex className="flex items-center justify-between gap-3 px-1 pt-2">
        <Flex className="flex items-center gap-2 text-secondary">
          <Terminal size={16} />
          <Text kind="body/regular/sm">Claude Code</Text>
        </Flex>
        <Tooltip slotContent="Send">
          <Button
            color="brand"
            size="small"
            aria-label="Send message"
            type="submit"
            disabled={!input.trim()}
          >
            <Send size={16} />
          </Button>
        </Tooltip>
      </Flex>
    </form>
  );
};

const DEFAULT_LANDING_ACTIONS = [
  {
    title: 'Explore repo',
    description: 'Give me a concise map of this repo and the main places I should know about.',
    prompt: 'Give me a concise map of this repo and the main places I should know about.',
    icon: <Search size={18} />,
  },
  {
    title: 'Draft a change',
    description: 'Help me plan and implement the next small product improvement in nemo-platform.',
    prompt: 'Help me plan and implement the next small product improvement in nemo-platform.',
    icon: <Hammer size={18} />,
  },
  {
    title: 'Review recent work',
    description: 'Review the current working tree and call out anything risky or unfinished.',
    prompt: 'Review the current working tree and call out anything risky or unfinished.',
    icon: <GitBranch size={18} />,
  },
] satisfies SkillActionCard[];

export const DashboardLandingRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const navigate = useNavigate();
  const [input, setInput] = useState('');
  const {
    data: skills,
    isError: isSkillsError,
    isLoading: isSkillsLoading,
  } = useQuery({
    queryKey: CLAUDE_CODE_SKILLS_QUERY_KEY,
    queryFn: listClaudeCodeSkills,
  });
  const skillActionSuggestions = useMemo(
    () => (isSkillsError ? DEFAULT_LANDING_ACTIONS : getSkillActionSuggestions(skills ?? [])),
    [isSkillsError, skills]
  );
  const totalActionSourceCount = isSkillsError
    ? DEFAULT_LANDING_ACTIONS.length
    : (skills?.length ?? 0);

  useBreadcrumbs({
    items: [{ slotLabel: 'Dashboard' }],
  });

  const handlePromptSelect = useCallback((prompt: string) => {
    setInput(prompt);
  }, []);

  const handleSubmit = useCallback(
    (prompt: string) => {
      const state: ClaudeCodeChatRouteState = { initialPrompt: prompt };
      navigate(getClaudeCodeChatRoute(workspace), { state });
    },
    [navigate, workspace]
  );

  return (
    <ClaudeCodeLayout>
      <AccessibleTitle title="Dashboard">
        <GradientBackground className="h-full w-full">
          <main className="relative flex h-full w-full items-center justify-center px-4 py-10 text-primary">
            <Flex className="mx-auto flex w-full min-w-0 max-w-4xl flex-col items-center gap-8">
              <Flex className="flex flex-col items-center gap-3 text-center">
                <Text kind="body/bold/2xl" className="text-center">
                  What would you like to do?
                </Text>
              </Flex>

              <LandingComposer input={input} onChange={setInput} onSubmit={handleSubmit} />

              <SkillActionSection
                actions={skillActionSuggestions}
                isLoading={isSkillsLoading}
                onSelect={handlePromptSelect}
                totalSkillCount={totalActionSourceCount}
              />
            </Flex>
          </main>
        </GradientBackground>
      </AccessibleTitle>
    </ClaudeCodeLayout>
  );
};
