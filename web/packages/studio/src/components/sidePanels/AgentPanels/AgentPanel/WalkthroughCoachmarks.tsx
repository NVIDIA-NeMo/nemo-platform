// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Coachmark } from '@studio/components/sidePanels/AgentPanels/AgentPanel/Coachmark';
import {
  type WalkthroughStep,
  WALKTHROUGH_COPY,
} from '@studio/components/sidePanels/AgentPanels/AgentPanel/walkthrough';
import type { FC, RefObject } from 'react';

interface WalkthroughCoachmarksProps {
  walkthroughStep: WalkthroughStep | null;
  deployButtonRef: RefObject<HTMLDivElement | null>;
  tabsRef: RefObject<HTMLDivElement | null>;
  chatAreaRef: RefObject<HTMLDivElement | null>;
  onDismiss: () => void;
}

export const WalkthroughCoachmarks: FC<WalkthroughCoachmarksProps> = ({
  walkthroughStep,
  deployButtonRef,
  tabsRef,
  chatAreaRef,
  onDismiss,
}) => (
  <>
    {walkthroughStep === 'deploy' && (
      <Coachmark
        targetRef={deployButtonRef}
        placement="left"
        stepLabel="Step 1 of 3"
        title={WALKTHROUGH_COPY.deploy.title}
        body={WALKTHROUGH_COPY.deploy.body}
        onDismiss={onDismiss}
      />
    )}
    {walkthroughStep === 'switch-to-chat' && (
      <Coachmark
        targetRef={tabsRef}
        placement="left"
        stepLabel="Step 2 of 3"
        title={WALKTHROUGH_COPY['switch-to-chat'].title}
        body={WALKTHROUGH_COPY['switch-to-chat'].body}
        onDismiss={onDismiss}
      />
    )}
    {walkthroughStep === 'wait' && (
      <Coachmark
        targetRef={chatAreaRef}
        placement="left"
        stepLabel="Step 3 of 3"
        title={WALKTHROUGH_COPY.wait.title}
        body={WALKTHROUGH_COPY.wait.body}
        onDismiss={onDismiss}
      />
    )}
    {walkthroughStep === 'chat' && (
      <Coachmark
        targetRef={chatAreaRef}
        placement="left"
        title={WALKTHROUGH_COPY.chat.title}
        body={WALKTHROUGH_COPY.chat.body}
        primaryLabel="Got it"
        onPrimary={onDismiss}
        onDismiss={onDismiss}
      />
    )}
  </>
);
