// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Pending deploy→chat walkthroughs, keyed by agent name in sessionStorage so
// the trigger is scoped to the agent that was just created (not shareable via
// URL, not started against arbitrary agents). Cleared when the walkthrough ends.

const key = (agentName: string): string => `nemo:agent-walkthrough:${agentName}`;

export const markAgentWalkthroughPending = (agentName: string): void => {
  try {
    sessionStorage.setItem(key(agentName), '1');
  } catch {
    // sessionStorage unavailable (private mode / SSR) — walkthrough just won't show.
  }
};

export const isAgentWalkthroughPending = (agentName: string): boolean => {
  try {
    return sessionStorage.getItem(key(agentName)) === '1';
  } catch {
    return false;
  }
};

export const clearAgentWalkthroughPending = (agentName: string): void => {
  try {
    sessionStorage.removeItem(key(agentName));
  } catch {
    // ignore
  }
};

// Session-global flag: has the example-agent intro (open sidepanel + deploy→chat
// walkthrough) already been shown this session? Only the first example agent created
// per session gets the guided intro; later creations land quietly on the list. Being
// session-scoped, the first creation also covers the first-ever case.
const EXAMPLE_AGENT_INTRO_KEY = 'nemo:example-agent-intro-shown';

export const hasShownExampleAgentIntro = (): boolean => {
  try {
    return sessionStorage.getItem(EXAMPLE_AGENT_INTRO_KEY) === '1';
  } catch {
    return false;
  }
};

export const markExampleAgentIntroShown = (): void => {
  try {
    sessionStorage.setItem(EXAMPLE_AGENT_INTRO_KEY, '1');
  } catch {
    // sessionStorage unavailable (private mode / SSR) — intro just won't be suppressed.
  }
};
