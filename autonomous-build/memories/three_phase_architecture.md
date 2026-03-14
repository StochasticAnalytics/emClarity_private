---
name: three_phase_architecture
description: Three-phase product roadmap (emClarity → cisTEM → CryoPrior) with portable autonomous-build across all repos
type: project
---

The autonomous build system serves three phases across three separate repositories:

**Phase 0 — emClarity (cisTEMx repo, current)**
- Proof of concept. Simple GUI wrapping MATLAB CLI tools.
- MATLAB core (alignment/, ctf/, masking/, etc.) stays untouched.
- New web frontend + lightweight backend/middleware.
- Goal: prove the autonomous build system works on a simpler application.

**Phase 1 — cisTEM (separate repo, existing wxWidgets GUI)**
- Replicate all functionality of the existing cisTEM wxWidgets GUI in a modern web stack.
- Existing code (source/core/, source/gui/) must stay untouched.
- New web frontend lives alongside existing GUI, not replacing it.
- Middle layer replaces wxWidgets' coordination role: parallelization, SQLite database interactions, monitoring, sockets, and more complex orchestration.
- Builds on lessons from Phase 0 implementation.

**Phase 2 — CryoPrior (new commercial product, from scratch)**
- New product with new GUI, new middleware, potentially new backend.
- Easiest structurally since nothing pre-exists.
- Takes all lessons from Phase 0 and Phase 1.

**autonomous-build as portable tool:**
- Should work as an "unofficial submodule" across all three repos.
- Needs to "step out" and look at the host project regardless of which phase/repo.
- config.json's project_root points to the host repo.
- Must not collide with orchestrator's own working state.

**Why:** This context was established in a prior session but lost due to the orchestrator's `git reset --hard` destroying uncommitted work. Preserving it here prevents future re-discovery.

**How to apply:** All directory layout decisions, worktree/isolation strategies, and config patterns must work across all three phases. Don't optimize only for Phase 0.
