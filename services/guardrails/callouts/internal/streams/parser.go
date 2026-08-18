// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

package streams

import (
	"bytes"
	"encoding/json"
	"strings"

	"github.com/openai/openai-go/v2"
)

/*
Overview

The backend LLM (OpenAI-compatible Chat Completions with stream=true) returns
a stream of Server-Sent Events (SSE). Envoy may split the SSE stream into smaller chunks or
coalesce multiple SSEs into a larger one before delivering them to the external processor.
Therefore, bytes received by the processor must be treated as an arbitrary bytestream
with no guarantees that SSE boundaries align with Envoy's chunk boundaries.

- SSE shape
  A single SSE consists of one or more messages separated by a pair of newline characters.
  Each message consists of one or more lines of text listing the fields for that message.
  Each field is represented by the field name, followed by a colon, followed by the text data.
  A single colon as the first character is considered a comment, and is ignored.

  OpenAI uses standard SSE framing delivered with Content-Type: text/event-stream:
	: this is an example stream of chat completion chunks

	event: response.created
    data: { ... chat.completion.chunk JSON ... }

	event: response.completed
    data: { ... chat.completion.chunk JSON ... }

    data: [DONE]

  ASSUME that each data line contains the entire JSON payload: newlines
  are escaped properly by JSON encoding ('\n' -> '\' + 'n'); splitting JSON across
  multiple data lines inserts literal newlines that typically break JSON parsing.

- Parser
  The Parser accepts arbitrary byte slices from Envoy and incrementally parses
  them into complete SSE event payloads:
    - Buffers partial lines across calls and handles both LF and CRLF endings.
    - Treats a pair of newlines as the delimiter.
    - Strips the "data:" prefix (and an optional space) from each data line
    - Returns each complete event payload as a []byte, preserving the JSON
      exactly as received (no trimming/rewriting beyond the "data:" prefix).

  Because Envoy may split or coalesce arbitrarily, the Parser must be robust to:
    - Lines split across chunk boundaries.
    - Multiple events in one chunk.
    - Partial events spanning many chunks.
    - Optional whitespace after "data:" and arbitrary whitespace inside JSON.

- ContentAggregator
  The ContentAggregator consumes complete event payloads produced by the
  Parser and reconstructs the assistant’s textual output:
    - Treats the literal "[DONE]" payload as terminal.
    - For JSON chunks, parses the OpenAI chat-completion stream schema and
      extracts delta.content text from choices (typically index 0).
    - Appends only assistant text content to an internal buffer (strings.Builder),
      ignoring non-textual deltas such as role changes, tool/function calls, and
      other metadata.
    - Exposes the accumulated assistant text as a single string suitable for
      downstream safety checks.
*/

const (
	EVENT_FIELD_PREFIX = "event:"
	DATA_FIELD_PREFIX  = "data:"
	SEP                = '\n'
	DONE_SENTINEL      = "[DONE]"
)

// Parser accepts arbitrary byte slices, emits [][]byte that maps to SSEs.
type Parser struct {
	// buffer holds bytes of a partial line between calls (no trailer newline).
	buffer []byte
}

// Push appends new bytes and returns any complete events parsed.
func (p *Parser) Push(b []byte) [][]byte {
	var out [][]byte

	// Return early when there's nothing to parse.
	if len(b) == 0 && len(p.buffer) == 0 {
		return out
	}

	// Build the working buffer
	buf := make([]byte, 0, len(p.buffer)+len(b))
	if len(p.buffer) > 0 {
		buf = append(buf, p.buffer...)
		p.buffer = p.buffer[:0]
	}
	buf = append(buf, b...)

	// Scan for lines delimited by LF
	start := 0
	for i := 0; i < len(buf); i++ {
		if buf[i] != SEP {
			continue
		}
		end := i
		// Deal with CRLF
		if end > start && buf[end-1] == '\r' {
			end--
		}
		line := buf[start:end]

		// Process complete line
		if bytes.HasPrefix(line, []byte(DATA_FIELD_PREFIX)) {
			line = line[len(DATA_FIELD_PREFIX):]
			// clear white spaces
			for len(line) > 0 && line[0] == ' ' {
				line = line[1:]
			}
			// It's important to allocate a new []byte, and copy the line into it.
			// This drops the reference to the window in the buffer, and allows the GC to free the memory.
			dataLine := make([]byte, 0, len(line))
			dataLine = append(dataLine, line...)
			out = append(out, dataLine)
		}
		// Next line starts after the '\n' character
		start = i + 1
	}

	// Remainder is partial line; stash in buffer
	if start < len(buf) {
		p.buffer = append(p.buffer[:0], buf[start:]...)
	} else {
		// Ensure we release reference to buf to avoid retaining large arrays
		p.buffer = p.buffer[:0]
	}
	return out
}

// ContentAggregator incrementally collects assistant content text from
// OpenAI-compatible chat completion streaming "data:" JSON chunks.
// IDEA consider using OpenAI's ChatCompletionAccumulator https://github.com/openai/openai-go/blob/main/streamaccumulator.go
type ContentAggregator struct {
	// Text accumulates only assistant textual content (not role/tool/function tokens).
	Text strings.Builder

	// done is set when a “[DONE]” sentinel is observed by the caller and
	// propagated to the aggregator, or when a chunk explicitly indicates finish.
	done bool
	// Extracted dynamically as we append the chat completion chunks.
	chatCmplID    string
	chatCmplModel string
}

// AppendChunk parses one SSE payload (the JSON behind "data:") and appends any
// assistant delta content to Text. It ignores non-content deltas (role changes, too/function calls).
// If the payload is "[DONE]" then it marks as done.
func (a *ContentAggregator) AppendChunk(payload []byte) error {
	if a.done {
		return nil
	}
	if bytes.Equal(payload, []byte("[DONE]")) {
		a.done = true
		return nil
	}
	payload = bytes.TrimSpace(payload)
	if len(payload) == 0 {
		return nil
	}
	var msg openai.ChatCompletionChunk
	if err := json.Unmarshal(payload, &msg); err != nil {
		// For robustness in streaming, prefer to skip malformed chunks rather than fail hard.
		// But here we return the error, and let the caller decide.
		return err
	}
	// HACK only the ContentAggregator can extract the chatcmpl-id and model name right now.
	// Consider a better place to extract this information.
	if a.chatCmplID == "" {
		a.chatCmplID = msg.ID
	}
	if a.chatCmplModel == "" {
		a.chatCmplModel = msg.Model
	}
	// Aggregate content from all choices (usually there's only one choice).
	for _, choice := range msg.Choices {
		if choice.Delta.Content != "" {
			a.Text.WriteString(choice.Delta.Content)
		}
	}
	return nil
}

func (a *ContentAggregator) GetText() string {
	return a.Text.String()
}

func (a *ContentAggregator) BuildChatCompletionMessage() openai.ChatCompletionMessageParamUnion {
	msg := openai.AssistantMessage(a.Text.String())
	// Role is empty by default. It only gets set during serialization.
	// Might be a bug, but for now lets fill it in case downstream depends on it.
	msg.OfAssistant.Role = msg.OfAssistant.Role.Default()
	return msg
}

func (a *ContentAggregator) Done() bool {
	return a.done
}

func (a ContentAggregator) GetChatCompletionID() string {
	return a.chatCmplID
}

func (a ContentAggregator) GetModelName() string {
	return a.chatCmplModel
}

func (a *ContentAggregator) Reset() {
	a.done = false
	a.chatCmplID = ""
	a.chatCmplModel = ""
	a.Text.Reset()
}
