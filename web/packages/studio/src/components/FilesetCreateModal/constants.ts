// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { FILESET_NAME_MAX_LENGTH, FILESET_NAME_REGEXP } from '@nemo/common/src/utils/filesetName';
import { FilesetPurpose } from '@nemo/sdk/generated/platform/schema';
import { FilesCreateFilesetBody } from '@nemo/sdk/generated/platform/zod/files';
import { z } from 'zod';

const NAME_REQUIRED_MESSAGE = 'Name is required.';

const NAME_PATTERN_MESSAGE =
  'Name must start with a lowercase letter, be 2-63 characters, and contain only lowercase letters, digits, hyphens, dots, underscores, plus, and @ (no consecutive hyphens, cannot end with a hyphen).';

export enum StorageMode {
  Local = 'local',
  External = 'external',
}

export type SupportedPurpose = typeof FilesetPurpose.dataset | typeof FilesetPurpose.model;

// Override the SDK-generated `name` validation. The generated zod uses the
// Files service DTO's loose pattern (`^[\w\-.]+$`, max 255); the entity store
// downstream enforces a stricter RFC-1035-ish pattern. We validate against the
// strict one here so the user sees a useful error instead of a 422 toast.
export const filesetCreateFormSchema = FilesCreateFilesetBody.pick({
  name: true,
  description: true,
}).extend({
  name: z
    .string()
    .trim()
    .min(1, NAME_REQUIRED_MESSAGE)
    .max(FILESET_NAME_MAX_LENGTH)
    .regex(FILESET_NAME_REGEXP, NAME_PATTERN_MESSAGE),
  url: z.string().optional(),
  secretKey: z.string().optional(),
});

export type FilesetCreateFormData = z.infer<typeof filesetCreateFormSchema>;

export const PURPOSE_COPY: Record<SupportedPurpose, { title: string; submit: string }> = {
  [FilesetPurpose.dataset]: {
    title: 'Create Dataset',
    submit: 'Create Dataset',
  },
  [FilesetPurpose.model]: {
    title: 'Create Model Fileset',
    submit: 'Create Model Fileset',
  },
};
