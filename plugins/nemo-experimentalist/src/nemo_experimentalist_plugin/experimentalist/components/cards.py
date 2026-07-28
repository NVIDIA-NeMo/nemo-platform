# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from nooa import Skill
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ModelCatalogEntry(BaseModel):
    """One curated model choice for OptimizeModelCapability."""

    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(
        min_length=1,
        description="Model identifier.",
    )
    provider: str = Field(
        min_length=1,
        description="Model provider.",
    )
    range: str = Field(
        min_length=1,
        description="Capability or cost range.",
    )
    notes: str = Field(
        min_length=1,
        description="Short model notes.",
    )
    endpoint: str | None = Field(
        default=None,
        min_length=1,
        description="Optional endpoint override. Uses default_endpoint when omitted.",
    )
    api_key_env: str | None = Field(
        default=None,
        min_length=1,
        description="Optional API key environment variable override. Uses default_api_key_env when omitted.",
    )


class ModelCatalog(BaseModel):
    """Schema for assets/models.yaml."""

    model_config = ConfigDict(extra="forbid")

    default_endpoint: str = Field(
        min_length=1,
        description="Default inference endpoint.",
    )
    default_api_key_env: str = Field(
        min_length=1,
        description="Default API key environment variable.",
    )
    id_field: str = Field(
        pattern="^model_id$",
        description="Model identifier field name.",
    )
    models: list[ModelCatalogEntry] = Field(
        min_length=1,
        description="Curated model entries.",
    )

    @model_validator(mode="after")
    def model_ids_are_unique(self) -> "ModelCatalog":
        """Validate that all model_id values in the catalog are unique.

        Returns:
            ModelCatalog: the validated catalog instance.

        Raises:
            ValueError: if any model_id appears more than once.

        """
        seen: set[str] = set()
        duplicates: set[str] = set()
        for model in self.models:
            if model.model_id in seen:
                duplicates.add(model.model_id)
            seen.add(model.model_id)

        if duplicates:
            duplicate_list = ", ".join(sorted(duplicates))
            raise ValueError(f"Duplicate model_id values: {duplicate_list}")
        return self


class OptimizeArchitecture(Skill):
    """Use when the agent's structure is the bottleneck — context overflow causes earlier conclusions to be forgotten, a single method mixes separable concerns, or missing phase boundaries let the agent skip steps. Covers add_subagent, remove_subagent, split_method, merge_method.

    # Optimization Card: Architecture

    ## When to Use

    Use this card when traces show the agent's **structure is the bottleneck**, not its knowledge or reasoning:

    - A single method is doing issue parsing + bug localization + patch writing — and loses earlier conclusions by the end
    - A phase is ended prematurely because the agent is not forced to complete it by phase boundaries
    - Context overflow: patch written at turn N contradicts the bug location identified at turn 2 because earlier context was compressed
    - A task decomposes into genuinely separable concerns that each need their own tool access, model, or reasoning chain
    - Multiple methods each paraphrase the previous output without adding new reasoning (consolidation needed)
    - The agent produces correct intermediate results but incorrect final patches due to information overload

    **Key diagnostic**: Errors are inconsistent — the agent solves the same issue correctly sometimes and incorrectly other times with no change in inputs. This is a context/structure problem, not a knowledge problem.

    ## When NOT to Use

    - Agent reasons incorrectly in a structured way → use `opt-reasoning` (fix the logic, not the structure)
    - Agent skips operations → use `opt-execution`
    - Rules are wrong → use `opt-domain-knowledge`

    ---

    ## Core Pattern

    Architecture fixes restructure **how methods are organized and connected**. The public entrypoint remains programmatic. The change is in how LLM-driven sub-methods are decomposed — splitting into subagents, splitting methods at phase boundaries, or collapsing redundant methods.

    ---

    ## Approaches

    ### Approach 1: Add a Subagent

    **When**: A method is doing multiple separable tasks that each need their own context, tool access, or reasoning chain.

    **Optimization type**: `add_subagent`

    **How**: Extract the concern into a separate `Agent` subclass. The parent delegates to it and consumes its structured output. **The subagent must have its own tools** — passing a callback is insufficient.

    **Code example** — extracting issue triage into a dedicated subagent so the main agent focuses on patching:

    ```python
    class IssueTriager(Agent):
        '''Subagent specialized in parsing GitHub issues into structured bug reports.'''
        search = CodeSearchTool()

        async def triage(self, issue: str, repo: str) -> BugReport:
            '''Parse the issue and identify the affected area.

            Steps:
            1. Extract the symptom and expected vs. actual behavior from the issue text
            2. Identify the module or function likely responsible
            3. Search the repo for the symbol mentioned in the issue
            4. Return a BugReport — do not write a patch here.
            '''
            ...


    class SWEAgent(Agent):
        '''Main agent — delegates issue parsing, focuses on patch writing and verification.'''
        run_tests = RunTestsTool()
        triager   = IssueTriager()   # subagent as attribute

        async def _write_and_verify(
            self, bug_report: BugReport, test_results: dict
        ) -> Patch:
            '''Write and verify a patch given pre-triaged bug report and test results.

            bug_report: structured output from IssueTriager (pre-fetched).
            test_results: pre-run test output (pre-fetched).
            Do not re-triage or re-run tests — use what's passed in.
            '''
            ...

        async def solve(self, issue: str, repo: str) -> Patch:
            '''Solve the GitHub issue.'''
            bug_report   = await self.triager.triage(issue, repo)  # subagent
            test_results = self.run_tests(repo)                    # concrete
            return await self._write_and_verify(bug_report, test_results)
    ```

    **When NOT to add a subagent**: if the concern can be handled by a deterministic method or a new reasoning step. Subagents add latency — reserve them for genuinely separable multi-step concerns.

    ---

    ### Approach 2: Split a Method

    **When**: A single stochastic method combines multiple phases that each produce intermediate conclusions, and the agent loses track of early conclusions by the final step.

    **Optimization type**: `split_method`

    **How**: Split at natural phase boundaries. Each phase produces a typed output consumed by the next. Wire the split into the public entrypoint's Python body.

    **Code example** — splitting a monolithic solve into localization + patch writing:

    ```python
    class SWEAgent(Agent):

        def collect_repo_structure(self, repo: str) -> dict: ...   # concrete

        async def _locate_bug(
            self, issue: str, repo_structure: dict
        ) -> BugLocation:
            '''Locate the bug from the issue and repo structure.

            Return all candidate locations including contradictory evidence.
            Do NOT write a patch — only locate and return evidence.
            '''
            ...

        async def _write_patch(
            self, issue: str, bug_location: BugLocation
        ) -> Patch:
            '''Write a patch for the located bug.

            Do NOT re-locate. Work only from bug_location.
            Apply the output format from the skill file.
            '''
            ...

        async def solve(self, issue: str, repo: str) -> Patch:
            '''Solve the GitHub issue.'''
            structure    = self.collect_repo_structure(repo)
            bug_location = await self._locate_bug(issue, structure)
            return await self._write_patch(issue, bug_location)
    ```

    **Split boundary rules**:
    - Split at the boundary between *fact gathering* and *reasoning*, or between *reasoning* and *patch generation*
    - Each phase must produce a reusable typed output — not a free-form string
    - Do NOT split a focused method — splitting adds latency without benefit

    ---

    ### Approach 3: Merge Methods

    **When**: Multiple sequential stochastic methods each paraphrase the previous output without adding new reasoning, bloating context and diluting signal.

    **Optimization type**: `merge_method`

    **How**: Identify methods whose output is structurally identical to their input (just reformatted). Merge into one method that does the combined work. Update the entrypoint accordingly.

    **Code example** — eliminating a redundant summarization step between localization and patching:

    ```python
    # Before: _summarize_location just reformats _locate_bug output without adding reasoning
    async def _locate_bug(self, issue: str, structure: dict) -> BugLocation: ...
    async def _summarize_location(self, loc: BugLocation) -> str: ...   # redundant
    async def _write_patch(self, summary: str) -> Patch: ...

    # After: _locate_bug feeds _write_patch directly
    async def _locate_bug(self, issue: str, structure: dict) -> BugLocation: ...
    async def _write_patch(self, issue: str, bug_location: BugLocation) -> Patch: ...

    # Entrypoint updates to match
    async def solve(self, issue: str, repo: str) -> Patch:
        structure    = self.collect_repo_structure(repo)
        bug_location = await self._locate_bug(issue, structure)
        return await self._write_patch(issue, bug_location)
    ```

    ---

    ### Approach 4: Remove a Subagent

    **When**: A subagent adds latency and complexity without measurable accuracy gain. The parent could do the work inline without context overflow.

    **Optimization type**: `remove_subagent`

    **How**: Collapse the subagent's tools and behavior into the parent agent. Move the subagent's tool access and relevant prompt content into the parent. Remove the subagent if no other caller uses it.

    **Code example** — collapsing a trivial triage subagent back into the parent:

    ```python
    # Before: IssueTriager subagent just extracts keywords — doesn't need its own context
    class IssueTriager(Agent):
        async def triage(self, issue: str) -> dict:
            '''Extract key terms from issue.'''
            ...

    class SWEAgent(Agent):
        triager = IssueTriager()
        async def solve(self, issue: str, repo: str) -> Patch:
            keywords = await self.triager.triage(issue)
            return await self._write_patch(issue, keywords)

    # After: triage is a deterministic method on the parent — no subagent overhead
    class SWEAgent(Agent):
        def extract_keywords(self, issue: str) -> dict:
            '''Extract key terms from issue text.'''
            import re
            return {"terms": re.findall(r'`([^`]+)`', issue)}

        async def solve(self, issue: str, repo: str) -> Patch:
            keywords = self.extract_keywords(issue)
            return await self._write_patch(issue, keywords)
    ```

    **When to remove vs. keep**: If removing causes context overflow or inconsistent results, keep the subagent. Remove only when the task is simple enough for a single method + tool call.

    ---

    ## Success Criteria

    A good architecture fix:
    - Reduces "contradicts earlier conclusion" errors in traces
    - Each method/subagent has a **single clear responsibility** readable from its name alone
    - Intermediate outputs are **typed structs** — not free-form strings
    - Performance improves on tasks that previously showed inconsistent results
    - Does not add subagents/splits that increase latency without measurable accuracy gain
    """


class OptimizeReasoning(Skill):
    """Use when the agent retrieves the right data and has the right rules but draws the wrong conclusion — it conflates distinct concepts, skips implicit inference steps, or its chain of reasoning is plausible but logically flawed. Covers edit_method (steps/logic), add_method, remove_method, split_method, make_method_abstract.

    # Optimization Card: Reasoning

    ## When to Use

    Use this card when traces show the agent **has the right data and the right rules but reasons incorrectly**:

    - Agent found the right file but patched the wrong function within it
    - Agent conflated two distinct concepts (e.g. "test fails" = "bug is in the test" rather than in the code under test)
    - Agent skipped an implicit reasoning step that was never made explicit
    - Agent's chain of reasoning is plausible but logically flawed
    - A method does multiple things at once and loses track of one of them
    - The same reasoning error recurs across different issues with different inputs

    **Key diagnostic**: The trace shows correct data retrieval — the failure is in the inference step. More data won't help. Clearer step-by-step reasoning structure will.

    ## When NOT to Use

    - Agent skips steps it knows it should take → use `opt-execution`
    - Agent reasons correctly but from a wrong domain rule → use `opt-domain-knowledge`
    - The reasoning load is too high for one method → use `opt-architecture`

    ---

    ## Core Pattern

    Reasoning fixes restructure the **private stochastic method** (`_locate_bug`, `_write_patch`, etc.) — the method defined by its method prompt, implemented by the LLM at runtime. The orchestration entrypoint stays unchanged. The fix makes implicit reasoning steps explicit, breaks conflations into separate questions, or adds a new stochastic method for a missing phase.

    ---

    ## Approaches

    ### Approach 1: Make an Implicit Reasoning Step Explicit

    **When**: The agent conflates two concepts or skips an implicit inference. The fix is adding an explicit intermediate conclusion step to the stochastic method's prompt.

    **Optimization type**: `edit_method`

    **How**: Break the conflation by requiring the LLM to answer sub-questions explicitly and separately before drawing the final conclusion.

    **Code example** — fixing conflation of "test fails" with "bug is in the test file":

    ```python
    async def _locate_bug(self, issue: str, test_results: dict) -> BugLocation:
        '''Locate the source of the bug described in issue given test results.

        ## Root Cause Localization (answer each question separately)

        Before concluding where the bug is, answer these in sequence — do NOT merge them:

        Q1: Which test(s) are failing?
        → Check test_results["failed"]. Answer: list the failing test names.

        Q2: What is each failing test actually testing?
        → Read the test body. Identify the function or class under test.
          Answer: the production symbol being tested, NOT the test file.

        Q3: Is the failure caused by wrong test logic, or wrong production code?
        → Check if the test assertion matches the documented behavior in the issue.
          If the test expectation is correct and production code produces the wrong value:
          bug is in production code.
          If the test expectation is wrong: bug is in the test.

        Only conclude "bug is in test file" if Q3 shows the test expectation is wrong.
        Failing test → bug in test is the most common wrong inference — always check Q2 and Q3.
        '''
        ...
    ```

    ---

    ### Approach 2: Fix the method contract

    **When**: A method reasons correctly but hands downstream callers output they can't
    reliably consume — free-form text where a caller expects specific fields, or an
    untyped value that varies run to run. The symptom is a *contract* problem, not a
    reasoning problem: the method's logic may be fine; only its output shape is wrong.
    Reach for this instead of adding a soft "please include X" constraint to the prompt.

    **Optimization type**: `edit_method`

    **How**: Change the method's return type annotation to a typed struct and update its
    prompt to require that format. Then update the outgoing edge label in the architecture
    diagram to reflect the new contract. This is a **signature change**, not a prompt
    reasoning edit.

    **Code example** — fixing a method that returns raw text to return a typed result:

    ```python
    from pydantic import BaseModel

    class AnalysisResult(BaseModel):
        conclusion: str       # the primary finding
        confidence: str       # "high" | "medium" | "low"
        evidence: list[str]   # supporting observations

    class SWEAgent(Agent):

        async def _analyze(self, data: dict) -> AnalysisResult:
            '''Analyze the data and return a structured finding.

            Return an AnalysisResult with:
            - conclusion: the primary finding, one sentence
            - confidence: "high" if evidence is unambiguous, "low" if uncertain
            - evidence: list of supporting observations from the data

            Do NOT return raw text — structure the output into the fields above.
            '''
            ...
    ```

    **Architecture diagram update** — change the edge label to make the contract explicit:

    ```
    _analyze* -->|result: AnalysisResult| _write_patch*
    ```

    **When NOT to use**: If the method's reasoning logic is also wrong (wrong inference, conflated
    concepts), combine this with Approach 1 or 3 as needed. If the caller is the problem (can't
    handle structured input), fix the caller instead.

    ---

    ### Approach 3: Add a New Reasoning Method

    **When**: The agent is missing an entire reasoning phase — a distinct analytical concern that needs its own context and typed output, not just a step within an existing method.

    **Optimization type**: `add_method`

    **How**: Add a new private stochastic method that produces a structured intermediate output. The downstream method consumes that output instead of re-deriving it. Wire it into the public entrypoint's Python body.

    **Code example** — adding a dedicated reproduction phase before patch writing:

    ```python
    class SWEAgent(Agent):

        async def _reproduce(
            self, issue: str, repo_structure: dict, test_results: dict
        ) -> ReproductionResult:
            '''Determine whether the issue is reproduced by current test failures.

            Evaluate in three layers:
            1. Symptom match: do the failing tests match the behavior described in the issue?
            2. Scope: is the failure isolated to the area described, or is it broader?
            3. Confidence: is this a reliable reproduction or an unrelated pre-existing failure?

            Return a ReproductionResult with:
            - reproduced: True | False | "partial"
            - failing_tests: list of test names that reproduce the issue
            - confidence: "high" | "medium" | "low"
            - notes: any observations that affect patch strategy
            '''
            ...

        async def _write_patch(
            self, issue: str, reproduction: ReproductionResult
        ) -> Patch:
            '''Write a patch that resolves the issue.

            Do NOT re-run tests or re-reproduce — trust the reproduction result.
            Focus on fixing the production code identified in reproduction.failing_tests.
            '''
            ...

        async def solve(self, issue: str, repo: str) -> Patch:
            '''Solve the GitHub issue.'''
            structure    = self.collect_repo_structure(repo)
            test_results = self.run_test_suite(repo)
            reproduction = await self._reproduce(issue, structure, test_results)
            return await self._write_patch(issue, reproduction)
    ```

    ---

    ### Approach 4: Split a Method That Does Too Much

    **When**: A single stochastic method combines evidence interpretation + intermediate reasoning + final classification, causing the LLM to lose earlier conclusions by the final step.

    **Optimization type**: `split_method`

    **How**: Split at natural phase boundaries. Each phase receives only what it needs and produces a typed output. Wire the split into the public entrypoint's Python body.

    **Code example** — splitting `_solve()` into bug location + patch writing:

    ```python
    class SWEAgent(Agent):

        def collect_repo_structure(self, repo: str) -> dict: ...   # concrete

        async def _locate_bug(
            self, issue: str, repo_structure: dict, test_results: dict
        ) -> BugLocation:
            '''Locate the bug from the issue description and test results.

            Report all candidate locations including uncertain ones.
            Do NOT write a patch — only locate and return evidence.
            '''
            ...

        async def _write_patch(
            self, issue: str, bug_location: BugLocation
        ) -> Patch:
            '''Write a patch that fixes the located bug.

            Do NOT re-locate. Work only from bug_location.
            The patch must change the file and function identified in bug_location.
            '''
            ...

        async def solve(self, issue: str, repo: str) -> Patch:
            '''Solve the GitHub issue.'''
            structure    = self.collect_repo_structure(repo)
            test_results = self.run_test_suite(repo)
            bug_location = await self._locate_bug(issue, structure, test_results)
            return await self._write_patch(issue, bug_location)
    ```

    **When to split vs. edit**: If the method is short and the error is about conflation, prefer `edit_method`. Split when the trace shows early conclusions disappearing by the final step.

    ---

    ### Approach 5: Remove a Redundant Reasoning Method

    **When**: A stochastic method paraphrases the previous output without adding new reasoning, or a reasoning phase was added but traces show it always produces the same conclusion regardless of input.

    **Optimization type**: `remove_method`

    **How**: Remove the method and update the entrypoint to skip that phase. Pass the upstream output directly to the downstream consumer.

    **Code example** — removing a validation step that always rubber-stamps the previous output:

    ```python
    # Before: _validate_location just restates _locate_bug output without adding reasoning
    async def _locate_bug(self, issue: str, structure: dict) -> BugLocation: ...
    async def _validate_location(self, loc: BugLocation) -> BugLocation: ...  # always returns loc unchanged
    async def _write_patch(self, issue: str, loc: BugLocation) -> Patch: ...

    async def solve(self, issue: str, repo: str) -> Patch:
        structure = self.collect_repo_structure(repo)
        loc = await self._locate_bug(issue, structure)
        validated = await self._validate_location(loc)  # wasted step
        return await self._write_patch(issue, validated)

    # After: _locate_bug feeds _write_patch directly
    async def _locate_bug(self, issue: str, structure: dict) -> BugLocation: ...
    async def _write_patch(self, issue: str, loc: BugLocation) -> Patch: ...

    async def solve(self, issue: str, repo: str) -> Patch:
        structure = self.collect_repo_structure(repo)
        loc = await self._locate_bug(issue, structure)
        return await self._write_patch(issue, loc)
    ```

    **When to remove vs. keep**: If removing the method causes downstream errors because it was doing useful transformation (even subtle), keep it. Remove only when traces show the method's output is structurally identical to its input across multiple tasks.

    ---

    ### Approach 6: Convert a Concrete Method to an Stochastic Method

    **When**: A deterministic method uses brittle heuristics (regex, keyword matching, hardcoded thresholds) that fail on novel inputs. The task requires judgment, not pattern matching — but the current implementation is hardcoded Python.

    **Optimization type**: `make_method_abstract`

    **How**: Replace the concrete method with a stochastic method. Move the intent into a prompt with structured reasoning steps. The public entrypoint calls the new stochastic method where it previously called the concrete one.

    **Code example** — converting a regex-based classifier that misclassifies edge cases:

    ```python
    # Before: concrete method — brittle regex can't handle ambiguous issue descriptions
    class SWEAgent(Agent):

        def classify_issue(self, issue: str) -> str:
            '''Classify issue type by keyword matching.'''
            if "crash" in issue.lower() or "traceback" in issue.lower():
                return "crash"
            if "slow" in issue.lower() or "timeout" in issue.lower():
                return "performance"
            return "bug"

        async def solve(self, issue: str, repo: str) -> Patch:
            issue_type = self.classify_issue(issue)  # hardcoded
            return await self._write_patch(issue, issue_type)

    # After: LLM method — handles ambiguous and novel descriptions
    class SWEAgent(Agent):

        async def _classify_issue(self, issue: str) -> IssueClassification:
            '''Classify the issue into one of: crash, performance, regression, bug.

            Read the full issue text. Determine:
            1. Is there an explicit stack trace or "raises" keyword? → crash
            2. Does the issue describe degraded speed, timeouts, or resource exhaustion? → performance
            3. Does the issue say "used to work" or reference a prior version? → regression
            4. Otherwise → bug

            Return the classification and a one-sentence justification.
            '''
            ...

        async def solve(self, issue: str, repo: str) -> Patch:
            classification = await self._classify_issue(issue)  # LLM handles ambiguity
            return await self._write_patch(issue, classification)
    ```

    **When to convert vs. keep concrete**: If the operation is truly deterministic (parsing structured output, running a command, filtering by exact match), keep it concrete. Convert only when traces show the hardcoded logic fails on inputs that require judgment.

    ---

    ## Success Criteria

    A good reasoning fix:
    - Eliminates a **specific logical error** visible in the trace — not "improves reasoning generally"
    - The intermediate conclusion is explicitly formed and visible in the trace
    - The error does not reappear when the same logical scenario occurs with different inputs
    - Does not add steps that increase latency without measurable accuracy gain
    """


class OptimizeExecution(Skill):
    """Use when the agent knows what to do but skips or inconsistently performs a deterministic operation — the same prompt instruction has been added multiple rounds without fixing the failure, or a mechanical step works on train but fails on novel inputs. Covers add_concrete_method, remove_concrete_method, add_tool, remove_tool, edit_concrete_method, make_method_concrete.

    # Optimization Card: Execution

    ## When to Use

    Use this card when traces show the agent **knows what it should do but doesn't reliably do it**:

    - Agent was instructed to run an operation but skipped it on some inputs
    - A method was added to the architecture but the LLM never calls it
    - The same prompt instruction has been added multiple rounds without fixing the failure
    - Agent executes a deterministic operation inconsistently — correct on train, wrong on novel inputs
    - The operation is purely mechanical: parsing, querying, filtering, enumerating — no reasoning required

    **Key diagnostic**: If you have added an instruction "call X" or "run Y" and the agent still skips it on novel cases, adding it to the method prompt again will not work. The fix is enforcing the call in Python.

    ## When NOT to Use

    - Agent runs the operation but interprets results incorrectly → use `opt-reasoning`
    - Agent lacks the domain rule to know *what* to check → use `opt-domain-knowledge`
    - The operation requires reasoning to decide whether to run → use `opt-reasoning` or `opt-architecture`

    ---

    ## Core Pattern

    The public method is **programmatic** (has a Python body). It calls deterministic sub-methods unconditionally, then delegates reasoning to a **private stochastic method** (`_locate_and_fix`, `_classify`, etc.) that receives the pre-fetched data.

    ```python
    class SWEAgent(Agent):

        # Deterministic sub-method — always runs, LLM cannot skip
        async def collect_repo_structure(self, repo: str) -> dict:
            '''Deterministically collect file tree and test suite locations.'''
            files = await self.shell.run(f"find {repo} -name '*.py' | head -200")
            tests = await self.shell.run(f"find {repo} -name 'test_*.py' -o -name '*_test.py'")
            return {"files": files.splitlines(), "tests": tests.splitlines()}

        # Private LLM method — implements reasoning, receives pre-fetched data
        async def _locate_and_fix(self, issue: str, repo_structure: dict) -> Patch:
            '''Locate the bug described in issue and write a patch.

            repo_structure contains: files (list of .py paths), tests (list of test paths).
            Use these fields directly — do not re-scan the repo.
            '''
            ...

        # Public entrypoint — programmatic, enforces sub-calls in Python body
        async def solve(self, issue: str, repo: str) -> Patch:
            '''Solve the GitHub issue by locating and patching the bug.'''
            structure = await self.collect_repo_structure(repo)  # enforced in Python
            return await self._locate_and_fix(issue, structure)
    ```

    **Why this works**: `solve()` has a Python body — the LLM doesn't decide whether to call sub-steps. `collect_repo_structure()` always runs. The LLM only implements `_locate_and_fix()`, which receives the data it needs.

    ---

    ## Approaches

    ### Approach 1: Add a Concrete Sub-Method

    **When**: A deterministic operation is currently described in a method prompt but the LLM skips it. Extract it as a deterministic method and call it from the public method's Python body.

    **Optimization type**: `add_concrete_method`

    **Steps**:
    1. Implement the operation as a deterministic `def` method
    2. Make the public method programmatic (give it a Python body)
    3. Call the sub-method from that body
    4. Pass the result to a new private LLM `_<method>()` for reasoning

    **Code example** — adding test output parsing that the LLM kept skipping despite method prompt instructions:

    ```python
    class SWEAgent(Agent):

        async def run_test_suite(self, repo: str, test_file: str) -> dict:
            '''Run the specified test file and return structured output.'''
            raw = await self.shell.run(f"cd {repo} && python -m pytest {test_file} -v 2>&1")
            passed, failed = [], []
            for line in raw.splitlines():
                if " PASSED" in line:
                    passed.append(line.strip())
                elif " FAILED" in line or " ERROR" in line:
                    failed.append(line.strip())
            return {"passed": passed, "failed": failed, "raw": raw}

        async def _verify_patch(self, patch: Patch, test_results: dict) -> VerificationResult:
            '''Assess whether the patch fixes the issue given pre-run test results.

            test_results: {"passed": [...], "failed": [...], "raw": str}
            Use these directly — do not re-run tests.
            '''
            ...

        async def verify(self, repo: str, patch: Patch, test_file: str) -> VerificationResult:
            '''Verify that patch fixes the issue.'''
            test_results = await self.run_test_suite(repo, test_file)  # enforced in Python
            return await self._verify_patch(patch, test_results)
    ```

    ---

    ### Approach 2: Add a Tool and Call It Unconditionally

    **When**: The agent needs an external capability it lacks. Wire the tool call into the public method's Python body so it always runs.

    **Optimization type**: `add_tool`

    **Code example** — adding a code search tool that the agent was approximating by reading files manually:

    ```python
    class CodeSearchTool:
        '''Search for a symbol or pattern across all Python files in a repo.'''
        def __call__(self, repo: str, pattern: str) -> list[dict]:
            import subprocess, json
            result = subprocess.run(
                ["grep", "-rn", "--include=*.py", "-l", pattern, repo],
                capture_output=True, text=True
            )
            return [{"file": f} for f in result.stdout.splitlines() if f]


    class SWEAgent(Agent):
        search = CodeSearchTool()

        async def _write_patch(self, issue: str, symbol_locations: list[dict]) -> Patch:
            '''Write a patch for the issue given pre-located symbol sites.

            symbol_locations: list of {"file": str} dicts.
            Read only these files — do not search again.
            '''
            ...

        async def solve(self, issue: str, repo: str, symbol: str) -> Patch:
            '''Solve the issue by finding and patching the relevant symbol.'''
            locations = self.search(repo, symbol)   # always runs
            return await self._write_patch(issue, locations)
    ```

    ---

    ### Approach 3: Fix a Broken Concrete Method

    **When**: A deterministic method exists and is already called from the Python body, but has wrong logic or silent failures.

    **Optimization type**: `edit_concrete_method`

    **Code example** — fix a test parser that silently drops failures reported on multi-line output:

    ```python
    # Before — misses FAILED lines that follow a traceback (not immediately after test name)
    def parse_test_output(self, raw: str) -> dict:
        failed = [l for l in raw.splitlines() if "FAILED" in l and "::" in l]
        return {"failed": failed}

    # After — collects all FAILED markers regardless of surrounding context
    def parse_test_output(self, raw: str) -> dict:
        failed = []
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("FAILED") or ("FAILED" in line and "::" in line):
                failed.append(line)
        return {"failed": failed}
    ```

    ---

    ### Approach 4: Remove an Unused Deterministic Method

    **When**: A deterministic helper is never called in traces, or its logic is now handled elsewhere (by another method or tool).

    **Optimization type**: `remove_concrete_method`

    **How**: Remove the method definition and any calls to it in the entrypoint's Python body. Verify traces still show correct behavior without it.

    **Code example** — removing a helper that was superseded by a tool:

    ```python
    # Before: manual file counting helper, but CodeSearchTool now handles this
    def count_python_files(self, repo: str) -> int:
        '''Count .py files in repo.'''
        return len(glob.glob(f"{repo}/**/*.py", recursive=True))

    # After: remove the helper, use self.search directly in the entrypoint
    ```

    ---

    ### Approach 5: Remove an Unused Tool

    **When**: A tool attribute is never invoked in traces, or the agent consistently calls it but ignores the result, or it returns misleading output that confuses the LLM.

    **Optimization type**: `remove_tool`

    **How**: Remove the tool attribute and any references in method prompts or Python bodies. If a method's Python body called the tool unconditionally, update that body to skip the call.

    **Code example** — removing a linter tool that the agent never uses productively:

    ```python
    # Before: linter tool added in round 2, but traces show agent ignores lint output
    class SWEAgent(Agent):
        linter = LintTool()  # never produces actionable signal

        async def solve(self, issue: str, repo: str) -> Patch:
            lint_output = self.linter(repo)  # wasted call
            return await self._write_patch(issue, lint_output)

    # After: remove the tool, pass what the agent actually needs
    class SWEAgent(Agent):
        async def solve(self, issue: str, repo: str) -> Patch:
            structure = self.collect_repo_structure(repo)
            return await self._write_patch(issue, structure)
    ```

    ---

    ### Approach 6: Convert an Stochastic Method to a Concrete Method

    **When**: A stochastic method performs a purely deterministic operation — parsing, filtering, formatting, string extraction — where the output is fully determined by the input with no judgment needed. The LLM wastes tokens and introduces inconsistency on what should be a mechanical step.

    **Optimization type**: `make_method_concrete`

    **How**: Replace the `async def` stochastic method with a concrete `def` that implements the same logic in Python. Call it from the public entrypoint's Python body so it always runs identically.

    **Code example** — converting a stochastic method that extracts test names from pytest output into a deterministic parser:

    ```python
    # Before: LLM method — wastes tokens parsing structured output, sometimes misses entries
    class SWEAgent(Agent):

        async def _extract_failing_tests(self, raw_output: str) -> list[str]:
            '''Extract the names of failing tests from pytest output.

            Look for lines containing FAILED and extract the test name after '::'.
            Return a list of fully qualified test names.
            '''
            ...

        async def solve(self, issue: str, repo: str) -> Patch:
            raw = await self.shell.run(f"cd {repo} && python -m pytest -v 2>&1")
            failing = await self._extract_failing_tests(raw)  # LLM parses structured text
            return await self._write_patch(issue, failing)

    # After: concrete method — deterministic, zero tokens, never misses a line
    class SWEAgent(Agent):

        def extract_failing_tests(self, raw_output: str) -> list[str]:
            '''Parse failing test names from pytest -v output.'''
            failing = []
            for line in raw_output.splitlines():
                line = line.strip()
                if "FAILED" in line and "::" in line:
                    # Extract "path/test_file.py::test_name" before the FAILED marker
                    parts = line.split(" ")
                    for part in parts:
                        if "::" in part:
                            failing.append(part)
                            break
            return failing

        async def solve(self, issue: str, repo: str) -> Patch:
            raw = await self.shell.run(f"cd {repo} && python -m pytest -v 2>&1")
            failing = self.extract_failing_tests(raw)  # deterministic, enforced in Python
            return await self._write_patch(issue, failing)
    ```

    **When to convert vs. keep as stochastic**: If the output depends on understanding natural language, ambiguous input, or requires judgment — keep it as a stochastic method. Convert only when the transformation is mechanical and fully specifiable in code.

    ---

    ## Success Criteria

    A good execution fix:
    - The public method has a **Python body** that calls deterministic sub-methods before delegating to `_<method>()`
    - Deterministic operations run **unconditionally** — the LLM receives results as arguments, not instructions
    - The trace shows every deterministic method firing on every task, including ones previously skipped
    - If the LLM still skips an operation after the fix, the fix is still prompt-based — move the call into Python
    """


class OptimizeDomainKnowledge(Skill):
    """Use when the agent applies the wrong domain rule, misclassifies because of a missing taxonomy entry, or reasons coherently from a wrong premise — the reasoning chain is logical but starts from incorrect knowledge. Covers edit_skill, add_skill, remove_skill, edit_method (rules section).

    # Optimization Card: Domain Knowledge

    ## When to Use

    Use this card when traces show the agent **has the right information but applies the wrong rule**:

    - Agent correctly locates the bug but patches the wrong layer (e.g. patches the caller instead of the implementation)
    - Agent applies a rule meant for a different issue type
    - Agent lacks a taxonomy entry for the specific failure mode
    - The same misclassification pattern appears across multiple issues with different inputs
    - Agent's reasoning is internally consistent but starts from a wrong premise

    **Key diagnostic**: The reasoning chain is coherent, but it starts from a wrong or missing rule. More execution steps won't help — the agent needs the right knowledge.

    ## When NOT to Use

    - Agent has the right rule but doesn't consistently apply it → use `opt-execution`
    - Agent's reasoning process is flawed (correct rules, wrong logic) → use `opt-reasoning`
    - The knowledge gap requires a new reasoning phase → use `opt-architecture`

    ---

    ## Core Pattern

    Domain knowledge fixes go into the **skill module** (shared, versioned, independent of method structure) or into the method's prompt as a rules section. They do not change the Python execution flow — that's `opt-execution`.

    **Do NOT embed dataset-specific cases into the skill.** Skills must encode generalizable rules (decision tables, classification taxonomies, process steps) — never facts about specific inputs, libraries, or CVEs from the training data. That is memorization, not domain knowledge.
    ---

    ## Approaches

    ### Approach 1: Edit the Skill File

    **When**: The gap is in the shared domain skill — a wrong classification rule, missing taxonomy entry, or incomplete decision table. Fixing it propagates to all methods that load the skill.

    **Optimization type**: `edit_skill`

    **How**: Open the agent's skill module and add or correct the rule. Be specific — vague rules get ignored. Include concrete examples with correct outcomes. Consult the framework skill to find the correct skill location and format for the target framework.

    **Code example** — adding a missing patch location rule that caused systematic wrong-layer fixes:

    ```markdown
    ## Patch Location Policy (MANDATORY)

    When the bug is in a utility called by multiple callers, patch the utility — not the callers:

    | Bug location | Wrong fix | Correct fix |
    |---|---|---|
    | `utils/parser.py` raises ValueError | Add try/except in every caller | Fix the parser to not raise |
    | `db/connection.py` leaks connections | Close connection at each call site | Fix connection lifecycle in `db/connection.py` |
    | `auth/token.py` returns wrong expiry | Adjust expiry at each consumer | Fix expiry logic in `auth/token.py` |

    Patching callers instead of the source is a **layering violation** — it leaves the bug in place and masks it.
    ```

    **Code example** — adding a missing issue type for flaky tests:

    ```markdown
    ## Issue Classification

    Issues fall into one of four types. Classification determines where to look for the bug:

    | Type | Signal in issue text | Where to look |
    |---|---|---|
    | `regression` | "used to work", "worked in v<X>" | git log for the breaking commit |
    | `flaky_test` | "fails intermittently", "CI sometimes" | test isolation, shared state, timing |
    | `wrong_output` | "returns X but should return Y" | logic in the computation path |
    | `crash` | "raises", "exception", "traceback" | the stack trace entry points |

    Do not apply `wrong_output` debugging strategy to `flaky_test` issues — they require different tools.
    ```

    ---

    ### Approach 2: Add a New Skill File

    **When**: The agent lacks an entire knowledge domain that needs its own versioned skill — too large or orthogonal for a section in an existing skill.

    **Optimization type**: `add_skill`

    **How**: Create a new skill module with a focused scope, then wire it into the agent using the framework's skill attachment mechanism.

    **Example skill content** (framework-neutral markdown):

    ```markdown
    # Test Framework Identification

    Repos use different test runners. Running with the wrong command silently passes when tests aren't discovered.

    ## Detection

    1. Check `pyproject.toml` or `setup.cfg` for `[tool.pytest]`, `[tool.unittest]`, or `testpaths`
    2. Check for `pytest.ini` or `tox.ini`
    3. Presence of `conftest.py` → pytest
    4. Presence of `unittest.TestCase` subclasses with no pytest config → unittest
    ```

    **Wiring the skill** — the mechanism depends on the framework. Read the framework skill before wiring to find the correct attachment pattern.

    **Example** (consult the framework skill for the correct location and API):
    ```python
    self.test_framework = TextSkill(path="skills/test-framework")
    ```

    ---

    ### Approach 3: Add a Rules Section to the Method Docstring

    **When**: The knowledge gap is specific to one method's decision logic and is too narrow for the shared skill. The rule is about how *this method* should interpret its inputs.

    **Optimization type**: `edit_method`

    **How**: Add a named "Rules" or "Policy" section to the method's prompt. Keep it targeted — if the rule applies broadly, use `edit_skill` instead.

    **Code example** — adding a test-only change policy to the patch classification method:

    ```python
    async def _classify_patch(self, patch: Patch, issue: str) -> PatchResult:
        '''Classify whether the patch correctly addresses the issue.

        ## Test-Only Change Policy
        A patch that only modifies test files (paths matching `test_*.py`, `*_test.py`,
        or files under `tests/`) does NOT fix the underlying bug.
        Classify as `incomplete` if no production source file was changed.

        Apply this rule when:
        - All changed files are under test directories
        - No module outside `tests/` was modified

        Do NOT apply when the issue explicitly asks to add a missing test — in that case,
        a test-only patch is correct.
        '''
        ...
    ```

    ---

    ### Approach 4: Remove a Confusing Skill

    **When**: A skill file contradicts method prompts, introduces rules the agent misapplies, or adds noise that dilutes more important rules. Traces show the agent citing skill rules incorrectly or applying them to wrong contexts.

    **Optimization type**: `remove_skill`

    **How**: Detach the skill from the agent and un-wire it from the agent. If some rules are still needed, migrate them into the relevant method prompt where they'll have narrower scope before detaching.

    **Example** — the diagnostic and the detachment:

    ```
    # The skill says: "Always classify network-reachable code as HIGH severity"
    # But the method prompt says: "Classify based on actual exploit path,
    # not reachability alone" — the agent oscillates between the two rules.
    # Fix: keep the method-level rule (more nuanced) and detach the skill.
    ```

    Remove the skill attachment from the agent's initialisation (the exact API depends on the framework — consult the framework skill) and delete or move the skill file so it cannot be re-loaded through a future scan or import.

    **Example** — removing a skill attachment (consult the framework skill for the correct API and file location):
    ```python
    # Remove the skill attribute from __init__ and delete the skill files
    # self.confusing_skill = TextSkill(path="skills/confusing-skill")  ← delete this line
    ```

    **When to remove vs. edit**: If the skill has a mix of correct and incorrect rules, prefer `edit_skill` to fix the bad rules. Remove only when the entire skill is a net negative — confusing more than helping.

    ---

    ## Success Criteria

    A good domain knowledge fix:
    - Adds a **concrete, verifiable rule** — not a vague instruction like "be more careful"
    - Includes an example of correct vs. incorrect application
    - The failure pattern does not reappear on held-out tasks after the fix
    - Does not contradict existing rules in the skill — check for conflicts before adding
    - For `add_skill` / `remove_skill`: the attachment step actually ran. After the change, the skill is reachable by the agent at runtime (loaded, injected, or otherwise accessible) — a skill file on disk that nothing loads or imports is not a fix.
    """


class OptimizeModelCapability(Skill):
    """Use when prompt, code, and architecture improvements have plateaued, or the agent has correct instructions and architecture but is unable to follow them — the current model is too weak for complex tasks, too expensive for simple steps, or config limits (iterations, timeouts) cut the agent off mid-task. Covers edit_llm, add_llm, remove_llm, edit_config.

    # Optimization Card: Tuning

    ## When to Use

    Use this card **only after prompt, code, and architecture improvements have plateaued**:

    - Agent has correct prompts and architecture but fails on complex reasoning that a stronger model would handle
    - Agent has correct instructions and architecture but is unable to follow them reliably
    - Agent uses an expensive model for a simple filtering step where a cheaper model would suffice
    - Agent hits iteration limits or timeouts — traces show it was cut off mid-task
    - Multiple LLMs exist but one is unused or consistently inferior

    **Key diagnostic**: The trace shows correct architecture, prompts, and instructions. The agent understands what it should do but cannot follow through reliably; the failure is about model capability (too weak for the task) or execution limits (ran out of time/iterations).

    ## When NOT to Use

    - Agent has wrong reasoning logic → use `opt-reasoning`
    - Agent skips operations → use `opt-execution`
    - Agent lacks domain rules → use `opt-domain-knowledge`
    - Agent's structure is the bottleneck → use `opt-architecture`

    ---

    ## Approaches

    ### Approach 1: Swap the Model on an Existing LLM

    **When**: The agent's current model is too weak for complex reasoning tasks, or too expensive for simple tasks. Try ONLY after prompt/code improvements plateau.

    **Optimization type**: `edit_llm`

    **How**: Change the model identifier on an existing LLM attribute. Always use models from the curated model catalog — never invent model IDs. Test on the same tasks to verify the swap helps.

    #### Available Models

    Use the `model_id` field with `get_llm_client()`.
    Candidate agents should use only model IDs listed in `assets/models.yaml`;
    do not invent provider/model IDs outside that catalog.

    To inspect the catalog from the optimizer Coder, run:

    ```python
    catalog = self.optimize.optimize_model_capability.read_model_catalog()
    models = catalog.models
    ```

    The YAML contains one entry per underlying model with `model_id`, `provider`,
    `range`, and `notes`. The catalog defines `default_endpoint` and
    `default_api_key_env`; model entries may define `endpoint` and `api_key_env`
    overrides, and if they omit either field, use the corresponding catalog
    default. Duplicate provider route aliases are intentionally omitted so tuning
    choices are not split across equivalent IDs. If editing an LLM model id, also
    call `available_model_ids = await self.list_available_models()` first and
    choose a catalog model that is currently available.

    > **Tip**: The full live catalog can be queried at runtime — `requests.get("https://inference-api.nvidia.com/v1/models", headers={"Authorization": f"Bearer {key}"})`. `assets/models.yaml` is a curated subset.

    **Code example** — upgrading from a fast model to a stronger one for classification:

    ```python
    from nooa.unifiedllm import get_llm_client

    class SWEAgent(Agent):
        # Before — a small model struggles with nuanced classification
        classifier_llm = get_llm_client("azure/openai/gpt-5-mini")

        # After — a stronger open-weight model handles the edge cases
        classifier_llm = get_llm_client("azure/openai/gpt-5.5")
    ```

    **When NOT to swap**: If the agent fails on simple, unambiguous tasks — the model isn't the problem. If accuracy is already high on train but low on validation — the model is fine, the prompt is overfitting.

    ---

    ### Approach 2: Add a Second LLM

    **When**: A sub-task needs a different model — either because it needs stronger reasoning, or because a cheaper/faster model suffices and the expensive one is wasted. This can be done **per-method** (same agent, different LLM for one method) or **via a subagent** (separate context).

    **Optimization type**: `add_llm`

    #### Option A: Per-Method LLM Override

    **When**: The method shares the parent agent's context but needs a different model. No context isolation needed.

    **How**: Assign a dedicated LLM to a specific method using the `llm=` parameter on the method decorator or attribute.

    **Code example** — a cheap model for a simple filtering method, strong model for everything else:

    ```python
    from nooa.unifiedllm import get_llm_client

    fast_llm = get_llm_client("azure/openai/gpt-5-mini")

    class SWEAgent(Agent):
        '''Main agent uses the default strong model. _quick_filter uses a fast model.'''

        async def _quick_filter(self, candidates: list[dict], llm=fast_llm) -> list[dict]:
            '''Discard obviously irrelevant candidates. Speed matters more than depth.'''
            ...

        async def _deep_classify(self, candidate: dict) -> dict:
            '''Deep classification — uses the agent's default (strong) model.'''
            ...

        async def run(self, candidates: list[dict]) -> list[dict]:
            filtered = await self._quick_filter(candidates)
            return [await self._deep_classify(c) for c in filtered]
    ```

    #### Option B: Dedicated Subagent

    **When**: The sub-task needs both a different model AND its own context — the subagent sees only what you pass it, not the parent's full history.

    **How**: Create a separate agent class with its own LLM. The parent delegates to it.

    **Code example** — a fast filter subagent with separate context, strong main agent for final classification:

    ```python
    from nooa.unifiedllm import get_llm_client

    fast_llm = get_llm_client("azure/openai/gpt-5-mini")

    class FilterAgent(Agent, llm=fast_llm):
        '''Quick pre-filter for candidates. Sees only the candidate batch, not the full analysis context.'''

        async def filter(self, candidates: list[dict]) -> list[dict]:
            '''Discard obviously irrelevant candidates. Speed matters more than depth.'''
            ...

    class SWEAgent(Agent):
        '''Main agent — strong model for deep classification.'''

        def __init__(self):
            super().__init__()
            self.filter_agent = FilterAgent()

        async def run(self, candidates: list[dict]) -> list[dict]:
            filtered = await self.filter_agent.filter(candidates)
            return [await self._classify(c) for c in filtered]

        async def _classify(self, candidate: dict) -> dict:
            '''Deep classification of a single candidate.'''
            ...
    ```

    **When to use per-method vs. subagent**: Per-method is simpler — use it when the method just needs a different model. Use a subagent when you also need context isolation (the sub-task shouldn't see the parent's full conversation).

    ---

    ### Approach 3: Remove a Redundant LLM

    **When**: Multiple LLMs exist but one is unused, or two methods share the same model and there's no reason to keep them separate.

    **Optimization type**: `remove_llm`

    **How**: Consolidate to a single LLM. Remove the extra attribute and update any methods that referenced it.

    **Code example** — consolidating after a filtering step was removed:

    ```python
    from nooa.unifiedllm import get_llm_client

    # Before: filter_llm was added for _filter_candidates, but that method was merged into _classify
    class SWEAgent(Agent):
        filter_llm = get_llm_client("azure/openai/gpt-5-mini")  # orphaned — no method uses it

    # After: remove the unused LLM
    class SWEAgent(Agent):
        # Only the agent-level default LLM remains
        ...
    ```

    **When to remove**: If traces show both LLMs produce equivalent results, or the cheaper model was added for a step that was later merged or removed.

    ---

    ### Approach 4: Tune Config Attributes

    **When**: The agent hits execution limits — traces show it was cut off mid-task, or it completes but with too few iterations to reason properly.

    **Optimization type**: `edit_config`

    **How**: Adjust `max_iterations`, timeouts, or similar execution bounds. Only when traces confirm the agent is cut off mid-task, not when it's reasoning poorly within the allotted steps.

    **Code example** — increasing iteration limit because traces show the agent running out mid-analysis:

    ```python
    class SWEAgent(Agent):
        # Before — agent consistently hits 30-iteration cap during complex tasks
        config = {"max_iterations": 30}

        # After — enough headroom for multi-step analysis
        config = {"max_iterations": 60}
    ```

    **Warning signs this is the WRONG fix**:
    - Agent completes well within the limit but produces wrong output → reasoning/knowledge problem
    - Agent uses many iterations but most are wasted on retries → fix the retry logic instead
    - Increasing the limit doesn't change the outcome → the limit wasn't the bottleneck

    ---

    ## Success Criteria

    A good tuning fix:
    - Only applied AFTER prompt/code/architecture improvements plateau
    - Model swap produces measurable accuracy gain on previously-failing tasks
    - Config change allows the agent to complete tasks it was previously cut off on
    - Does not increase cost/latency without measurable accuracy benefit
    - Cheaper model substitutions maintain accuracy while reducing cost
    """

    def __init__(self, model_catalog_path: Path | None = None, **kwargs: Any):
        """Initialize the card with an optional model catalog override."""
        super().__init__(**kwargs)
        self._model_catalog_path = model_catalog_path

    def read_model_catalog(self) -> ModelCatalog:
        """Return the validated model catalog from ``assets/models.yaml``.

        Returns:
            ModelCatalog: the parsed and validated catalog of available models.

        Raises:
            FileNotFoundError: if ``assets/models.yaml`` does not exist.
            ValidationError: if the YAML does not conform to the ModelCatalog schema.

        """
        if self._model_catalog_path is not None:
            raw_catalog = self._model_catalog_path.read_text()
        else:
            catalog_ref = resources.files("nemo_experimentalist_plugin").joinpath("assets/models.yaml")
            try:
                raw_catalog = catalog_ref.read_text()
            except FileNotFoundError:
                catalog_path = Path(__file__).resolve().parents[2] / "assets" / "models.yaml"
                raw_catalog = catalog_path.read_text()
        return ModelCatalog.model_validate(yaml.safe_load(raw_catalog))


class Fix(Skill):
    """Use when the agent crashes or produces degraded output due to a mechanical defect — truncation errors, wrong config limits, missing imports, broken paths, or unhandled exceptions. Not a reasoning or strategy problem; the code itself is broken. Covers edit_config, edit_concrete_method.

    # Optimization Card: Fix

    ## When to Use

    The agent crashes or produces degraded output due to a **mechanical defect** — not
    a reasoning or strategy problem. The code is broken in a way any developer would fix
    on sight:

    - Truncation or size limit exceeded (prompt too large for configured limit)
    - Wrong config parameters on a method or class (limits, timeouts, retries)
    - Missing or incorrect decorator parameters
    - `sys.exit()` on a recoverable error instead of graceful degradation
    - Output written to wrong path or wrong format
    - Missing error handling around external service calls
    - Import errors, typos in method names, wrong variable references

    **Key diagnostic**: The trace shows an exception, an error message, or
    output that is structurally wrong (wrong path, wrong schema). The agent's reasoning
    logic is irrelevant — the code itself is broken.

    ## When NOT to Use

    - Agent reasons incorrectly → use `opt-reasoning`
    - Agent skips operations → use `opt-execution`
    - Agent lacks domain rules → use `opt-domain-knowledge`
    - Agent's structure is the bottleneck → use `opt-architecture`
    - Model too weak for the task → use `opt-model-capability`

    ---

    ## Approaches

    ### Approach 1: Fix Config Limits

    **When**: Agent crashes with truncation or size limit errors. The input is within
    the model's context window but exceeds a framework-imposed config limit.

    **Optimization type**: `edit_config`

    **How**: Raise the relevant limit on the class or method. Read the error message —
    it tells you the parameter name and current value. Common limits:
    - Per-block character limit (truncates input before the LLM sees it)
    - Per-parameter character limit (rejects large method arguments)
    - Iteration limits (cuts off the agent mid-task)
    - Timeout limits

    **When NOT to fix config**: If the input is genuinely too large for the model's context
    window — truncate or summarize the data instead of raising the limit.

    ---

    ### Approach 2: Fix Error Handling

    **When**: Agent calls `sys.exit()`, raises unhandled exceptions, or silently drops
    data on recoverable errors.

    **Optimization type**: `edit_concrete_method`

    **Code example** — replacing fatal exit with graceful fallback:

    ```python
    # Before — crashes when scraping fails
    if not sources:
        sys.exit(1)

    # After — falls back to search snippets
    if not scraped_sources:
        sources = [{"content": r["snippet"], ...} for r in search_results if r.get("snippet")]
    ```

    ---

    ### Approach 3: Fix Output Path/Schema

    **When**: Agent writes output to the wrong location or in the wrong format.
    The verifier expects a specific path and schema.

    **Optimization type**: `edit_concrete_method`

    **How**: Inspect the dataset file list and verifier files to find the
    expected path, schema, service state, or side effect, then fix the agent's
    output/finalization code to match.

    ---

    ## Success Criteria

    A good fix:
    - Eliminates the crash or error — the agent completes the task
    - Is mechanical — doesn't change reasoning strategy
    - Addresses the root cause, not a symptom (e.g., raise the limit vs. suppress the error)
    - Can be verified by re-running the same task that triggered the failure
    """


class Optimize(Skill):
    """Top-level optimization skill — progressive disclosure index. Start here when proposing improvements. Routes to the specific optimization card based on the root cause diagnosis.

    # Optimization Skill Index

    ## Core concepts

    An agent is a graph of components. Each component is a lever — identifying which one is the
    bottleneck determines which optimization to apply:

    | Component | What it is | What can go wrong | Cards that target it |
    | --------- | ---------- | ----------------- | -------------------- |
    | **Method prompt** | The instruction that shapes what a stochastic method does | Wrong reasoning, missing rules, conflated responsibilities | `optimize_reasoning`, `optimize_domain_knowledge` |
    | **Method** | A deterministic callable at agent disposal | Agent skips it, brittle heuristics fail | `optimize_execution`, `fix` |
    | **Stochastic method** | A callable implemented by the LLM at runtime | Wrong conclusion, lost context, mixed concerns | `optimize_reasoning`, `optimize_domain_knowledge` |
    | **Subagent** | Another agent the component delegates work to | Unnecessary latency, context overflow, wrong decomposition | `optimize_architecture` |
    | **Model config** | Which LLM and with what parameters | Model too weak/expensive, context or rate limits hit | `optimize_capability`, `fix` |
    | **Skills** | Domain knowledge and methods the agent can draw on | Missing rules, outdated knowledge, wrong scope | `optimize_domain_knowledge` |

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
            '''Summarize the search hits into a concise paragraph.''' # method prompt
            ...

        async def run(self, question: str) -> str:            # stochastic method (LLM)
            '''Answer the question by searching and summarizing.''' # method prompt
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

    When proposing an improvement, **diagnose the root cause first**, then load the matching card.

    ## Decision Tree

    Each numbered entry names a card available as an attribute on this skill —
    load the card for the detailed approach.

    0. **Does the agent crash?**
       → Card `fix` — fix the mechanical defect: raise a config limit, fix a path, add error handling.
       Covers: `edit_config`, `edit_concrete_method`

    1. **Does the agent skip or inconsistently perform a deterministic operation?**
       → Card `optimize_execution` — move the call into Python so the LLM can't skip it.
       Covers: `add_concrete_method`, `remove_concrete_method`, `add_tool`, `remove_tool`, `edit_concrete_method`, `make_method_concrete`

    2. **Does the agent have the right data but draw the wrong conclusion, conflate concepts, or produce unstructured output that callers cannot parse?**
       → Card `optimize_reasoning` — make implicit reasoning steps explicit, fix untyped output contracts, split overloaded methods, convert brittle concrete logic to LLM reasoning.
       Covers: `edit_method` (steps/logic, output signature), `add_method`, `remove_method`, `split_method`, `make_method_abstract`

    3. **Does the agent reason correctly but from a wrong or missing domain rule?**
       → Card `optimize_domain_knowledge` — fix the skill module or add domain rules to the method's prompt.
       Covers: `edit_skill`, `add_skill`, `remove_skill`, `edit_method` (rules section)

    4. **Is the agent's structure the bottleneck — context overflow, separable concerns in one method?**
       → Card `optimize_architecture` — restructure methods, add/remove subagents, merge redundant steps.
       Covers: `add_subagent`, `remove_subagent`, `split_method`, `merge_method`

    5. **Has tuning plateaued — is the model too weak, too expensive, or are config limits too restrictive?**
       → Card `optimize_model_capability` — swap models, add/remove LLMs, adjust config limits.
       Covers: `edit_llm`, `add_llm`, `remove_llm`, `edit_config`

    ## Quick Reference

    | Symptom | Card | Key Diagnostic |
    |---------|------|----------------|
    | Crash, truncation error, framework limit | `fix` | Exception or error message in trace, agent never completes |
    | Skips operations despite instructions | `optimize_execution` | Same instruction added multiple rounds without effect |
    | LLM does purely mechanical work (parsing, filtering) | `optimize_execution` | Method output is fully determined by input, no judgment needed |
    | Right data, wrong conclusion | `optimize_reasoning` | Trace shows correct retrieval, flawed inference |
    | Untyped method output, callers can't parse | `optimize_reasoning` | Method returns `str`; downstream nodes receive inconsistent blobs |
    | Hardcoded logic fails on novel inputs | `optimize_reasoning` | Concrete method uses brittle heuristics that need judgment |
    | Coherent reasoning from wrong premise | `optimize_domain_knowledge` | Reasoning chain is logical but starts from wrong rule |
    | Inconsistent errors across same inputs | `optimize_architecture` | Context/structure problem, not knowledge |
    | Correct prompts but model too weak, too expensive, or limits hit | `optimize_model_capability` | Prompt/code/architecture improvements plateaued; traces show capability or config limit gap |

    ## Usage

    Pick the matching card from the decision tree above, then read the card
    via `doc(card)` for detailed approaches, code examples, and success criteria.
    """

    def __init__(self, model_catalog_path: Path | None = None, **kwargs: Any):
        """Initialize the Optimize skill and register all sub-skill cards."""
        super().__init__(**kwargs)
        self.fix = Fix()
        self.optimize_architecture = OptimizeArchitecture()
        self.optimize_reasoning = OptimizeReasoning()
        self.optimize_execution = OptimizeExecution()
        self.optimize_domain_knowledge = OptimizeDomainKnowledge()
        self.optimize_model_capability = OptimizeModelCapability(model_catalog_path=model_catalog_path)
