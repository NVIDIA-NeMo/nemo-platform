// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

package main

import (
	"encoding/json"
	"fmt"
	"log"
	"math"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/openai/openai-go/v2"
)

// The structure for the unsafe chunk config.
// This is used to configure the unsafe chunk.
type UnsafeConfig struct {
	UnsafeChunkID int    `json:"unsafe_chunk_id"`
	UnsafeWord    string `json:"unsafe_word"`
	UnsafeTrigger string
}

var (
	unsafeConfig UnsafeConfig
)

func init() {
	var err error
	var unsafeChunkId int
	chunk_id_str, ok := os.LookupEnv("DEFAULT_UNSAFE_CHUNK_ID")
	if !ok {
		unsafeChunkId = math.MaxInt32
	} else {
		log.Printf("DEFAULT_UNSAFE_CHUNK_ID: %s", chunk_id_str)
		unsafeChunkId, err = strconv.Atoi(chunk_id_str)
		if err != nil {
			unsafeChunkId = math.MaxInt32
		}
	}

	unsafeWord, ok := os.LookupEnv("UNSAFE_CHUNK_WORD")
	if !ok {
		unsafeWord = "YOU ARE STUPID"
	} else {
		log.Printf("UNSAFE_CHUNK_WORD: %s", unsafeWord)
	}

	unsafeTrigger, ok := os.LookupEnv("UNSAFE_TRIGGER")
	if !ok {
		unsafeTrigger = "[UNSAFE]"
	}

	// Initialize the unsafe chunk config after unsafeChunkId is determined
	unsafeConfig = UnsafeConfig{
		UnsafeChunkID: unsafeChunkId,
		UnsafeWord:    unsafeWord,
		UnsafeTrigger: unsafeTrigger,
	}
}

type ChatMessage struct {
	Role    string `json:"role"`
	Content string `json:"content,omitempty"`
}

type ChatCompletionRequest struct {
	Model    string        `json:"model"`
	Messages []ChatMessage `json:"messages"`
	Stream   bool          `json:"stream,omitempty"`
	// Add more fields if needed
}

// Simple mock server to avoid having to spin up real NIM which requires GPUs.
func main() {
	// Get port from environment or default to 8000
	port := os.Getenv("PORT")
	if port == "" {
		port = "8000"
	}

	// Create a new HTTP server mux
	mux := http.NewServeMux()

	// Register routes
	mux.HandleFunc("/health", healthHandler)
	mux.HandleFunc("/v1/chat/completions", fakeChatCompletionHandler)

	// Add logging middleware
	loggedMux := loggingMiddleware(mux)

	log.Printf("Starting Go REST API server on port %s", port)
	log.Printf("Health check endpoint: http://localhost:%s/health", port)
	log.Printf("Streaming chat completion endpoints: http://localhost:%s/v1/chat/completions", port)

	// Start server
	if err := http.ListenAndServe(":"+port, loggedMux); err != nil {
		log.Fatalf("Server failed to start: %v", err)
	}
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	type HealthResponse struct {
		Healthy bool   `json:"healthy"`
		Time    string `json:"time"`
	}
	log.Println("Health check requested")

	response := HealthResponse{
		Healthy: true,
		Time:    time.Now().Format(time.RFC3339),
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(response)
}

func fakeChatCompletionHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "only POST", http.StatusMethodNotAllowed)
		return
	}

	// Parse JSON request into ChatCompletionRequest
	var req ChatCompletionRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "invalid JSON body", http.StatusBadRequest)
		return
	}
	if req.Model == "" {
		req.Model = "fake-model"
	}

	// Decide streaming vs non-streaming from request.stream
	if req.Stream {
		handleStreaming(w, r, req)
	} else {
		handleNonStreaming(w, r, req)
	}

}

func handleNonStreaming(w http.ResponseWriter, r *http.Request, chatReq ChatCompletionRequest) {
	// Compose a fake answer from last user message or a canned string.
	reply := synthesizeReply(chatReq)

	resp := openai.ChatCompletion{
		ID:      makeChatCompletionID(),
		Created: time.Now().Unix(),
		Model:   chatReq.Model,
		Choices: []openai.ChatCompletionChoice{
			{
				Index: 0,
				Message: openai.ChatCompletionMessage{
					Content: reply,
				},
				FinishReason: string(openai.CompletionChoiceFinishReasonStop),
			},
		},
		Usage: openai.CompletionUsage{
			CompletionTokens: estimateTokens(reply),
			PromptTokens:     estimateTokens(joinMessages(chatReq.Messages)),
			TotalTokens:      estimateTokens(joinMessages(chatReq.Messages)) + estimateTokens(reply),
		},
	}
	w.Header().Set("Content-Type", "application/json")
	payload, err := json.Marshal(resp)
	if err != nil {
		http.Error(w, fmt.Sprintf("failed to encode chat completion response: %v", err), http.StatusInternalServerError)
		return
	}
	w.WriteHeader(http.StatusOK)
	if _, err := w.Write(payload); err != nil {
		log.Printf("failed to send non-streaming chat completion response: %v", err)
	}
	log.Printf("Sent Chat Completion Response %s", string(payload))
}

func handleStreaming(w http.ResponseWriter, r *http.Request, chatReq ChatCompletionRequest) {
	// Determine if the user wants an unsafe response.
	var last string
	for i := len(chatReq.Messages) - 1; i >= 0; i-- {
		if chatReq.Messages[i].Role == "user" && chatReq.Messages[i].Content != "" {
			last = chatReq.Messages[i].Content
			break
		}
	}
	unsafeSelected := strings.Contains(last, unsafeConfig.UnsafeTrigger)

	// Streaming
	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, "Streaming not supported!", http.StatusInternalServerError)
		return
	}
	defer flusher.Flush()

	// Set headers. DO NOT set Content-Length for a streaming response.
	w.Header().Set("Content-Type", "text/event-stream; charset=utf-8")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.WriteHeader(http.StatusOK)

	// Send initial chunk with role=assistant (optional but common).
	chatCmplID := makeChatCompletionID()
	initial := openai.ChatCompletionChunk{
		ID:      chatCmplID,
		Created: time.Now().Unix(),
		Model:   chatReq.Model,
		Choices: []openai.ChatCompletionChunkChoice{
			{
				Delta: openai.ChatCompletionChunkChoiceDelta{Role: "assistant"},
			},
		},
	}
	if err := writeSSEChunk(w, initial); err != nil {
		return
	}

	// Large chunk of text
	zenOfPython := `Beautiful is better than ugly.
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
	words := strings.Split(zenOfPython, " ")
	for i, word := range words {
		// Handle client cancellation
		select {
		case <-r.Context().Done():
			log.Printf("context done: %v", r.Context().Err())
			return
		default:
		}
		// If unsafe chunk id is reached, generate an unsafe chunk.
		if unsafeSelected && i == unsafeConfig.UnsafeChunkID {
			word = unsafeConfig.UnsafeWord
		}
		// Write the chunk to the response writer
		chunk := openai.ChatCompletionChunk{
			ID:      chatCmplID,
			Created: time.Now().Unix(),
			Model:   chatReq.Model,
			Choices: []openai.ChatCompletionChunkChoice{
				{
					Delta: openai.ChatCompletionChunkChoiceDelta{
						Content: word + " ",
					},
				},
			},
		}
		if err := writeSSEChunk(w, chunk); err != nil {
			log.Printf("Failed to send chunk: %v", err)
			return
		}
		// DO NOT call flusher.Flush(), because we want to simulate Envoy's splitting or coalescing of chunks.
		// Simulate a small delay
		time.Sleep(20 * time.Millisecond)
	}
	// Final chunk with finish_reason=stop and empty delta
	final := openai.ChatCompletionChunk{
		ID:      chatCmplID,
		Created: time.Now().Unix(),
		Model:   chatReq.Model,
		Choices: []openai.ChatCompletionChunkChoice{
			{
				Delta:        openai.ChatCompletionChunkChoiceDelta{},
				FinishReason: string(openai.CompletionChoiceFinishReasonStop),
			},
		},
	}
	if err := writeSSEChunk(w, final); err != nil {
		log.Printf("Failed to send last chunk: %v", err)
		return
	}
	// Stream terminator.
	if _, err := fmt.Fprintf(w, "data: [DONE]\n\n"); err != nil {
		log.Printf("Failed to send last chunk: %v", err)
	}
	flusher.Flush()
}

func writeSSEChunk(w http.ResponseWriter, chunk openai.ChatCompletionChunk) error {
	b, err := json.Marshal(chunk)
	if err != nil {
		log.Printf("marshal chunk: %v", err)
		return err
	}
	_, err = fmt.Fprintf(w, "data: %s\n\n", b)
	if err != nil {
		return err
	}
	log.Printf("Sent chunk: %s", string(b))
	return nil
}

// Logging middleware to track all requests
func loggingMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		next.ServeHTTP(w, r)
		log.Printf("%s %s %s", r.Method, r.URL.Path, time.Since(start))
	})
}

// --- Helpers ---
func makeChatCompletionID() string {
	return "chatcmpl-" + uuid.New().String()
}

func synthesizeReply(req ChatCompletionRequest) string {
	// Simple echo of the last user message content; replace with any behavior you want.
	var last string
	for i := len(req.Messages) - 1; i >= 0; i-- {
		if req.Messages[i].Role == "user" && req.Messages[i].Content != "" {
			last = req.Messages[i].Content
			break
		}
	}
	if strings.Contains(last, unsafeConfig.UnsafeTrigger) {
		return unsafeConfig.UnsafeWord
	}
	if last == "" {
		return "Hello from fake LLM."
	}
	return "Echo: " + last
}

func joinMessages(msgs []ChatMessage) string {
	var b strings.Builder
	for _, m := range msgs {
		if m.Content != "" {
			b.WriteString(m.Content)
			b.WriteString("\n")
		}
	}
	return b.String()
}

func estimateTokens(s string) int64 {
	// Very rough; good enough for tests.
	parts := strings.Fields(s)
	if n := int64(len(parts)); n > 0 {
		return n
	}
	if s == "" {
		return 0
	}
	return 1
}
