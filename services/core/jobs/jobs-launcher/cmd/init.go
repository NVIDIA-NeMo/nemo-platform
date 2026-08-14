// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

package cmd

import (
	"fmt"
	"io"
	"os"
	"path/filepath"

	"github.com/spf13/cobra"
)

var (
	sourcePath string
	destPath   string
)

var initCmd = &cobra.Command{
	Use:   "init",
	Short: "Install the launcher binary to a destination path",
	RunE: func(cmd *cobra.Command, args []string) error {
		return copySelf(sourcePath, destPath)
	},
}

func init() {
	initCmd.Flags().StringVarP(&sourcePath, "source", "s", "", "Source path of the launcher binary (required)")
	initCmd.Flags().StringVarP(&destPath, "dest", "d", "", "Destination path to copy launcher binary to (required)")
	initCmd.MarkFlagRequired("source") // nolint:errcheck
	initCmd.MarkFlagRequired("dest")   // nolint:errcheck
	rootCmd.AddCommand(initCmd)
}

// copySelf copies the launcher binary from source to destination
func copySelf(source, dest string) error {
	if source == dest {
		return fmt.Errorf("source and destination paths cannot be the same")
	}

	input, err := os.Open(source)
	if err != nil {
		return fmt.Errorf("failed to open source binary: %w", err)
	}
	defer input.Close() // nolint:errcheck

	if err := os.MkdirAll(filepath.Dir(dest), 0o755); err != nil {
		return fmt.Errorf("failed to create destination dir: %w", err)
	}

	output, err := os.Create(dest)
	if err != nil {
		return fmt.Errorf("failed to create destination file: %w", err)
	}
	defer output.Close() // nolint:errcheck

	if _, err := io.Copy(output, input); err != nil {
		return fmt.Errorf("failed to copy binary: %w", err)
	}

	if err := os.Chmod(dest, 0o755); err != nil {
		return fmt.Errorf("failed to set permissions: %w", err)
	}

	logger.Printf("Launcher installed at %s\n", dest)
	return nil
}
