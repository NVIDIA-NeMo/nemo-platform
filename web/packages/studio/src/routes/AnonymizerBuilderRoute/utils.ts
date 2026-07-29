// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { DataDesignerModelOption } from '@studio/components/NewDataDesignerJobForm/utils';

export const isGlinerModel = (model: DataDesignerModelOption): boolean =>
  /gliner/i.test(model.name) || /gliner/i.test(model.served_model_name ?? '');
