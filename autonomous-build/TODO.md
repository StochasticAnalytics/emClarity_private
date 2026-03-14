# Autonomous Build — TODO

Persistent task list for work to do when the orchestrator is not running.
Items added during planning/discussion sessions with the user.

---

- [x] **Preflight effort query**: ~~Update preflight prompt to query effort level.~~ **Resolved**: Per [Anthropic effort docs](https://platform.claude.com/docs/en/build-with-claude/effort), effort is a request-level parameter not exposed to the model. The agent cannot self-report it. Removed from preflight prompt. The orchestrator's own config printout (`effort: medium`) is the authoritative source.
