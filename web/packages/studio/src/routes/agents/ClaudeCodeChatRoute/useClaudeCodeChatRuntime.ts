// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ThreadMessageLike } from '@assistant-ui/react';
import {
  CANCELLED_STATUS,
  COMPLETE_STATUS,
} from '@nemo/common/src/components/AssistantChat/constants';
import type {
  AgentDecisionChoice,
  AgentDecisionInputStatus,
  AgentDecisionRequest,
  AgentDecisionSubmission,
} from '@studio/components/agents/AgentDecisionInput';
import {
  CLAUDE_CODE_HISTORY_SESSIONS_QUERY_KEY,
  createClaudeCodeSession,
  resolveClaudeCodeInput,
  resolveClaudeCodePermission,
  streamClaudeCodeMessage,
} from '@studio/routes/agents/ClaudeCodeChatRoute/api';
import {
  createEmptyClaudeCodeChatArtifacts,
  updateClaudeCodeChatArtifactsFromEvent,
  updateClaudeCodeChatArtifactsFromSelections,
} from '@studio/routes/agents/ClaudeCodeChatRoute/artifacts';
import { getAssistantPartsFromClaudeEvent } from '@studio/routes/agents/ClaudeCodeChatRoute/stream';
import {
  getStudioUiNavigationSuggestion,
  type StudioUiNavigationSuggestion,
} from '@studio/routes/agents/ClaudeCodeChatRoute/studioUiNavigationSuggestions';
import type {
  ClaudeCodeChatArtifacts,
  ClaudeCodeInputDecision,
  ClaudeCodeInputRequest,
  ClaudeCodePermissionRequest,
} from '@studio/routes/agents/ClaudeCodeChatRoute/types';
import {
  useCustomAssistantChatRuntime,
  type CustomAssistantRunContext,
  type CustomAssistantRunResult,
} from '@studio/routes/agents/ClaudeCodeChatRoute/useCustomAssistantChatRuntime';
import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';

const ASK_USER_QUESTION_TOOL_NAME = 'AskUserQuestion';
const CUSTOM_INSTRUCTION_LABEL = 'No, and tell the Agent what to do';
const CUSTOM_INSTRUCTION_PLACEHOLDER = 'Tell the Agent what to do';

const createCustomInstructionChoice = (id: string): AgentDecisionChoice => ({
  id,
  label: CUSTOM_INSTRUCTION_LABEL,
  input: {
    ariaLabel: CUSTOM_INSTRUCTION_PLACEHOLDER,
    placeholder: CUSTOM_INSTRUCTION_PLACEHOLDER,
  },
});

const PERMISSION_CHOICES: readonly AgentDecisionChoice[] = [
  { id: 'yes', label: 'Yes' },
  { id: 'no', label: 'No' },
  createCustomInstructionChoice('alternative'),
];

interface AskUserQuestionOption {
  label: string;
  description?: string;
}

interface AskUserQuestion {
  question: string;
  header?: string;
  options: readonly AskUserQuestionOption[];
}

interface PermissionDecisionState {
  kind: 'permission';
}

interface AskUserQuestionDecisionState {
  kind: 'ask-user-question';
  questions: readonly AskUserQuestion[];
  questionIndex: number;
  answers: Record<string, string>;
}

type ActiveDecisionState = PermissionDecisionState | AskUserQuestionDecisionState;

export type StudioNavigationDecision = 'continue' | 'navigate' | 'cancel';

export interface StudioNavigationRequest {
  id: string;
  prompt: string;
  suggestion: StudioUiNavigationSuggestion;
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null;

const isDefined = <T>(value: T | undefined): value is T => value !== undefined;

const trimString = (value: unknown): string | undefined => {
  if (typeof value !== 'string') return undefined;
  const trimmed = value.trim();
  return trimmed || undefined;
};

const parseAskUserQuestionOption = (value: unknown): AskUserQuestionOption | undefined => {
  if (!isRecord(value)) return undefined;

  const label = trimString(value.label);
  if (!label) return undefined;

  return {
    label,
    description: trimString(value.description),
  };
};

const parseAskUserQuestion = (value: unknown): AskUserQuestion | undefined => {
  if (!isRecord(value)) return undefined;

  const question = trimString(value.question);
  if (!question) return undefined;

  const options = Array.isArray(value.options)
    ? value.options.map(parseAskUserQuestionOption).filter(isDefined)
    : [];

  return {
    question,
    header: trimString(value.header),
    options,
  };
};

const parseAskUserQuestions = (input: Record<string, unknown>): readonly AskUserQuestion[] => {
  if (!Array.isArray(input.questions)) return [];
  return input.questions.map(parseAskUserQuestion).filter(isDefined);
};

const createAskUserQuestionChoices = (
  question: AskUserQuestion
): readonly AgentDecisionChoice[] => {
  if (!question.options.length) {
    return [createCustomInstructionChoice('answer-text')];
  }

  return [
    ...question.options.map((option, index) => ({
      id: `answer-${index}`,
      label: option.label,
      description: option.description,
    })),
    createCustomInstructionChoice('answer-custom'),
  ];
};

const createAskUserQuestionRequest = (
  requestId: string,
  state: AskUserQuestionDecisionState
): AgentDecisionRequest => {
  const question = state.questions[state.questionIndex];
  const title = question.header ?? 'Agent question';

  return {
    id: `${requestId}:${state.questionIndex}`,
    title:
      state.questions.length > 1
        ? `${title} (${state.questionIndex + 1} of ${state.questions.length})`
        : title,
    description: question.question,
  };
};

const quoteAnswerValue = (value: string): string =>
  `"${value.replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`;

const formatAskUserQuestionReason = (
  questions: readonly AskUserQuestion[],
  answers: Record<string, string>
): string => {
  const answerText = questions
    .map((question) => {
      const answer = answers[question.question];
      if (!answer) return undefined;
      return `${quoteAnswerValue(question.question)}=${quoteAnswerValue(answer)}`;
    })
    .filter(isDefined)
    .join(', ');

  if (questions.length === 1) {
    return `Your question has been answered: ${answerText}. You can now continue with this answer in mind.`;
  }

  return `Your questions have been answered: ${answerText}. You can now continue with these answers in mind.`;
};

const formatAskUserQuestionDisplayText = (
  questions: readonly AskUserQuestion[],
  answers: Record<string, string>
): string =>
  questions
    .map((question) => {
      const answer = answers[question.question];
      if (!answer) return undefined;
      return `${question.question}\n${answer}`;
    })
    .filter(isDefined)
    .join('\n\n');

const getArtifactsSignature = (artifacts: ClaudeCodeChatArtifacts | undefined): string =>
  artifacts ? JSON.stringify(artifacts) : '';

const createWorkspaceArtifacts = (
  artifacts: ClaudeCodeChatArtifacts | undefined,
  workspace: string | undefined
): ClaudeCodeChatArtifacts => {
  const nextArtifacts = artifacts ?? createEmptyClaudeCodeChatArtifacts();
  return nextArtifacts.workspace || !workspace
    ? nextArtifacts
    : {
        ...nextArtifacts,
        workspace,
      };
};

interface UseClaudeCodeChatRuntimeOptions {
  initialArtifacts?: ClaudeCodeChatArtifacts;
  initialMessages?: readonly ThreadMessageLike[];
  initialSessionId?: string;
  onError?: (error: Error) => void;
  onSessionIdChange?: (sessionId: string | null) => void;
  studioPathname?: string;
  workspace?: string;
}

interface LoadClaudeCodeSessionOptions {
  artifacts?: ClaudeCodeChatArtifacts;
  messages: readonly ThreadMessageLike[];
  sessionId: string;
}

export const useClaudeCodeChatRuntime = (options?: UseClaudeCodeChatRuntimeOptions) => {
  const queryClient = useQueryClient();
  const workspace = options?.workspace;
  const [sessionId, setSessionId] = useState<string | null>(options?.initialSessionId ?? null);
  const [artifacts, setArtifacts] = useState<ClaudeCodeChatArtifacts>(
    createWorkspaceArtifacts(options?.initialArtifacts, workspace)
  );
  const [decisionRequest, setDecisionRequest] = useState<AgentDecisionRequest | null>(null);
  const [decisionChoices, setDecisionChoices] = useState<readonly AgentDecisionChoice[]>([]);
  const [decisionStatus, setDecisionStatus] = useState<AgentDecisionInputStatus>('pending');
  const [inputRequest, setInputRequest] = useState<ClaudeCodeInputRequest | null>(null);
  const [inputStatus, setInputStatus] = useState<AgentDecisionInputStatus>('pending');
  const [studioNavigationRequest, setStudioNavigationRequest] =
    useState<StudioNavigationRequest | null>(null);
  const [studioNavigationStatus, setStudioNavigationStatus] =
    useState<AgentDecisionInputStatus>('pending');
  const sessionIdRef = useRef<string | null>(options?.initialSessionId ?? null);
  const permissionRequestRef = useRef<ClaudeCodePermissionRequest | null>(null);
  const inputRequestRef = useRef<ClaudeCodeInputRequest | null>(null);
  const studioNavigationResolverRef = useRef<((decision: StudioNavigationDecision) => void) | null>(
    null
  );
  const activeDecisionRef = useRef<ActiveDecisionState | null>(null);
  const initialArtifactsRef = useRef<ClaudeCodeChatArtifacts | undefined>(
    options?.initialArtifacts
  );
  const initialArtifactsSignature = getArtifactsSignature(options?.initialArtifacts);
  const onError = options?.onError;
  const onSessionIdChange = options?.onSessionIdChange;
  const studioPathname = options?.studioPathname;

  initialArtifactsRef.current = options?.initialArtifacts;

  useEffect(() => {
    setArtifacts(createWorkspaceArtifacts(initialArtifactsRef.current, workspace));
  }, [initialArtifactsSignature, workspace]);

  const ensureSessionId = useCallback(async (): Promise<string> => {
    if (sessionIdRef.current) return sessionIdRef.current;

    const nextSessionId = await createClaudeCodeSession();
    sessionIdRef.current = nextSessionId;
    setSessionId(nextSessionId);
    onSessionIdChange?.(nextSessionId);
    return nextSessionId;
  }, [onSessionIdChange]);

  const clearPermissionRequest = useCallback((requestId?: string) => {
    if (requestId && permissionRequestRef.current?.requestId !== requestId) return;

    permissionRequestRef.current = null;
    activeDecisionRef.current = null;
    setDecisionRequest(null);
    setDecisionChoices([]);
    setDecisionStatus('pending');
  }, []);

  const clearInputRequest = useCallback((requestId?: string) => {
    if (requestId && inputRequestRef.current?.requestId !== requestId) return;

    inputRequestRef.current = null;
    setInputRequest(null);
    setInputStatus('pending');
  }, []);

  const clearStudioNavigationRequest = useCallback(() => {
    studioNavigationResolverRef.current = null;
    setStudioNavigationRequest(null);
    setStudioNavigationStatus('pending');
  }, []);

  const resolveStudioNavigationRequest = useCallback((decision: StudioNavigationDecision) => {
    const resolve = studioNavigationResolverRef.current;
    if (!resolve) return;

    setStudioNavigationStatus('submitting');
    resolve(decision);
  }, []);

  const setAskUserQuestionDecision = useCallback(
    (request: ClaudeCodePermissionRequest, state: AskUserQuestionDecisionState) => {
      const question = state.questions[state.questionIndex];
      const choices = createAskUserQuestionChoices(question);

      activeDecisionRef.current = state;
      setDecisionStatus('pending');
      setDecisionRequest(createAskUserQuestionRequest(request.requestId, state));
      setDecisionChoices(choices);
    },
    []
  );

  const handlePermissionRequest = useCallback(
    (request: ClaudeCodePermissionRequest) => {
      const actionDescription =
        typeof request.input.description === 'string' ? request.input.description : undefined;

      clearInputRequest();
      permissionRequestRef.current = request;
      activeDecisionRef.current = { kind: 'permission' };
      setDecisionStatus('pending');

      if (request.toolName === ASK_USER_QUESTION_TOOL_NAME) {
        const questions = parseAskUserQuestions(request.input);
        if (questions.length) {
          const state: AskUserQuestionDecisionState = {
            kind: 'ask-user-question',
            questions,
            questionIndex: 0,
            answers: {},
          };
          setAskUserQuestionDecision(request, state);
          return;
        }
      }

      setDecisionRequest({
        id: request.requestId,
        title: 'Approval required',
        description: `Agent wants to use ${request.toolName}${
          actionDescription ? `: ${actionDescription}` : ''
        }.`,
        details: request.input,
      });
      setDecisionChoices(PERMISSION_CHOICES);
    },
    [clearInputRequest, setAskUserQuestionDecision]
  );

  const handleInputRequest = useCallback(
    (request: ClaudeCodeInputRequest) => {
      clearPermissionRequest();
      clearStudioNavigationRequest();

      inputRequestRef.current = request;
      setInputStatus('pending');
      setInputRequest(request);
    },
    [clearPermissionRequest, clearStudioNavigationRequest]
  );

  const requestStudioNavigationDecision = useCallback(
    async ({
      prompt,
      signal,
      prepareForUserInput,
      isCurrentRun,
    }: {
      prompt: string;
      signal: AbortSignal;
      prepareForUserInput: () => void;
      isCurrentRun: () => boolean;
    }): Promise<'continue' | 'cancel'> => {
      if (!workspace) return 'continue';

      const suggestion = getStudioUiNavigationSuggestion(prompt, workspace);
      if (!suggestion) return 'continue';

      clearPermissionRequest();
      clearInputRequest();
      prepareForUserInput();

      let resolveDecision: (decision: StudioNavigationDecision) => void = () => undefined;
      const decisionPromise = new Promise<StudioNavigationDecision>((resolve) => {
        resolveDecision = resolve;
      });
      studioNavigationResolverRef.current = resolveDecision;
      setStudioNavigationStatus('pending');
      setStudioNavigationRequest({
        id: `${suggestion.id}:${Date.now()}`,
        prompt,
        suggestion,
      });

      const handleAbort = () => resolveDecision('cancel');
      signal.addEventListener('abort', handleAbort, { once: true });

      try {
        const decision = await decisionPromise;
        if (!isCurrentRun()) return 'cancel';
        return decision === 'continue' ? 'continue' : 'cancel';
      } finally {
        signal.removeEventListener('abort', handleAbort);
        if (studioNavigationResolverRef.current === resolveDecision) {
          clearStudioNavigationRequest();
        }
      }
    },
    [clearInputRequest, clearPermissionRequest, clearStudioNavigationRequest, workspace]
  );

  // Extracted into useCallback so onRun is a stable reference. An inline async
  // function recreates on every render, which propagates through runCompletion →
  // handleNewMessage → useExternalStoreRuntime, causing the runtime to be
  // recreated on every streaming chunk and every message to re-render/flicker.
  const handleRun = useCallback(
    async ({
      prompt,
      signal,
      appendAssistantParts,
      prepareForUserInput,
      isCurrentRun,
    }: CustomAssistantRunContext): Promise<CustomAssistantRunResult | void> => {
      clearPermissionRequest();
      clearInputRequest();
      clearStudioNavigationRequest();
      const activeSessionId = await ensureSessionId();
      let doneReceived = false;

      try {
        await streamClaudeCodeMessage({
          sessionId: activeSessionId,
          message: prompt,
          studioPathname,
          workspace,
          signal,
          handlers: {
            onClaudeEvent: (event) => {
              if (signal.aborted || !isCurrentRun()) return;

              setArtifacts((current) => updateClaudeCodeChatArtifactsFromEvent(current, event));
              appendAssistantParts(getAssistantPartsFromClaudeEvent(event));
            },
            onPermissionRequest: (request) => {
              if (signal.aborted || !isCurrentRun()) return;
              prepareForUserInput();
              handlePermissionRequest(request);
            },
            onInputRequest: (request) => {
              if (signal.aborted || !isCurrentRun()) return;
              prepareForUserInput();
              handleInputRequest(request);
            },
            onDone: () => {
              doneReceived = true;
            },
            onError: (error) => {
              throw error;
            },
          },
        });
        void queryClient.invalidateQueries({ queryKey: CLAUDE_CODE_HISTORY_SESSIONS_QUERY_KEY });
      } finally {
        if (isCurrentRun()) {
          clearPermissionRequest();
          clearInputRequest();
        }
      }

      return { status: doneReceived ? COMPLETE_STATUS : CANCELLED_STATUS };
    },
    [
      clearPermissionRequest,
      clearInputRequest,
      clearStudioNavigationRequest,
      ensureSessionId,
      studioPathname,
      workspace,
      setArtifacts,
      handlePermissionRequest,
      handleInputRequest,
      queryClient,
    ]
  );

  const {
    appendUserMessage,
    handleReset: resetThread,
    isRunning,
    replaceMessages,
    runtime,
    submitPrompt,
  } = useCustomAssistantChatRuntime({
    initialMessages: options?.initialMessages,
    onBeforeRun: requestStudioNavigationDecision,
    onError,
    onRun: handleRun,
  });

  const resolveInputRequest = useCallback(
    async ({
      decision,
      displayText,
    }: {
      decision: ClaudeCodeInputDecision;
      displayText?: string;
    }) => {
      const activeSessionId = sessionIdRef.current;
      const activeRequest = inputRequestRef.current;
      if (!activeSessionId || !activeRequest) return;

      const trimmedDisplayText = displayText?.trim();
      setInputStatus('submitting');

      try {
        await resolveClaudeCodeInput({
          sessionId: activeSessionId,
          requestId: activeRequest.requestId,
          decision,
        });
        if (!decision.skipped && trimmedDisplayText) {
          appendUserMessage(trimmedDisplayText);
        }
        clearInputRequest(activeRequest.requestId);
      } catch (error: unknown) {
        if (inputRequestRef.current?.requestId === activeRequest.requestId) {
          setInputStatus('pending');
        }
        const errorMessage =
          error instanceof Error ? error.message : 'Failed to resolve Claude Code input';
        onError?.(new Error(errorMessage));
      }
    },
    [appendUserMessage, clearInputRequest, onError]
  );

  const submitActiveDecision = useCallback(
    async ({
      approved,
      displayText,
      reason,
    }: {
      approved: boolean;
      displayText?: string;
      reason?: string;
    }): Promise<boolean> => {
      const activeSessionId = sessionIdRef.current;
      const activeRequest = permissionRequestRef.current;
      if (!activeSessionId || !activeRequest) return false;

      const trimmedReason = reason?.trim();
      const trimmedDisplayText = displayText?.trim();
      setDecisionStatus('submitting');

      try {
        await resolveClaudeCodePermission({
          sessionId: activeSessionId,
          requestId: activeRequest.requestId,
          decision: {
            approved,
            reason: approved ? undefined : trimmedReason || 'Denied by user',
          },
        });
        if (!approved && trimmedDisplayText) {
          appendUserMessage(trimmedDisplayText);
        }
        clearPermissionRequest(activeRequest.requestId);
        return true;
      } catch (error: unknown) {
        if (permissionRequestRef.current?.requestId === activeRequest.requestId) {
          setDecisionStatus('pending');
        }
        const errorMessage =
          error instanceof Error ? error.message : 'Failed to resolve Claude Code permission';
        onError?.(new Error(errorMessage));
        return false;
      }
    },
    [appendUserMessage, clearPermissionRequest, onError]
  );

  const resolveAskUserQuestionDecision = useCallback(
    async (choice: AgentDecisionChoice, submission?: AgentDecisionSubmission) => {
      const activeRequest = permissionRequestRef.current;
      const state = activeDecisionRef.current;
      if (!activeRequest || state?.kind !== 'ask-user-question') return;

      const activeQuestion = state.questions[state.questionIndex];
      const answer = submission?.text?.trim() || choice.label.trim();
      if (!answer) return;

      const answers = {
        ...state.answers,
        [activeQuestion.question]: answer,
      };

      if (state.questionIndex < state.questions.length - 1) {
        setAskUserQuestionDecision(activeRequest, {
          ...state,
          answers,
          questionIndex: state.questionIndex + 1,
        });
        return;
      }

      const submitted = await submitActiveDecision({
        approved: false,
        reason: formatAskUserQuestionReason(state.questions, answers),
        displayText: formatAskUserQuestionDisplayText(state.questions, answers),
      });
      if (submitted) {
        setArtifacts((current) =>
          updateClaudeCodeChatArtifactsFromSelections(current, state.questions, answers)
        );
      }
    },
    [setAskUserQuestionDecision, submitActiveDecision]
  );

  const resolveDecisionRequest = useCallback(
    async (choice: AgentDecisionChoice, submission?: AgentDecisionSubmission) => {
      const state = activeDecisionRef.current;
      if (state?.kind === 'ask-user-question') {
        await resolveAskUserQuestionDecision(choice, submission);
        return;
      }

      const approved = choice.id === 'yes';
      const trimmedReason = submission?.text?.trim();

      await submitActiveDecision({
        approved,
        reason: approved ? undefined : trimmedReason || 'Denied by user',
        displayText: approved ? undefined : trimmedReason,
      });
    },
    [resolveAskUserQuestionDecision, submitActiveDecision]
  );

  const skipDecisionRequest = useCallback(async () => {
    await submitActiveDecision({ approved: false, reason: 'Skipped by user' });
  }, [submitActiveDecision]);

  const skipInputRequest = useCallback(async () => {
    await resolveInputRequest({ decision: { skipped: true } });
  }, [resolveInputRequest]);

  const handleReset = useCallback(() => {
    sessionIdRef.current = null;
    setSessionId(null);
    onSessionIdChange?.(null);
    setArtifacts(createWorkspaceArtifacts(undefined, workspace));
    clearPermissionRequest();
    clearInputRequest();
    resolveStudioNavigationRequest('cancel');
    clearStudioNavigationRequest();
    resetThread();
  }, [
    clearInputRequest,
    clearPermissionRequest,
    clearStudioNavigationRequest,
    onSessionIdChange,
    resetThread,
    resolveStudioNavigationRequest,
    workspace,
  ]);

  const loadSession = useCallback(
    ({
      artifacts: nextArtifacts,
      messages,
      sessionId: nextSessionId,
    }: LoadClaudeCodeSessionOptions) => {
      sessionIdRef.current = nextSessionId;
      setSessionId(nextSessionId);
      onSessionIdChange?.(nextSessionId);
      setArtifacts(createWorkspaceArtifacts(nextArtifacts, workspace));
      clearPermissionRequest();
      clearInputRequest();
      resolveStudioNavigationRequest('cancel');
      clearStudioNavigationRequest();
      replaceMessages(messages);
    },
    [
      clearInputRequest,
      clearPermissionRequest,
      clearStudioNavigationRequest,
      onSessionIdChange,
      replaceMessages,
      resolveStudioNavigationRequest,
      workspace,
    ]
  );

  return {
    artifacts,
    decisionChoices,
    decisionRequest,
    decisionStatus,
    handleReset,
    inputRequest,
    inputStatus,
    isRunning,
    loadSession,
    resolveInputRequest,
    resolveDecisionRequest,
    resolveStudioNavigationRequest,
    runtime,
    sessionId,
    skipInputRequest,
    skipDecisionRequest,
    studioNavigationRequest,
    studioNavigationStatus,
    submitPrompt,
  };
};

export type ClaudeCodeChatRuntime = ReturnType<typeof useClaudeCodeChatRuntime>;
