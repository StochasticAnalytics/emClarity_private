# Autonomous Build System — Complete Archive

**Version:** 1.0  
**Date:** March 11, 2026  
**Purpose:** AI agent-based autonomous development framework for scientific computing GUI applications

---

## Quick Links

- **[QUICKSTART.md](QUICKSTART.md)** - Get running in 15 minutes
- **[SETUP.md](SETUP.md)** - Detailed installation guide
- **[guides/PHASE_0_GUIDE.md](guides/PHASE_0_GUIDE.md)** - Knowledge ingestion workflow
- **[guides/PHASE_1_GUIDE.md](guides/PHASE_1_GUIDE.md)** - Mirror build workflow
- **[guides/PHASE_2_GUIDE.md](guides/PHASE_2_GUIDE.md)** - Enhancement workflow

## What This Is

An autonomous multi-agent development framework that:

1. **Uses adversarial agents** (Developer vs QA) with external validation
2. **Prevents cheating** through hard constraints (read-only tests, external oracle)
3. **Manages context exhaustion** via intelligent task splitting
4. **Runs multi-day builds** through external orchestration loop
5. **Learns from failures** via structured post-phase reviews

Based on patterns from: ImpossibleBench, Ralph-Wiggum/Lisa Loops, Agyn multi-agent system, Praetorian context gates.

## Three-Phase Strategy

**Phase 0: Knowledge Ingestion (Proving Ground)**  
Build simpler application (e.g., emClarity GUI) to validate pipeline. Conduct structured interviews to extract domain knowledge into machine-readable artifacts.

**Phase 1: Mirror Build**  
Replicate existing application (e.g., CryoPrior wxWidgets GUI) exactly in modern stack. Fixed requirements validate architecture before creative decisions.

**Phase 2: Enhancement**  
Apply new UX design to validated components. Innovation on proven foundation.

## Core Architecture

```
Developer Agent (Claude Code)
    ↓ implements task, commits code
QA Agent (separate context, read-only)
    ↓ reviews diff, flags defects
External Oracle (Python script)
    ↓ validates (TS compile, pytest, E2E, immutability)
Orchestrator (Python loop)
    ↓ coordinates, monitors context, splits tasks
```

**Key Principles:**

1. **Assume adversarial behavior** - Agents will cheat without hard constraints
2. **Hard constraints over prompts** - File permissions, external validation
3. **Fresh sessions via external loop** - No in-memory state
4. **No shared Dev/QA context** - Independent review
5. **Context-aware task splitting** - Before overflow degrades quality
6. **Multi-pass execution** - Run, review, refine, repeat

## Directory Structure

```
.claude/autonomous-build/
├── README.md                          # This file
├── QUICKSTART.md                      # Recipe-style usage guide
├── SETUP.md                           # Installation & first-run
│
├── orchestrator.py                    # Main orchestration loop
├── oracle.py                          # External validation script
├── task_splitter.py                   # Intelligent task decomposition
├── requirements.txt                   # Python dependencies
│
├── prompts/
│   ├── developer-prompt.md            # Dev agent instructions
│   └── qa-prompt.md                   # QA agent instructions
│
├── hooks/
│   ├── stop-hook.sh                   # Blocks premature completion
│   └── pre-commit-hook.sh             # Pre-commit validation
│
├── templates/
│   ├── prd.json                       # Task list structure
│   ├── progress.txt                   # Cross-iteration memory
│   ├── ci-results.json                # Oracle output format
│   ├── phase0-artifacts/              # Phase 0 interview outputs
│   └── interview-session-guides/      # Phase 0 question templates
│
├── guides/
│   ├── PHASE_0_GUIDE.md               # Phase 0: Knowledge ingestion
│   ├── PHASE_1_GUIDE.md               # Phase 1: Mirror build
│   ├── PHASE_2_GUIDE.md               # Phase 2: Enhancement
│   └── LESSONS_LEARNED_TEMPLATE.md    # Post-phase review
│
└── config.example.json                # Agent team configuration
```

## Quick Start

```bash
# 1. Extract
cd your-project-repo/.claude
tar -xzf autonomous-build-system.tar.gz
cd autonomous-build

# 2. Install
pip install -r requirements.txt

# 3. Configure
cp config.example.json config.json
# Edit config.json - add Claude API key

# 4. Lock tests
chmod -R 444 tests/

# 5. Initialize
python oracle.py --init-baseline

# 6. Run Phase 0
./orchestrator.py --phase 0 --max-iterations 100
```

See [QUICKSTART.md](QUICKSTART.md) for detailed walkthrough.

## How It Works

### Multi-Pass Execution

1. **Pass 1: Initial Build**
   - Orchestrator reads task from PRD
   - Launches Developer agent (fresh context)
   - Developer implements, commits
   - Launches QA agent (separate fresh context)
   - QA reviews, flags defects or approves
   - Oracle validates (external Python script)
   - If pass: mark complete, next task
   - If fail: retry or split based on context usage
   - Repeat until max iterations

2. **Pass 2-N: Refinement**
   - Review logs, commits, failures
   - Identify patterns (missing context, vague specs, oversized tasks)
   - Update prompts/PRD/reference materials
   - Resume with `--resume` flag
   - Converge toward completion

### Context-Aware Task Splitting

LLM sessions have fixed context windows. As sessions accumulate code/feedback/errors, context fills and quality degrades.

**Orchestrator monitors context usage:**
- <50%: Normal operation
- 50-70%: Monitor for convergence
- 70-85%: Prepare to split if retry fails
- >85%: Immediate split, spawn fresh sessions

**Splitting strategies:**
- **Vertical:** UI component vs backend endpoint
- **Horizontal:** Happy path vs error handling
- **Dependency-first:** Data model then implementation
- **Simplify:** Minimal version first, full version later

### Adversarial Review Architecture

**Developer Agent:**
- Full filesystem access (read/write/edit)
- Can run commands, tests
- **Cannot** modify `tests/` (read-only)
- **Cannot** modify `oracle.py`
- Evaluated on delivering passing code

**QA Agent:**
- Read-only access
- Separate context (doesn't know Developer's reasoning)
- Reviews git diff + task spec only
- **First checks for cheating** (test mods, operator overloads, hardcoded values)
- Then checks spec compliance
- Maximum 2 rounds per task

**External Oracle:**
- Python script, runs as subprocess
- Validates: TypeScript compile, pytest backend, pytest E2E, test immutability, assert count, coverage
- Unforgeable (agents cannot modify it or fake its output)
- Provides ground truth when Dev/QA disagree

## Phase 0: Knowledge Ingestion

**Goal:** Extract domain knowledge into machine-readable artifacts before autonomous build.

**Four Interview Sessions:**

1. **Parameter File Deep Dive (30-60 min)**
   - Input: Raw parameter file
   - Output: `parameter-schema.json`
   - Extracts field types, defaults, validation, grouping

2. **Workflow & Command Map (45-90 min)**
   - Input: Narration of typical usage
   - Output: `workflow-graph.json`
   - Maps commands, inputs, outputs, dependencies

3. **Bash Scripts Audit (30-60 min)**
   - Input: Existing orchestration scripts
   - Output: `orchestration-spec.md`
   - Catalogs SSH patterns, parallelization, error handling

4. **Architecture Confirmation (30-45 min)**
   - Input: Sessions 1-3 outputs
   - Output: `build-context-master.md`
   - Resolves contradictions, confirms component map, lists assumptions

**Result:** Autonomous agent receives complete context, minimal ambiguity blockers.

See [guides/PHASE_0_GUIDE.md](guides/PHASE_0_GUIDE.md) for detailed workflow.

## Phase 1: Mirror Build

**Goal:** Replicate existing GUI exactly in modern stack (React/TypeScript + FastAPI).

**Information Gathering:**
1. Screenshot collection (every window, dialog, state)
2. Workflow transcription (step-by-step user interactions)
3. Component mapping (original framework → React equivalents)
4. API contract (endpoint specs)
5. Test suite baseline (lock `tests/`, record metrics)

**Agent Input:**
- All screenshots in `docs/screenshots/`
- All workflows in `docs/workflows/`
- `docs/component-map.md`
- `docs/api-contract.md`
- Locked tests with baseline metrics

See [guides/PHASE_1_GUIDE.md](guides/PHASE_1_GUIDE.md) for detailed workflow.

## Phase 2: Enhancement

**Goal:** Apply new UX design to validated Phase 1 components.

**Information Gathering:**
1. Design spec review (mockups, wireframes)
2. Feature specification (user stories, acceptance criteria)
3. Migration plan (which tests keep vs update)

**Agent Input:**
- Working Phase 1 baseline
- Design specifications
- Feature specs
- Updated PRD with Phase 2 tasks

See [guides/PHASE_2_GUIDE.md](guides/PHASE_2_GUIDE.md) for detailed workflow.

## File Formats

### PRD (Task List)

```json
{
  "_metadata": {
    "phase": "0",
    "created": "2026-03-11T12:00:00Z"
  },
  "tasks": [
    {
      "id": "TASK-001",
      "title": "Project scaffold setup",
      "description": "Initialize React + TypeScript + Vite + FastAPI",
      "type": "infrastructure",
      "status": "pending",
      "depends_on": [],
      "reference": null,
      "acceptance_criteria": [
        "TypeScript compiles",
        "Dev server starts",
        "FastAPI server starts"
      ]
    }
  ]
}
```

### Progress Log

```
=== ORCHESTRATOR RUN STARTED ===
Phase: 0
Start time: 2026-03-11 12:00:00

=== TASK-001: Project scaffold setup ===
Assigned: 2026-03-11 12:05:00
Developer: Completed 12:23:00 (18 minutes)
  - Initialized Vite + React + TypeScript
  - Set up FastAPI backend
QA Round 1: PASS
Oracle: PASS
Status: COMPLETE
Iterations consumed: 2
```

### Oracle Results

```json
{
  "task_id": "TASK-001",
  "timestamp": "2026-03-11T12:23:00Z",
  "passed": true,
  "checks": [
    {"name": "typescript", "passed": true, "duration_ms": 1234},
    {"name": "backend_tests", "passed": true, "duration_ms": 5678},
    {"name": "e2e_tests", "passed": true, "duration_ms": 12345},
    {"name": "test_immutability", "passed": true},
    {"name": "assert_count", "passed": true, "baseline": 247, "current": 247},
    {"name": "coverage", "passed": true, "baseline": 78.3, "current": 78.5}
  ]
}
```

## Troubleshooting

### Tests Being Modified

```bash
# Re-lock tests
chmod -R 444 tests/

# Verify
ls -la tests/  # Should show r--r--r--
```

### Tasks Failing Repeatedly

1. Check `ci-results.json` for specific error
2. Review task description clarity
3. Check reference material quality
4. Manually attempt task - is it achievable?
5. Consider splitting into smaller sub-tasks

### Context Exhaustion

```python
# config.json - adjust thresholds
{
  "context_warning_threshold": 0.80,  # from 0.70
  "context_split_threshold": 0.90     # from 0.85
}
```

### Oracle Too Strict/Lenient

Edit `oracle.py` validation thresholds (coverage drop tolerance, timeout limits, etc.)

## Daily Review Workflow

```bash
# Morning review
tail -n 100 orchestrator.log
git log --oneline -20
cat ci-results.json | jq .
tail -n 50 progress.txt

# Decide action
# - Continue: ./orchestrator.py --phase N --max-iterations 50 --resume
# - Refine: Edit prompts/PRD, then resume
# - Next phase: Complete review, start next phase
```

## Success Metrics

**Target per phase:**
- >80% tasks completed automatically
- <3 average retries per task
- <10% manual intervention
- >90% oracle pass rate
- <20% context splitting

## References

- [1] ImpossibleBench: LLMs cheat 50-76% without constraints
- [2] Ralph Wiggum Loop: External orchestration for multi-day runs
- [3] Ralph-Lisa Loop: Adversarial dual-agent architecture
- [4] Agyn Multi-Agent: 72.4% SWE-bench via hierarchical supervision
- [5] Praetorian Patterns: Context gates and tool boundaries

## License

Provided as-is for internal use. Adapt as needed.

---

**For complete system reference, see sections above.**  
**For quick start, see [QUICKSTART.md](QUICKSTART.md).**  
**For installation, see [SETUP.md](SETUP.md).**
