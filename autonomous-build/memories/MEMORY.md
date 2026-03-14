# Autonomous Build — Project Memory Compendium

## Memory Merge Workflow

This file is the persistent master. The home-dir MEMORY.md (`/home/cisTEMdev/.claude/projects/-workspaces-cisTEMx/memory/MEMORY.md`) is ephemeral and accumulates new auto-memories during sessions.

**Merge procedure (do this periodically):**
1. Read both files. Identify entries in home-dir that are not yet in this compendium.
2. Move new entries from home-dir → here (or into a topic file in this directory).
3. Remove the moved entries from home-dir so it stays lean. What remains in home-dir is "new since last merge."
4. **Simple conflicts** (same topic, different detail): the home-dir version is more recent — use it.
5. **Complex conflicts** (contradictory conclusions, changed assumptions): flag these and review with the user before resolving. Do not silently pick a winner.
6. After merge, the home-dir MEMORY.md should only contain entries that haven't been merged yet.

## Memory Index

| File | Type | Summary |
|------|------|---------|
| [claude_cli_patterns.md](claude_cli_patterns.md) | reference | CLI flags, output formats, subprocess patterns |
| [orchestrator_tuning.md](orchestrator_tuning.md) | project | Streaming fix, QA parser, config lessons |
| [phase_0_notes.md](phase_0_notes.md) | project | Developer/QA agent observations, self-correction on oversight |

## Environment

- Home directory (`/home/cisTEMdev/`) is **ephemeral** — wiped on container restart
- This compendium at `autonomous-build/memories/` is the persistent master copy
- `claude-launcher.sh` in autonomous-build/ appends this file to system prompt via `--append-system-prompt`

## Project Structure

- **Frontend**: React 19 + TypeScript 5 + Vite 8 at `gui/`
- **Backend**: FastAPI + Pydantic v2 at `backend/`
- **E2E Tests**: 35 tests at `tests/` (LOCKED, chmod 444/555)
- **Backend Tests**: 27 tests at `backend/tests/`
- **Phase 0 artifacts**: `autonomous-build/templates/phase0-artifacts/`
  - `parameter_schema.json` — 160 params from BH_parseParameterFile.m
  - `workflow_map.md` — 28 commands, pipeline order, dependencies
  - `build-context-master.md` — full architecture spec (React+TS stack)
  - `orchestration-spec.md` — shell scripts, parallelization, external tools
- **PRD**: `autonomous-build/templates/prd.json` — 16+ tasks, TASK-001 complete
- **Component log**: `autonomous-build/COMPONENT_LOG.md`
- **Oracle baseline**: 83 assertions

## API Contract (tests are ground truth)

E2E tests define the API contract the developer agent must implement:
- Endpoints use `/api/v1/` prefix
- Schema response: `{"parameters": [...]}`
- Project creation: `{name, directory, parameters}` → `{id, state, ...}`
- Project-scoped workflow routes: `/workflow/{project_id}/...`
- State machine endpoint: `/workflow/state-machine`
- Job model requires: `id, project_id, command, status`

## Sandbox

- Bash commands in Claude Code need `dangerouslyDisableSandbox: true` (bwrap namespace restriction)
- Background agents (`run_in_background=true`) cannot get interactive permission prompts — tools auto-denied

## Critical Design Principle

**When oversight mechanisms fail technically, fix the mechanism — never remove the oversight.** The adversarial QA architecture exists to protect against agents (including helpful ones) removing their own checks. See `phase_0_notes.md` for the full lesson.
