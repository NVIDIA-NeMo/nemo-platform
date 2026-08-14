// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Banner } from '@nvidia/foundations-react-core';
import {
  type JobBuilderFormValues,
  type TemplateModelIssue,
  unresolvedTemplateModelIssues,
} from '@studio/routes/DataDesignerJobBuildRoute/useJobBuilder';
import { type FC, memo } from 'react';
import { useFormContext, useWatch } from 'react-hook-form';

export interface MissingTemplateModelBannerProps {
  issues: TemplateModelIssue[];
}

const describeIssue = (issue: TemplateModelIssue): string =>
  `${issue.requested}, used by “${issue.alias}”`;

/**
 * Reports that this template names a model the workspace does not serve. The model field keeps
 * the requested name, so this banner is the only thing saying the recipe cannot run as written —
 * it stays until the user picks a model that exists, hence no dismiss affordance.
 */
export const MissingTemplateModelBanner: FC<MissingTemplateModelBannerProps> = memo(
  function MissingTemplateModelBanner({ issues }) {
    const { control } = useFormContext<JobBuilderFormValues>();
    const models = useWatch({ control, name: 'models' }) ?? [];
    const unresolved = unresolvedTemplateModelIssues(issues, models);
    if (unresolved.length === 0) return null;

    return (
      <div className="shrink-0 px-density-2xl py-density-md">
        <Banner kind="inline" status="error">
          {unresolved.length === 1
            ? `This template asks for a model your workspace doesn't have: ${describeIssue(unresolved[0])}. Select an available model in the model panel before generating.`
            : "This template asks for models your workspace doesn't have. Select available models in the model panel before generating:"}
          {unresolved.length > 1 && (
            <ul className="list-disc pl-density-lg">
              {unresolved.map((issue) => (
                <li key={issue.id}>{describeIssue(issue)}</li>
              ))}
            </ul>
          )}
        </Banner>
      </div>
    );
  }
);
