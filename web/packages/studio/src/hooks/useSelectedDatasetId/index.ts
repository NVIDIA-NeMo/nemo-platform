// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useParams } from 'react-router';

interface Props {
  datasetId?: string;
}
export const useSelectedDatasetId = ({ datasetId }: Props = {}) => {
  // `useParams()` already returns decoded values and route helpers encode when
  // building the URL, so decoding again here would corrupt names containing `%`.
  const { [ROUTE_PARAMS.filesetId]: routeDatasetId } = useParams();
  const usedDatasetId = datasetId ?? routeDatasetId ?? '';
  if (!usedDatasetId) {
    throw new Error('Missing Dataset ID');
  }
  return usedDatasetId;
};
