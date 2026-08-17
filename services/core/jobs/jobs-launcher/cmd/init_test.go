// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

package cmd

import (
	"os"
	"testing"
)

func TestInitCommand(t *testing.T) {
	tempDir := t.TempDir()
	dummySource := tempDir + "/launcher_test"
	err := os.WriteFile(dummySource, []byte("dummy content"), 0755)
	if err != nil {
		panic("Failed to create dummy source file for testing: " + err.Error())
	}

	dummyDest := tempDir + "/launcher_copy_test"

	cases := []struct {
		name       string
		source     string
		dest       string
		shouldFail bool
	}{
		// Good path
		{"ValidPaths", dummySource, dummyDest, false},
		// Error paths
		{"InvalidSource", "/invalid/source/path", dummyDest, true},
		{"SameSourceDest", dummySource, dummySource, true},
	}

	for _, c := range cases {
		err := copySelf(c.source, c.dest)
		if c.shouldFail && err == nil {
			panic("Test " + c.name + " failed: expected error but got none")
		}
		if !c.shouldFail && err != nil {
			panic("Test " + c.name + " failed: unexpected error: " + err.Error())
		}
	}
}
