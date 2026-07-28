// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { DataDesignerModelOption } from '@studio/components/NewDataDesignerJobForm/utils';

/**
 * The detector role is handed GLiNER-only inference params server-side, so only a GLiNER
 * endpoint can serve it. Either identifier may carry the name depending on how it was registered.
 */
export const isGlinerModel = (model: DataDesignerModelOption): boolean =>
  /gliner/i.test(model.name) || /gliner/i.test(model.served_model_name ?? '');
