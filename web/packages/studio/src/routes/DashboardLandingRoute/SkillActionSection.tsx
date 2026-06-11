// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Banner, Button, Card, Flex, Skeleton, Stack, Text } from '@nvidia/foundations-react-core';
import { Empty } from '@studio/components/Empty';
import type { SkillActionSuggestion } from '@studio/routes/DashboardLandingRoute/skillActionSuggestions';
import type { FC } from 'react';

const SKILL_ACTION_CARD_CLASS = 'h-40 w-72 flex-none cursor-pointer shadow-none!';

const HORIZONTAL_SCROLLBAR_CLASS = [
  '[scrollbar-width:thin]',
  '[scrollbar-color:var(--border-color-interaction-base)_var(--background-color-interaction-hover)]',
  '[&::-webkit-scrollbar]:h-2',
  '[&::-webkit-scrollbar-corner]:bg-transparent',
  '[&::-webkit-scrollbar-track]:rounded-full',
  '[&::-webkit-scrollbar-track]:bg-[var(--background-color-interaction-hover)]',
  '[&::-webkit-scrollbar-thumb]:rounded-full',
  '[&::-webkit-scrollbar-thumb]:bg-[var(--border-color-interaction-base)]',
  '[&::-webkit-scrollbar-thumb:hover]:bg-[var(--border-color-interaction-strong)]',
].join(' ');

interface SkillActionListProps {
  actions: SkillActionSuggestion[];
  onSelect: (prompt: string) => void;
}

const SkillActionList: FC<SkillActionListProps> = ({ actions, onSelect }) => {
  return (
    <div
      aria-label="Skill action suggestions"
      className={`w-full overflow-x-auto ${HORIZONTAL_SCROLLBAR_CLASS}`}
    >
      <div
        className="flex w-max min-w-full items-stretch gap-density-md pb-density-lg"
        data-testid="skill-action-row"
      >
        {actions.map((action) => (
          <div
            key={`${action.skillName}:${action.claudeName}`}
            className="w-72 flex-none"
            data-testid={`skill-action-card-${action.skillName}`}
          >
            <Card asChild interactive className="h-40 w-full cursor-pointer shadow-none!">
              <button
                type="button"
                className="flex h-full w-full flex-col gap-density-md text-left"
                onClick={() => onSelect(action.prompt)}
              >
                <span className="flex size-8 shrink-0 items-center justify-center rounded bg-surface-raised text-accent">
                  {action.icon}
                </span>
                <span className="flex min-h-0 flex-1 flex-col gap-density-xxs">
                  <Text kind="label/bold/sm" className="line-clamp-1 block">
                    {action.title}
                  </Text>
                  <Text
                    kind="body/regular/xs"
                    color="secondary"
                    className="block truncate"
                    data-testid="skill-action-skill-name"
                  >
                    {action.skillName}
                  </Text>
                  <Text kind="body/regular/sm" color="secondary" className="line-clamp-2 block">
                    {action.description}
                  </Text>
                </span>
              </button>
            </Card>
          </div>
        ))}
      </div>
    </div>
  );
};

const SkillActionSkeleton = () => (
  <Flex gap="density-md" className="w-full overflow-hidden" data-testid="skill-actions-loading">
    {Array.from({ length: 3 }, (_, index) => (
      <Skeleton key={index} className={SKILL_ACTION_CARD_CLASS} />
    ))}
  </Flex>
);

export interface SkillActionSectionProps {
  actions: SkillActionSuggestion[];
  isError: boolean;
  isLoading: boolean;
  onRetry: () => void;
  onSelect: (prompt: string) => void;
  totalSkillCount: number;
}

export const SkillActionSection: FC<SkillActionSectionProps> = ({
  actions,
  isError,
  isLoading,
  onRetry,
  onSelect,
  totalSkillCount,
}) => {
  if (isLoading) {
    return <SkillActionSkeleton />;
  }

  if (isError) {
    return (
      <Stack gap="density-sm" className="w-full" data-testid="skill-actions-error">
        <Banner kind="inline" status="error">
          Could not load Claude skills.
        </Banner>
        <Flex justify="center">
          <Button kind="secondary" size="small" type="button" onClick={onRetry}>
            Retry
          </Button>
        </Flex>
      </Stack>
    );
  }

  if (!totalSkillCount) {
    return (
      <div className="w-full" data-testid="skill-actions-empty">
        <Empty
          title="No skills found"
          description="Claude Code skills will appear here once they are available in this workspace."
        />
      </div>
    );
  }

  if (!actions.length) {
    return (
      <Stack gap="density-sm" className="w-full text-center" data-testid="skill-actions-disabled">
        <Text kind="body/regular/sm" color="secondary">
          Skills are installed, but none are enabled for this workspace configuration.
        </Text>
      </Stack>
    );
  }

  return <SkillActionList actions={actions} onSelect={onSelect} />;
};
