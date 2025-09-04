#!/bin/bash
# Local Python code quality checker for emClarity
# Run this script to perform the same checks as CI locally
# Usage: ./scripts/check-python-quality.sh [--fix] [--fast]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default options
FIX_ISSUES=false
FAST_MODE=false
PYTHON_DIR="python"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --fix)
            FIX_ISSUES=true
            shift
            ;;
        --fast)
            FAST_MODE=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [--fix] [--fast]"
            echo "  --fix   Automatically fix issues where possible"
            echo "  --fast  Skip slower checks (bandit, safety)"
            exit 0
            ;;
        *)
            echo "Unknown parameter: $1"
            exit 1
            ;;
    esac
done

# Check if we're in the right directory
if [[ ! -f "pyproject.toml" ]] || [[ ! -d "$PYTHON_DIR" ]]; then
    echo -e "${RED}Error: Must be run from emClarity root directory${NC}"
    exit 1
fi

# Check if tools are installed
echo -e "${BLUE}Checking tool availability...${NC}"
MISSING_TOOLS=()

if ! command -v ruff &> /dev/null; then
    MISSING_TOOLS+=("ruff")
fi

if ! command -v pyright &> /dev/null; then
    MISSING_TOOLS+=("pyright")
fi

if [[ "$FAST_MODE" == "false" ]]; then
    if ! command -v bandit &> /dev/null; then
        MISSING_TOOLS+=("bandit")
    fi
    
    if ! command -v safety &> /dev/null; then
        MISSING_TOOLS+=("safety")
    fi
fi

if [[ ${#MISSING_TOOLS[@]} -gt 0 ]]; then
    echo -e "${RED}Missing tools: ${MISSING_TOOLS[*]}${NC}"
    echo -e "${YELLOW}Install with: pip install ruff pyright bandit[toml] safety${NC}"
    exit 1
fi

echo -e "${GREEN}All tools available!${NC}"
echo

# Track overall status
OVERALL_STATUS=0

# Function to run a check
run_check() {
    local name="$1"
    local command="$2"
    local fix_command="$3"
    
    echo -e "${BLUE}==================== $name ====================${NC}"
    
    if [[ "$FIX_ISSUES" == "true" && -n "$fix_command" ]]; then
        echo -e "${YELLOW}Running with auto-fix...${NC}"
        if eval "$fix_command"; then
            echo -e "${GREEN}✓ $name (fixed)${NC}"
        else
            echo -e "${RED}✗ $name (fix failed)${NC}"
            OVERALL_STATUS=1
        fi
    else
        if eval "$command"; then
            echo -e "${GREEN}✓ $name${NC}"
        else
            echo -e "${RED}✗ $name${NC}"
            OVERALL_STATUS=1
        fi
    fi
    echo
}

# Run Ruff linting
run_check "Ruff Linting" \
    "ruff check $PYTHON_DIR/" \
    "ruff check $PYTHON_DIR/ --fix"

# Run Ruff formatting
run_check "Ruff Formatting" \
    "ruff format --check --diff $PYTHON_DIR/" \
    "ruff format $PYTHON_DIR/"

# Run type checking
run_check "Type Checking (Pyright)" \
    "pyright $PYTHON_DIR/" \
    ""

# Run security checks (unless in fast mode)
if [[ "$FAST_MODE" == "false" ]]; then
    run_check "Security Scanning (Bandit)" \
        "bandit -r $PYTHON_DIR/ -ll" \
        ""
    
    run_check "Dependency Vulnerabilities (Safety)" \
        "safety check" \
        ""
fi

# Summary
echo -e "${BLUE}==================== SUMMARY ====================${NC}"
if [[ $OVERALL_STATUS -eq 0 ]]; then
    echo -e "${GREEN}All checks passed! 🎉${NC}"
else
    echo -e "${RED}Some checks failed. See output above for details.${NC}"
    echo -e "${YELLOW}Tip: Run with --fix to automatically fix some issues${NC}"
fi

exit $OVERALL_STATUS
