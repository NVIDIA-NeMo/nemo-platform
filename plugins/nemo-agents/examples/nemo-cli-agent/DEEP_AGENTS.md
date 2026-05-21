# DeepAgents Runtime

These instructions apply when this folder is run through the bundled
LangChain DeepAgents graph.

## Skills

The runtime loads `.agents/skills/` with DeepAgents `SkillsMiddleware`. It
injects every skill's name, description, and path into this prompt in an
**Available Skills** section.

For every user request, scan **Available Skills** first. If a skill matches the
intent, even loosely, call `read_file` on that skill's `SKILL.md` path before
running any `nemo` command.

## Tools

Use `nemo_cli` only for a single command whose first token is `nemo`. It cannot
run shell pipelines, redirection, `echo`, `cat`, `&&`, or local file creation.
When an instruction shows unsupported shell syntax, adapt it to an equivalent
single `nemo` command.

Do not claim tools are insufficient until you have attempted reasonable
equivalent operations with valid `nemo_cli` commands.

The `write_file` tool defaults to an in-memory scratchpad that subprocess tools,
including `nemo_cli`, cannot read. When a file you create needs to be read by a
subprocess, write it under `/tmp/` and reference that same `/tmp/...` path from
the subprocess.
