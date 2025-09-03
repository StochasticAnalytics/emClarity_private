# Copilot Rules

## Project specific goals

- emClarity is an application written in matlab and also uses mex and mexCuda for high-performance computing tasks, particularly in the field of cryo-electron microscopy (cryo-EM).
- The original application is entirely command line driven, and our goal is to build a simple Pyside6 GUI to facilitate user interaction with the underlying functionality.
- The GUI should provide a user-friendly interface for configuring and running cryo-EM data processing workflows.
- As we develop, we want to clean up and simplify code as well as adding tests to ensure functionality and prevent regressions.

## Copilot Behavior

- Copilot should activate and within virtual environment when working with python.
- Copilot should provide concise and relevant code suggestions.
- Copilot should avoid suggesting large blocks of code without context.
- Copilot should prioritize user intent and project context in its suggestions.

## Copilot code preferences

- Copilot should generate code that is idiomatic to the programming language being used.
- Copilot should prefer built-in language features and standard libraries over external dependencies.
- Copilot should aim for simplicity and clarity in its code suggestions.
- Copilot should never hard-code variables and instead place them in a relevant configuration file or environment variable.
- Copilot should strive for consistency in naming conventions and code style, and use descriptive names for variables and functions.
- Copilot should not allow default values or other design patterns that could lead to ambiguity or confusion.
- Copilot should prefer to fail fast and descriptively.

## Special prompts

- If copilot is asked to work on a rb prompt or a rubber band prompt, it should look in /tmp/emclarity_gui_prompts for the most recent prompt generated with the rubber band tool and use the text and context provided for the next set of work.

## Critical Development Rules

- **Never replace real panels/widgets with dummy versions**: Before swapping out any functional panel or widget for a placeholder, stub, or dummy version, always check with the user first. Real functionality should be preserved unless explicitly requested to be removed.

- **Never alter production database**: Never modify the database schema or delete/alter contents of the production database for development purposes. Always work on copies of the database when testing or debugging. Use commands like `cp emclarity_gui_state.db emclarity_gui_state_backup.db` before any database operations.

- **All temporary files must go in /tmp/copilot-test/**: Never create temporary test files, demo data, or experimental files directly in the project directories. Always use `/tmp/copilot-test/` for any temporary files during development and testing. This keeps the project clean and prevents accidental commits of temporary data.

- Start with the simplest solution and if you think you need to be more creative or expand scope, explain why and we can discuss if we proceed.

- Following any major work, like a GUI rubber band prompt, you should check to see if we are satisified, if so create a WIP commit with a short message using git. But only with permission!


## Development Environment Notes

- **Project Location**: `/sa_shared/git/emClarity/`
- **Virtual Environment**: `.venv/` in project root
- **GUI Location**: `gui/` subdirectory
- **Qt Platform**: Use `QT_QPA_PLATFORM=xcb` for stability
- **Branch**: `ctf3d_work`

## emClarity GUI Development - Key Learnings & Best Practices

*Generated from GUI development session on August 26, 2025*

### Key Learnings for Future GUI Development Sessions

#### 1. **Virtual Environment Context Management**

**Problem**: Frequently forgot to activate the virtual environment when testing Python imports or running the GUI, leading to import errors and wasted debugging time.

**Solution Pattern**:
```bash

# Always use this pattern for Python testing in emClarity
cd /sa_shared/git/emClarity && source .venv/bin/activate && cd gui && python -c "..."

# For GUI launches
cd /sa_shared/git/emClarity && source .venv/bin/activate && cd gui && QT_QPA_PLATFORM=xcb python main.py &

# When launching the gui for testing, always launch in rubberband mode that way I can add more context if needed.
source .venv/bin/activate ./gui/run_gui.sh --rubber-band-mode
```

**Impact**: This pattern eliminates 80% of "import not found" errors and ensures consistent testing environment.

---

#### 2. **Incremental GUI Testing with State Cleanup**

**Problem**: Making multiple changes before testing led to complex debugging when things broke. Also, GUI processes would accumulate without proper cleanup.

**Solution Pattern**:
```bash

# Always kill existing GUI processes before launching new ones
pkill -f "python main.py"

# Then launch fresh instance
cd /sa_shared/git/emClarity && source .venv/bin/activate && cd gui && QT_QPA_PLATFORM=xcb python main.py &
```

**Impact**: This approach caught errors early (e.g., the toggle_keep_on_top parameter issue, import errors) and prevented GUI state conflicts.

---

#### 3. **File Context Awareness for Complex Edits**

**Problem**: When making large-scale changes (like the parameter system rewrite), I sometimes lost track of file state and made edits that corrupted files or created inconsistencies.

**Solution Pattern**:
```python

# Before major file restructuring, always read current state
read_file(file_path, start_line=1, end_line=50)  # Check current structure

# For complex replacements, verify the exact context
grep_search(pattern, include_pattern=file_path)  # Find exact locations

# After major edits, immediately test key functionality
python -c "from module import Class; test_basic_functionality()"
```

**Impact**: This prevented the parameters.py file corruption incident and caught the unit/scaling issues early in development.

#### 4. What Worked Well in a second session:

- Iterative development approach with small, focused changes
- Database design with composite keys for robust copy/paste functionality
- IMOD tool integration with subprocess management and real-time validation
- Python multiprocessing implementation with shared memory and queue communication
- Project-aware state management with tab notification system

---

#### 5. **Session 3 Learnings: Rubber Band Tool & Advanced UI Development**

*Key insights from August 27, 2025 - Rubber Band selection tool and UI refinement session*

**A. Layout Clearing vs Stacked Widget Approach**

**Problem**: Attempted to implement dynamic panel switching by clearing and rebuilding Qt layouts, which caused segmentation faults and loss of widget state.

**Dead End Approach**:
```python
# This approach failed - caused crashes and state loss
def clear_layout(self):
    layout = self.layout()
    while layout.count():
        child = layout.takeAt(0)
        child.widget().setParent(None)  # Too aggressive
```

**Successful Solution**:
```python
# QStackedWidget approach - preserves widget state
self.stacked_widget = QStackedWidget()
# Create all panels once at startup
self.tilt_series_panel = self.create_tilt_series_alignment_panel()
self.stacked_widget.addWidget(self.tilt_series_panel)
# Switch panels without destroying them
self.stacked_widget.setCurrentWidget(self.tilt_series_panel)
```

**Key Learning**: For complex widget switching, use QStackedWidget to preserve state rather than destroying/recreating layouts.

---

**B. Iterative Problem Solving Pattern**

**Effective Cycle**: 
1. Small incremental changes (single button, single UI element)
2. Immediate testing with `./gui/run_gui.sh --rubber-band-mode`
3. Quick verification through rubber band tool analysis
4. Fix issues before proceeding to next change

**Example Success**: Through 3 rubber band prompts, we successfully:
- Fixed title text cutoff (removed constraining CSS)
- Added "Averaging" button and increased font sizes
- Implemented complete Actions panel with dynamic switching

**Impact**: This iterative approach prevented large-scale rollbacks and caught UI issues immediately.

---

**C. Function Key Reliability Issues**

**Problem**: F1 key functionality was unreliable across different environments/terminals.

**Solution Evolution**:
- F1 → F15 → ESC key (for rubber band) + L key (for click logging)
- Simple keys (ESC, L) proved much more reliable than function keys
- Used ESC for toggle (natural "cancel" association)
- Used L for "Logging" (mnemonic association)

**Learning**: Avoid function keys for critical features; prefer simple letter keys with clear mnemonics.

---

**D. Rubber Band Tool as Development Multiplier**

**Breakthrough**: The rubber band tool became a development force multiplier by:
- Generating AI-friendly prompts with precise coordinates
- Moving REQUEST section to top of prompts (eliminated scrolling)
- Enabling rapid UI issue identification and fixes
- Providing structured context for AI assistance

**Workflow Innovation**: "Use rubber band tool to identify issues → Generate prompt → Apply AI-suggested fixes → Test with rubber band tool again"

**Impact**: This created a feedback loop that accelerated UI development significantly.

---

**E. File Organization & Cleanup Best Practices**

**Pattern**: Regular cleanup prevents project bloat:
```bash
# Organize test files
mkdir gui/tests gui/docs
mv test_*.py gui/tests/
mv *_GUIDE.md *_SUMMARY.md gui/docs/

# Remove dead-end files
rm unused_temp_files.py duplicate_new_versions.py

# Check for unused imports before removing
grep -r "import filename" gui/*.py
```

**Learning**: Regular file organization prevents confusion and makes project navigation easier for both human and AI collaborators.

---
