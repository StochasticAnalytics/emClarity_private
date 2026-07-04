"""Layer purity: domain-free ``core/`` never couples to a sibling domain package (DESIGN §0/§1.6).

The ``core`` is pure geometry/tensor and "never mentions emClarity or mitochondria". Two rules:

* ``core/`` must NOT import ``emclarity`` at all (not even type-only) -- that was the finding-2/6
  bug (``core.points`` imported ``emclarity.constants``), a bidirectional cycle.
* ``core/`` must NOT have a RUNTIME import of any other sibling domain package (a ``TYPE_CHECKING``
  forward-reference for provenance typing, e.g. ``fields.provider``, is allowed -- it is type-only
  and creates no runtime coupling / import cycle).

This walks every ``core/*.py`` AST and enforces both.
"""

from __future__ import annotations

import ast
from pathlib import Path

import mito_filter

_CORE_DIR = Path(mito_filter.__file__).parent / "core"
_DOMAIN_SIBLINGS = {
    "emclarity",
    "fields",
    "constraints",
    "features",
    "scan",
    "model",
    "candidates",
    "exec",
    "datasets",
    "optimize",
    "validate",
}


def _is_type_checking_test(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _sibling_head(node: ast.AST) -> str | None:
    """Return the mito_filter domain-sibling package a `from ...`/`import ...` targets, or None."""
    if isinstance(node, ast.ImportFrom):
        if node.level >= 2 and node.module:  # relative `from ..emclarity...`
            head = node.module.split(".")[0]
            if head in _DOMAIN_SIBLINGS:
                return head
        if node.module and node.module.startswith("mito_filter."):
            head = node.module.split(".")[1]
            if head in _DOMAIN_SIBLINGS:
                return head
    elif isinstance(node, ast.Import):
        for alias in node.names:
            parts = alias.name.split(".")
            if len(parts) >= 2 and parts[0] == "mito_filter" and parts[1] in _DOMAIN_SIBLINGS:
                return parts[1]
    return None


def _classify(path: Path) -> tuple[set[str], set[str]]:
    """Return (emclarity_hits, runtime_domain_hits) for one core module."""
    tree = ast.parse(path.read_text(), filename=str(path))
    tc_nodes: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and _is_type_checking_test(node.test):
            for child in ast.walk(node):
                if isinstance(child, (ast.Import, ast.ImportFrom)):
                    tc_nodes.add(id(child))
    emclarity_hits: set[str] = set()
    runtime_hits: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        head = _sibling_head(node)
        if head is None:
            continue
        if head == "emclarity":
            emclarity_hits.add(head)  # forbidden even under TYPE_CHECKING
        elif id(node) not in tc_nodes:
            runtime_hits.add(head)  # runtime coupling to a domain sibling
    return emclarity_hits, runtime_hits


def test_core_never_imports_emclarity() -> None:
    offenders = {py.name: emc for py in sorted(_CORE_DIR.glob("*.py")) if (emc := _classify(py)[0])}
    assert not offenders, f"core/ imports emclarity (DESIGN §1.6): {offenders}"


def test_core_has_no_runtime_domain_sibling_import() -> None:
    offenders = {py.name: rt for py in sorted(_CORE_DIR.glob("*.py")) if (rt := _classify(py)[1])}
    assert not offenders, f"core/ has a runtime domain-sibling import (DESIGN §1.6): {offenders}"
