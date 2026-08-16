// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

package streams

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"
	"github.com/openai/openai-go/v2"
)

// helper: fixed-size chunking
func genFixedSizedChunks(b []byte, n int) [][]byte {
	if n <= 0 {
		panic("chunk size must be > 0")
	}
	var out [][]byte
	for i := 0; i < len(b); i += n {
		j := i + n
		if j > len(b) {
			j = len(b)
		}
		out = append(out, b[i:j])
	}
	return out
}

// helper: byte-by-byte chunking
func genOneByteChunks(b []byte) [][]byte {
	return genFixedSizedChunks(b, 1)
}

// helper: mkChunk builds a minimal OpenAI-style streaming JSON chunk with delta.content = content
func mkChunk(content string) ([]byte, error) {

	chunk := openai.ChatCompletionChunk{
		Choices: []openai.ChatCompletionChunkChoice{
			{
				Delta: openai.ChatCompletionChunkChoiceDelta{
					Content: content,
				},
			},
		},
	}
	return json.Marshal(chunk)
}

// helper: buildOpenAIStyleStream returns a canonical SSE stream (as raw bytes) and the expected SSE payloads.
// It uses SSE framing: "data: <json>\n\n" per event, plus a final [DONE].
func buildOpenAIStyleStream(inputText, sep string) (stream []byte, expected [][]byte, expectedAggregatedText string, err error) {
	dataPrefix := []byte(DATA_FIELD_PREFIX)
	sseSep := []byte(sep + sep)
	// Simulate some top-level comments that should be ignored by our parser.
	stream = append(stream, []byte(": this is an SSE comment")...)
	stream = append(stream, sseSep...)
	// Split the inputText into individual words and construct JSON chunks
	words := strings.Split(inputText, " ")
	for i, word := range words {
		// Simulate adding an event type, which is valid SSE framing.
		// Our parser simply ignores these right now.
		stream = append(stream, []byte("event: ignore"+sep)...)
		// Push the actual data chunk
		var chunk []byte
		if i < len(words)-1 {
			word += " "
		}
		chunk, err = mkChunk(word)
		if err != nil {
			return
		}
		stream = append(stream, dataPrefix...)
		stream = append(stream, chunk...)
		stream = append(stream, sseSep...)
		expected = append(expected, chunk)
	}
	// Add the [DONE]
	done := []byte("[DONE]")
	stream = append(stream, dataPrefix...)
	stream = append(stream, done...)
	stream = append(stream, sseSep...)
	expected = append(expected, done)

	expectedAggregatedText = inputText
	return
}

func TestParserAndAggregator(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		// takses inputText and builds the stream of SSEs
		streamFn func(inputText, sep string) (stream []byte, expectedSSEs [][]byte, expectedAggregatedText string, err error)
		// takes the stream and breaks it into chunks, where chunk boundaries don't map to SSE boundaries.
		chunkify func([]byte) [][]byte
		// plain text to be broken down into tokens
		inputText string
		// separater character -- \n or \r\n
		sep string
	}{
		"hello_LF_all_at_once": {
			streamFn:  buildOpenAIStyleStream,
			inputText: "Hello, world!",
			sep:       "\n",
			chunkify:  func(b []byte) [][]byte { return [][]byte{b} },
		},
		"hello_LF_one_by_one": {
			streamFn:  buildOpenAIStyleStream,
			inputText: "Hello, world!",
			sep:       "\n",
			chunkify:  genOneByteChunks,
		},
		"hello_LF_fixed_7": {
			streamFn:  buildOpenAIStyleStream,
			inputText: "Hello, world!",
			sep:       "\n",
			chunkify:  func(b []byte) [][]byte { return genFixedSizedChunks(b, 7) },
		},
		"hello_CRLF_fixed_8": {
			streamFn:  buildOpenAIStyleStream,
			inputText: "Hello, world!",
			sep:       "\r\n",
			chunkify:  func(b []byte) [][]byte { return genFixedSizedChunks(b, 8) },
		},
		"zen_of_python_LF_all_at_once": {
			streamFn:  buildOpenAIStyleStream,
			inputText: zenOfPython,
			sep:       "\n",
			chunkify:  func(b []byte) [][]byte { return [][]byte{b} },
		},
		"zen_of_python_LF_one_by_one": {
			streamFn:  buildOpenAIStyleStream,
			inputText: zenOfPython,
			sep:       "\n",
			chunkify:  genOneByteChunks,
		},
		"zen_of_python_LF_fixed_256": {
			streamFn:  buildOpenAIStyleStream,
			inputText: zenOfPython,
			sep:       "\n",
			chunkify:  func(b []byte) [][]byte { return genFixedSizedChunks(b, 256) },
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			stream, expectedChunks, expectedAggregated, err := tc.streamFn(tc.inputText, tc.sep)
			if err != nil {
				t.Errorf("failed to build stream: %v", err)
			}
			parts := tc.chunkify(stream)

			var p Parser
			var gotChunks [][]byte
			for _, part := range parts {
				gotChunks = append(gotChunks, p.Push(part)...)
			}

			// Validate parser outputs
			if len(gotChunks) != len(expectedChunks) {
				t.Fatalf("parser chunks count mismatch: got %d, want %d", len(gotChunks), len(expectedChunks))
			}
			for i := range expectedChunks {
				if diff := cmp.Diff(string(expectedChunks[i]), string(gotChunks[i])); diff != "" {
					t.Fatalf("bytes not equal (-want +got):\n%s", diff)
				}
			}

			// Pipe into aggregator
			var agg ContentAggregator
			for _, ev := range gotChunks {
				if err := agg.AppendChunk(ev); err != nil {
					// If a stream contains non-JSON “data: …” events, AppendChunk may error.
					// For this integration test, treat errors as non-fatal for those events:
					// skip them and continue. This mirrors robust streaming behavior.
					continue
				}
			}

			msg := agg.BuildChatCompletionMessage()
			got := msg.OfAssistant.Content.OfString.Value
			if diff := cmp.Diff(expectedAggregated, got); diff != "" {
				t.Fatalf("aggregated text mismatch: (-want +got):\n%s", diff)
			}
		})
	}
}

var zenOfPython = `Beautiful is better than ugly.
Explicit is better than implicit.
Simple is better than complex.
Complex is better than complicated.
Flat is better than nested.
Sparse is better than dense.
Readability counts.
Special cases aren't special enough to break the rules.
Although practicality beats purity.
Errors should never pass silently.
Unless explicitly silenced.
In the face of ambiguity, refuse the temptation to guess.
There should be one-- and preferably only one --obvious way to do it.
Although that way may not be obvious at first unless you're Dutch.
Now is better than never.
Although never is often better than *right* now.
If the implementation is hard to explain, it's a bad idea.
If the implementation is easy to explain, it may be a good idea.
Namespaces are one honking great idea -- let's do more of those!`
