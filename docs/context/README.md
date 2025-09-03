# emClarity Development Context

This directory contains key documentation and guidelines for working with emClarity. Reference this when working with AI assistants or new team members.

## Core Documentation Files

### Development Guidelines

- `../PYTHON_STYLE_GUIDE.md` - Python coding standards and examples
- `../.clang-format` - C++ formatting configuration
- `copilot-instructions.md` - AI assistant behavioral guidelines and critical rules
- `python_conversion_instructions.md` - Guidelines for converting MATLAB to Python

### Project Documentation

- `../emClarity_Tutorial.md` - Main tutorial and usage guide
- `GUI_IMPLEMENTATION_SUMMARY.md` - GUI architecture and design decisions
- `agent_notes.md` - Accumulated notes from development sessions

## Quick Reference for AI Assistants

Instead of specifying individual files, you can reference:

```markdown
#file:docs/context/MAIN_CONTEXT.md
```

This will provide the AI assistant with pointers to all relevant context files, and they can then read the specific files they need for the current task.

## Usage Pattern

1. Start conversations by referencing this README
2. AI assistant reads this index and determines which specific files to load
3. Reduces repetitive file specifications while maintaining access to all context
