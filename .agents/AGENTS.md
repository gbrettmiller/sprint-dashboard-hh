# Agent Guidelines for sprint-metrics-dashboard

## Scope

These instructions apply to the entire repository unless a more specific
`AGENTS.md` file is present in a subdirectory.

## Doctrine and Primary References

When working in this repo, always treat the following files as the
source of truth for behavior, architecture, and workflow:

- `VECTOR.md`    project identity, doctrine, and expectations
- `CLAUDE.md`    detailed architecture and AI workflow guidance
- `ARCHITECTURE.md`  technical stack and data-flow description
- `README.md`    user-facing usage and setup

Before making non-trivial changes (new features, refactors, or changes
to CI/AI behavior), skim the relevant sections of these files and align
with their guidance. If doctrine appears outdated, call it out in your
notes rather than silently deviating.

## Working Style

- Prefer **small, surgical changes** over broad refactors.
- Do **not** reorganize files, rename modules, or change public
  interfaces unless explicitly requested.
- Surface ambiguity and missing context with a short question instead
  of guessing when a reasonable assumption would be risky.
- Keep existing behavior and data formats stable unless the task
  explicitly calls for a change.

## Coding Conventions

- Follow the existing style of nearby code (imports, logging, argument
  parsing, etc.).
- Use descriptive names rather than one-letter variables.
- Avoid adding new dependencies unless necessary; prefer reusing
  existing libraries and patterns.
- For Python scripts under `scripts/`, preserve compatibility with
  non-interactive CI usage (no interactive prompts unless the script is
  clearly documented as interactive only).

## AI / Tooling Integration

This projects historical documentation refers to **Claude Code** and an
Anthropic-based pipeline. When working with **Codex** or other AI
assistants:

- Treat all guidance written for "Claude" or "Claude Code" as applying
  equally to the current assistant.
- Keep the existing Claude / Anthropic paths **intact** in code and
  docs unless the task explicitly says to remove them.
- When adding new AI integrations (for example, OpenAI- or AskSage-
  backed models), prefer additive designs:
  - Add feature flags or environment-variable switches.
  - Maintain backward compatibility with the Anthropic configuration
    documented in `CLAUDE.md` and `ARCHITECTURE.md`.

## Validation

- When possible, run the narrowest tests or scripts that cover the
  changes you made (for example, a single Python script or targeted
  vitest suite), and report the commands you ran.
- Do not attempt to fix unrelated failing tests unless asked; mention
  them briefly in your notes instead.

