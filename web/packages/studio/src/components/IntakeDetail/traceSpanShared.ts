// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Small helpers shared by the trace span explorer (orchestrator + tree/list views).

/** A pending "add note" request: which span to focus, plus a nonce that bumps on
 * every click so the same span can be re-targeted. */
export type NoteRequest = { spanId: string; nonce: number } | null;

/** The focus nonce for a span, or undefined when it isn't the current target. */
export const noteFocusNonce = (request: NoteRequest, spanId: string): number | undefined =>
  request?.spanId === spanId ? request.nonce : undefined;

/** DOM id for a span's accordion item, used to scroll it into view. */
export const spanAccordionId = (spanId: string): string => `intake-span-${spanId}`;
