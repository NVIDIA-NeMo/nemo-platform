// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type {
  MarkdownAstListItemNode,
  MarkdownAstListNode,
  MarkdownAstNode,
  MarkdownAstParent,
} from '@nemo/common/src/components/Chat/MessageContent/types';

const isMarkdownAstNode = (value: unknown): value is MarkdownAstNode =>
  typeof value === 'object' &&
  value !== null &&
  typeof (value as { type?: unknown }).type === 'string';

const hasMarkdownAstChildren = (node: MarkdownAstNode): node is MarkdownAstParent =>
  Array.isArray(node.children);

const isMarkdownAstList = (node: MarkdownAstNode): node is MarkdownAstListNode =>
  node.type === 'list' && hasMarkdownAstChildren(node);

const isMarkdownAstListItem = (node: MarkdownAstNode): node is MarkdownAstListItemNode =>
  node.type === 'listItem' && hasMarkdownAstChildren(node);

const isMarkdownAstParagraph = (node: MarkdownAstNode): boolean => node.type === 'paragraph';

const getMarkdownAstText = (node: MarkdownAstNode): string => {
  if (typeof node.value === 'string') return node.value;
  if (!hasMarkdownAstChildren(node)) return '';
  return node.children.map(getMarkdownAstText).join('');
};

const isEmptyMarkdownAstListItem = (
  node: MarkdownAstNode | undefined
): node is MarkdownAstListItemNode =>
  isMarkdownAstNode(node) &&
  isMarkdownAstListItem(node) &&
  (node.children.length === 0 ||
    node.children.every(
      (child) => isMarkdownAstParagraph(child) && !getMarkdownAstText(child).trim()
    ));

const getMarkdownListStart = (node: MarkdownAstListNode): number => node.start ?? 1;

const shouldMergeOrderedLists = (
  currentNode: MarkdownAstNode,
  nextNode: MarkdownAstNode | undefined
): nextNode is MarkdownAstListNode => {
  if (!isMarkdownAstList(currentNode) || !currentNode.ordered) return false;
  if (!nextNode || !isMarkdownAstList(nextNode) || !nextNode.ordered) return false;

  return (
    getMarkdownListStart(nextNode) ===
    getMarkdownListStart(currentNode) + currentNode.children.length
  );
};

const mergeAdjacentOrderedLists = (children: MarkdownAstNode[], index: number): void => {
  const currentNode = children[index];
  if (!currentNode || !isMarkdownAstList(currentNode)) return;

  while (true) {
    const nextNode = children[index + 1];
    if (!shouldMergeOrderedLists(currentNode, nextNode)) break;

    currentNode.children.push(...nextNode.children);
    children.splice(index + 1, 1);
  }
};

const mergeEmptyOrderedListMarker = (children: MarkdownAstNode[], index: number): void => {
  const currentNode = children[index];
  const nextNode = children[index + 1];
  if (!currentNode || !nextNode || !isMarkdownAstList(currentNode) || !currentNode.ordered) return;
  if (currentNode.children.length !== 1 || !isEmptyMarkdownAstListItem(currentNode.children[0])) {
    return;
  }
  if (!isMarkdownAstParagraph(nextNode)) return;

  const listItem = currentNode.children[0];
  listItem.children = [nextNode];
  listItem.spread = false;
  currentNode.spread = false;

  const followingNode = children[index + 2];
  const shouldNestFollowingUnorderedList =
    followingNode !== undefined &&
    isMarkdownAstList(followingNode) &&
    followingNode.ordered !== true;

  if (shouldNestFollowingUnorderedList) {
    listItem.children.push(followingNode);
    children.splice(index + 1, 2);
    return;
  }

  children.splice(index + 1, 1);
};

const normalizeMarkdownAstLists = (parent: MarkdownAstParent): void => {
  for (let index = 0; index < parent.children.length; index++) {
    mergeEmptyOrderedListMarker(parent.children, index);
  }

  for (let index = 0; index < parent.children.length; index++) {
    mergeAdjacentOrderedLists(parent.children, index);
  }

  for (let index = 0; index < parent.children.length; index++) {
    const child = parent.children[index];
    if (child && hasMarkdownAstChildren(child)) normalizeMarkdownAstLists(child);
  }
};

export const remarkNormalizeEmptyOrderedListMarkers =
  () =>
  (tree: unknown): void => {
    if (!isMarkdownAstNode(tree) || !hasMarkdownAstChildren(tree)) return;
    normalizeMarkdownAstLists(tree);
  };
