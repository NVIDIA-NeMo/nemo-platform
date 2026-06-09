// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { AssistantChat, type AssistantChatProps } from '@nemo/common/src/components/AssistantChat';
import type { AssistantMessageCompletion } from '@nemo/common/src/components/AssistantChat/types';
import type { ModelChatStatus } from '@nemo/common/src/utils/models';
import { DEFAULT_SEED_QUESTIONS } from '@studio/components/chat/defaultSeedQuestions';
import { SeedQuestions } from '@studio/components/chat/SeedQuestions';
import { StatsBadge, type ChatMetrics } from '@studio/components/chat/StatsBadge';
import { handleGenericError } from '@studio/util/logger';
import { type ReactNode, useEffect, useRef, useState, type FC } from 'react';

interface ModelChatProps extends Pick<
  AssistantChatProps,
  | 'model'
  | 'workspace'
  | 'baseURL'
  | 'promptData'
  | 'tools'
  | 'assistantName'
  | 'placeholder'
  | 'disabled'
  | 'className'
  | 'initialMessages'
  | 'emptyState'
  | 'onError'
  | 'hideComposer'
  | 'broadcast'
  | 'stopCount'
  | 'onRunningChange'
> {
  /**
   * When provided, ModelChat derives default `disabled` state and a
   * status-aware empty state ("Chat Unavailable" / "Model Deployment in
   * Progress") from this status. Explicit `disabled` and `emptyState` take
   * precedence.
   */
  modelChatStatus?: ModelChatStatus;
  /** When set, renders the suggestion-chip strip above the composer when there
   *  are no messages yet. Clicking a chip seeds the composer (using the
   *  AssistantChat composer set-input API via a small DOM bridge). */
  seedQuestions?: string[];
  /** When false, hides the per-response StatsBadge. Default true. */
  showMetrics?: boolean;
  /** Rendered right-aligned at the trailing end of the seed-questions row. */
  composerToggle?: ReactNode;
  /** When triggerCount changes, pre-fills the panel's composer textarea with text. */
  composerSeed?: { triggerCount: number; text: string };
}

const STATUS_EMPTY_STATE: Record<
  Exclude<ModelChatStatus, 'enabled'>,
  NonNullable<AssistantChatProps['emptyState']>
> = {
  disabled: {
    slotHeading: 'Chat Unavailable',
    slotSubheading: 'This model does not have an active deployment.',
  },
  pending: {
    slotHeading: 'Model Deployment in Progress',
    slotSubheading: 'Check back in a few minutes to chat with this model.',
  },
};

export const ModelChat: FC<ModelChatProps> = ({
  model,
  modelChatStatus,
  disabled,
  assistantName,
  emptyState,
  onError,
  promptData,
  seedQuestions = DEFAULT_SEED_QUESTIONS,
  showMetrics = true,
  composerToggle,
  composerSeed,
  workspace,
  ...rest
}) => {
  const resolvedDisabled = disabled ?? (modelChatStatus ? modelChatStatus !== 'enabled' : false);
  const statusDerivedEmptyState =
    disabled === undefined && modelChatStatus && modelChatStatus !== 'enabled'
      ? STATUS_EMPTY_STATE[modelChatStatus]
      : undefined;
  // In Compare mode (hideComposer = true) the page-level composer is the
  // affordance, so the per-panel subhead "Prompt your model to get started."
  // is redundant — surface only the headline.
  const compareEmptyState = rest.hideComposer
    ? { slotHeading: 'Ready', slotSubheading: '' }
    : undefined;
  const resolvedEmptyState = emptyState ?? statusDerivedEmptyState ?? compareEmptyState;

  // Per-message metrics: store the latest completion so a single StatsBadge
  // can render under the chat surface.
  const [latestMetrics, setLatestMetrics] = useState<ChatMetrics | null>(null);

  // Clear stale metrics when inference identity changes (different model or workspace).
  const prevModelRef = useRef(model);
  const prevWorkspaceRef = useRef(workspace);
  if (model !== prevModelRef.current || workspace !== prevWorkspaceRef.current) {
    prevModelRef.current = model;
    prevWorkspaceRef.current = workspace;
    if (latestMetrics !== null) setLatestMetrics(null);
  }

  const handleMessageComplete = (info: AssistantMessageCompletion) => {
    setLatestMetrics({
      ttftMs: info.ttftMs,
      totalMs: info.totalMs,
      completionTokens: info.completionTokens,
      tokensPerSec: info.tokensPerSec,
    });
  };

  const containerRef = useRef<HTMLDivElement>(null);

  // Scoped textarea setter — finds the panel's own composer, not any global one.
  // Kept DOM-based until AssistantChat exposes a proper setInput API.
  const setComposerText = (text: string) => {
    if (typeof document === 'undefined' || !containerRef.current) return;
    const textarea = containerRef.current.querySelector<HTMLTextAreaElement>(
      'textarea[aria-label="Task prompt"]'
    );
    if (!textarea) return;
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
    setter?.call(textarea, text);
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
    textarea.focus();
  };

  const seedComposer = (text: string) => setComposerText(text);

  // Pre-fill from parent (mode toggle transfer: broadcast→panels).
  // Intentionally omits composerSeed.text: only fire when triggerCount changes.
  useEffect(() => {
    if (composerSeed?.text) setComposerText(composerSeed.text);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [composerSeed?.triggerCount]);

  // Seeds render INSIDE the AssistantChat composer card (above the textarea).
  // Always shown when the composer is visible — not suppressed after first response.
  // In broadcast-all mode (hideComposer=true) the page-level CompareComposer owns seeds.
  const showChatSeeds = !!seedQuestions && seedQuestions.length > 0 && !rest.hideComposer;

  // In per-panel mode: metrics sit above seeds in slotAboveComposer so they
  // appear inside the composer frame, above the textarea.
  // In broadcast-all mode: hideComposer hides slotAboveComposer entirely, so
  // metrics fall back to the standalone div below the chat surface.
  const metricsInComposer = showMetrics && latestMetrics && !rest.hideComposer;
  const metricsBelow = showMetrics && latestMetrics && !!rest.hideComposer;

  const chatSeedSlot =
    showChatSeeds || metricsInComposer || (composerToggle && !rest.hideComposer) ? (
      <>
        {metricsInComposer && (
          <div className="px-3 pt-1">
            <StatsBadge metrics={latestMetrics} />
          </div>
        )}
        {(showChatSeeds || (composerToggle && !rest.hideComposer)) && (
          <SeedQuestions
            questions={showChatSeeds ? seedQuestions : []}
            onSelect={seedComposer}
            slotEnd={composerToggle}
          />
        )}
      </>
    ) : undefined;

  return (
    <div ref={containerRef} className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1">
        <AssistantChat
          model={model}
          workspace={workspace}
          assistantName={assistantName ?? model}
          disabled={resolvedDisabled}
          emptyState={resolvedEmptyState}
          onError={onError ?? handleGenericError}
          promptData={promptData}
          onMessageComplete={handleMessageComplete}
          {...rest}
          slotAboveComposer={chatSeedSlot}
        />
      </div>
      {metricsBelow && (
        <div className="shrink-0 px-3 pt-1">
          <StatsBadge metrics={latestMetrics} />
        </div>
      )}
    </div>
  );
};
