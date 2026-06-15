#!/usr/bin/env python
"""Tally the distribution of adversarial *jailbreak tactics* in WildGuardTrain.

IMPORTANT — what this does and does not measure
------------------------------------------------
WildGuardMix has **no tactic label**. Its only categorical column is
``subcategory`` (the *harm* taxonomy: "others", "benign", ...), not the jailbreak
technique. So a "tactic distribution" cannot be read off a field — it must be
*inferred*. This script infers tactics with a deterministic, transparent,
**multi-label** heuristic tagger (a prompt can carry several tactics, matching
the WildTeaming finding that adversarial prompts compose 2-7 tactics).

Because it is heuristic, the single most important output is the **residual**:
the share of adversarial prompts that match *zero* known tactics. That residual
is our honest coverage gap and the "novel / under-covered tactic" bucket the
flywheel should target. Treat the per-tactic counts as approximate; treat the
residual and the relative ordering as the actionable signal. Validate with the
optional LLM pass (see ``--help``) before quoting absolute numbers.

Usage
-----
    .venv/bin/python data_flywheels/wildguard/analyze_tactics.py
    .venv/bin/python data_flywheels/wildguard/analyze_tactics.py --samples 5
    .venv/bin/python data_flywheels/wildguard/analyze_tactics.py --parquet /path/to/wildguard_train.parquet

Outputs (written next to this script, under ``tactics_out/``):
    - tactic_summary.json    machine-readable tallies, %, co-occurrence, residual
    - tactic_per_row.parquet per-row multi-hot tactic flags (for downstream use)
    - samples_<tactic>.txt    truncated example prompts per tactic (spot-check)
    - residual_samples.txt    adversarial prompts matching no known tactic
"""

from __future__ import annotations

import argparse
import glob
import json
import re
from collections import Counter
from itertools import combinations
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
DEFAULT_GLOB = (
    "/home/albcui/.cache/huggingface/hub/"
    "datasets--allenai--wildguardmix/snapshots/*/train/wildguard_train.parquet"
)


# ---------------------------------------------------------------------------
# Tactic taxonomy. Each tactic maps to a list of case-insensitive regex
# patterns; a prompt is tagged with the tactic if ANY pattern matches. Keep
# patterns conservative (precision over recall) so the residual stays honest.
# Derived from the WildTeaming tactic families + common jailbreak literature.
# ---------------------------------------------------------------------------
TACTIC_PATTERNS: dict[str, list[str]] = {
    # task_list_injection is handled by a custom detector (see CUSTOM_DETECTORS),
    # because the dominant form is a *prose* list with no numbered markers. The
    # regexes below are only the high-precision keyword cues; the verb-count
    # heuristic in the custom detector catches the prose variants.
    "task_list_injection": [
        r"(?:^|\n)\s*\d+\s*[\.\)]\s+\S",       # enumerated "1. ... 2. ..."
        r"\b1\s*[\.\)]\s.+?\b2\s*[\.\)]\s",     # inline 1. .. 2. ..
        r"\bfollowing (?:tasks|items|requests|list)\b",
        r"\bhelp me with (?:these|the following|a few)\b",
        r"\bcomplete the following\b",
    ],
    "roleplay_persona": [
        r"\byou are (?:now |going to be )?(?:a|an|going|dan|stan|dude)\b",
        r"\bpretend (?:to be|you are|that you)\b",
        r"\bact as\b",
        r"\brole[\s-]?play\b",
        r"\bstay in character\b",
        r"\bfrom now on,? you\b",
        r"\b(?:dan|do anything now|developer mode|jailbreak mode)\b",
        r"\byou (?:will|must) (?:play|portray|embody)\b",
        # Open-class persona: "as a <profession/role>", named AIs, special modes.
        r"\bas (?:a|an) [a-z]+(?:ist|ologist|iatrist|grapher|cian|naut|eer|smith)\b",
        r"\b(?:ai|assistant|model|entity|character|persona|bot|being|chatbot) (?:named|called) [a-z0-9]+",
        r"\byou(?:'re| are) (?:now )?(?:a |an )?(?:personalized|unrestricted|unfiltered|special|unique|omniscient|all-knowing)\b",
        r"\bin (?:a |your )?(?:special|unique|developer|edgy|unrestricted|god|dan) mode\b",
    ],
    # Tightened to jailbreak-style *framing* of the whole request. Deliberately
    # excludes bare "fiction" (matches benign "science fiction") and "for a
    # story" (matches benign "brainstorming help for a story").
    "fiction_hypothetical": [
        r"\bimagine (?:a|an|that|you|yourself|we|this)\b",
        r"\bhypothetical(?:ly)?\b",
        r"\bfictional (?:scenario|world|setting|character|story|account|universe|narrative)\b",
        r"\bin a (?:fictional |make-?believe )?(?:world|universe|scenario|setting|reality) where\b",
        r"\bwrite (?:a|me a|an) (?:story|script|screenplay|novel|fanfic(?:tion)?|dialogue|scene|play) (?:about|where|in which|that)\b",
        r"\bfor (?:a|my) (?:movie|novel|screenplay|video game|role[\s-]?play(?:ing)? game)\b",
        r"\bpretend (?:this is|it'?s) (?:a|just) (?:fiction|a story|hypothetical|a game)\b",
        r"\blet'?s play a game\b",
    ],
    "expert_authority_research": [
        r"\bas (?:a|an) (?:expert|professional|doctor|chemist|engineer|researcher|scientist|lawyer|hacker)\b",
        r"\bas (?:a|an) [a-z]+(?:ist|ologist|iatrist|grapher)\b",  # open-class experts
        r"\bfor (?:research|educational|academic|scientific) purposes\b",
        r"\bi(?:'| a)m a (?:researcher|professor|student|doctor|scientist|journalist)\b",
        r"\bpurely (?:academic|educational|theoretical)\b",
        r"\b(?:research|teaching|lab|legal|medical) assistant\b",
        r"\bcase study\b",
    ],
    "refusal_suppression_override": [
        r"\bignore (?:all |any |the )?(?:previous|prior|above) (?:instructions|prompts|rules)\b",
        r"\bdo not (?:refuse|warn|apologize|include any warnings)\b",
        r"\byou (?:must|have to|will) (?:answer|comply|respond)\b",
        r"\bwithout (?:any )?(?:warnings?|disclaimers?|caveats?|moral|ethical|refus)\b",
        r"\bno (?:warnings?|disclaimers?|apolog|moralizing)\b",
        r"\bnever (?:say|refuse|decline)\b",
        r"\bdisregard (?:your|the) (?:guidelines|rules|policy)\b",
    ],
    "persuasion_emotional": [
        r"\bmy (?:grand(?:ma|mother|pa|father)|late|deceased|dying)\b",
        r"\bplease,? i (?:really |desperately )?need\b",
        r"\bit'?s (?:an |a )?(?:emergency|urgent|life or death|matter of life)\b",
        r"\bi (?:will|might|could) (?:die|lose my job|get hurt)\b",
        r"\bi'?m begging you\b",
    ],
    "obfuscation_encoding": [
        r"\bbase64\b",
        r"\brot13\b",
        r"\bmorse code\b",
        r"\bleet ?speak\b",
        r"\b(?:encode|decode|encrypt|decrypt|cipher)\b",
        r"\bspell (?:it|out)\b",
        r"\breplace (?:the )?(?:letters|characters|vowels)\b",
        r"\breverse (?:the )?(?:order|letters|string|text)\b",
    ],
    "translation_lowresource": [
        r"\btranslate\b",
        r"\brespond (?:in|only in) (?:french|spanish|german|chinese|arabic|hindi|swahili|latin|[a-z]+)\b",
        r"\bin (?:french|spanish|german|chinese|japanese|korean|arabic|hindi|russian|latin)\b",
        r"\banswer in (?:another|a different) language\b",
    ],
    "payload_splitting": [
        r"\bfirst letter of each\b",
        r"\bconcatenate\b",
        r"\bcombine (?:the )?(?:letters|words|parts|following)\b",
        r"\bput (?:it|them) together\b",
        r"\bsplit (?:into|across)\b",
    ],
    "tense_historical_shift": [
        r"\bhow did (?:people|they|one)\b",
        r"\bin the (?:past|old days|\d{4}s)\b",
        r"\bhistorically,?\b",
        r"\bback (?:then|in the day)\b",
        r"\bhow (?:will|would) (?:people|society)\b",
    ],
    "output_format_priming": [
        r"\bstart (?:your (?:answer|response)|with) (?:by saying |with )?[\"']?(?:sure|certainly|absolutely|of course|here)\b",
        r"\brespond only with\b",
        r"\bbegin (?:your (?:answer|reply))? ?with\b",
        r"\boutput (?:as |in )?(?:json|a table|markdown|format)\b",
        r"\bformat (?:your answer|the response) as\b",
    ],
}

# Plain-English definitions of each tactic. Shared with the LLM-based classifier
# (classify_tactics_llm.py) so the heuristic and the LLM use the SAME taxonomy
# and their distributions are directly comparable. Keep keys in sync with
# TACTIC_PATTERNS.
TACTIC_DEFINITIONS: dict[str, str] = {
    "task_list_injection": (
        "The harmful request is hidden inside a list of mostly-benign tasks "
        "(numbered, bulleted, or prose) so it blends in, e.g. 'translate hello, "
        "give a cake recipe, and explain how to build a bomb'."
    ),
    "roleplay_persona": (
        "The model is told to adopt a persona, character, or alter-ego (DAN, a "
        "named AI, a fictional villain, 'developer mode', 'as a <role>') that is "
        "framed as exempt from normal rules."
    ),
    "fiction_hypothetical": (
        "The request is wrapped in a fictional, hypothetical, story, or "
        "'imagine a world where' framing so the harmful content is presented as "
        "make-believe."
    ),
    "expert_authority_research": (
        "The user claims an authoritative/professional identity or a research/"
        "educational/academic justification ('as a chemist', 'for research "
        "purposes', 'case study') to legitimize the request."
    ),
    "refusal_suppression_override": (
        "Explicit instructions to bypass safety: 'ignore previous instructions', "
        "'do not refuse', 'no warnings/disclaimers', 'you must answer'."
    ),
    "persuasion_emotional": (
        "Emotional manipulation or social pressure: the dying/grandmother trick, "
        "urgency, begging, appeals to harm-if-you-refuse."
    ),
    "obfuscation_encoding": (
        "The harmful content is encoded or disguised (base64, ROT13, leetspeak, "
        "morse, character substitution, 'spell it out', reversed text)."
    ),
    "translation_lowresource": (
        "Using translation or a non-English / low-resource language to smuggle or "
        "elicit the harmful content."
    ),
    "payload_splitting": (
        "The harmful string is split into pieces the model is told to "
        "concatenate/combine (e.g. 'take the first letter of each', 'put these "
        "parts together')."
    ),
    "tense_historical_shift": (
        "Reframing the harmful ask in past/future tense or as a historical "
        "question ('how did people in the past...', 'how will society...') to "
        "dodge present-tense refusals."
    ),
    "output_format_priming": (
        "Constraining the output to force compliance: 'start your answer with "
        "Sure', 'respond only with...', answer as JSON/table, affirmative-prefix "
        "priming."
    ),
}

COMPILED: dict[str, list[re.Pattern[str]]] = {
    name: [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in pats]
    for name, pats in TACTIC_PATTERNS.items()
}

# Request/imperative verbs that head a "task" clause. The dominant adversarial
# form in WildGuardMix is a list of such clauses (numbered OR prose) with one
# harmful item buried among benign ones. Counting >=3 distinct task clauses is a
# far better detector for the prose variant than looking for "1. 2. 3." markers.
_TASK_VERB_RE = re.compile(
    r"\b(explain|describe|calculate|recommend|suggest|provide|give|tell|show|list|"
    r"translate|write|summari[sz]e|outline|define|generate|find|teach|create|compose|"
    r"offer|advise|draft|design|invent|propose|make|remind|name|identify|"
    r"help me (?:with|to)?|how (?:do|to|can) i)\b",
    re.IGNORECASE,
)


_LISTY_LEADIN = re.compile(
    r"\b(please provide|provide me|can you (?:help|assist|tell|give|provide)|"
    r"i need (?:help|assistance|you|some|the following)|here(?:'s| are)|"
    r"give me|tell me|outline|list (?:the|me|out))\b",
    re.IGNORECASE,
)


def _is_task_list_injection(text: str) -> bool:
    if any(p.search(text) for p in COMPILED["task_list_injection"]):
        return True
    # Prose variant A: >=3 distinct task-verb clauses joined in one request.
    if len(_TASK_VERB_RE.findall(text)) >= 3:
        return True
    # Prose variant B: a request lead-in followed by a >=3-item comma list with
    # a trailing "and" (catches noun-headed lists like "provide X, Y, Z, and W").
    return bool(_LISTY_LEADIN.search(text)) and text.count(",") >= 3 and " and " in text.lower()


CUSTOM_DETECTORS = {"task_list_injection": _is_task_list_injection}


def detect_tactics(text: str) -> set[str]:
    """Return the set of tactics whose patterns match ``text`` (multi-label)."""
    if not isinstance(text, str) or not text:
        return set()
    found: set[str] = set()
    for name, patterns in COMPILED.items():
        custom = CUSTOM_DETECTORS.get(name)
        if custom is not None:
            if custom(text):
                found.add(name)
        elif any(p.search(text) for p in patterns):
            found.add(name)
    return found


def resolve_parquet(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    matches = sorted(glob.glob(DEFAULT_GLOB))
    if not matches:
        raise SystemExit(
            f"Could not find wildguard_train.parquet via glob:\n  {DEFAULT_GLOB}\n"
            "Pass --parquet /path/to/wildguard_train.parquet"
        )
    return Path(matches[-1])


def analyze(df: pd.DataFrame, samples: int, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)

    adv = df[df["adversarial"] == True].copy()  # noqa: E712
    adv["tactics"] = adv["prompt"].map(detect_tactics)
    adv["n_tactics"] = adv["tactics"].map(len)

    n_adv = len(adv)
    adv_harm = adv[adv["prompt_harm_label"] == "harmful"]
    adv_benign = adv[adv["prompt_harm_label"] == "unharmful"]

    def tally(frame: pd.DataFrame) -> dict[str, int]:
        c: Counter[str] = Counter()
        for s in frame["tactics"]:
            c.update(s)
        return dict(c.most_common())

    counts_all = tally(adv)
    counts_harm = tally(adv_harm)
    counts_benign = tally(adv_benign)

    # Co-occurrence (top pairs).
    pair_counter: Counter[tuple[str, str]] = Counter()
    for s in adv["tactics"]:
        for a, b in combinations(sorted(s), 2):
            pair_counter[(a, b)] += 1

    # Residual: adversarial prompts matching zero known tactics.
    residual = adv[adv["n_tactics"] == 0]

    # Multi-hot per-row table for downstream use.
    per_row = adv[["prompt", "prompt_harm_label", "n_tactics"]].copy()
    for name in TACTIC_PATTERNS:
        per_row[name] = adv["tactics"].map(lambda s, n=name: n in s)
    per_row.to_parquet(out_dir / "tactic_per_row.parquet", index=False)

    # Per-tactic sample dumps for spot-checking precision.
    for name in TACTIC_PATTERNS:
        hits = adv[adv["tactics"].map(lambda s, n=name: n in s)]
        lines = []
        for _, r in hits.head(samples).iterrows():
            t = str(r["prompt"]).replace("\n", " ")
            lines.append(f"[{r['prompt_harm_label']}] {t[:300]}")
        (out_dir / f"samples_{name}.txt").write_text("\n".join(lines) + "\n")

    res_lines = []
    for _, r in residual.head(max(samples * 4, 20)).iterrows():
        t = str(r["prompt"]).replace("\n", " ")
        res_lines.append(f"[{r['prompt_harm_label']}] {t[:300]}")
    (out_dir / "residual_samples.txt").write_text("\n".join(res_lines) + "\n")

    def pct(n: int) -> float:
        return round(100.0 * n / n_adv, 2) if n_adv else 0.0

    summary = {
        "dataset_rows_total": int(len(df)),
        "adversarial_rows": int(n_adv),
        "adversarial_harmful": int(len(adv_harm)),
        "adversarial_benign": int(len(adv_benign)),
        "avg_tactics_per_adv_prompt": round(float(adv["n_tactics"].mean()), 3),
        "residual_no_tactic": {
            "count": int(len(residual)),
            "pct_of_adversarial": pct(len(residual)),
            "harmful": int((residual["prompt_harm_label"] == "harmful").sum()),
            "benign": int((residual["prompt_harm_label"] == "unharmful").sum()),
        },
        "tactic_counts_all": {k: {"count": v, "pct_of_adv": pct(v)} for k, v in counts_all.items()},
        "tactic_counts_harmful": counts_harm,
        "tactic_counts_benign": counts_benign,
        "top_cooccurring_pairs": [
            {"pair": list(p), "count": c} for p, c in pair_counter.most_common(15)
        ],
        "n_tactics_histogram": {
            str(k): int(v) for k, v in adv["n_tactics"].value_counts().sort_index().items()
        },
    }
    (out_dir / "tactic_summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def print_report(summary: dict) -> None:
    n_adv = summary["adversarial_rows"]
    print("=" * 72)
    print("WildGuardTrain adversarial-tactic distribution (heuristic, multi-label)")
    print("=" * 72)
    print(f"Total rows:            {summary['dataset_rows_total']:,}")
    print(f"Adversarial rows:      {n_adv:,} "
          f"(harmful={summary['adversarial_harmful']:,}, benign={summary['adversarial_benign']:,})")
    print(f"Avg tactics / prompt:  {summary['avg_tactics_per_adv_prompt']}")
    res = summary["residual_no_tactic"]
    print(f"Residual (0 tactics):  {res['count']:,} ({res['pct_of_adversarial']}% of adversarial) "
          f"[harmful={res['harmful']:,}, benign={res['benign']:,}]  <-- coverage gap")
    print("\nTactic                          count      %adv   (harmful / benign)")
    print("-" * 72)
    ch, cb = summary["tactic_counts_harmful"], summary["tactic_counts_benign"]
    for name, d in summary["tactic_counts_all"].items():
        print(f"{name:<30} {d['count']:>7,}  {d['pct_of_adv']:>6}   "
              f"({ch.get(name, 0):,} / {cb.get(name, 0):,})")
    print("\nTop co-occurring tactic pairs")
    print("-" * 72)
    for item in summary["top_cooccurring_pairs"]:
        a, b = item["pair"]
        print(f"  {a} + {b}: {item['count']:,}")
    print("\nTactics-per-prompt histogram:", summary["n_tactics_histogram"])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--parquet", default=None, help="Path to wildguard_train.parquet (default: HF cache glob)")
    ap.add_argument("--samples", type=int, default=3, help="Example prompts to dump per tactic")
    ap.add_argument("--out", default=str(HERE / "tactics_out"), help="Output directory")
    args = ap.parse_args()

    path = resolve_parquet(args.parquet)
    print(f"Loading {path}")
    df = pd.read_parquet(path)
    summary = analyze(df, samples=args.samples, out_dir=Path(args.out))
    print_report(summary)
    print(f"\nWrote outputs to {args.out}/")


if __name__ == "__main__":
    main()
