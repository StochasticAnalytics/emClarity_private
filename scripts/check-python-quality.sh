#!/bin/bash

# Local Python Code Quality Checker for emClarity
# Runs the same checks as CI workflows but locally
# Supports --fix for auto-fixing and focused check options

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default settings
SHOULD_FIX=false
FAST_MODE=false
RUN_STYLE=true
RUN_TYPES=true
RUN_SECURITY=true

# Parse arguments
for arg in "$@"; do
    case $arg in
        --fix)
            SHOULD_FIX=true
            shift
            ;;
        --fast)
            FAST_MODE=true
            shift
            ;;
        --style-only)
            RUN_TYPES=false
            RUN_SECURITY=false
            shift
            ;;
        --types-only)
            RUN_STYLE=false
            RUN_SECURITY=false
            shift
            ;;
        --security-only)
            RUN_STYLE=false
            RUN_TYPES=false
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --fix           Auto-fix issues where possible"
            echo "  --fast          Skip slower checks (no security scan)"
            echo "  --style-only    Run only Ruff style/linting checks"
            echo "  --types-only    Run only Pyright type checking"
            echo "  --security-only Run only security scans"
            echo "  --help          Show this help message"
            echo ""
            echo "Mirrors the CI workflows:"
            echo "  - Code Style (.github/workflows/code-style.yml)"
            echo "  - Type Checking (.github/workflows/type-checking.yml)"  
            echo "  - Security Scan (.github/workflows/security-scan.yml)"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown argument: $arg${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Fast mode disables security scanning
if [ "$FAST_MODE" = true ]; then
    RUN_SECURITY=false
fi

# Check if we're in the right directory
if [[ ! -f "pyproject.toml" ]] || [[ ! -d "python" ]]; then
    echo -e "${RED}Error: Must be run from emClarity root directory${NC}"
    exit 1
fi

echo -e "${BLUE}==================== Code Quality Check ====================${NC}"
echo "Checking tool availability..."

# Check if required tools are installed
MISSING_TOOLS=()

if [ "$RUN_STYLE" = true ]; then
    if ! command -v ruff &> /dev/null; then
        MISSING_TOOLS+=("ruff")
    fi
fi

if [ "$RUN_TYPES" = true ]; then
    if ! command -v pyright &> /dev/null; then
        MISSING_TOOLS+=("pyright")
    fi
fi

if [ "$RUN_SECURITY" = true ]; then
    if ! command -v bandit &> /dev/null; then
        MISSING_TOOLS+=("bandit")
    fi
    if ! command -v safety &> /dev/null; then
        MISSING_TOOLS+=("safety")
    fi
fi

if [ ${#MISSING_TOOLS[@]} -ne 0 ]; then
    echo -e "${RED}Missing required tools: ${MISSING_TOOLS[*]}${NC}"
    echo "Install with: pip install ${MISSING_TOOLS[*]}"
    exit 1
fi

echo -e "${GREEN}All required tools available!${NC}"
echo ""

# Exit codes for each check
STYLE_EXIT=0
TYPES_EXIT=0  
SECURITY_EXIT=0

# Code Style Checks (Ruff)
if [ "$RUN_STYLE" = true ]; then
    echo -e "${BLUE}==================== Code Style (Ruff) ====================${NC}"
    
    if [ "$SHOULD_FIX" = true ]; then
        echo -e "${YELLOW}Auto-fixing with Ruff...${NC}"
        ruff check python/ --fix || STYLE_EXIT=$?
        ruff format python/ || STYLE_EXIT=$?
        echo -e "${GREEN}Ruff auto-fixes applied${NC}"
    else
        echo -e "${YELLOW}Checking code style...${NC}"
        ruff check python/ || STYLE_EXIT=$?
        ruff format --check --diff python/ || STYLE_EXIT=$?
    fi
    echo ""
fi

# Type Checking  
if [ "$RUN_TYPES" = true ]; then
    echo -e "${BLUE}==================== Type Checking (Pyright) ====================${NC}"
    pyright python/ || TYPES_EXIT=$?
    echo ""
fi

# Security Scanning
if [ "$RUN_SECURITY" = true ]; then
    echo -e "${BLUE}==================== Security Scan ====================${NC}"
    
    echo -e "${YELLOW}Running Bandit security scan...${NC}"
    bandit -r python/ -f txt || SECURITY_EXIT=$?
    
    echo -e "${YELLOW}Running Safety dependency scan...${NC}"
    safety check || SECURITY_EXIT=$?
    echo ""
fi

# Summary
echo -e "${BLUE}==================== SUMMARY ====================${NC}"

if [ "$RUN_STYLE" = true ]; then
    if [ $STYLE_EXIT -eq 0 ]; then
        echo -e "  - Code Style: ${GREEN}✓ Passed${NC}"
    else
        echo -e "  - Code Style: ${RED}❌ Failed${NC}"
    fi
fi

if [ "$RUN_TYPES" = true ]; then
    if [ $TYPES_EXIT -eq 0 ]; then
        echo -e "  - Type Checking: ${GREEN}✓ Passed${NC}"
    else
        echo -e "  - Type Checking: ${RED}❌ Failed${NC}"
    fi
fi

if [ "$RUN_SECURITY" = true ]; then
    if [ $SECURITY_EXIT -eq 0 ]; then
        echo -e "  - Security Scan: ${GREEN}✓ Passed${NC}"
    else
        echo -e "  - Security Scan: ${RED}❌ Failed${NC}"
    fi
fi

echo ""
if [ $STYLE_EXIT -eq 0 ] && [ $TYPES_EXIT -eq 0 ] && [ $SECURITY_EXIT -eq 0 ]; then
    echo -e "${GREEN}All checks passed! 🎉${NC}"
    exit 0
else
    echo -e "${RED}Some checks failed. See output above for details.${NC}"
    if [ "$SHOULD_FIX" = false ]; then
        echo -e "${YELLOW}Tip: Run with --fix to automatically fix some issues${NC}"
    fi
    exit 1
fi
