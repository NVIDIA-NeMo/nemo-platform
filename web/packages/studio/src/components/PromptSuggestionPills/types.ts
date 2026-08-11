// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/** A one-click example prompt offered next to a prompt field. */
export interface PromptSuggestion {
  /** Short pill label — a few words, not the prompt itself. */
  label: string;
  /** Full prompt written into the field when the pill is clicked. */
  prompt: string;
}

export interface PromptSuggestionPillsProps {
  suggestions: PromptSuggestion[];
  onSelect: (prompt: string) => void;
  /** Merged into the row's classes, for callers that own the row's flex behaviour. */
  className?: string;
}
