// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Button, Card, Flex, Text, TextArea, Tooltip } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import type { ClaudeCodeChatRouteState } from '@studio/routes/agents/ClaudeCodeChatRoute/types';
import { getClaudeCodeChatRoute } from '@studio/routes/utils';
import { GitBranch, Hammer, Search, Send, Terminal } from 'lucide-react';
import {
  type ChangeEvent,
  type FC,
  type FormEvent,
  type ReactNode,
  useCallback,
  useState,
} from 'react';
import { useNavigate } from 'react-router-dom';

interface PromptSuggestion {
  title: string;
  prompt: string;
  icon: ReactNode;
}

const PROMPT_SUGGESTIONS: PromptSuggestion[] = [
  {
    title: 'Explore repo',
    prompt: 'Give me a concise map of this repo and the main places I should know about.',
    icon: <Search size={18} />,
  },
  {
    title: 'Draft a change',
    prompt: 'Help me plan and implement the next small product improvement in nemo-platform.',
    icon: <Hammer size={18} />,
  },
  {
    title: 'Review recent work',
    prompt: 'Review the current working tree and call out anything risky or unfinished.',
    icon: <GitBranch size={18} />,
  },
];

const PromptCard = ({
  suggestion,
  onSelect,
}: {
  suggestion: PromptSuggestion;
  onSelect: () => void;
}) => (
  <Card asChild interactive className="min-h-28 w-full cursor-pointer shadow-none!">
    <button type="button" onClick={onSelect}>
      <span className="flex size-8 items-center justify-center rounded bg-surface-raised text-accent">
        {suggestion.icon}
      </span>
      <span className="min-w-0">
        <Text kind="label/bold/md">{suggestion.title}</Text>
        <Text kind="body/regular/sm" color="secondary" className="mt-1 line-clamp-2">
          {suggestion.prompt}
        </Text>
      </span>
    </button>
  </Card>
);

const LandingComposer = ({
  input,
  onChange,
  onSubmit,
}: {
  input: string;
  onChange: (value: string) => void;
  onSubmit: (prompt: string) => void;
}) => {
  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const prompt = input.trim();
    if (!prompt) return;

    onSubmit(prompt);
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="w-full rounded-2xl border border-base bg-surface-base p-2 shadow-xl"
    >
      <TextArea
        aria-label="Message Claude"
        value={input}
        onChange={(event: ChangeEvent<HTMLTextAreaElement>) => onChange(event.target.value)}
        placeholder="Message Claude"
        rows={3}
        resizeable="auto"
        className="max-h-56 w-full border-0 bg-transparent"
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

export const DashboardLandingRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const navigate = useNavigate();
  const [input, setInput] = useState('');

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
    <AccessibleTitle title="Dashboard">
      <main className="flex h-full min-h-[calc(100vh-var(--nv-app-bar-height))] items-center justify-center bg-surface-sunken px-4 py-10 text-primary">
        <Flex className="mx-auto flex w-full max-w-4xl flex-col items-center gap-8">
          <Flex className="flex flex-col items-center gap-3 text-center">
            <Text kind="body/bold/2xl" className="text-center">
              What would you like to do?
            </Text>
          </Flex>

          <LandingComposer input={input} onChange={setInput} onSubmit={handleSubmit} />

          <Flex className="grid w-full grid-cols-1 gap-3 md:grid-cols-3">
            {PROMPT_SUGGESTIONS.map((suggestion) => (
              <PromptCard
                key={suggestion.title}
                suggestion={suggestion}
                onSelect={() => handlePromptSelect(suggestion.prompt)}
              />
            ))}
          </Flex>
        </Flex>
      </main>
    </AccessibleTitle>
  );
};
