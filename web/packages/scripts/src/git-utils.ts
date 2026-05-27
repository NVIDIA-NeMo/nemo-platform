// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { execFile, execFileSync } from 'child_process';
import * as process from 'process';

/**
 * Open a URL in the default browser (works on macOS, Windows, and most Linux distros).
 */
export function openBrowser(url: string): void {
  let cmd: string;
  let args: string[];
  if (process.platform === 'darwin') {
    cmd = 'open';
    args = [url];
  } else if (process.platform === 'win32') {
    cmd = 'cmd';
    args = ['/c', 'start', '', url];
  } else {
    cmd = 'xdg-open';
    args = [url];
  }
  execFile(cmd, args, (error) => {
    if (error) {
      console.error('Failed to open browser:', error);
    }
  });
}

/**
 * Convert the remote URL to an HTTPS URL without the .git suffix.
 * For example, convert:
 *  "git@code.example.com:namespace/project.git" → "https://code.example.com/namespace/project"
 *  "https://code.example.com/namespace/project.git" → "https://code.example.com/namespace/project"
 *  "ssh://git@code.example.com/namespace/project.git" → "https://code.example.com/namespace/project"
 *  "ssh://git@code.example.com:12051/namespace/project.git" → "https://code.example.com/namespace/project"
 */
export function getBaseUrl(remoteUrl: string): string {
  let url = remoteUrl;
  if (url.endsWith('.git')) {
    url = url.slice(0, -4);
  }
  if (url.startsWith('git@')) {
    return url.replace('git@', 'https://').replace(':', '/');
  } else if (url.startsWith('ssh://git@')) {
    const withoutSsh = url.replace('ssh://git@', 'https://');
    // Has port number
    if (withoutSsh.substring('https://'.length).includes(':')) {
      return withoutSsh.replace(/:\d+/, '');
    }
    return withoutSsh;
  } else if (url.startsWith('http')) {
    return url;
  }
  return url;
}

// Check if git status is clean (no uncommitted changes)
export function isGitStatusClean(): boolean {
  try {
    const status = execFileSync('git', ['status', '--porcelain']).toString().trim();
    return status === '';
  } catch (error) {
    console.error('Failed to check git status:', error);
    return false;
  }
}

// Get the current branch name
export function getCurrentBranch(): string {
  try {
    return execFileSync('git', ['rev-parse', '--abbrev-ref', 'HEAD']).toString().trim();
  } catch (error) {
    console.error('Failed to get current branch:', error);
    throw error;
  }
}
