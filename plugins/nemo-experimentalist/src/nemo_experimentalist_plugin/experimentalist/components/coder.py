# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import ast  # noqa: D100, F401
import json
import os  # noqa: F401
import random
import re  # noqa: F401
import shutil
from collections import Counter, defaultdict  # noqa: F401
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx
from nemo_experimentalist_plugin.experimentalist.components.evaluator import Dataset, EvaluationResult, Evaluator, EvaluatorConfig, Task, TrialResult
from nemo_experimentalist_plugin.entities import Candidate
from nooa import Agent, CodeActStrategy, strategy
from nooa.agentdoc import doc, spec
from nooa.agents import TokenBudgetSummarizer
from nooa.config import CodeActConfig
from nooa.config.summarizer_config import TokenBudgetConfig
from nooa.skill import Skill
from nooa.skill_registry import SkillRegistry
from nooa.tools import Match, TodoManager
from pydantic import BaseModel, Field

from .cards import Optimize
from .model_config import get_fast_model, get_mid_model, get_smart_model
from .tools import GuardedShellTools
from .util import load_framework_skills


class CoderConfig(BaseModel):
    """Store tuning parameters for Coder optimization."""

    max_summary_tokens: int = Field(
        default=80_000,
        description="Max tokens the token-budget summarizer may use.",
    )
    max_fix_attempts: int = Field(
        default=2,
        description="Max LLM repair iterations inside integration_check before giving up on a candidate.",
    )
    timeout_model_list_secs: float = Field(
        default=10.0,
        description="HTTP timeout in seconds when fetching the list of available LLM models.",
    )
    model_catalog_path: Path | None = Field(
        default=None,
        description="Optional YAML model catalog path overriding the packaged assets/models.yaml.",
    )


class IntegrationCheckFailed(RuntimeError):
    """Signal that a candidate cannot pass the integration check within the allotted repair budget."""


class ArchitectureSkill(Skill):
    """Guide to writing architecture documentation for an agent.

    An architecture documentation file is a human- and LLM-readable snapshot of an agent's diagram,
    written as a mermaid class diagram. The optimizer reads it to understand what can be changed and
    proposes improvements targeting specific degrees of freedom.

    ---

    ## Core concepts

    An agent is a graph of components. Regardless of framework, every agent has:

    | Concept | What it is |
    | ------- | ---------- |
    | **Prompt** | The string, template, or policy object that shapes what the LLM is asked |
    | **Method** | A callable the agent invokes to interact with the world (search, SQL, API, bash, files, etc.). A tool at agent disposal. |
    | **Stochastic Method** | A callable the agent invokes to interact with the world using a LLM (e.g. a tool that uses a LLM). A tool at agent disposal. |
    | **Subagent** | Another agent/executor instance the component delegates work to (e.g. a planner agent) |
    | **Model config** | Which LLM model and with what parameters (temperature, max_tokens, etc.) |
    | **Skills** | A collection of methods and knowledge that the agent can use to interact with the world |
    | **Association arrows** | The arrows that connect the components in the diagram |


    Based on the framework of choice, the components look different.
    Some popular frameworks example:

    **NeMo OO Agents**

    ```python
    from nooa import Agent, TextSkill
    from nooa.unifiedllm import get_llm_client

    llm = get_llm_client("aws/anthropic/claude-haiku-4-5-v1")  # model config

    class ResearchAgent(Agent, llm=llm):
        '''You are a research assistant.'''  # system prompt

        def __init__(self):
            super().__init__()
            self.rules = TextSkill(path=".claude/skills/domain-rules")  # skill

        async def search(self, query: str) -> list[str]:      # deterministic method
            return http_search(query)

        async def summarize(self, hits: list[str]) -> str:    # stochastic method (LLM)
            '''Summarize the search hits into a concise paragraph.'''  # method prompt
            ...

        async def run(self, question: str) -> str:            # stochastic method (LLM)
            '''Answer the question by searching and summarizing.'''  # method prompt
            ...
    ```

    **LangGraph / LangChain**

    ```python
    from langgraph.graph import StateGraph, START, END
    from langchain_core.tools import tool
    from langchain_openai import ChatOpenAI

    model = ChatOpenAI(model="gpt-4o", temperature=0)    # model config

    @tool
    def search(query: str) -> list[str]:                  # deterministic method
        return http_search(query)

    def call_model(state):                                # stochastic method (LLM node)
        prompt = "You are a research assistant. Answer questions precisely."  # method prompt
        messages = [{"role": "system", "content": prompt}] + list(state["messages"])
        return {"messages": [model.bind_tools([search]).invoke(messages)]}

    graph = StateGraph(State)
    graph.add_node("agent", call_model)
    graph.add_edge(START, "agent")
    ```

    **Deep Agents (LangChain)**

    ```python
    from langchain_nvidia_ai_endpoints import create_deep_agent
    from langchain_core.tools import tool
    from langchain_openai import ChatOpenAI

    summarize_llm = ChatOpenAI(model="gpt-4o-mini")       # model config (per-tool)

    @tool
    def search(query: str) -> list[str]:                  # deterministic method
        return http_search(query)

    @tool
    def summarize(hits: list[str]) -> str:                # stochastic method (LLM)
        prompt = "Summarize the search hits into a concise paragraph."  # method prompt
        return summarize_llm.invoke([
            {"role": "system", "content": prompt},
            {"role": "user", "content": str(hits)},
        ]).content

    agent = create_deep_agent(
        model="anthropic:claude-sonnet-4-5",              # model config
        tools=[search, summarize],                        # methods
        system_prompt="Answer questions precisely.",      # system prompt
        skills=["domain-rules"],                          # skills
    )
    ```

    Understand how each framework defines the components and the relationships between them.

    ---

    ## Scope — what to include and what to exclude

    The diagram must contain ONLY components the optimizer can improve. Include and exclude strictly:

    **Include:**
    - All components listed above (agents, subagents, methods, tools, skills, prompts, etc.)
    - Default configuration (models being used, tool configurations, etc.)


    **Exclude — do not diagram these:**
    - Any infrastructure code (e.g. web framework, database, logging, monitoring, feature-flag plumbing, etc.) around the agent.
    - Non default configuration (e.g. tool configurations, model configurations, etc.)
    - Anything that's not strictly called by the agent (e.g. code that is not part of the agent's logic, such as setup code, testing code, etc.)
    - Legacy paths or non default paths that are not exercised in the current evaluation

    **Default path tracing:** When the entrypoint dispatches based on a feature flag or if/else,
    follow only the actively exercised branch based on the entrypoint. Check for flags, env variables and default runner.

    When in doubt: if the optimizer changing this component would not affect agent behavior on the task, exclude it.

    ---

    ## Format

    `architecture.md` has two sections: a **Mermaid flowchart** and a **prompts** appendix.

    ### Section 1 — Mermaid flowchart

    > **Mental model, not a code transcript.** The diagram is a friendly visualization of agent
    > topology — it is meant to be readable by humans and useful to the optimizer, not a one-to-one
    > copy of implementation details. For example, a dict of tool callables
    > (`self.TOOLS = {'search': search_fn}`) may be shown as individual method nodes because that
    > conveys the logical structure more clearly. What matters is capturing *what the agent can do
    > and how components relate*, not mirroring every syntactic choice in the source.
    > It is meant to be an execution overview of the agent, not a detailed code transcript.

    A mermaid `flowchart TD`. Every node is one of four types:

    **Node shapes:**

    Use `<br/>` for line breaks inside node labels — `\n` is not valid Mermaid syntax.

    | Node type | Mermaid syntax | When to use |
    | --------- | -------------- | ----------- |
    | Agent | `id{{"Name<br/>model: model-id<br/>system: <truncated><br/>skills: s1 · s2"}}` | The agent itself — hexagon. Omit `skills:` line if none. |
    | Method | `id["name<br/>in:  arg: Type<br/>out: ReturnType"]` | Deterministic callable with real logic (dispatch, transform, branch) — no LLM involved. Rectangle. Pure `await`-sequence methods are invisible — see rule below. |
    | Stochastic method | `id(["name*<br/>in:  arg: Type<br/>out: ReturnType<br/>prompt: <truncated>"])` | LLM-driven callable. Stadium shape. Append `<br/>model: override` only when the method overrides the agent's default model. |
    | Subagent | `subgraph AgentName["AgentName · model: model-id · system: <truncated>"]` ... `end` | Delegates work to another agent. Use a Mermaid subgraph containing the subagent's method nodes. |

    Truncate long strings to ~60 chars with `...` — the prompts appendix holds verbatim content.

    **Arrow types:**

    | Arrow | Meaning |
    | ----- | ------- |
    | `A --> B` | Forced path: A always invokes B — enforced by code (explicit `await self.B()`, `graph.add_edge`, etc.) |
    | `A -.-> B` | Optional path: A may invoke B — the LLM decides at runtime |

    **Critical rule:** prompt-instructed sequences are dashed, not solid. A stochastic method's
    prompt may say "always call X then Y" but the LLM may still deviate — only Python code or
    graph edges that unconditionally invoke a method justify a solid arrow.

    **Sequence vs fan-out:** When an orchestrator method calls A then B then C in code, draw a
    chain `run --> A --> B --> C`, not a fan-out `run --> A`, `run --> B`, `run --> C`. The arrow
    shows execution sequence, not just who owns whom.

    **Tool access:** If a method (class or other callable) is accessible from a stochastic method, draw a dashed arrow FROM
    that method TO the method. A method (class or other callable) is accessible if it is reachable from that method at runtime
    — e.g. `self.shell`, a module-level instance, or a closure variable. Accessibility, not call
    frequency, determines the arrow.

    **Invisible sequencers:** If a method's body consists entirely of `await` calls to other
    methods in sequence, omit it from the diagram. The diagram IS the graph that method builds.
    The agent hexagon connects directly to the first step in the chain.

    **Labeled solid arrows:** Label every solid arrow with the data flowing between steps:
    `A -->|param: Type| B`. If one step's output flows to multiple downstream steps, draw a
    labeled arrow for each downstream node. Dashed arrows are not labeled — LLM-decided data
    flow is not deterministic.

    **Mermaid edge label quoting:** If a label contains `[`, `]`, `<`, or `>`, wrap the entire
    label in double quotes: `A -->|"list[T]"| B`. Plain `|param: Type|` is fine when no special
    characters are present.

    Node labels use `<br/>` for line breaks. Each node type has a fixed field order:

    **Agent / Subagent fields** (include only fields that apply):
    ```
    AgentName
    model: <model-id>
    system: <first ~60 chars of system prompt>...
    skills: skill1 · skill2
    ```

    **Method fields** (deterministic — no LLM, rectangle `[...]`):
    ```
    method_name
    in:  param1: Type, param2: Type
    out: ReturnType
    ```

    **Stochastic method fields** (LLM-driven, stadium `([...])`, always ends with `*`):
    ```
    method_name*
    in:  param1: Type, param2: Type
    out: ReturnType
    prompt: <first ~60 chars>...
    model: <override-id>       ← only when different from agent default
    temperature: N             ← only when explicitly set non-default
    max_tokens: N              ← only when explicitly set non-default
    ```

    ---

    **Example 1 — NeMo OO: agent with skills, LLM tool dispatch**

    Demonstrates: agent hexagon with skills, stochastic methods, tool nodes,
    solid entrypoint from framework, all LLM-driven calls dashed.

    ```python
    class MyAgent(Agent, llm=get_smart_model()):
        '''You are a research assistant.'''

        def __init__(self):
            self.shell = ShellTools()
            self.domain = TextSkill(path=".claude/skills/domain.md")

        async def solve_task(self, task_input: str) -> str:
            '''Solve the task using available tools.'''
            ...

        async def summarize(self, text: str) -> str:
            '''Summarize the text into a concise paragraph.'''
            ...
    ```

    ```mermaid
    flowchart TD
        MyAgent{{"MyAgent<br/>model: claude-opus-4-5<br/>system: You are a research assistant.<br/>skills: domain"}}

        shell["ShellTools<br/>in: command: str, path: str, content: str<br/>out: ShellResult | Match"]
        solve_task(["solve_task*<br/>in:  task_input: str<br/>out: str<br/>prompt: Solve the task using available tools."])
        summarize(["summarize*<br/>in:  text: str<br/>out: str<br/>prompt: Summarize the text into a concise paragraph."])

        MyAgent --> solve_task
        solve_task -.-> summarize
        solve_task -.-> shell
        summarize -.-> shell
    ```

    `MyAgent --> solve_task` solid: framework calls `solve_task` as the entrypoint in code.
    Everything else dashed: the LLM inside `solve_task` freely decides what to call.
    Both `solve_task` and `summarize` get dashed tool arrows — every stochastic method can use tools.

    ---

    **Example 2 — LangGraph: hard-wired graph edges, deterministic node, tool choice**

    Demonstrates: `add_edge` produces solid arrows, deterministic method (rectangle, no LLM),
    dashed tool choice when dispatch depends on runtime state.

    ```python
    SYSTEM = "You are a planner. Break the query into sub-steps."

    class PlannerAgent:
        def __init__(self):
            self.llm = ChatNVIDIA(model="meta/llama-3.1-70b-instruct")
            self.TOOLS = {"search": search_tool, "sql": sql_tool}

        def create_plan(self, state: AgentState) -> AgentState:
            # LLM call
            ...

        def execute_step(self, state: AgentState) -> AgentState:
            # deterministic dispatch — reads state["plan"][0]["tool"], no LLM
            result = self.TOOLS[state["plan"][0]["tool"]](state["plan"][0]["input"])
            state["result"] = result
            return state

        def generate_final_answer(self, state: AgentState) -> AgentState:
            # LLM call
            ...

        def create_graph(self):
            graph = StateGraph(AgentState)
            graph.add_edge("plan", "execute")    # hard-wired
            graph.add_edge("execute", "answer")  # hard-wired
            return graph.compile()
    ```

    ```mermaid
    flowchart TD
        PlannerAgent{{"PlannerAgent<br/>model: meta/llama-3.1-70b-instruct<br/>system: You are a planner. Break the query into sub-steps."}}

        create_plan(["create_plan*<br/>in:  state: AgentState<br/>out: AgentState<br/>prompt: You are a planner. Break the query into sub-steps."])
        execute_step["execute_step<br/>in:  state: AgentState<br/>out: AgentState"]
        generate_final_answer(["generate_final_answer*<br/>in:  state: AgentState<br/>out: AgentState<br/>prompt: Summarize: {state[result]}"])
        search["search_tool<br/>in:  query: str<br/>out: list[str]"]
        sql["sql_tool<br/>in:  query: str<br/>out: str"]

        PlannerAgent --> create_plan
        create_plan --> execute_step
        execute_step -.-> search
        execute_step -.-> sql
        execute_step --> generate_final_answer
    ```

    Solid arrows: `add_edge` calls in Python code. `execute_step` is a rectangle (no LLM).
    Dashed to tools: `execute_step` reads `state["plan"][0]["tool"]` at runtime — either tool.

    ---

    **Example 3 — Code-enforced sequence with model override and generation params**

    Demonstrates: explicit Python `await` chain produces solid arrows; stochastic method
    with a different model and non-default temperature; deterministic orchestrator method.

    ```python
    class WriterAgent(Agent, llm=get_smart_model()):
        '''You are a writing assistant. Draft and refine content.'''

        def __init__(self):
            self.style = TextSkill(path=".claude/skills/style.md")
            self.tone  = TextSkill(path=".claude/skills/tone.md")

        async def draft(self, brief: str) -> str:
            '''Write a first draft from the brief.'''
            ...

        @strategy(PredictStrategy(), llm=get_fast_model(), temperature=0.0)
        async def critique(self, draft: str) -> str:
            '''List exactly three weaknesses in the draft. Be terse.'''
            ...

        async def revise(self, draft: str, notes: str) -> str:
            '''Revise the draft to address every critique note.'''
            ...

        async def run(self, brief: str) -> str:
            # explicit await chain — deterministic Python, not LLM-driven
            draft  = await self.draft(brief)
            notes  = await self.critique(draft)
            return await self.revise(draft, notes)
    ```

    ```mermaid
    flowchart TD
        WriterAgent{{"WriterAgent<br/>model: claude-opus-4-5<br/>system: You are a writing assistant. Draft and refine content.<br/>skills: style · tone"}}

        draft(["draft*<br/>in:  brief: str<br/>out: str<br/>prompt: Write a first draft from the brief."])
        critique(["critique*<br/>in:  draft: str<br/>out: str<br/>prompt: List exactly three weaknesses in the draft. Be terse.<br/>model: claude-haiku-4-5<br/>temperature: 0.0"])
        revise(["revise*<br/>in:  draft: str, notes: str<br/>out: str<br/>prompt: Revise the draft to address every critique note."])

        WriterAgent -->|brief: str| draft
        draft -->|draft: str| critique
        draft -->|draft: str| revise
        critique -->|notes: str| revise
    ```

    `run` is invisible — it is a pure `await`-sequence method, so the diagram encodes what it builds.
    `WriterAgent` connects directly to `draft`, the first step, labeled with the input type.
    `draft` fans to both `critique` and `revise` because both consume its output.
    `critique` carries `model:` and `temperature:` because both differ from the agent default.

    ---

    **Example 4 — Multi-agent: subagent as nested subgraph, execution chain**

    Demonstrates: subagent as a Mermaid `subgraph` containing its method nodes, execution
    sequence as a chain (not fan-out), every stochastic method gets dashed arrows to all tools.

    ```python
    class Orchestrator(Agent, llm=get_smart_model()):
        '''You are an optimization orchestrator.'''

        def __init__(self):
            self.shell = GuardedShellTools(...)
            self.analyzer = AnalyzerAgent(...)

        async def propose_improvements(self, analysis: str) -> list[Improvement]:
            '''Propose candidate improvements based on the analysis.'''
            ...

        async def implement_improvement(self, candidate: Candidate) -> None:
            '''Implement the proposed improvement in agent source.'''
            ...

        async def run(self, dataset: Dataset) -> None:
            analysis = await self.analyzer.analyze_trace(...)  # explicit subagent call
            proposal = await self.propose_improvements(analysis)
            await self.implement_improvement(proposal)
    ```

    ```mermaid
    flowchart TD
        Orchestrator{{"Orchestrator<br/>model: claude-opus-4-5<br/>system: You are an optimization orchestrator."}}

        shell["GuardedShellTools<br/>in: command: str, path: str, content: str<br/>out: ShellResult | Match"]
        propose(["propose_improvements*<br/>in:  analysis: str<br/>out: list[Improvement]<br/>prompt: Propose candidate improvements based on the analysis."])
        implement(["implement_improvement*<br/>in:  candidate: Candidate<br/>out: None<br/>prompt: Implement the proposed improvement in agent source."])

        subgraph AnalyzerAgent["AnalyzerAgent · model: claude-haiku-4-5 · system: You are a trace analyzer. Identify failure patterns..."]
            analyze_trace(["analyze_trace*<br/>in:  trace_path: str<br/>out: str<br/>prompt: Analyze the trace and identify failure patterns."])
        end

        Orchestrator -->|dataset: Dataset| analyze_trace
        analyze_trace -->|analysis: str| propose
        propose -->|candidate: Candidate| implement
        propose -.-> shell
        implement -.-> shell
    ```

    `run` is invisible — pure `await`-sequence method, the diagram encodes what it builds.
    `Orchestrator` connects directly to `analyze_trace` (first step) with the input data label.
    Solid labeled chain shows exact data contracts between steps — the optimizer knows what breaks if types change.
    Every stochastic method (`propose`, `implement`) gets dashed arrows to all tools Orchestrator owns.

    ---

    **Example 5 — Types and Prompts appendix** (for PlannerAgent from Example 2):

    `AgentState` appears in every arrow label and node signature — the optimizer needs its fields
    to propose schema changes. `str`, `list` etc. are primitives and need no entry.

    ```markdown
    ## Types

    ### AgentState
    - query: str
    - plan: list
    - result: str

    ## Prompts

    ### PlannerAgent.create_plan
    You are a planner. Break the query into sub-steps.

    {state[query]}

    ### PlannerAgent.generate_final_answer
    Summarize {state[result]}
    ```

    ### Section 2 — Types

    Full definitions of every non-primitive custom type that appears in the diagram — in `in:`,
    `out:`, or arrow labels. Primitive types (`str`, `int`, `bool`, `float`, `list[str]`, etc.)
    are self-explanatory and do not need an entry. Include every `TypedDict`, `dataclass`,
    `Pydantic model`, or named type that the optimizer would need to understand in order to
    propose a schema change.

    ```markdown
    ## Types

    ### TypeName
    - field1: Type
    - field2: Type
    - field3: Type | None
    ```

    ### Section 3 — Prompts

    Full verbatim content of every prompt found in the codebase — system prompts, user prompts,
    prompt templates, and prompt-returning methods. This is the primary optimization target.

    ```markdown
    ## Prompts

    ### ClassName.method_name  (or  module.CONSTANT_NAME)
    <full prompt string or method body, verbatim>

    ### ClassName.other_method
    <full prompt string or method body, verbatim>
    ```

    Include:
    - Every prompt that is passed to an LLM that can be acted upon or modified by someone coding the agent.

    ---

    ## AGENT-SPEC.md — read first if it exists

    An `AGENT-SPEC.md` (or `AGENT_SPEC.md`) in the workspace is a durable contract written by the
    agent's author. When present, read it before any source file. It is authoritative on the scope of the agent.

    It helps discern what is agent-pertinent and what is not.
    If AGENT-SPEC.md is absent, infer all of the above from source code.

    ---

    ## Writing architecture.md

    1. Check for documentation (specs, readmes) and read it first if present. Understand the scope of the agent.
    2. Read the agent's source `.py` files, starting from the entrypoint, following imports. Use the spec's framework and harness to anchor what you're looking for.
    3. Apply the Scope rules above: include only agent components, tools, skills, and prompts. Do not include anything that's infrastructure around it, evaluation code, storage code, etc.
       Only include default paths. If a user has to change configs to use this path, it should not be included.
    4. Collect key imports and write the diagram note.
    5. If the file already EXISTS (it is seeded from the ancestor for every non-baseline agent),
       edit it IN PLACE: apply only the minimal delta for the one change being documented and
       preserve everything else verbatim — same section order, Mermaid dialect, node-shape syntax,
       wording, and type-annotation style. Do **not** re-render or restyle unchanged content.
    6. Only when the file does NOT already exist, author it from scratch: write the diagram, then
       the prompts appendix (verbatim content of all prompt strings found).

    """


class Coder(Agent, llm=get_smart_model()):
    """Create and modify agent source code as part of the optimization loop."""

    def __init__(
        self,
        workspace: Path,
        config: CoderConfig | None = None,
        framework_skills_dirs: list[Path] | None = None,
        **kwargs: Any,
    ):
        """Initialize the coder for the given workspace."""
        super().__init__(**kwargs)
        self._config = config or CoderConfig()
        self._workspace_path = workspace.resolve()
        self.shell = GuardedShellTools(cwd=self._workspace_path)
        self.todos = TodoManager()
        self.context["file_match"] = doc(Match)

        self.skills: SkillRegistry = SkillRegistry(self)
        spec(self, "skills", hidden=True)
        load_framework_skills(self.skills, framework_skills_dirs or [])
        self.skills.register("ext.architecture_skill", ArchitectureSkill())
        # Attach the optimization-card index so apply_change / wire_up_change
        # can consult the card matching candidate.optimization_type. Without
        # this, the Coder only sees the proposer's prose and the framework
        # skill -- the optimize cards never reach it (gitlab #148).
        self.optimize = Optimize(model_catalog_path=self._config.model_catalog_path)
        self.skills.register("ext.optimize", self.optimize)
        self.skills.activate(["cmd.*", "ext.*"])
        self._models_cache: list[str] | None = None
        TokenBudgetSummarizer.install(
            self,
            llm=get_fast_model(),
            config=TokenBudgetConfig(max_tokens=self._config.max_summary_tokens),
        )

    async def list_available_models(self) -> list[str]:
        """Fetch available LLM model IDs from the configured inference API.

        Results are cached in memory for the lifetime of this instance.

        Returns:
            list[str]: model ID strings as returned by the API.

        Raises:
            ValueError: if EXPERIMENTALIST_API_BASE or EXPERIMENTALIST_API_KEY is not set.
            httpx.HTTPStatusError: if the API returned a non-2xx response.
            httpx.RequestError: if there was a network or connection failure.

        """
        if self._models_cache is not None:
            return self._models_cache

        async with httpx.AsyncClient() as client:
            api_base = os.environ.get("EXPERIMENTALIST_API_BASE")
            api_key = os.environ.get("EXPERIMENTALIST_API_KEY")
            if api_base is None or api_key is None:
                raise ValueError("EXPERIMENTALIST_API_BASE and EXPERIMENTALIST_API_KEY must be set")

            resp = await client.get(
                f"{api_base}/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=self._config.timeout_model_list_secs,
            )
            resp.raise_for_status()
            data = resp.json()

        rows = data.get("data", [])
        if not isinstance(rows, list):
            raise ValueError("Invalid /models response: expected data to be a list")
        models = [
            model_id
            for row in rows
            if isinstance(row, dict) and isinstance(model_id := row.get("id"), str) and model_id
        ]
        if not models:
            raise ValueError("No model ids found in /models response")
        self._models_cache = models
        return models

    async def run(
        self,
        candidate: Candidate,
        dataset: Dataset,
        evaluator: Evaluator,
        evaluator_options: EvaluatorConfig | None = None,
        source_path: str | None = None,
        entrypoint: str | None = None,
    ) -> None:
        """Implement the improvement described in candidate and verify it integrates cleanly.

        Args:
            candidate: The agent variant to implement. Identifies the agent directory,
                carries the optimization description, and links to its ancestor.
            dataset: The dataset to use for the evaluation.
            evaluator: The evaluator to use for the evaluation.
            evaluator_options: The options to pass to the evaluator.
            source_path: The path to the agent source code, relative to the agent directory.
            entrypoint: The file that the evaluation harness invokes to run the agent, relative to the agent directory.

        Raises:
            RuntimeError: if no training tasks are available for integration_check.
            IntegrationCheckFailed: if the candidate cannot pass a smoke eval after the
                bounded number of fix attempts.

        """
        await self.apply_change(candidate)
        await self.wire_up_change(candidate)
        await self.run_pyright(candidate.name)
        await self.optimize_subproblem(candidate, dataset, evaluator, evaluator_options)
        await self.run_pyright(candidate.name)
        if not await self.integration_check(candidate, dataset, evaluator, evaluator_options):
            raise IntegrationCheckFailed(f"{candidate.name} smoke eval failed after fix attempts")
        if candidate.ancestor:
            ancestor_arch = (
                self._workspace_path / "eval-and-optimize" / "agents" / candidate.ancestor / "architecture.md"
            )
            candidate_arch = self._workspace_path / "eval-and-optimize" / "agents" / candidate.name / "architecture.md"
            if ancestor_arch.exists() and not candidate_arch.exists():
                shutil.copy2(ancestor_arch, candidate_arch)
        await self.create_architecture_doc(candidate.name, source_path=source_path, entrypoint=entrypoint)

    @strategy(CodeActStrategy(config=CodeActConfig(max_iterations=50, cell_timeout=3600.0)))
    async def apply_change(self, candidate: Candidate) -> None:
        """Apply the ONE change from candidate.optimization.

        Args:
        - candidate (Candidate): the agent variant being built. Identifies
          which agent directory to modify, describes the change to apply, and
          carries lineage info from its ancestor

        ## Pre-staged destination — DO NOT re-copy from the ancestor
        The destination directory ``agents/{candidate.id}/`` has ALREADY been
        populated by the framework with a copy of the ancestor's source files
        (everything except generated framework artifacts: ``metadata.json`` and
        ``architecture.md``). Runtime harness files are inherited when present
        but are not part of the agent behavior being optimized.
        Open and modify files in place. You do NOT need to copy anything in.

        ## Required reading before editing
        - The framework skill — how to write agents in the target framework (NeMo OO, LangChain, etc.).
        - The optimization card for this change. First run `print(doc(self.optimize))`
          to see the decision tree mapping optimization types to cards. Find which
          card covers `candidate.optimization_type` (e.g. `add_concrete_method` is
          covered by `optimize_execution`), then load that card's details with
          `print(doc(self.optimize.optimize_execution))`. The card lists approved approaches,
          code examples, and success criteria.
        - If the change involves methods that handle large inputs (scraped pages,
          documents, search results), read `print(doc(self.processing_large_data))`
          for chunking patterns that avoid `max_param_chars` truncation errors.

        ## Constraints
        - Make one change matching candidate.optimization
        - No hardcoded knowledge (keyword lists, lookup tables, if/elif on task-specific strings). This applies to BOTH code AND skill edits: skill additions must improve generalizable methodology (process steps, classification rules, evidence requirements), never add dataset-specific facts about specific libraries, frameworks, CVEs, or package internals — that is memorization of training data, not domain knowledge.
        - NEVER read from, copy from, or overwrite files in any OTHER agent
          directory (``agents/agent-N/`` for N != candidate.id). The pre-staged
          files in your own directory are the only source you should edit.
        - NEVER modify ``metadata.json`` in any agent directory. It is owned by
          the framework and carries the correct agent id, lineage, and scores.
        - VERIFY INTEGRATION: In the integration test, check traces to confirm new code is actually
          called by the agent. Code that exists but isn't invoked is useless.
        - If the change involves editing an LLM model id, call
          `models = await self.list_available_models()` first and pick one of the
          returned ids. Do NOT invent or abbreviate model ids.
        """
        ...

    @strategy(CodeActStrategy(config=CodeActConfig(max_iterations=50, cell_timeout=3600.0)))
    async def wire_up_change(self, candidate: Candidate) -> None:
        """Wire up the change to the agent such that it is called by the agent. Load the framework skill and use it to understand how to wire up the change.

        Args:
        - candidate (Candidate): the agent variant being built. Identifies
          which agent directory to modify, describes the change to apply, and
          carries lineage info from its ancestor

        Consult `doc(self.optimize)` to find which card covers
        `candidate.optimization_type`, then read that card via
        `doc(self.optimize.optimize_<type>)` for what "wired" means in the target framework.
        (e.g. for `add_skill` covered by `optimize_domain_knowledge`, the new skill
        must be reachable by the agent at runtime — a file that is never imported or
        registered is not wired, regardless of framework).
        """
        ...

    @strategy(CodeActStrategy(config=CodeActConfig(max_iterations=200, cell_timeout=3600.0)))
    async def optimize_subproblem(
        self,
        candidate: Candidate,
        dataset: Dataset,
        evaluator: Evaluator,
        evaluator_options: EvaluatorConfig | None = None,
    ) -> None:
        """Validate and iteratively refine the subproblem fix until the agent's behavior improves.

        Args:
        - candidate (Candidate): the agent variant being built. Identifies
          which agent directory to modify, describes the change to apply, and
          carries lineage info from its ancestor
        - dataset (Dataset): The dataset to use for the evaluation.
        - evaluator (Evaluator): The evaluator to use for the evaluation.
        - evaluator_options (EvaluatorConfig): The options to pass to the evaluator.

        ## Workflow

        1. **Pick test tasks**:
           - **Target tasks**: use `candidate.task_ids` — the tasks the Proposer flagged as
             most directly exercising this candidate's root cause. The fix must improve these.
             Only if `candidate.task_ids` is empty, fall back to picking 2-3 representative
             tasks that exercise the subproblem yourself.
           - **Regression tasks**: also pick 2-3 tasks the ancestor/baseline already handled
             correctly and that are unrelated to this subproblem. The fix must NOT regress
             these — they guard against the change breaking previously-working behavior.
           - Consider `candidate.optimization` to understand what was changed

        2. **Isolate the subproblem**:
           - Read the agent's architecture.md to understand the agent's behavior
           - Read the optimization card for `candidate.optimization_type` to understand what was changed
           - Read `candidate.optimization` to understand the specific subproblem being fixed
           - Run the subproblem fix on the tasks and inspect the results.
             E.g. if the subproblem was the behavior of a single method, call that method on the tasks
             and inspect the results. If it was a single tool, run that tool directly.
             Always prefer isolated calls for speed; only run a full smoke eval if needed.

           Example: Adding a new method to the agent to create unit tests.

            ```python
            class SWEAgent(Agent):
                async def create_unit_tests(self, issue: str, repo: str) -> str:
                    '''Create unit tests for the issue.'''
                    return "Unit tests created."

            ### Test
            task_description = ...
            repo = ...
            print(SweAgent().create_unit_tests(task_description, repo))
            ```

        3. **Reason about whether the behavior improved**:
           - Compare what you observe to what the fix was supposed to achieve
           - Look for concrete evidence in traces and outputs

           **Example**: Subproblem = "agent prematurely concludes without thorough analysis"
           - Fix applied: increased minimum reasoning steps before concluding
           - What to check: Does the trace show multiple reasoning/analysis tool calls?
           - Verdict: subproblem is fixed only if BOTH hold — the target tasks now show the
             improved behavior AND the regression tasks still behave as they did on the baseline
             (no regression). If both → you're done.
           - If no: identify specifically what's still wrong — either the target isn't fixed
             ("train-005 still has only 1 reasoning call") or a regression task broke
             ("train-012 was passing but now fails").

        4. **If not fixed** (max 3 iterations):
           - Make targeted changes to the agent source based on what you observed
           - Repeat from step 2 with the same tasks (for consistency)

        5. **Done** - no cleanup needed

        ## Key principle

        You're validating **behavior change**, not just correctness. The subproblem is about
        how the agent acts (thoroughness, reasoning depth, tool usage patterns, report quality).
        Use the traces as evidence of whether the agent's behavior actually improved.

        """
        ...

    async def integration_check(
        self,
        candidate: Candidate,
        dataset: Dataset,
        evaluator: Evaluator,
        evaluator_options: EvaluatorConfig | None = None,
        max_fix_attempts: int | None = None,
    ) -> bool:
        """Smoke-test the candidate and attempt bounded LLM repairs if it fails.

        Args:
            candidate: The agent variant to smoke-test.
            dataset: The dataset to use for the evaluation.
            evaluator: The evaluator to use for the evaluation.
            evaluator_options: The options to pass to the evaluator.
            max_fix_attempts: Maximum repair iterations; defaults to
                ``self._config.max_fix_attempts``.

        Returns:
            bool: True if the candidate passes the smoke eval, False otherwise.

        Raises:
            RuntimeError: if no training tasks are available.

        """
        _max_fix_attempts = max_fix_attempts if max_fix_attempts is not None else self._config.max_fix_attempts

        all_tasks = list(dataset.list_tasks())
        if not all_tasks:
            raise RuntimeError("No tasks available for integration_check")
        # One task to keep smoke wall time low; seeded by candidate.name so retries hit the same task.
        tasks = [random.Random(candidate.name).choice(all_tasks)]
        for attempt in range(_max_fix_attempts + 1):
            evaluation = await self.run_smoke_eval(candidate.name, tasks, dataset, evaluator, evaluator_options)
            if self._is_smoke_results_healthy(evaluation, tasks):
                return True
            if attempt < _max_fix_attempts:
                await self._fix_runtime_issues(candidate, evaluation)
        return False

    def _is_smoke_results_healthy(self, evaluation: EvaluationResult, tasks: Sequence[Task]) -> bool:
        """Return True if each selected task has a completed trial without evaluator error.

        Args:
            evaluation: Smoke evaluation result.
            tasks: Tasks included in the smoke evaluation.

        Returns:
            bool: True if all tasks produced at least one clean trial.

        """
        trials_by_task: dict[str, list[TrialResult]] = defaultdict(list)
        for trial in evaluation.trials:
            trials_by_task[trial.task_id].append(trial)

        for task in tasks:
            trials = trials_by_task.get(task.id, [])
            if not trials:
                return False
            if not any(self._trial_runtime_healthy(trial) for trial in trials):
                return False
        return True

    def _trial_runtime_healthy(self, trial: TrialResult) -> bool:
        """Return True if evaluator status/error indicates runtime success."""
        if trial.error is not None:
            return False
        return trial.status == "completed"

    @strategy(CodeActStrategy(config=CodeActConfig(max_iterations=50, cell_timeout=3600.0)))
    async def _fix_runtime_issues(self, candidate: Candidate, evaluation: EvaluationResult) -> None:
        """Diagnose and repair runtime failures surfaced by the most recent smoke eval.

        Args:
        - candidate (Candidate): the agent variant being repaired. Identifies
          which agent directory to modify, describes the change that was applied,
          and carries lineage info from its ancestor
        - evaluation (EvaluationResult): the smoke evaluation result. Use its
          trials, metrics, outputs, resources, errors, and metadata as failure evidence.

        The orchestrator (`integration_check`) just ran `run_smoke_eval` and the
        deterministic health check returned False. Your job is to read the failure
        evidence and edit the agent source so the next smoke eval will pass. Do NOT
        re-run smoke eval yourself — the orchestrator does it.

        ## Failure context (read in this order)

        For each trial in `evaluation.trials`:
        1. `trial.status` and `trial.error` — crash, timeout, or evaluator-owned
           failure details.
        2. `trial.outputs` — agent-visible output values or referenced output files.
        3. `trial.resources` — logs, traces, manifests, or artifact references made
           visible by the evaluator.
        4. `trial.metrics` — numeric evaluator results. Names are evaluator-defined.
        5. `trial.metadata` — adapter facts that help locate or interpret evidence.

        Read ResourceRef descriptions and metadata before opening referenced files.
        Do not assume any particular directory layout or artifact filename.

        ## What to fix

        Edit files in `eval-and-optimize/agents/{candidate.id}/` — the same files
        `apply_change` and `wire_up_change` produced. Common runtime failure modes
        and their fixes:

        - **TypeError / wrong signature** — tool/function called with bad kwargs.
          Match the call to the definition.
        - **NameError / ImportError** — the change references a symbol that doesn't
          exist or removed an import. Add the import or revert the reference.
        - **KeyError on env var / config** — the change added a config read without
          a default or `.env` entry. Use `os.environ.get(..., default)` or revert.
        - **Evaluator failure, no exception** — the agent ran but failed task checks.
          Read visible outputs/resources to identify the missing file, wrong schema,
          bad side effect, service failure, or incorrect final value. Required
          artifact paths are task-defined; do not assume a generic `output.*`.
        - **Tool that no longer exists is being called** — a tool was removed but
          a call site wasn't updated. Update the call site.

        ## Constraints

        - Do NOT modify `metadata.json`.
        - Do NOT touch optimizer infrastructure: `init_structure.py`,
          `optimize_agent.py`, anything under `.claude/skills/`.
        - Do NOT call `run_smoke_eval` — the orchestrator re-runs it after you finish.
        - Make the minimum edit that fixes the failure. Don't introduce new behavior.
        """
        ...

    async def run_pyright(self, agent_id: str) -> str:
        """Run pyright on the agent's directory and return diagnostic lines.

        Args:
            agent_id: The agent directory under eval-and-optimize/agents/ to check.

        Returns:
            str: newline-separated error and warning lines, or an empty string
                if pyright reports no issues.

        """
        r = await self.shell.run(f"pyright --outputjson eval-and-optimize/agents/{agent_id} 2>/dev/null || true")
        output = (r.stdout or "").strip()
        try:
            data = json.loads(output)
            diags = data.get("generalDiagnostics", [])
            if not diags:
                return ""
            lines = []
            for d in diags:
                if d.get("severity") in ("error", "warning"):
                    file_ = d.get("file", "")
                    rule = d.get("rule", "")
                    msg = d.get("message", "")
                    rng = d.get("range", {}).get("start", {})
                    line_no = rng.get("line", "?")
                    lines.append(f"{file_}:{line_no}: {d['severity']}: {msg} ({rule})")
            return "\n".join(lines)
        except Exception:
            return output

    async def run_smoke_eval(
        self,
        agent_id: str,
        tasks: Sequence[Task],
        dataset: Dataset,
        evaluator: Evaluator,
        evaluator_options: EvaluatorConfig | None = None,
    ) -> EvaluationResult:
        """Run smoke evaluation against a specific subset of tasks.

        Args:
            agent_id: The agent directory under eval-and-optimize/agents/ to evaluate.
            tasks: Non-empty task objects to evaluate.
            dataset: The dataset to use for the evaluation.
            evaluator: The evaluator to use for the evaluation.
            evaluator_options: The options to pass to the evaluator.

        Returns:
            EvaluationResult: smoke evaluation result.

        Raises:
            ValueError: if ``tasks`` is empty.

        """
        if not tasks:
            raise ValueError("run_smoke_eval requires at least one task")

        smoke_dataset = dataset.subset([task.id for task in tasks])
        base_options = evaluator_options if evaluator_options is not None else evaluator.options
        smoke_options = base_options.model_copy(update={"force_rerun": True})
        agent_path = self._workspace_path / "eval-and-optimize" / "agents" / agent_id
        return await evaluator.run(
            agent=agent_path,
            dataset=smoke_dataset,
            options=smoke_options,
        )

    @strategy(CodeActStrategy(config=CodeActConfig(max_iterations=50, cell_timeout=3600.0)), llm=get_mid_model())
    async def create_architecture_doc(
        self, agent_id: str, source_path: str | None = None, entrypoint: str | None = None
    ) -> None:
        """Update (or, only if absent, create) architecture.md for the given agent.

        Args:
        - agent_id (str): identifies which agent directory under {self._workspace_path}/eval-and-optimize/agents/ to document
        - source_path (str | None): directory containing the agent source code, relative to the
          agent directory (e.g. "app/"). Read .py files from here when following imports.
          When absent, infer the source root from AGENT-SPEC.md or the directory structure.
        - entrypoint (str | None): the file that the evaluation harness invokes to run the agent,
          relative to the agent directory (e.g. "harbor/runner.py"). Start reading here to
          determine the call chain and identify the default execution path before reading
          source_path. When absent, infer from AGENT-SPEC.md or the directory structure.

        Load the agent-architecture skill and use it to document the agent.

        ## Edit in place — do NOT regenerate from scratch
        For any candidate with an ancestor, the framework has ALREADY seeded
        {self._workspace_path}/eval-and-optimize/agents/{agent_id}/architecture.md with a
        byte-for-byte copy of the ancestor's architecture.md. Open the existing file and edit it
        in place to reflect the FINAL state of the candidate source (after all automated repairs),
        not just its originally declared change. Compare the final source against the ancestor and
        capture every resulting difference — nodes, edges, prompts, and type definitions — as a
        MINIMAL, targeted delta:

        - Preserve the existing document verbatim wherever the code did not change — same section
          order and headings, same Mermaid dialect and node-shape syntax, same wording, spacing,
          and type-annotation style. Do NOT restyle, reflow, re-title, re-render, or "improve" any
          part the change did not touch.
        - Edit ONLY the lines the final source differs from the ancestor: a node added/removed/
          modified, an edge rerouted, an affected custom type definition, or a prompt string that
          changed. If a node or type was already drawn a certain way in the ancestor's file, keep
          drawing it that way.
        - A reviewer diffing this file against the ancestor's must see only the real architectural
          delta. Spurious formatting churn (different Mermaid dialect, added prose, re-cased type
          names, reordered sections) hides the actual change and is a defect.

        ## Steps

        1. Read the entrypoint {entrypoint} to identify the default execution path — which feature
           flag value is default, which if/else branch runs in production. The entrypoint itself
           is infrastructure and must NOT appear in the diagram. Use it only to determine scope.
           Then read source files under {source_path}, following only imports reachable from the
           default path. If entrypoint is None, infer it from AGENT-SPEC.md or the directory.
           Apply the scope rules from the architecture skill:
           include only agent components (agents, stochastic methods, deterministic methods, tools),
           exclude the entrypoint/harness itself, evaluation code, test data, and infrastructure.

        2. Diff your understanding of the current source against the EXISTING architecture.md and
           apply the minimal edit that brings it up to date. Pay special attention to prompt strings
           (Section 3), which change frequently: copy them verbatim from source definitions, not
           call sites. A reader must understand what the LLM is asked to do without opening any
           source file.

        3. ONLY if architecture.md does not already exist (e.g. a baseline agent with no ancestor),
           author it from scratch using the node shapes and arrow conventions from the architecture
           skill exactly:
           - Agent hexagon {{}} for each agent
           - Stochastic method stadium ([]) with * suffix for every method that calls an LLM
           - Deterministic method rectangle [] for methods with real logic but no LLM
           - Dashed arrows -.-> for LLM-decided calls; solid arrows --> for code-enforced calls
           - Labeled solid arrows -->|param: Type| next showing data contracts
           - Section 2: Types — definitions of all non-primitive custom types used in the diagram
           - Section 3: Prompts — verbatim prompt strings the LLM will read (instruction sentences,
             role descriptions, template content). Copy from source definitions, not call sites.
        """
        ...
