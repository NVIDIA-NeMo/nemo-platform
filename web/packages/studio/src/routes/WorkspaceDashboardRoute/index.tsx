// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { GradientBackground } from '@nemo/common/src/components/GradientBackground';
import ModelEvaluationIcon from '@nemo/common/src/svgs/model_evaluation.svg?react';
import ModelPromptTuningIcon from '@nemo/common/src/svgs/model_prompt_tuning.svg?react';
import SafeSynthesizerLogo from '@nemo/common/src/svgs/safe_synthesizer_logo.svg?react';
import { Grid, PageHeader, Stack, Text } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import {
  CUSTOMIZER_ENABLED,
  EVALUATOR_ENABLED,
  MODEL_COMPARE_ENABLED,
  SAFE_SYNTHESIZER_ENABLED,
} from '@studio/constants/environment';
import {
  LINK_DOCS_MODELS,
  LINK_DOCS_SAFE_SYNTHESIZER,
  LINK_DOCS_STUDIO_CUSTOMIZATION,
  LINK_DOCS_STUDIO_EVALUATION,
} from '@studio/constants/links';
import { ROUTES } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { getEvaluationResultsRoute, getModelCompareRoute } from '@studio/routes/utils';
import { DashboardCard } from '@studio/routes/WorkspaceDashboardRoute/DashboardCard';
import { ResourcesSection } from '@studio/routes/WorkspaceDashboardRoute/ResourcesSection';
import { Sliders, Boxes } from 'lucide-react';
import type { FC } from 'react';
import { generatePath } from 'react-router-dom';

export const WorkspaceDashboardRoute: FC = () => {
  const workspace = useWorkspaceFromPath();

  useBreadcrumbs({
    items: [{ slotLabel: 'Dashboard' }],
  });

  return (
    <GradientBackground>
      <AccessibleTitle title="Dashboard">
        <Stack gap="density-3xl" padding="density-2xl" className="relative">
          <PageHeader
            slotHeading="Welcome to NeMo Studio"
            slotDescription={
              CUSTOMIZER_ENABLED
                ? 'Fine-tune and evaluate models, generate synthetic data, and monitor NeMo Platform jobs.'
                : 'Evaluate models, generate synthetic data, and monitor NeMo Platform jobs.'
            }
          />

          <Stack gap="density-lg" data-tour="dashboard-get-started">
            <Stack gap="density-sm">
              <Text kind="title/md">Get Started</Text>
              <Text kind="body/regular/sm" color="secondary">
                Kick off a new job that matches your use case.
              </Text>
            </Stack>
            <Grid cols={{ md: 1, lg: 3 }} gap="density-xl">
              {MODEL_COMPARE_ENABLED && (
                <DashboardCard
                  icon={<Boxes className="w-8 h-8" />}
                  title="Chat with a Model"
                  description="Chat with base models and explore capabilities."
                  actionLabel="Chat"
                  actionHref={getModelCompareRoute(workspace)}
                />
              )}
              {/* Fine-tune a Model */}
              {CUSTOMIZER_ENABLED && (
                <DashboardCard
                  icon={<Sliders className="w-8 h-8" />}
                  title="Fine-tune a Model"
                  description="Customize pre-trained models with your data for better performance on specific tasks."
                  docsUrl={LINK_DOCS_STUDIO_CUSTOMIZATION}
                  actionLabel="Fine-tune"
                  actionHref={generatePath(ROUTES.workspace.newCustomizationJob, { workspace })}
                />
              )}

              {/* Prompt Tune a Model */}
              {CUSTOMIZER_ENABLED && (
                <DashboardCard
                  icon={<ModelPromptTuningIcon className="w-8 h-8" />}
                  title="Prompt Tune a Model"
                  description="Optimize model responses using prompt-based techniques without fine-tuning."
                  docsUrl={LINK_DOCS_MODELS}
                  actionLabel="Prompt Tune"
                  actionHref={generatePath(ROUTES.workspace.promptTuningForm, { workspace })}
                />
              )}

              {/* Evaluate a Model or Dataset */}
              {EVALUATOR_ENABLED && (
                <DashboardCard
                  icon={<ModelEvaluationIcon className="w-8 h-8" />}
                  title="Evaluate a Model or Dataset"
                  description="Assess models or datasets with automated metrics and workflows."
                  docsUrl={LINK_DOCS_STUDIO_EVALUATION}
                  actionLabel="Evaluate"
                  actionHref={getEvaluationResultsRoute(workspace)}
                />
              )}

              {/* Synthesize Safe Data */}
              {SAFE_SYNTHESIZER_ENABLED && (
                <DashboardCard
                  icon={<SafeSynthesizerLogo className="w-8 h-8" />}
                  title="Synthesize Safe Data"
                  description="Generate synthetic datasets with built-in safety and quality controls."
                  docsUrl={LINK_DOCS_SAFE_SYNTHESIZER}
                  actionLabel="Synthesize"
                  actionHref={generatePath(ROUTES.workspace.safeSynthesizerNew, { workspace })}
                />
              )}
            </Grid>
          </Stack>

          <Stack gap="density-lg">
            <Text kind="title/md">Resources</Text>
            <ResourcesSection />
          </Stack>
        </Stack>
      </AccessibleTitle>
    </GradientBackground>
  );
};
