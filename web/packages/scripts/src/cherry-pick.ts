// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { execFileSync } from 'child_process';
import * as readline from 'readline';
import * as process from 'process';
import { openBrowser, getBaseUrl } from './git-utils.js';

const git = (...args: string[]) => execFileSync('git', args, { stdio: 'inherit' });

// Helper to prompt the user for input.
function prompt(question: string): Promise<string> {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });
  return new Promise((resolve) =>
    rl.question(question, (ans) => {
      rl.close();
      resolve(ans);
    })
  );
}

async function handleMergeConflicts() {
  let resolved = false;
  while (!resolved) {
    const response = (await prompt('Have you resolved the conflicts? (yes/no/abort): '))
      .trim()
      .toLowerCase();
    if (response === 'yes') {
      try {
        console.log('Staging resolved changes...');
        git('add', '.');
        console.log('Attempting to continue cherry-pick...');
        git('cherry-pick', '--continue');
        console.log('Cherry-pick completed successfully after resolving conflicts.');
        resolved = true;
      } catch {
        console.error(
          'There are still unresolved conflicts or issues. Please resolve them and try again.'
        );
      }
    } else if (response === 'no') {
      await prompt('Waiting for you to resolve conflicts. Press enter to check again...');
    } else if (response === 'abort') {
      console.log('Aborting cherry-pick...');
      git('cherry-pick', '--abort');
      process.exit(1);
    } else {
      console.log("Please answer 'yes', 'no', or 'abort'.");
    }
  }
}

async function main() {
  const args = process.argv.slice(2);
  if (args.length < 2) {
    console.error('Usage: tsx cherry_pick.ts <commit_hash> <release_branch>');
    process.exit(1);
  }

  const commitHash = args[0];
  const releaseBranch = args[1];

  try {
    console.log('Fetching latest changes from origin...');
    git('fetch', 'origin');

    console.log(`Checking out the release branch: ${releaseBranch}`);
    git('checkout', releaseBranch);
    git('pull', 'origin', releaseBranch);

    // Create a new branch based on the release branch.
    const newBranchName = `cherry-pick-${commitHash.substring(0, 7)}`;
    console.log(`Creating and switching to new branch: ${newBranchName}`);
    git('checkout', '-b', newBranchName);

    console.log(`Attempting to cherry-pick commit: ${commitHash}`);
    try {
      git('cherry-pick', commitHash);
      console.log('Cherry-pick completed successfully without conflicts.');
    } catch {
      console.error('Merge conflicts detected during cherry-pick!');
      await handleMergeConflicts();
    }

    // Push the new branch to origin.
    console.log(`Pushing branch ${newBranchName} to origin...`);
    git('push', 'origin', newBranchName);

    // Retrieve the remote URL to construct the merge request URL.
    const remoteUrlRaw = execFileSync('git', ['remote', 'get-url', 'origin']).toString().trim();
    const baseUrl = getBaseUrl(remoteUrlRaw);
    const mergeRequestUrl = `${baseUrl}/-/merge_requests/new?merge_request[source_branch]=${newBranchName}&merge_request[target_branch]=${releaseBranch}`;

    console.log('Opening merge request page in your browser...');
    console.log(`URL: ${mergeRequestUrl}`);
    openBrowser(mergeRequestUrl);
  } catch (error) {
    console.error('An error occurred:', error);
    process.exit(1);
  }
}

main();
