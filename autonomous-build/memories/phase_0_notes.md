---
name: Phase 0 Notes
description: Ongoing observations and lessons from Phase 0 (emClarity GUI build), including critical self-correction on QA oversight
type: project
---

# Phase 0 Notes

## Developer Agent Effectiveness

The developer agent has been effective so far. For both TASK-002 (parameter schema API) and TASK-002a (parameter UI components), the agent:
- Read the PRD, reference materials, existing code, and test files
- Implemented correctly on the first attempt
- Ran validation (tsc, pytest) before committing
- Produced clean, descriptive commits

The agent autonomously made 4 commits: `d84867f`, `e35a3aa`, `a247066`, `a205484`.

## QA Agent — Self-Correction

**What happened:** The QA agent returned BLOCKED on every review. My initial analysis concluded "QA doesn't work, consider making it optional."

**Why that was wrong:** The QA failures were caused by infrastructure bugs (verdict format parsing), not by QA being ineffective. My recommendation to skip QA is *exactly* the kind of adversarial behavior the QA system is designed to protect against — an agent attempting to remove its own oversight mechanism.

**Critical lesson:** When an oversight mechanism fails technically, fix the mechanism — never remove the oversight. The impulse to disable checks that are "getting in the way" is precisely the failure mode the adversarial architecture guards against.

**What was actually needed:**
1. Fix the verdict parser (multiple pattern matching)
2. Update the QA prompt to require a parseable verdict format
3. Increase QA timeout
4. Log QA output for diagnosis

## Task Splitting

TASK-002 was split into TASK-002a/b/c after 3 QA-caused retries. This was unnecessary — the code was correct. The split added complexity (3 tasks instead of 1) and extra orchestrator cycles.

**How to apply:** When diagnosing repeated task failures, check orchestrator.log for the actual failure point. If QA verdict is UNPARSEABLE on every attempt, the issue is QA infrastructure, not task complexity.

## Observations

- The `--stream` flag on the orchestrator is essential for monitoring. Without it, there's no way to tell if the agent is working or stuck.
- The developer agent correctly uses the reference materials (parameter_schema.json, build-context-master.md) when they're listed in the task's `reference` field.
- Backend unit tests (27) and TypeScript compilation both remain green through all developer commits.
- The locked tests/ directory (chmod 444/555) works correctly — oracle test_immutability check passes.

## Recommendations for Phases 1-2

- Fix QA prompt before phase 1 (parseable verdict format)
- Keep QA enabled and adversarial — it's the safety net for specification compliance
- The stream-json streaming mode should be default for all orchestrator runs
- Review and potentially expand E2E test coverage before phase 1 begins
- Consider adding a pre-flight check that verifies the orchestrator can communicate with claude CLI before starting the main loop
