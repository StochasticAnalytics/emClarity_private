---
name: Orchestrator Tuning
description: Configuration lessons, bug fixes, and behavioral tuning for the autonomous build orchestrator
type: project
---

# Orchestrator Tuning Notes

## Streaming Fix (2026-03-14)

**Problem:** `--stream` flag showed no output — user saw nothing for 7+ minutes per task.

**Root cause:** `--verbose` outputs to stdout, not stderr. The streaming code read stderr (empty) while stdout accumulated unseen. Additionally, the original `select()`-based approach had a pipe deadlock.

**Fix:** Use `--output-format stream-json --verbose` which produces newline-delimited JSON on stdout. Read stdout line-by-line in main thread, drain stderr in background thread.

**How to apply:** When modifying the orchestrator's CLI invocation, prefer the stream-json path for `--stream` mode. Note that `--verbose` output went to stdout in our testing — verify stderr assumptions empirically before relying on them.

## QA Verdict Parsing

**Problem:** QA agent consistently returned verdicts that didn't match the expected `**VERDICT:** PASS` markdown pattern. Parser defaulted to BLOCKED, causing unnecessary retries and task splitting.

**Fix applied:**
1. Parser tries 3 patterns: exact markdown, plain text `VERDICT: PASS`, heading pattern
2. Unparseable output tagged as `UNPARSEABLE` — defers to oracle instead of blocking
3. QA timeout increased from 300s to 600s (was timing out)

**Still needed:** Update QA prompt to require plain-text verdict format on its own line (not inside code blocks).

**Why:** The QA prompt shows the verdict format inside a markdown code block example. The QA agent may reproduce the code block formatting literally, which the parser then can't extract because the asterisks are inside a fenced block.

## Retry and Split Behavior

**Observation:** TASK-002 was split into 3 sub-tasks after 3 retries. All retries were caused by QA parsing failures, not code quality issues. The developer agent's code was correct on every attempt.

**How to apply:** Before attributing task failure to complexity, check whether the failure is in infrastructure (parsing, timeouts, permissions) vs. actual code quality. The orchestrator log now captures QA raw output at INFO level for this diagnosis.

## Logging

**Added in this session:**
- Per-stage timing: `[DEV] TASK-002 done in 302s`
- Token/cost tracking in progress.txt
- Full QA output logged at INFO level (first 2000 chars)
- Parse result logged separately: `verdict=X parsed=True/False`
- Task lifecycle summary: `╰── TASK-002 COMPLETE (485s total)`
- End-of-run report with per-status breakdown and retry counts

## Config Notes

- `config.json` `project_root` must be `/workspaces/cisTEMx` (absolute path)
- E2E tests disabled in oracle (`"e2e_tests": false`) — they require a running backend server. Enable for TASK-016 (integration).
- Oracle `assert_count` baseline: 83 (from locked tests/ directory)
