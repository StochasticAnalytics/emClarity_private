# emClarity Main Context File

This file aggregates key development context for AI assistants working on emClarity.

## Quick Start for AI Assistants

Read these files for complete context:

- `../PYTHON_STYLE_GUIDE.md` - Essential Python coding standards
- `../emClarity_Tutorial.md` - Project overview and usage
- `copilot-instructions.md` - AI assistant behavioral guidelines and critical rules
- `python_conversion_instructions.md` - MATLAB to Python conversion guidelines
- `GUI_IMPLEMENTATION_SUMMARY.md` - GUI architecture
- `agent_notes.md` - Accumulated development insights

## Key Development Rules Summary

### Critical Rules (from copilot-instructions.md)

- **Never replace real panels/widgets with dummy versions** without user approval
- **Never alter production database** - always work on copies
- **All temporary files must go in /tmp/copilot-test/** - never in project directories
- **All development scripts (testing, migration, etc.) must go in /tmp/agent-tmp/** - never in project directories
- Start with simplest solutions and explain if scope needs expansion

### Python Development

- Use Black + isort with pyproject.toml configuration
- Follow PEP 8 with 88-character line length
- Use type hints consistently
- Prefer f-strings over .format() or % formatting

### MATLAB to Python Conversion (from python_conversion_instructions.md)

- Mirror directory structure: `metaData/BH_file.m` → `python/metaData/emc_file.py`
- Use `emc_` prefix for Python modules
- Create unit tests in `python/folderName/tests/`
- Update README.md files and agent_notes.md
- For CUDA: use `extern "C"` wrapper, prefer int to uint
- **Always use Fortran-style (column-major) CuPy arrays** - construct with `order='F'`
- **Never use ambiguous terms like rows/columns** - use nx/ny/nz consistently
- **Wrap library call outputs with ensure_f()** to catch memory layout issues

### Git Workflow

- Work on feature branches (like ctf3d_work)
- Ensure CI passes before merging
- Use descriptive commit messages

### AI Assistant Guidelines

- Always run linting checks locally before committing
- Test changes comprehensively
- Read full file context before making edits
- Use proper tool selection (replace_string_in_file vs edit_notebook_file)
- **Execute independent operations in parallel** - invoke relevant tools simultaneously for efficiency
- **Create general-purpose solutions** - implement code that handles all valid inputs, not just test cases
- **Avoid hard-coding values** - solutions should be robust, maintainable, and extendable
- **Focus on algorithm correctness** - understand requirements before implementation
- **Raise concerns about incorrect tests** - if tests seem wrong, communicate this clearly

### Implementation Principles

- **Algorithm first, tests second** - Tests verify correctness but don't define the solution
- **Focus on maintainability** - Write clean, well-documented code following established patterns
- **Design for the general case** - Solutions should handle edge cases and unusual inputs
- **Apply software design principles** - Use proper abstractions, separation of concerns
- **Report infeasibility** - If a task seems unreasonable or has contradictory requirements, communicate this
- **Maximize parallel operations** - When gathering context or performing multiple edits, batch operations

## File Locations

Key files are organized as:

```text
emClarity/
├── PYTHON_STYLE_GUIDE.md              # Python coding standards
├── .clang-format                       # C++ formatting
├── pyproject.toml                      # Python tool configuration
├── docs/
│   ├── emClarity_Tutorial.md           # Main documentation
│   └── context/                        # This directory
│       ├── MAIN_CONTEXT.md             # This file
│       ├── copilot-instructions.md     # AI assistant rules
│       ├── python_conversion_instructions.md # MATLAB→Python guidelines
│       ├── GUI_IMPLEMENTATION_SUMMARY.md
│       └── agent_notes.md
└── python/gui/prompts/                 # AI assistant context files
```

Reference this file as: `#file:docs/context/MAIN_CONTEXT.md`
