# PRD Hardening: kanban-v2.json

## Context

The autobuilder PRD `autonomous-build/prd/kanban-v2.json` (9 tasks, 4 backend + 5 frontend) and its supplement `autonomous-build/prd/kanban-v2-supplement.md` need hardening before submission to the autobuilder. A previous autobuilder run wasted 17 hours due to a missing CuPy dependency — this review prevents similar failures by catching issues the autobuilder agent cannot self-correct.

A Yang/Yin adversarial review was conducted against the full codebase. Findings are below, organized by severity.

## Files to Modify

- `autonomous-build/prd/kanban-v2.json` — all fixes below
- `autonomous-build/prd/kanban-v2-supplement.md` — one addition (Issue 4)

---

## BLOCKERS (6) — Will cause task failure or wrong implementation

### B1. TASK-003/TASK-004 dependency gap — `/scan` calls nonexistent script

**Problem**: TASK-003 adds `POST /scan` which invokes `file_classifier.py` via subprocess. TASK-004 creates that script. But TASK-003 `depends_on` is `["TASK-002"]` — no dependency on TASK-004. The autobuilder may execute TASK-003 first. `subprocess.run()` will raise `FileNotFoundError`, not return an empty array as the acceptance criteria claim.

**Fix**: Add guard logic to TASK-003 description for the `/scan` route:
> "Before invoking subprocess, check if the script path exists (Path.exists()). If the script does not exist, return an empty list[ScanResult] with 200 status. Only invoke subprocess.run() if the file is present."

Update TASK-003 acceptance criterion #7 to:
> "POST /api/pipeline/scan with {mode:'stragglers'} returns 200 with empty array if file_classifier.py does not yet exist, or with scan results if it does"

### B2. TASK-002 — `"completed"` vs `"complete"` status string mismatch (existing bug)

**Problem**: `pipeline_service.py:201` counts `statuses.get("completed", 0)` but the orchestrator writes `"complete"` everywhere (`task_manager.py:141`, `core.py:1170`, `reporting.py:120,134`). The PRD progress bar has **never worked** — it always shows 0/N completed. TASK-002 modifies `_enrich_item()` and will propagate this bug into the new working-copy code path.

**Fix**: Add to TASK-002 description in the `_enrich_item()` section:
> "CRITICAL FIX: The existing code counts statuses.get('completed', 0) but the orchestrator writes status as 'complete' (not 'completed'). Change to statuses.get('complete', 0). Apply this fix to BOTH the existing original-PRD code path AND the new working-copy code path."

Add acceptance criterion:
> "PrdTaskSummary.completed counts tasks with status='complete' (not 'completed'), matching orchestrator_pkg/task_manager.py actual values"

### B3. TASK-002 — raw `re.sub` violates project regex rules

**Problem**: Description says `re.sub(r'[^a-z0-9]+', '_', title.lower()).strip('_')`. Project rules prohibit raw `re` module in production code without supervisor approval.

**Fix**: Replace with string-method approach in TASK-002 description:
> "Convert title to snake_case slug using string methods (no raw regex): `'_'.join(word for word in re.split... )` — or preferably: iterate chars, replace non-alphanumeric with underscore, collapse consecutive underscores, strip edges. Do NOT use raw re.sub — use a simple loop or comprehension, e.g.: `slug = '_'.join(filter(None, ''.join(c if c.isalnum() else '_' for c in title.lower()).split('_')))`"

### B4. TASK-002 — hash disambiguation needed

**Problem**: `prd.py` has TWO hash functions: `compute_prd_hash()` (8 chars, spec-only fields) and `archive_and_copy_prd()` (12 chars, full content). An autobuilder agent could use the wrong one.

**Fix**: Add explicit warning to TASK-002 description after the hash sentence:
> "WARNING: prd.py contains TWO different hash functions. Use archive_and_copy_prd()'s full-content fingerprint: hashlib.sha256(prd_path.read_bytes()).hexdigest()[:12]. Do NOT use compute_prd_hash() which is an 8-char hash over immutable spec fields only."

### B5. TASK-005 — `DisplayStage` vs `PipelineStage` type incompatibility

**Problem**: TASK-005 adds `DisplayStage = 'idea'|'research'|'plan'|'prd'|'done'` as a separate type. All existing APIs (column props, drag handlers, color/label lookups) use `PipelineStage`. TypeScript will reject `DisplayStage` arguments where `PipelineStage` is expected — `tsc --noEmit` fails.

**Fix**: Add to TASK-005 description:
> "Define DisplayStage as `Extract<PipelineStage, 'idea'|'research'|'plan'|'prd'|'done'>` so it is a narrowing of PipelineStage assignable to PipelineStage-typed APIs. Type PIPELINE_DISPLAY_STAGES as `readonly DisplayStage[]`. This ensures column rendering, drag-and-drop handlers, and color/label lookups all pass type checking."

### B6. TASK-005 — `itemsByStage` modification is ambiguous

**Problem**: Description says "Change itemsByStage for the 'prd' display column" but `itemsByStage` is a generic function called for every column. An agent could replace it entirely or add the override in the wrong place.

**Fix**: Replace the ambiguous instruction with explicit code:
> "Modify itemsByStage to handle display-stage grouping: `const itemsByStage = (stage: PipelineStage) => stage === 'prd' ? items.filter(i => i.stage === 'prd' || i.stage === 'queued' || i.stage === 'running') : items.filter(i => i.stage === stage);`"

---

## WARNINGS (5) — Likely to cause rework or confusion

### W1. TASK-002 — `create_idea()` sets `origin.path` but not `plan_path`

**Problem**: `_resolve_path()` checks `plan_path` and `prd_path`, NOT `origin.path`. Without `plan_path`, created ideas will never show staleness data, file mtime, or content via the `/content` endpoint.

**Fix**: Add to TASK-002 `create_idea()`:
> "Set plan_path='pipeline/ideas/{slug}.md' on the registry entry in addition to origin.path, so _resolve_path() can locate the file for staleness checks and content retrieval."

### W2. TASK-006 — "Register" button needs fields not on `CreateIdeaBody`

**Problem**: Register button should pre-fill `stage='plan'` and `planPath`, but `CreateIdeaBody` (TASK-001) only has `{title, priority, description}`. Neither the old nor new create endpoints accept these fields.

**Fix**: Add optional fields to TASK-001's `CreateIdeaBody`:
> "Add optional fields: stage (PipelineStage, default='idea'), plan_path (Optional[str], default=None). When plan_path is provided, create_idea() uses it instead of generating a new ideas/ path."

### W3. TASK-002 — `discover_unregistered_plans()` globs wrong directory

**Problem**: Description says glob `DOT_CLAUDE_DIR/'cache'/'plans'` but plans actually live at `DOT_CLAUDE_DIR/'.claude'/'cache'/'plans'` (the `.claude` segment is missing). The current path is `dot-claude/.claude/cache/plans/` which is `_CLAUDE_DIR / 'cache' / 'plans'`.

**Fix**: Change primary glob path in TASK-002:
> "Glob _CLAUDE_DIR / 'cache' / 'plans' (i.e., DOT_CLAUDE_DIR / '.claude' / 'cache' / 'plans') recursively for *.md files. Also check DOT_CLAUDE_DIR / 'cache' / 'plans' as pre-migration fallback."

### W4. TASK-002/TASK-006 — slug format mismatch (backend underscores vs frontend hyphens)

**Problem**: Frontend `toSlug()` produces `my-cool-idea` (hyphens). Backend `create_idea()` produces `my_cool_idea` (underscores). TASK-006's live filename preview uses frontend `toSlug()`, so preview won't match actual filename.

**Fix**: Add note to TASK-006 description:
> "The filename preview must use underscore-separated slugs matching the backend algorithm, not the existing toSlug() which uses hyphens. Create a toBackendSlug() utility or inline: `title.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')`"

### W5. TASK-008 — local `useMutation` breaks project hook convention

**Problem**: TASK-008 says "Use a local useMutation" for POST /pipeline/prompt, but the project pattern is all API hooks in `usePipeline.ts`.

**Fix**: Add `useSavePrompt()` to TASK-006's hook additions (alongside `useCreateIdea`, `useUnregisteredPlans`, `useRefreshPipeline`), and change TASK-008 to reference it instead of a local mutation.

---

## SUGGESTIONS (2)

### S1. Add "complete" vs "completed" note to supplement

Add a note to the supplement's "Autobuilder Working Copy Pattern" section:
> "Task status values in working copy PRDs use 'complete' (not 'completed'), 'in_progress', 'pending', 'blocked', 'deferred'."

### S2. TASK-004 — regex rule applies to file_classifier.py too

The file_classifier.py script (TASK-004) does substring matching and path filtering. If any regex is used internally, it must follow the same Pregex rules. Add a note to TASK-004:
> "Any pattern matching must use string methods or claude_core.regex_utils Pregex patterns, not raw re module."

---

## Verification

After applying all fixes:
1. Re-read `kanban-v2.json` and verify each fix is present
2. Verify dependency graph: TASK-001 → TASK-002 → TASK-003, TASK-004 (independent), TASK-005 (independent), TASK-006 → [TASK-003, TASK-005], TASK-007 → TASK-006, TASK-008 → TASK-003, TASK-009 → [TASK-007, TASK-008]
3. Grep for any remaining `re.sub` or `re.compile` in task descriptions
4. Verify no task description references `"completed"` (should all use `"complete"`)
5. Run `python -m json.tool autonomous-build/prd/kanban-v2.json` to validate JSON syntax
