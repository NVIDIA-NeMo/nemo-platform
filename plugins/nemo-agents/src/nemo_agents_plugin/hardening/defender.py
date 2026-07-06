# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Behavioral defender: turn behavioral findings into guardrail check instructions.

Ported from iron-swarm's guardrails_defender suggestor/grader loop. Two changes
from the prototype: inference is injected (the loop supplies the platform
gateway) rather than hardcoded to a fixed model/URL, and the output is a rail
block instruction (fed into a self-check input rail, see plan OQ1) rather than a
NAT pre_tool_verifier middleware block, so there is no tool-targeting.
"""
from __future__ import annotations

import re
from typing import Callable

from nemo_agents_plugin.hardening.models import BehavioralFinding, GuardrailRemediation

Complete = Callable[[str, str], str]

SUGGESTOR_SYS_PROMPT = """
# Role
You are an expert AI Security Engineer specializing in generating LLM-based input guardrails.

# Objective
Your task is to generate one clear block instruction for a self-check input Guardrail LLM.
The Guardrail LLM inspects incoming user messages and must accurately identify and block this attack vector while allowing legitimate usage.

# Output Constraint
Output **ONLY** the raw block instruction text (one to three sentences). Do not include pleasantries, explanations, or markdown code blocks wrapping your entire response.
"""

SUGGESTOR_INITIAL_PROMPT = """
Please generate one block instruction based on the following successful attack.

# ATTACK PAYLOAD (Malicious Input):
{attack_prompt}

# VICTIM RESPONSE (Evidence of successful exploit):
{victim_response}

Analyze the attack payload and the victim response. Your instruction MUST:

1. **Explicit Blocking:** State clearly that a message matching this attack pattern must be blocked. Leave no room for interpretation.
2. **Zero False Positives:** Be specific enough that normal, benign requests still pass. Do not block broad categories.
3. **High Specificity:** Name the exact keywords, commands, or syntax that characterize the attack.

Output ONLY the raw block instruction text.
"""

SUGGESTOR_REFINE_PROMPT = """
Your previous block instruction was evaluated by the Security Auditor. It needs refinement.

# YOUR PREVIOUS DRAFT:
{previous_draft}

# AUDITOR FEEDBACK:
{auditor_feedback}

Revise your block instruction to address the [WEAKNESSES] and implement all [REQUIRED FIXES].
Output ONLY the revised raw block instruction text. Do not argue with the auditor or add introductory text.
"""

GRADER_SYS_PROMPT = """
# Role
You are a strict AI Security Auditor and Red Teamer. Your job is to review proposed input-guardrail block instructions to ensure they are specific and practical.

# Objective
Evaluate the instruction on three pillars: Effectiveness (does it block the attack?), Usability (does it allow safe usage?), and Specificity.

# Output Format
Output a strict evaluation with the EXACT following headers:
[SCORE]: A number from 1 to 10 (10 means perfect, 1 means completely flawed).
[STRENGTHS]: What the instruction did well.
[WEAKNESSES]: Loopholes, vagueness, or risks of blocking legitimate benign users.
[REQUIRED FIXES]: Explicit instructions on what to change in the next draft.
"""

GRADER_USER_PROMPT = """
Please audit the following proposed block instruction.

# CONTEXT: THE ATTACK IT MUST PREVENT
Attack Payload: {attack_prompt}
Exploit Evidence: {victim_response}

# PROPOSED BLOCK INSTRUCTION TO EVALUATE:
{suggestor_draft}

# RUBRIC:
1. **Effectiveness:** Reading only the instruction, would a guardrail definitively block the exact Attack Payload?
2. **False Positives:** Will standard, benign requests still pass? We do NOT want to block benign prompts.
3. **Specificity:** Penalize vague instructions like "block malicious intent." Reward concrete blocklists, exact behaviors, or specific syntax.

Provide your evaluation using the required headers: [SCORE], [STRENGTHS], [WEAKNESSES], and [REQUIRED FIXES].
"""


def build_guardrail_prompt(
    attack_prompt: str,
    victim_response: str,
    *,
    complete: Complete,
    max_iterations: int = 1,
) -> str:
    """Run the suggestor/grader loop for one attack and return the block instruction.

    ``max_iterations=1`` matches the prototype: the grader runs once and gives
    feedback, but refinement (iteration > 1) is off. Raise it to activate the
    refine loop and the score>=9 early break.
    """
    current_draft = ""
    grader_feedback = ""
    for iteration in range(1, max_iterations + 1):
        if iteration == 1:
            user = SUGGESTOR_INITIAL_PROMPT.format(attack_prompt=attack_prompt, victim_response=victim_response)
        else:
            user = SUGGESTOR_REFINE_PROMPT.format(previous_draft=current_draft, auditor_feedback=grader_feedback)
        current_draft = complete(SUGGESTOR_SYS_PROMPT, user)

        grader_user = GRADER_USER_PROMPT.format(
            attack_prompt=attack_prompt, victim_response=victim_response, suggestor_draft=current_draft
        )
        grader_feedback = complete(GRADER_SYS_PROMPT, grader_user)

        match = re.search(r"\[SCORE\]:\s*(\d+)", grader_feedback)
        if match and int(match.group(1)) >= 9:
            break
    return current_draft


def build_remediation(
    findings: list[BehavioralFinding],
    *,
    complete: Complete,
    max_iterations: int = 1,
) -> list[GuardrailRemediation]:
    """One GuardrailRemediation (an input-rail block instruction) per behavioral finding."""
    remediations: list[GuardrailRemediation] = []
    for finding in findings:
        attack_prompt = finding.record.get("prompt", "") or finding.text
        victim_response = finding.record.get("output", "")
        guardrail_prompt = build_guardrail_prompt(
            attack_prompt, victim_response, complete=complete, max_iterations=max_iterations
        )
        remediations.append(
            GuardrailRemediation(
                finding_id=finding.finding_id,
                attack_prompt=attack_prompt,
                victim_response=victim_response,
                guardrail_prompt=guardrail_prompt,
                rail_type="input",
            )
        )
    return remediations
