// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Collapsible, Stack, Text } from '@nvidia/foundations-react-core';
import { SuggestionTile } from '@studio/routes/agents/AgentSuggestionsRoute/components/SuggestionTile';
import type {
  OptimizationSuggestion,
  SuggestionTileProps,
} from '@studio/routes/agents/AgentSuggestionsRoute/types';
import { suggestionIdentity } from '@studio/routes/agents/AgentSuggestionsRoute/utils';
import { ChevronRight } from 'lucide-react';
import { type FC } from 'react';

interface AgentGroupSectionProps {
  group: { name: string; models: string[]; items: OptimizationSuggestion[] };
  getApplyState: (suggestion: OptimizationSuggestion) => {
    isApplying: boolean;
    isApplied: boolean;
    error: string | null;
  };
  getEvalState: (suggestion: OptimizationSuggestion) => SuggestionTileProps['evalState'];
  onApply: SuggestionTileProps['onApply'];
}

export const AgentGroupSection: FC<AgentGroupSectionProps> = ({
  group,
  getApplyState,
  getEvalState,
  onApply,
}) => (
  <Collapsible
    defaultOpen
    slotTrigger={
      <button
        type="button"
        className="group flex w-full items-center gap-density-sm py-density-sm text-left"
      >
        <ChevronRight
          size={16}
          className="text-secondary transition-transform duration-150 group-data-[state=open]:rotate-90"
        />
        <Text kind="body/bold/md">{group.name}</Text>
        {group.models.length > 0 && (
          <Text kind="body/regular/sm" color="secondary">
            {group.models.join(', ')}
          </Text>
        )}
      </button>
    }
  >
    <Stack gap="density-md" className="pt-density-sm">
      {group.items.map((suggestion) => {
        const applyState = getApplyState(suggestion);
        return (
          <SuggestionTile
            key={suggestionIdentity(suggestion)}
            suggestion={suggestion}
            onApply={onApply}
            isApplying={applyState.isApplying}
            isApplied={applyState.isApplied}
            applyError={applyState.error}
            evalState={getEvalState(suggestion)}
          />
        );
      })}
    </Stack>
  </Collapsible>
);
