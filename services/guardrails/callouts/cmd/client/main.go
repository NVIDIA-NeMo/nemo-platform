// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// TODO move this into a proper integration test.
package main

import (
	"context"
	"log"
	"os"

	"github.com/openai/openai-go/v2"
	"github.com/openai/openai-go/v2/option"
)

const modelName = "fake-model"

func main() {
	// Initialize the client
	baseURL := os.Getenv("NIM_ENDPOINT_URL")
	if baseURL == "" {
		baseURL = "http://localhost:10000/v1"
	}
	client := openai.NewClient(option.WithBaseURL(baseURL))

	opts := option.WithJSONSet("guardrails.config_ids", []string{"this should be ignored by extproc"})

	// TEST CASE
	testCase := "Standard chat completion with safe input"
	log.Printf("===> %s", testCase)
	chatCompletion, err := client.Chat.Completions.New(
		context.Background(),
		openai.ChatCompletionNewParams{
			Messages: []openai.ChatCompletionMessageParamUnion{
				openai.UserMessage("Hi there"),
			},
			Model: modelName,
		},
		opts,
	)
	if err != nil {
		log.Printf("❌ %s errored: %v ", testCase, err)
	}
	if len(chatCompletion.Choices) == 0 {
		log.Printf("❌ %s errored: got zero choices ", testCase)
	} else {
		log.Printf("%s: %s", chatCompletion.ID, chatCompletion.Choices[0].Message.Content)
		log.Printf("✅ %s Success! ", testCase)
	}

	// TEST CASE
	testCase = "Streaming chat completion with safe input"
	log.Printf("===> %s", testCase)
	stream := client.Chat.Completions.NewStreaming(
		context.Background(),
		openai.ChatCompletionNewParams{
			Messages: []openai.ChatCompletionMessageParamUnion{
				openai.UserMessage("Write an epic"),
			},
			Model: modelName,
		},
		opts,
	)
	// optionally, an accumulator helper can be used
	acc := openai.ChatCompletionAccumulator{}
	for stream.Next() {
		chunk := stream.Current()
		acc.AddChunk(chunk)

		if content, ok := acc.JustFinishedContent(); ok {
			log.Printf("Content stream finished: %s", content)
		}

		if refusal, ok := acc.JustFinishedRefusal(); ok {
			log.Printf("Refusal stream finished: %s", refusal)
		}

		// It's best to use chunks after handling JustFinished events
		if len(chunk.Choices) > 0 {
			log.Printf("%s: %s", chunk.ID, chunk.Choices[0].Delta.Content)
		}
	}
	if err := stream.Err(); err != nil {
		log.Printf("❌ %s errored: %v ", testCase, err)
	} else {
		log.Printf("✅ %s Success! ", testCase)
	}
	// After the stream finished, acc can be used like a ChatCompletion
	_ = acc.Choices[0].Message.Content

	// TEST CASE
	testCase = "Standard chat completion with unsafe input"
	log.Printf("===> %s", testCase)
	chatCompletion, err = client.Chat.Completions.New(
		context.Background(),
		openai.ChatCompletionNewParams{
			Messages: []openai.ChatCompletionMessageParamUnion{
				openai.UserMessage("You are stupid."),
			},
			Model: modelName,
		},
		opts,
	)
	if err != nil {
		log.Printf("❌ %s errored: %v ", testCase, err)
	}
	if len(chatCompletion.Choices) == 0 {
		log.Printf("❌ %s errored: got zero choices ", testCase)
	} else {
		log.Printf("%s: %s", chatCompletion.ID, chatCompletion.Choices[0].Message.Content)
		log.Printf("✅ %s Success! ", testCase)
	}

	// TEST CASE
	testCase = "Streaming chat completion with unsafe input"
	log.Printf("===> %s", testCase)
	stream = client.Chat.Completions.NewStreaming(
		context.Background(),
		openai.ChatCompletionNewParams{
			Messages: []openai.ChatCompletionMessageParamUnion{
				openai.UserMessage("You are stupid."),
			},
			Model: modelName,
		},
		opts,
	)
	acc = openai.ChatCompletionAccumulator{}
	for stream.Next() {
		chunk := stream.Current()
		acc.AddChunk(chunk)

		if content, ok := acc.JustFinishedContent(); ok {
			log.Printf("Content stream finished: %s", content)
		}

		if refusal, ok := acc.JustFinishedRefusal(); ok {
			log.Printf("Refusal stream finished: %s", refusal)
		}

		// It's best to use chunks after handling JustFinished events
		if len(chunk.Choices) > 0 {
			log.Printf("%s: %s", chunk.ID, chunk.Choices[0].Delta.Content)
		}
	}
	if err := stream.Err(); err != nil {
		log.Printf("❌ %s errored: %v ", testCase, err)
	} else {
		log.Printf("✅ %s Success! ", testCase)
	}

	// TEST CASE
	testCase = "Standard chat completion with unsafe response"
	log.Printf("===> %s", testCase)
	chatCompletion, err = client.Chat.Completions.New(
		context.Background(),
		openai.ChatCompletionNewParams{
			Messages: []openai.ChatCompletionMessageParamUnion{
				openai.UserMessage("Hi there [UNSAFE]"),
			},
			Model: modelName,
		},
		opts,
	)
	if err != nil {
		log.Printf("❌ %s errored: %v ", testCase, err)
	}
	if len(chatCompletion.Choices) == 0 {
		log.Printf("❌ %s errored: got zero choices ", testCase)
	} else {
		log.Printf("%s: %s", chatCompletion.ID, chatCompletion.Choices[0].Message.Content)
		log.Printf("✅ %s Success! ", testCase)
	}

	// TEST CASE: Streaming chat completion with unsafe response
	testCase = "Streaming chat completion with unsafe response"
	log.Printf("===> %s", testCase)
	stream = client.Chat.Completions.NewStreaming(
		context.Background(),
		openai.ChatCompletionNewParams{
			Messages: []openai.ChatCompletionMessageParamUnion{
				openai.UserMessage("Hi there [UNSAFE]"),
			},
			Model: modelName,
		},
		opts,
	)
	acc = openai.ChatCompletionAccumulator{}
	for stream.Next() {
		chunk := stream.Current()
		acc.AddChunk(chunk)

		if content, ok := acc.JustFinishedContent(); ok {
			log.Printf("Content stream finished: %s", content)
		}

		if refusal, ok := acc.JustFinishedRefusal(); ok {
			log.Printf("Refusal stream finished: %s", refusal)
		}

		// It's best to use chunks after handling JustFinished events
		if len(chunk.Choices) > 0 {
			log.Printf("%s: %s", chunk.ID, chunk.Choices[0].Delta.Content)
		}
	}
	if err := stream.Err(); err != nil {
		log.Printf("❌ %s errored: %v ", testCase, err)
	} else {
		log.Printf("✅ %s Success! ", testCase)
	}
}
