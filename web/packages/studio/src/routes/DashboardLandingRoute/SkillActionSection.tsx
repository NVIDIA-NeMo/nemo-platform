// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Banner, Button, Card, Flex, Skeleton, Stack, Text } from '@nvidia/foundations-react-core';
import { Empty } from '@studio/components/Empty';
import type { SkillActionSuggestion } from '@studio/routes/DashboardLandingRoute/skillActionSuggestions';
import { type FC, type WheelEvent, useCallback, useEffect, useRef } from 'react';

const SKILL_ACTION_CARD_CLASS = 'h-40 w-72 flex-none cursor-pointer shadow-none!';

const HIDDEN_NATIVE_SCROLLBAR_CLASS = '[scrollbar-width:none] [&::-webkit-scrollbar]:hidden';
const MIN_SCROLLBAR_THUMB_PERCENT = 12;

interface SkillActionListProps {
  actions: SkillActionSuggestion[];
  onSelect: (prompt: string) => void;
}

const SkillActionList: FC<SkillActionListProps> = ({ actions, onSelect }) => {
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const scrollbarThumbRef = useRef<HTMLDivElement>(null);

  const updateScrollbar = useCallback(() => {
    const scrollContainer = scrollContainerRef.current;
    const scrollbarThumb = scrollbarThumbRef.current;
    if (!scrollContainer) return;

    const { clientWidth, scrollLeft, scrollWidth } = scrollContainer;
    const maxScrollLeft = scrollWidth - clientWidth;
    if (maxScrollLeft <= 0 || scrollWidth <= 0) {
      if (scrollbarThumb) {
        scrollbarThumb.style.marginLeft = '0%';
        scrollbarThumb.style.width = '100%';
      }
      return;
    }

    const thumbWidthPercent = Math.max(
      MIN_SCROLLBAR_THUMB_PERCENT,
      (clientWidth / scrollWidth) * 100
    );
    if (scrollbarThumb) {
      scrollbarThumb.style.marginLeft = `${(scrollLeft / maxScrollLeft) * (100 - thumbWidthPercent)}%`;
      scrollbarThumb.style.width = `${thumbWidthPercent}%`;
    }
  }, []);

  const handleWheel = (event: WheelEvent<HTMLDivElement>) => {
    if (Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return;

    const scrollContainer = event.currentTarget;
    const maxScrollLeft = scrollContainer.scrollWidth - scrollContainer.clientWidth;
    if (maxScrollLeft <= 0) return;

    const nextScrollLeft = Math.min(
      maxScrollLeft,
      Math.max(0, scrollContainer.scrollLeft + event.deltaY)
    );
    if (nextScrollLeft === scrollContainer.scrollLeft) return;

    event.preventDefault();
    scrollContainer.scrollLeft = nextScrollLeft;
    updateScrollbar();
  };

  const handleScroll = () => {
    updateScrollbar();
  };

  useEffect(() => {
    updateScrollbar();

    const scrollContainer = scrollContainerRef.current;
    if (!scrollContainer) return;

    const resizeObserver =
      typeof ResizeObserver === 'undefined' ? undefined : new ResizeObserver(updateScrollbar);
    resizeObserver?.observe(scrollContainer);
    window.addEventListener('resize', updateScrollbar);

    return () => {
      resizeObserver?.disconnect();
      window.removeEventListener('resize', updateScrollbar);
    };
  }, [actions.length, updateScrollbar]);

  return (
    <div className="w-full">
      <div
        ref={scrollContainerRef}
        aria-label="Skill action suggestions"
        className={`w-full overflow-x-auto ${HIDDEN_NATIVE_SCROLLBAR_CLASS}`}
        onScroll={handleScroll}
        onWheel={handleWheel}
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
      <div
        aria-hidden="true"
        className="h-2 w-full rounded-full bg-[var(--background-color-interaction-hover)]"
        data-testid="skill-action-scrollbar"
      >
        <div
          ref={scrollbarThumbRef}
          className="h-full rounded-full bg-[var(--border-color-interaction-base)]"
          data-testid="skill-action-scrollbar-thumb"
        />
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
