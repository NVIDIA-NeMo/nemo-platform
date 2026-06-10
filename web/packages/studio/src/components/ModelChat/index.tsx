// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { AssistantChat, type AssistantChatProps } from '@nemo/common/src/components/AssistantChat';
import type { AssistantMessageCompletion } from '@nemo/common/src/components/AssistantChat/types';
import type { ModelChatStatus } from '@nemo/common/src/utils/models';
import { DEFAULT_SEED_QUESTIONS } from '@studio/components/chat/defaultSeedQuestions';
import type { InferenceParams } from '@studio/components/chat/params';
import { SeedQuestions } from '@studio/components/chat/SeedQuestions';
import type { AssistantMessageMetrics } from '@nemo/common/src/components/AssistantChat/types';
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
  /** Playground styling for the Chat tab single-panel layout. */
  variant?: 'default' | 'playground';
  /**
   * Fires with the full completion stats for each finished assistant turn, so a
   * parent (e.g. the Compare route) can aggregate timing across panels. Distinct
   * from the internal badge state, which keeps only the latest message.
   */
  onMetrics?: (info: AssistantMessageCompletion) => void;
}

/** Extra bottom inset inside compare panels so messages/stats clear the panel edge. */
const FLOATING_COMPOSER_CLEARANCE = 'pb-4';

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
  variant = 'default',
  placeholder,
  onMetrics,
  ...rest
}) => {
  const isPlayground = variant === 'playground';
  const resolvedPlaceholder = placeholder ?? (isPlayground ? 'Ask anything...' : undefined);
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
  const playgroundEmptyState = isPlayground
    ? { slotHeading: 'Ready', slotSubheading: 'Prompt your model to get started.' }
    : undefined;
  const resolvedEmptyState =
    emptyState ?? statusDerivedEmptyState ?? playgroundEmptyState ?? compareEmptyState;

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

  // Per-message timing keyed by assistant message id so every completed turn
  // renders its own stats, not just the latest reply.
  const [metricsById, setMetricsById] = useState<Record<string, AssistantMessageMetrics>>({});
  // Hide seed chips only after the user gets a reply via this panel's composer.
  // Compare-mode broadcasts also complete messages but must not suppress Chat-tab seeds.
  const [hasComposerResponse, setHasComposerResponse] = useState(false);

  const handleMessageComplete = (info: AssistantMessageCompletion) => {
    setMetricsById((prev) => ({
      ...prev,
      [info.assistantMessageId]: {
        ttftMs: info.ttftMs,
        completionTokens: info.completionTokens,
        tokensPerSec: info.tokensPerSec,
      },
    }));
    onMetrics?.(info);
    if (!rest.hideComposer) {
      setHasComposerResponse(true);
    }
  };

  // Seed-question handler: targets the AssistantChat composer's textarea by
  // selector and dispatches a native input event so assistant-ui picks it up.
  // Kept ugly-and-local on purpose — when the AssistantChat composer exposes a
  // proper setInput API we swap this out for a one-liner.
  const seedComposer = (text: string) => {
    if (typeof document === 'undefined') return;
    const composer = document.querySelector<HTMLTextAreaElement>(
      'textarea[aria-label="Task prompt"], .aui-composer-input textarea, [aria-label="Message Composer"] textarea, textarea[placeholder*="Ask anything"]'
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

  // Seeds sit above the playground composer until the user sends from this panel.
  // Compare mode owns its own seed row via CompareComposer.
  const showChatSeeds =
    !!seedQuestions && seedQuestions.length > 0 && !rest.hideComposer && !hasComposerResponse;
  const chatSeedSlot = showChatSeeds ? (
    <SeedQuestions
      questions={seedQuestions}
      onSelect={seedComposer}
      label={isPlayground ? 'Ask something like' : undefined}
    />
  ) : undefined;

  return (
    <div
      className={`flex h-full min-h-0 flex-col ${rest.hideComposer ? FLOATING_COMPOSER_CLEARANCE : ''}`}
    >
      <div className="min-h-0 flex-1">
        <AssistantChat
          model={model}
          assistantName={assistantName ?? model}
          disabled={resolvedDisabled}
          emptyState={resolvedEmptyState}
          onError={onError ?? handleGenericError}
          promptData={promptData}
          onMessageComplete={handleMessageComplete}
          placeholder={resolvedPlaceholder}
          composerVariant={isPlayground ? 'playground' : 'default'}
          assistantMessageMetricsById={metricsById}
          {...rest}
          slotAboveComposer={chatSeedSlot}
          onReset={() => {
            setHasComposerResponse(false);
            setMetricsById({});
          }}
        />
      </div>
    </div>
  );
};
