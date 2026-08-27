// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { PaginationQueryState } from '@nemo/common/src/utils/useQueryFromSearchParams';

export type GenerateJobsFilterState = PaginationQueryState & {
  search?: undefined;
};
