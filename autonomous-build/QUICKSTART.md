# Quickstart Guide

**Get autonomous build running in 15 minutes**

## Prerequisites Check

```bash
python --version  # Need 3.10+
node --version    # Need 18+
git --version
```

## Installation

### 1. Extract Archive

```bash
cd your-project-repo
mkdir -p .claude
cd .claude
tar -xzf autonomous-build-system.tar.gz
cd autonomous-build
```

### 2. Install Dependencies

```bash
pip install anthropic pytest pytest-cov
```

### 3. Configure

```bash
cp config.example.json config.json
# Edit config.json - add your Claude API key
```

### 4. Lock Tests

```bash
chmod -R 444 tests/
```

### 5. Initialize Baseline

```bash
python oracle.py --init-baseline
```

## Phase 0: Quick Start (Knowledge Ingestion)

### Day 1: Interview Sessions (2-3 hours)

Gather domain knowledge through structured sessions:

**Session 1: Parameter File (30-60 min)**
- Input: Your application's parameter/config file
- Output: `templates/phase0-artifacts/parameter-schema.json`
- What: LLM extracts fields, types, validation rules, descriptions

**Session 2: Workflow Mapping (45-90 min)**  
- Input: Your narration of typical user workflows
- Output: `templates/phase0-artifacts/workflow-graph.json`
- What: Map commands, inputs, outputs, dependencies

**Session 3: Orchestration Scripts (30-60 min)**
- Input: Your existing bash/Python scripts for job management
- Output: `templates/phase0-artifacts/orchestration-spec.md`
- What: Document parallelization, SSH patterns, error handling

**Session 4: Confirmation (30-45 min)**
- Input: Outputs from sessions 1-3
- Output: `templates/phase0-artifacts/build-context-master.md`
- What: Resolve contradictions, confirm architecture, list assumptions

### Day 2: Autonomous Build (Overnight)

```bash
./orchestrator.py --phase 0 --max-iterations 100
```

**Let it run overnight. Wake up to:**
- Project scaffold (React + TypeScript + FastAPI)
- Form components generated from parameter schema
- Pipeline stepper UI from workflow graph
- Job submission backend with validation
- Basic orchestration endpoints

### Day 3: Review & Refine

```bash
# Check what happened
tail -n 100 orchestrator.log
git log --oneline -20
cat templates/ci-results.json | jq .
tail -n 50 templates/progress.txt

# If issues found, refine and resume
./orchestrator.py --phase 0 --max-iterations 50 --resume
```

## Phase 1: Quick Start (Mirror Build)

### Prerequisites

- Phase 0 complete (basic autonomous pipeline validated)
- Existing GUI application to replicate
- Screenshots of every UI state
- Workflow transcripts

### Day 1: Information Gathering (1-2 hours)

```bash
# Capture screenshots
mkdir -p docs/screenshots
# Save: main-window.png, dialogs/*.png, workflows/*.png

# Transcribe workflows
mkdir -p docs/workflows
# Write: 01-job-submission.md, 02-parameter-tuning.md, etc.

# Document component mapping
# Write: docs/component-map.md

# Define API contract
# Write: docs/api-contract.md
```

### Day 2: Populate PRD

Update `templates/prd.json` with Phase 1 tasks:

```json
{
  "id": "TASK-101",
  "title": "Replicate main window layout",
  "reference": {
    "screenshot": "docs/screenshots/main-window.png"
  }
}
```

### Day 3-7: Autonomous Replication

```bash
./orchestrator.py --phase 1 --max-iterations 200
```

**Daily review cycle:**
1. Morning: Check logs, review commits
2. Refine specs if agents misunderstood
3. Evening: Launch next autonomous run
4. Repeat until complete

## Phase 2: Quick Start (Enhancement)

### Prerequisites

- Phase 1 complete (working baseline validated)
- Design mockups/wireframes
- Feature specifications

### Process

Same as Phase 1, but:
- Update PRD with enhancement tasks
- Mark which Phase 1 tests to keep vs modify
- Unlock specific test files if behavior changing

## Common Patterns

### Daily Review Routine

```bash
# Morning review (5 minutes)
tail -100 orchestrator.log          # What happened overnight?
git log --oneline -20               # What got committed?
cat templates/ci-results.json | jq  # Oracle results

# If failures:
# 1. Check specific error in ci-results.json
# 2. Review if task needs splitting
# 3. Update prompts if pattern detected
# 4. Resume with refinements

./orchestrator.py --phase [N] --max-iterations 50 --resume
```

### When Tasks Fail Repeatedly

1. **Check task clarity**
   - Are screenshots high-res?
   - Is description specific?
   - Are acceptance criteria measurable?

2. **Check task size**
   - Too complex? Split into smaller units
   - Multiple responsibilities? Separate concerns

3. **Check context**
   - Missing reference material?
   - Ambiguous requirements?
   - Conflicting specs?

4. **Manual attempt**
   - Can YOU implement it in one sitting?
   - If not, agent probably can't either

### When to Intervene

**Let it run:**
- Occasional failures (retries working)
- Context usage <70%
- Progress being made

**Intervene:**
- Same task failing 3+ times
- Context exhaustion every task
- Cheating detected
- Oracle too strict/lenient

## Troubleshooting Quick Fixes

### "Tests being modified"

```bash
# Re-lock tests
chmod -R 444 tests/

# Verify
ls -la tests/  # Should show r--r--r--
```

### "Context filling too fast"

```python
# config.json
{
  "context_warning_threshold": 0.80,  # Increase from 0.70
  "context_split_threshold": 0.90     # Increase from 0.85
}
```

### "Oracle too strict"

```python
# oracle.py - adjust thresholds
# Line ~200: Coverage check
if current_cov >= baseline_cov - 2.0:  # Changed from 1.0
```

### "QA and Dev disagree constantly"

1. Add more examples to prompts
2. Improve screenshot quality
3. Add workflow videos/annotations
4. Simplify tasks

## Success Metrics

**After each phase, you should see:**

✅ >80% tasks completed automatically  
✅ <3 average retries per task  
✅ <10% tasks requiring manual intervention  
✅ Oracle pass rate >90%  
✅ Context splitting <20% of tasks

**If not hitting these, refine:**
- Prompts (add examples)
- Task decomposition (smaller units)
- Reference materials (better screenshots)
- Oracle thresholds (calibrate)

## Next Steps

1. **Complete Phase 0** on simpler application (emClarity GUI)
2. **Learn patterns** from Phase 0 success/failure
3. **Apply to Phase 1** on target application (CryoPrior GUI)
4. **Refine system** based on real usage
5. **Phase 2** once foundation solid

**Remember:** Multi-pass execution. Each overnight run reveals new patterns. Iterate.
