// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { SamplerType } from '@nemo/sdk/generated/data-designer/schema';
import type { FilesetTemplate } from '@studio/components/CreateFilesetStart/types';
import { DEFAULT_BUILD_MODEL_NAME, DEFAULT_EMBEDDER_MODEL_NAME } from '@studio/constants/constants';
import {
  Braces,
  Code2,
  Database,
  FlaskConical,
  GraduationCap,
  PackageSearch,
  Scale,
  SearchCode,
  SquareFunction,
  Wrench,
} from 'lucide-react';

/**
 * The ready-made recipes shown as cards in the secondary area when "Start from a
 * template" is selected. Add entries here as more are authored — the card grid and
 * selection flow scale to any number without further changes. Each recipe carries one
 * or more use-case tags (see {@link FilesetTemplate.tags}).
 */
export const FILESET_TEMPLATES: FilesetTemplate[] = [
  {
    id: 'sft-instruction',
    title: 'Instruction fine-tuning (SFT)',
    description:
      'Instruction–response pairs for supervised fine-tuning: a sampled topic, an LLM-generated user instruction, and a model answer.',
    icon: GraduationCap,
    tags: [
      { label: 'Fine-tuning', color: 'blue', kind: 'outline' },
      { label: 'SFT', color: 'purple', kind: 'outline' },
      { label: 'Text', color: 'gray', kind: 'outline' },
    ],
    columns: [
      {
        columnType: 'sampler',
        samplerType: SamplerType.category,
        name: 'domain',
        values: {
          values:
            'science, technology, history, arts, business, health, education, sports, travel, cooking',
        },
      },
      {
        columnType: 'llm-text',
        name: 'instruction',
        values: {
          prompt:
            'Write a single, self-contained user instruction about {{ domain }}. Return only the instruction.',
          model_alias: 'default',
        },
      },
      {
        columnType: 'llm-text',
        name: 'response',
        values: {
          prompt:
            'Respond helpfully and concisely to the following instruction:\n\n{{ instruction }}',
          model_alias: 'default',
        },
      },
    ],
    models: [{ alias: 'default', model: DEFAULT_BUILD_MODEL_NAME }],
  },
  {
    id: 'sampler-showcase',
    title: 'All samplers (showcase)',
    description:
      'A column for each previewable sampler sub-type — UUID, category, subcategory, uniform, gaussian, Bernoulli, Bernoulli mixture, binomial, Poisson, scipy, datetime, and timedelta — seeded with valid params for QA.',
    icon: FlaskConical,
    tags: [
      { label: 'Showcase', color: 'green', kind: 'outline' },
      { label: 'Samplers', color: 'gray', kind: 'outline' },
      { label: 'No LLM', color: 'teal', kind: 'outline' },
    ],
    columns: [
      {
        columnType: 'sampler',
        samplerType: SamplerType.uuid,
        name: 'uuid_id',
        values: { prefix: 'user-', short_form: 'true', uppercase: 'false' },
      },
      {
        columnType: 'sampler',
        samplerType: SamplerType.category,
        name: 'category_topic',
        values: { values: 'science, technology, arts', weights: '3, 2, 1' },
      },
      {
        // Parent-category reference → draws an edge from `category_topic`.
        columnType: 'sampler',
        samplerType: SamplerType.subcategory,
        name: 'subcategory_topic',
        values: {
          category: 'category_topic',
          values:
            '{ "science": ["physics", "biology"], "technology": ["ai", "systems"], "arts": ["music", "painting"] }',
        },
      },
      {
        columnType: 'sampler',
        samplerType: SamplerType.uniform,
        name: 'uniform_score',
        values: { low: '0', high: '1', decimal_places: '3' },
      },
      {
        columnType: 'sampler',
        samplerType: SamplerType.gaussian,
        name: 'gaussian_measure',
        values: { mean: '100', stddev: '15', decimal_places: '2' },
      },
      {
        columnType: 'sampler',
        samplerType: SamplerType.bernoulli,
        name: 'bernoulli_flag',
        values: { p: '0.3' },
      },
      {
        columnType: 'sampler',
        samplerType: SamplerType.bernoulli_mixture,
        name: 'bernoulli_mixture_value',
        values: { p: '0.5', dist_name: 'norm', dist_params: '{ "loc": 10, "scale": 2 }' },
      },
      {
        columnType: 'sampler',
        samplerType: SamplerType.binomial,
        name: 'binomial_successes',
        values: { n: '10', p: '0.5' },
      },
      {
        columnType: 'sampler',
        samplerType: SamplerType.poisson,
        name: 'poisson_events',
        values: { mean: '4' },
      },
      {
        columnType: 'sampler',
        samplerType: SamplerType.scipy,
        name: 'scipy_sample',
        values: { dist_name: 'beta', dist_params: '{ "a": 2, "b": 5 }', decimal_places: '3' },
      },
      // The managed `person` sampler is intentionally omitted: it requires downloaded
      // Nemotron Personas datasets, so it can't preview in environments without them.
      {
        columnType: 'sampler',
        samplerType: SamplerType.datetime,
        name: 'created_at',
        values: { start: '2020-01-01', end: '2024-01-01', unit: 'D' },
      },
      {
        // Reference-datetime column → draws an edge from `created_at`.
        columnType: 'sampler',
        samplerType: SamplerType.timedelta,
        name: 'shipped_after',
        values: { dt_min: '1', dt_max: '30', reference_column_name: 'created_at', unit: 'D' },
      },
    ],
  },
  {
    id: 'code-generation',
    title: 'Code generation + validation (Python)',
    description:
      'Python coding challenges with LLM-generated solutions and automatic code validation: exercises a sampled topic, an LLM task description, a code answer, and a pass/fail validation column.',
    icon: Code2,
    tags: [
      { label: 'Fine-tuning', color: 'green', kind: 'outline' },
      { label: 'Code', color: 'blue', kind: 'outline' },
      { label: 'Validation', color: 'red', kind: 'outline' },
    ],
    columns: [
      {
        columnType: 'sampler',
        samplerType: SamplerType.category,
        name: 'topic',
        values: {
          values:
            'sorting algorithms, string manipulation, file I/O, data structures, recursion, decorators, generators, async I/O',
        },
      },
      {
        columnType: 'llm-text',
        name: 'task',
        values: {
          prompt:
            'Write a clear, self-contained Python coding challenge about {{ topic }}. State what the function should do and give one example input/output pair. Return only the problem statement.',
          model_alias: 'default',
        },
      },
      {
        columnType: 'llm-code',
        name: 'solution',
        values: {
          prompt:
            'Solve the following Python coding challenge. Return only the code — no prose, no markdown fences.\n\n{{ task }}',
          model_alias: 'default',
          code_lang: 'python',
        },
      },
      {
        columnType: 'validation',
        name: 'is_valid',
        values: {
          target_columns: 'solution',
          validator_type: 'code',
          validator_params: '{ "code_lang": "python" }',
        },
      },
    ],
    models: [{ alias: 'default', model: DEFAULT_BUILD_MODEL_NAME }],
  },
  {
    id: 'structured-extraction',
    title: 'Structured data extraction',
    description:
      'Free-form text paired with its structured JSON representation — for training extraction and information-retrieval models. An LLM writes a description; a second call extracts it into a typed schema.',
    icon: Braces,
    tags: [
      { label: 'Fine-tuning', color: 'purple', kind: 'outline' },
      { label: 'Extraction', color: 'blue', kind: 'outline' },
      { label: 'Structured', color: 'gray', kind: 'outline' },
    ],
    columns: [
      {
        columnType: 'sampler',
        samplerType: SamplerType.category,
        name: 'entity_type',
        values: {
          values: 'product, company, research paper, recipe, event, film',
        },
      },
      {
        columnType: 'llm-text',
        name: 'description',
        values: {
          prompt:
            'Write a realistic, detailed description of a {{ entity_type }} — include concrete names, dates, and figures. Return only the description.',
          model_alias: 'default',
        },
      },
      {
        columnType: 'llm-structured',
        name: 'structured',
        values: {
          prompt:
            'Extract the key attributes from the following {{ entity_type }} description:\n\n{{ description }}\n\nReturn the attributes as a JSON object.',
          model_alias: 'default',
          output_format:
            '{ "type": "object", "properties": { "name": { "type": "string" }, "attributes": { "type": "object" } }, "required": ["name", "attributes"] }',
        },
      },
    ],
    models: [{ alias: 'default', model: DEFAULT_BUILD_MODEL_NAME }],
  },
  {
    id: 'preference-pairs',
    title: 'Preference pairs (reward modeling)',
    description:
      'An instruction with a high-quality chosen answer, a lower-quality rejected answer, and an LLM judge score — for DPO fine-tuning and reward model training.',
    icon: Scale,
    tags: [
      { label: 'Alignment', color: 'yellow', kind: 'outline' },
      { label: 'DPO', color: 'purple', kind: 'outline' },
      { label: 'Reward model', color: 'blue', kind: 'outline' },
    ],
    columns: [
      {
        columnType: 'sampler',
        samplerType: SamplerType.category,
        name: 'topic',
        values: {
          values: 'science, history, philosophy, mathematics, literature, technology, ethics',
        },
      },
      {
        columnType: 'llm-text',
        name: 'instruction',
        values: {
          prompt:
            'Write a challenging, open-ended question about {{ topic }} that requires an explanatory answer. Return only the question.',
          model_alias: 'default',
        },
      },
      {
        columnType: 'llm-text',
        name: 'chosen',
        values: {
          prompt: 'Answer the following question accurately and thoroughly:\n\n{{ instruction }}',
          model_alias: 'default',
        },
      },
      {
        columnType: 'llm-text',
        name: 'rejected',
        values: {
          prompt:
            'Give a brief, vague, or slightly inaccurate answer to the following question — do not correct yourself:\n\n{{ instruction }}',
          model_alias: 'default',
        },
      },
      {
        columnType: 'llm-judge',
        name: 'quality_score',
        values: {
          prompt:
            'On a scale of 1–5 (1 = very poor, 5 = excellent), rate the quality of the following answer.\n\nQuestion: {{ instruction }}\nAnswer: {{ chosen }}\n\nReturn only the integer score.',
          model_alias: 'default',
          scores:
            '[{ "name": "Quality", "description": "Overall answer quality.", "options": { "1": "Very poor", "5": "Excellent" } }]',
        },
      },
    ],
    models: [{ alias: 'default', model: DEFAULT_BUILD_MODEL_NAME }],
  },
  {
    id: 'semantic-search',
    title: 'Semantic search dataset',
    description:
      'Query–passage pairs with vector embeddings for retrieval, RAG evaluation, and semantic similarity benchmarks. Requires an embedding model configured under the "embedder" alias.',
    icon: SearchCode,
    tags: [
      { label: 'Retrieval', color: 'blue', kind: 'outline' },
      { label: 'RAG', color: 'teal', kind: 'outline' },
      { label: 'Embeddings', color: 'purple', kind: 'outline' },
    ],
    columns: [
      {
        columnType: 'sampler',
        samplerType: SamplerType.category,
        name: 'domain',
        values: {
          values: 'science, technology, health, finance, culture, sports',
        },
      },
      {
        columnType: 'llm-text',
        name: 'passage',
        values: {
          prompt:
            'Write a factual, self-contained paragraph about a specific topic within {{ domain }}. Return only the paragraph.',
          model_alias: 'default',
        },
      },
      {
        columnType: 'llm-text',
        name: 'query',
        values: {
          prompt:
            'Write a short search query that a user might type to retrieve the following passage:\n\n{{ passage }}\n\nReturn only the query.',
          model_alias: 'default',
        },
      },
      {
        columnType: 'embedding',
        name: 'passage_embedding',
        values: {
          target_column: 'passage',
          model_alias: 'embedder',
        },
      },
    ],
    models: [
      { alias: 'default', model: DEFAULT_BUILD_MODEL_NAME },
      {
        alias: 'embedder',
        model: DEFAULT_EMBEDDER_MODEL_NAME,
        inferenceParams: {
          generation_type: 'embedding',
          encoding_format: 'float',
          extra_body: { input_type: 'passage', truncate: 'NONE' },
        },
      },
    ],
  },
  {
    // Recipe: Code Generation → Text to SQL
    // https://docs.nvidia.com/nemo/datadesigner/recipes/code-generation/text-to-sql
    id: 'text-to-sql',
    title: 'Text to SQL',
    description:
      'Natural-language instructions paired with SQL, across industries and complexity levels. Samples a domain, topic, and SQL concept; an LLM writes the task, a schema, and the query; then code validation and a multi-dimension judge score the result.',
    icon: Database,
    tags: [
      { label: 'Code', color: 'blue', kind: 'outline' },
      { label: 'Fine-tuning', color: 'green', kind: 'outline' },
      { label: 'SQL', color: 'purple', kind: 'outline' },
      { label: 'Validation', color: 'red', kind: 'outline' },
    ],
    columns: [
      {
        columnType: 'sampler',
        samplerType: SamplerType.category,
        name: 'industry_sector',
        values: { values: 'Healthcare, Finance, Technology' },
      },
      {
        columnType: 'sampler',
        samplerType: SamplerType.subcategory,
        name: 'topic',
        values: {
          category: 'industry_sector',
          values:
            '{ "Healthcare": ["Electronic Health Records (EHR) Systems", "Telemedicine Platforms", "AI-Powered Diagnostic Tools"], "Finance": ["Fraud Detection Software", "Automated Trading Systems", "Personal Finance Apps"], "Technology": ["Cloud Computing Platforms", "AI and Machine Learning Platforms", "DevOps and CI/CD Tools"] }',
        },
      },
      {
        columnType: 'sampler',
        samplerType: SamplerType.category,
        name: 'sql_complexity',
        values: { values: 'Beginner, Intermediate, Advanced' },
      },
      {
        columnType: 'sampler',
        samplerType: SamplerType.subcategory,
        name: 'sql_concept',
        values: {
          category: 'sql_complexity',
          values:
            '{ "Beginner": ["Basic SELECT Statements", "WHERE Clauses", "Basic JOINs", "INSERT/UPDATE/DELETE"], "Intermediate": ["Aggregation Functions", "Multiple JOINs", "Subqueries", "Views"], "Advanced": ["Window Functions", "CTEs", "Stored Procedures", "Query Optimization"] }',
        },
      },
      {
        columnType: 'sampler',
        samplerType: SamplerType.category,
        name: 'sql_task_type',
        values: {
          values: 'Data Retrieval, Data Manipulation, Analytics and Reporting, Data Transformation',
        },
      },
      {
        columnType: 'sampler',
        samplerType: SamplerType.category,
        name: 'instruction_phrase',
        values: {
          values:
            'Write an SQL query that, Create an SQL statement to, Develop an SQL query to, Can you write SQL that, Formulate an SQL query that',
        },
      },
      {
        columnType: 'llm-text',
        name: 'sql_prompt',
        values: {
          prompt:
            'Generate a natural-language {{ sql_task_type }} task for the {{ industry_sector }} domain, specifically about {{ topic }}. It should require {{ sql_complexity }}-level SQL using {{ sql_concept }}. Begin the task with the phrase: "{{ instruction_phrase }}". Return only the task description.',
          system_prompt: 'You are an expert at generating clear, specific SQL tasks.',
          model_alias: 'default',
        },
      },
      {
        columnType: 'llm-code',
        name: 'sql_context',
        values: {
          prompt:
            'Write the SQL DDL (CREATE TABLE statements, plus a few INSERTs of sample data) for a database schema that supports the following task. Return only SQL.\n\n{{ sql_prompt }}',
          system_prompt:
            'You are an expert SQL database designer who writes clean, efficient schemas.',
          model_alias: 'default',
          code_lang: 'sql:ansi',
        },
      },
      {
        columnType: 'llm-code',
        name: 'sql',
        values: {
          prompt:
            'Given the schema below, write a single {{ sql_complexity }}-level SQL query using {{ sql_concept }} that accomplishes the task. Return only the SQL query — no prose, no markdown fences.\n\nTask:\n{{ sql_prompt }}\n\nSchema:\n{{ sql_context }}',
          system_prompt: 'You are an expert SQL programmer who writes clean, efficient queries.',
          model_alias: 'default',
          code_lang: 'sql:ansi',
        },
      },
      {
        columnType: 'validation',
        name: 'code_validity_result',
        values: {
          target_columns: 'sql',
          validator_type: 'code',
          validator_params: '{ "code_lang": "sql:ansi" }',
        },
      },
      {
        columnType: 'llm-judge',
        name: 'code_judge_result',
        values: {
          prompt:
            'Evaluate the SQL query below against the task and schema.\n\nTask:\n{{ sql_prompt }}\n\nSchema:\n{{ sql_context }}\n\nQuery:\n{{ sql }}',
          model_alias: 'default',
          scores:
            '[{ "name": "Relevance", "description": "Does the query address the task?", "options": { "1": "Off-topic", "4": "Fully on-topic" } }, { "name": "SQL Correctness", "description": "Is the SQL valid and does it return the right result?", "options": { "1": "Broken", "4": "Correct" } }, { "name": "Readability", "description": "Is the query clear and well-formatted?", "options": { "1": "Unreadable", "4": "Very clear" } }, { "name": "Efficiency", "description": "Is the query performant for the schema?", "options": { "1": "Inefficient", "4": "Efficient" } }]',
        },
      },
    ],
    models: [{ alias: 'default', model: DEFAULT_BUILD_MODEL_NAME }],
  },
  {
    // Recipe: QA and Chat → Product Info QA
    // https://docs.nvidia.com/nemo/datadesigner/recipes/qa-and-chat/product-info-qa
    id: 'product-info-qa',
    title: 'Product info Q&A',
    description:
      'Synthetic product records paired with a question and answer — with a controlled fraction of hallucinated answers and an LLM judge scoring completeness and accuracy. Useful for training and evaluating grounded product-support assistants.',
    icon: PackageSearch,
    tags: [
      { label: 'QA & chat', color: 'teal', kind: 'outline' },
      { label: 'Grounding', color: 'blue', kind: 'outline' },
      { label: 'LLM judge', color: 'yellow', kind: 'outline' },
    ],
    columns: [
      {
        columnType: 'sampler',
        samplerType: SamplerType.category,
        name: 'category',
        values: {
          values:
            'Electronics, Clothing, Home Appliances, Groceries, Toiletries, Sports Equipment, Toys, Books, Pet Supplies, Tools & Home Improvement, Beauty, Health & Wellness, Outdoor Gear, Automotive, Office Supplies, Baby & Kids, Video Games, Software, Tech Devices',
        },
      },
      {
        columnType: 'sampler',
        samplerType: SamplerType.uniform,
        name: 'price_tens_of_dollars',
        values: { low: '1', high: '200', decimal_places: '0' },
      },
      {
        columnType: 'expression',
        name: 'product_price',
        values: {
          expr: '{{ (price_tens_of_dollars * 10) - 0.01 | round(2) }}',
          dtype: 'float',
        },
      },
      {
        columnType: 'sampler',
        samplerType: SamplerType.category,
        name: 'first_letter',
        values: {
          values: 'A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R, S, T, U, V, W, X, Y, Z',
        },
      },
      {
        columnType: 'sampler',
        samplerType: SamplerType.bernoulli,
        name: 'is_hallucination',
        values: { p: '0.5' },
      },
      {
        columnType: 'llm-structured',
        name: 'product_info',
        values: {
          prompt:
            'Generate a realistic product description for a product in the {{ category }} category that costs {{ product_price }}. The name of the product MUST start with the letter {{ first_letter }}.',
          model_alias: 'default',
          output_format:
            '{ "type": "object", "properties": { "product_name": { "type": "string" }, "key_features": { "type": "array", "items": { "type": "string" } }, "description": { "type": "string" }, "price_usd": { "type": "number" } }, "required": ["product_name", "key_features", "description", "price_usd"] }',
        },
      },
      {
        columnType: 'llm-text',
        name: 'question',
        values: {
          prompt: 'Ask a single question about the following product:\n\n{{ product_info }}',
          model_alias: 'default',
        },
      },
      {
        columnType: 'llm-text',
        name: 'answer',
        values: {
          prompt:
            '{% if is_hallucination == 0 %}Answer the question accurately using only the product information below.\n\nProduct:\n{{ product_info }}\n\nQuestion:\n{{ question }}{% else %}Answer the question below with a confident but fabricated response. Invent plausible-sounding details that are NOT supported by any product information. Do not mention that you are making it up.\n\nQuestion:\n{{ question }}{% endif %}',
          model_alias: 'default',
        },
      },
      {
        columnType: 'llm-judge',
        name: 'llm_answer_metrics',
        values: {
          prompt:
            'Judge the answer against the product information and question.\n\nProduct:\n{{ product_info }}\n\nQuestion:\n{{ question }}\n\nAnswer:\n{{ answer }}',
          model_alias: 'default',
          scores:
            '[{ "name": "Completeness", "description": "Does the answer fully address the question?", "options": { "1": "Ignores the question", "5": "Fully complete" } }, { "name": "Accuracy", "description": "Is the answer grounded in the product information (no fabrication)?", "options": { "1": "Fabricated", "5": "Fully grounded" } }]',
        },
      },
      {
        columnType: 'expression',
        name: 'completeness_result',
        values: {
          expr: '{{ llm_answer_metrics.Completeness.score }}',
          dtype: 'int',
        },
      },
      {
        columnType: 'expression',
        name: 'accuracy_result',
        values: {
          expr: '{{ llm_answer_metrics.Accuracy.score }}',
          dtype: 'int',
        },
      },
    ],
    models: [{ alias: 'default', model: DEFAULT_BUILD_MODEL_NAME }],
  },
  {
    id: 'expression-transforms',
    title: 'Expression transforms (no LLM)',
    description:
      'Derived columns computed via Jinja2 expressions — full-name concatenation, score banding into letter grades. No LLM calls; previews instantly.',
    icon: SquareFunction,
    tags: [
      { label: 'Transform', color: 'teal', kind: 'outline' },
      { label: 'No LLM', color: 'green', kind: 'outline' },
      { label: 'Jinja2', color: 'gray', kind: 'outline' },
    ],
    columns: [
      {
        columnType: 'sampler',
        samplerType: SamplerType.category,
        name: 'first_name',
        values: { values: 'Alice, Bob, Carol, Dave, Eve, Frank, Grace, Hank' },
      },
      {
        columnType: 'sampler',
        samplerType: SamplerType.category,
        name: 'last_name',
        values: { values: 'Smith, Jones, Williams, Brown, Davis, Miller' },
      },
      {
        columnType: 'sampler',
        samplerType: SamplerType.uniform,
        name: 'score',
        values: { low: '0', high: '100', decimal_places: '1' },
      },
      {
        columnType: 'expression',
        name: 'full_name',
        values: {
          expr: '{{ first_name }} {{ last_name }}',
        },
      },
      {
        columnType: 'expression',
        name: 'grade',
        values: {
          expr: '{% if score|float >= 90 %}A{% elif score|float >= 80 %}B{% elif score|float >= 70 %}C{% elif score|float >= 60 %}D{% else %}F{% endif %}',
          dtype: 'str',
        },
      },
    ],
  },
  {
    // Recipe: MCP and Tool Use → tool/function-calling training data.
    // Purely LLM-generated (no live MCP server): a domain toolbox, a user query
    // that needs a tool, the correct call, a grounded reply, and a judge check.
    // https://docs.nvidia.com/nemo/datadesigner/recipes/mcp-and-tool-use/basic-mcp-tool-use
    id: 'tool-calling',
    title: 'Tool / function calling',
    description:
      'Function-calling training data: a sampled domain, an LLM-generated toolbox of function schemas, a user query that requires a tool, the correct structured tool call, a grounded assistant reply, and an LLM judge verifying the call.',
    icon: Wrench,
    tags: [
      { label: 'Tool calling', color: 'blue', kind: 'outline' },
      { label: 'Agents', color: 'teal', kind: 'outline' },
      { label: 'Fine-tuning', color: 'green', kind: 'outline' },
      { label: 'Structured', color: 'purple', kind: 'outline' },
    ],
    columns: [
      {
        columnType: 'sampler',
        samplerType: SamplerType.category,
        name: 'domain',
        values: {
          values:
            'weather, travel booking, e-commerce orders, calendar scheduling, personal finance, smart home, messaging, food delivery, IT support, fitness tracking',
        },
      },
      {
        columnType: 'llm-structured',
        name: 'available_tools',
        values: {
          prompt:
            'Design a small toolbox of 2–4 functions that an AI assistant for the {{ domain }} domain could call. Each function needs a snake_case name, a one-sentence description, and a JSON Schema for its parameters (with realistic property names and types).',
          system_prompt:
            'You are an API designer who writes clean, minimal function schemas for LLM tool use.',
          model_alias: 'default',
          output_format:
            '{ "type": "array", "items": { "type": "object", "properties": { "name": { "type": "string" }, "description": { "type": "string" }, "parameters": { "type": "object" } }, "required": ["name", "description", "parameters"] } }',
        },
      },
      {
        columnType: 'llm-text',
        name: 'user_query',
        values: {
          prompt:
            'Write a single, natural user request for a {{ domain }} assistant that can be fully satisfied by calling exactly one of these tools. Do not mention the tools or their names. Return only the request.\n\nTools:\n{{ available_tools }}',
          model_alias: 'default',
        },
      },
      {
        columnType: 'llm-structured',
        name: 'tool_call',
        values: {
          prompt:
            "Select the single correct tool for the user request and produce the call. Use only a tool name present in the toolbox, and fill arguments that conform to that tool's parameter schema, drawing values from the request.\n\nRequest:\n{{ user_query }}\n\nTools:\n{{ available_tools }}",
          system_prompt: 'You are a precise function-calling engine. Emit only a valid tool call.',
          model_alias: 'default',
          output_format:
            '{ "type": "object", "properties": { "name": { "type": "string" }, "arguments": { "type": "object" } }, "required": ["name", "arguments"] }',
        },
      },
      {
        columnType: 'llm-text',
        name: 'assistant_response',
        values: {
          prompt:
            "Assume the tool call below was executed and returned a plausible successful result. Write the assistant's final natural-language reply to the user. Do not restate the raw JSON.\n\nUser request:\n{{ user_query }}\n\nTool call:\n{{ tool_call }}",
          model_alias: 'default',
        },
      },
      {
        columnType: 'llm-judge',
        name: 'tool_call_quality',
        values: {
          prompt:
            'Evaluate the tool call against the user request and the available tools.\n\nRequest:\n{{ user_query }}\n\nTools:\n{{ available_tools }}\n\nTool call:\n{{ tool_call }}',
          model_alias: 'default',
          scores:
            '[{ "name": "Tool Selection", "description": "Is the chosen tool the right one for the request and present in the toolbox?", "options": { "1": "Wrong or missing tool", "5": "Correct tool" } }, { "name": "Argument Validity", "description": "Do the arguments match the tool schema and the request?", "options": { "1": "Invalid arguments", "5": "Fully valid" } }]',
        },
      },
    ],
    models: [{ alias: 'default', model: DEFAULT_BUILD_MODEL_NAME }],
  },
];

export const findTemplate = (id: string): FilesetTemplate | undefined =>
  FILESET_TEMPLATES.find((template) => template.id === id);
