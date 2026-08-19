# Codex Usage Notes

This repository was originally set up for **Claude Code** and uses
Claude/Anthropic terminology throughout the documentation. When working
with **Codex** instead of Claude:

- Treat guidance written for "Claude" or "Claude Code" as applying
  equally to Codex.
- Follow the doctrine and architecture described in:
  - `VECTOR.md`
  - `CLAUDE.md`
  - `ARCHITECTURE.md`
  - `README.md`
- Use the existing Python scripts in `scripts/` for GitLab issue
  workflows (read/list/create/implement/etc.). Codex can invoke these
  scripts via the shell just as Claude Code did.

For more detail on the original Claude-focused setup, see
`CLAUDE_PBI_SKILLS.md` and the `.claude/` directory.

