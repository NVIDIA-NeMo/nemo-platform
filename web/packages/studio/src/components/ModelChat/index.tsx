// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { AssistantChat, type AssistantChatProps } from '@nemo/common/src/components/AssistantChat';
import type { AssistantMessageCompletion } from '@nemo/common/src/components/AssistantChat/types';
import type { ModelChatStatus } from '@nemo/common/src/utils/models';
import { DEFAULT_SEED_QUESTIONS } from '@studio/components/chat/defaultSeedQuestions';
import type { InferenceParams } from '@studio/components/chat/params';
import { SeedQuestions } from '@studio/components/chat/SeedQuestions';
import { StatsBadge, type ChatMetrics } from '@studio/components/chat/StatsBadge';
import { handleGenericError } from '@studio/util/logger';
import { useMemo, useState, type FC } from 'react';

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
  | 'cancelNonce'
  | 'onRunningChange'
> {
  /**
   * When provided, ModelChat derives default `disabled` state and a
   * status-aware empty state ("Chat Unavailable" / "Model Deployment in
   * Progress") from this status. Explicit `disabled` and `emptyState` take
   * precedence.
   */
  modelChatStatus?: ModelChatStatus;
  /** Per-panel system prompt; merged into promptData. */
  systemPrompt?: string;
  /** Per-panel inference parameters; merged into promptData.inference_params. */
  params?: InferenceParams;
  /** When set, renders the suggestion-chip strip above the composer when there
   *  are no messages yet. Clicking a chip seeds the composer (using the
   *  AssistantChat composer set-input API via a small DOM bridge). */
  seedQuestions?: string[];
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
  systemPrompt,
  params,
  promptData: promptDataProp,
  seedQuestions = DEFAULT_SEED_QUESTIONS,
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

  // Build the promptData payload AssistantChat understands. Explicit
  // `promptData` from the caller wins (existing callers like
  // ModelPanel / PromptTuningPanel set their own); otherwise we synthesize
  // one from the per-panel systemPrompt + params, falling back to undefined
  // so the runtime uses provider defaults.
  const promptData = useMemo(() => {
    if (promptDataProp) return promptDataProp;
    if (!systemPrompt && !params) return undefined;
    return {
      system_prompt: systemPrompt ?? '',
      inference_params: params
        ? {
            temperature: params.temperature,
            max_tokens: params.max_tokens,
          }
        : undefined,
    } as AssistantChatProps['promptData'];
  }, [promptDataProp, systemPrompt, params]);

  // Per-message metrics: store the latest completion so a single StatsBadge
  // can render under the chat surface.
  const [latestMetrics, setLatestMetrics] = useState<ChatMetrics | null>(null);

  const handleMessageComplete = (info: AssistantMessageCompletion) => {
    setLatestMetrics({
      ttftMs: info.ttftMs,
      totalMs: info.totalMs,
      completionTokens: info.completionTokens,
      tokensPerSec: info.tokensPerSec,
    });
  };

  // Seed-question handler: targets the AssistantChat composer's textarea by
  // selector and dispatches a native input event so assistant-ui picks it up.
  // Kept ugly-and-local on purpose — when the AssistantChat composer exposes a
  // proper setInput API we swap this out for a one-liner.
  const seedComposer = (text: string) => {
    if (typeof document === 'undefined') return;
    const composer = document.querySelector<HTMLTextAreaElement>(
      '.aui-composer-input textarea, [aria-label="Message Composer"] textarea, textarea[placeholder*="Message"]'
    );
    if (!composer) return;
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLTextAreaElement.prototype,
      'value'
    )?.set;
    setter?.call(composer, text);
    composer.dispatchEvent(new Event('input', { bubbles: true }));
    composer.focus();
  };

  // Seeds render INSIDE the AssistantChat composer card (above the textarea)
  // so the chip row + input share one bordered frame. Suppressed once the
  // panel has produced a metric (i.e. responded once) and in Compare mode
  // (the page-level CompareComposer owns seeds there).
  const showChatSeeds =
    !!seedQuestions && seedQuestions.length > 0 && !latestMetrics && !rest.hideComposer;
  const chatSeedSlot = showChatSeeds ? (
    <SeedQuestions questions={seedQuestions} onSelect={seedComposer} />
  ) : undefined;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1">
        <AssistantChat
          model={model}
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
      {latestMetrics && (
        <div className="shrink-0 px-3 pt-1 pb-2">
          <StatsBadge metrics={latestMetrics} />
        </div>
      )}
    </div>
  );
};
