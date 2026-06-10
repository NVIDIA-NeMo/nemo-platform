// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Button, Flex } from '@nvidia/foundations-react-core';
import { SeedQuestions } from '@studio/components/chat/SeedQuestions';
import { RotateCcw, Send, Square } from 'lucide-react';
import * as React from 'react';
import { type FC, useCallback, useState } from 'react';

interface CompareComposerProps {
  /** Any panel currently streaming? Switches the Send button into a Stop button. */
  isAnyRunning: boolean;
  /** Number of panels with a model selected — used for the placeholder + disable state. */
  readyPanelCount: number;
  /** Total panel count — used to phrase the placeholder when models are missing. */
  totalPanelCount: number;
  onSubmit: (text: string) => void;
  onStop: () => void;
  /** Clears all panel histories. */
  onResetAll: () => void;
  /** Suggested prompts in a row above the input bar. */
  seedQuestions?: string[];
}

/**
 * Page-level composer for Compare mode. Mirrors the Chat-tab playground
 * composer: an "Ask something like" seed-chip row, then a tall input card with
 * the reset + broadcast/stop controls pinned to the bottom-right.
 */
export const CompareComposer: FC<CompareComposerProps> = ({
  isAnyRunning,
  readyPanelCount,
  totalPanelCount,
  onSubmit,
  onStop,
  onResetAll,
  seedQuestions,
}) => {
  const [draft, setDraft] = useState('');

  const canSend = !isAnyRunning && readyPanelCount > 0 && draft.trim().length > 0;

  const handleSubmit = useCallback(() => {
    if (!canSend) return;
    onSubmit(draft.trim());
    setDraft('');
  }, [canSend, draft, onSubmit]);

  const onKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit]
  );

  const placeholder =
    readyPanelCount === 0
      ? totalPanelCount > 0
        ? 'Pick a model in each panel to broadcast a prompt…'
        : 'Add panels and pick models to broadcast…'
      : `Broadcast to ${readyPanelCount} of ${totalPanelCount} panel${
          totalPanelCount === 1 ? '' : 's'
        }…`;

  const showSeeds =
    !!seedQuestions && seedQuestions.length > 0 && !isAnyRunning && draft.trim().length === 0;

  return (
    <Flex direction="col" gap="density-md" className="w-full">
      {showSeeds ? (
        <SeedQuestions questions={seedQuestions} onSelect={(text) => setDraft(text)} />
      ) : null}
      <div className="relative w-full rounded-lg border border-base bg-surface-base focus-within:border-emphasis">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          rows={1}
          disabled={readyPanelCount === 0}
          aria-label="Compare prompt"
          className="placeholder:text-fg-subdued max-h-64 min-h-[88px] w-full resize-none border-0 bg-transparent p-3 pb-14 text-sm outline-none disabled:cursor-not-allowed disabled:text-fg-disabled"
        />
        <Flex gap="density-sm" align="center" justify="end" className="absolute bottom-2 right-2">
          <Button
            kind="tertiary"
            size="small"
            onClick={onResetAll}
            title="Clear all panels"
            aria-label="Clear all panels"
          >
            <RotateCcw size={16} />
          </Button>
          {isAnyRunning ? (
            <Button
              color="danger"
              size="small"
              onClick={onStop}
              title="Stop all panels"
              aria-label="Stop all panels"
            >
              <Square size={16} />
            </Button>
          ) : (
            <Button
              color="brand"
              size="small"
              onClick={handleSubmit}
              disabled={!canSend}
              title="Broadcast to all panels"
              aria-label="Broadcast to all panels"
            >
              <Send size={16} />
            </Button>
          )}
        </Flex>
      </div>
    </Flex>
  );
};
