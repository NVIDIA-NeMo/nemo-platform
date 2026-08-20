// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

export { RangeBand } from '@studio/components/charts/RangeBand/RangeBand';
export { DEFAULT_BAND_OPACITY } from '@studio/components/charts/RangeBand/consts';
export {
  buildRangeBandRows,
  hasCenterLine,
  hasPlottableBands,
  lowerKeyFor,
  upperKeyFor,
} from '@studio/components/charts/RangeBand/utils';
export type { RangeBandChartRow } from '@studio/components/charts/RangeBand/utils';
export { useRangeBand } from '@studio/components/charts/RangeBand/useRangeBand';
export type { UseRangeBandOptions } from '@studio/components/charts/RangeBand/useRangeBand';
export type {
  ColoredBandSeries,
  RangeBandProps,
  RangeBandSeries,
} from '@studio/components/charts/RangeBand/types';
