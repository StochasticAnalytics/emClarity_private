#!/usr/bin/env python3
"""
Intelligent Task Decomposition

Analyzes tasks and splits them when context exhaustion threatens or
repeated failures indicate task is too complex.
"""

from typing import Dict, List
import re


class TaskSplitter:
    """Intelligent task decomposition strategies"""

    def split(self, task: Dict, strategy: str = "auto") -> List[Dict]:
        """
        Split task into sub-tasks

        Args:
            task: Task dictionary from PRD
            strategy: "auto", "vertical", "horizontal", "dependency", "simplify"

        Returns:
            List of sub-task dictionaries
        """

        if strategy == "auto":
            strategy = self._determine_strategy(task)

        if strategy == "vertical":
            return self._vertical_slice(task)
        elif strategy == "horizontal":
            return self._horizontal_slice(task)
        elif strategy == "dependency":
            return self._dependency_first(task)
        elif strategy == "simplify":
            return self._simplify_scope(task)
        else:
            # Default: horizontal slice
            return self._horizontal_slice(task)

    def _determine_strategy(self, task: Dict) -> str:
        """Automatically determine best splitting strategy"""

        title = task.get("title", "").lower()
        desc = task.get("description", "").lower()
        combined = title + " " + desc

        # Keywords suggesting vertical slice (separate frontend/backend)
        if any(word in combined for word in ["form", "endpoint", "api", "ui"]):
            return "vertical"

        # Keywords suggesting horizontal slice (happy path vs error handling)
        if any(word in combined for word in ["validation", "error", "edge case"]):
            return "horizontal"

        # Keywords suggesting dependency-first
        if any(word in combined for word in ["model", "schema", "type", "interface"]):
            return "dependency"

        # Default: simplify
        return "simplify"

    def _vertical_slice(self, task: Dict) -> List[Dict]:
        """
        Split by feature layer (UI vs backend)

        Example:
            "Job submission form with validation"
        Becomes:
            1. "Job submission form UI (no validation)"
            2. "Backend endpoint for job submission"
            3. "Add validation to job submission"
        """

        base_id = task["id"]
        title = task["title"]

        sub_tasks = []

        # UI component
        sub_tasks.append({
            "id": f"{base_id}a",
            "title": f"{title} - UI component only",
            "description": f"Implement frontend UI for: {task.get('description', title)}. No backend integration yet.",
            "type": "frontend",
            "status": "pending",
            "depends_on": task.get("depends_on", []),
            "reference": task.get("reference")
        })

        # Backend component
        sub_tasks.append({
            "id": f"{base_id}b",
            "title": f"{title} - Backend endpoint",
            "description": f"Implement backend logic for: {task.get('description', title)}",
            "type": "backend",
            "status": "pending",
            "depends_on": task.get("depends_on", []),
            "reference": task.get("reference")
        })

        # Integration
        sub_tasks.append({
            "id": f"{base_id}c",
            "title": f"{title} - Frontend/backend integration",
            "description": "Connect UI to backend endpoint",
            "type": "integration",
            "status": "pending",
            "depends_on": [f"{base_id}a", f"{base_id}b"],
            "reference": task.get("reference")
        })

        return sub_tasks

    def _horizontal_slice(self, task: Dict) -> List[Dict]:
        """
        Split by functionality level (happy path vs edge cases)

        Example:
            "Parameter validation with error messages"
        Becomes:
            1. "Basic parameter validation (happy path)"
            2. "Error message display for validation failures"
        """

        base_id = task["id"]
        title = task["title"]

        sub_tasks = []

        # Happy path
        sub_tasks.append({
            "id": f"{base_id}a",
            "title": f"{title} - Happy path",
            "description": f"Implement basic functionality: {task.get('description', title)}. Handle valid inputs only.",
            "type": task.get("type", "feature"),
            "status": "pending",
            "depends_on": task.get("depends_on", []),
            "reference": task.get("reference")
        })

        # Error handling
        sub_tasks.append({
            "id": f"{base_id}b",
            "title": f"{title} - Error handling",
            "description": "Add error handling, validation, edge cases",
            "type": task.get("type", "feature"),
            "status": "pending",
            "depends_on": [f"{base_id}a"],
            "reference": task.get("reference")
        })

        return sub_tasks

    def _dependency_first(self, task: Dict) -> List[Dict]:
        """
        Split prerequisite from main implementation

        Example:
            "User profile form with avatar upload"
        Becomes:
            1. "User profile data model"
            2. "User profile form (no avatar)"
            3. "Add avatar upload to profile"
        """

        base_id = task["id"]
        title = task["title"]

        sub_tasks = []

        # Data model / types
        sub_tasks.append({
            "id": f"{base_id}a",
            "title": f"{title} - Data model",
            "description": f"Define types, interfaces, schema for: {task.get('description', title)}",
            "type": "infrastructure",
            "status": "pending",
            "depends_on": task.get("depends_on", []),
            "reference": task.get("reference")
        })

        # Basic implementation
        sub_tasks.append({
            "id": f"{base_id}b",
            "title": f"{title} - Basic implementation",
            "description": f"Implement core functionality using data model from {base_id}a",
            "type": task.get("type", "feature"),
            "status": "pending",
            "depends_on": [f"{base_id}a"] + task.get("depends_on", []),
            "reference": task.get("reference")
        })

        return sub_tasks

    def _simplify_scope(self, task: Dict) -> List[Dict]:
        """
        Reduce scope - implement partial functionality first

        Example:
            "Form with 10 fields and validation"
        Becomes:
            1. "Form with first 3 fields"
            2. "Form with fields 4-7"
            3. "Form with fields 8-10 and validation"
        """

        base_id = task["id"]
        title = task["title"]

        sub_tasks = []

        # Minimal version
        sub_tasks.append({
            "id": f"{base_id}a",
            "title": f"{title} - Minimal version",
            "description": f"Simplified implementation of: {task.get('description', title)}. Core functionality only.",
            "type": task.get("type", "feature"),
            "status": "pending",
            "depends_on": task.get("depends_on", []),
            "reference": task.get("reference")
        })

        # Extended version
        sub_tasks.append({
            "id": f"{base_id}b",
            "title": f"{title} - Full version",
            "description": "Extend minimal version to full specification",
            "type": task.get("type", "feature"),
            "status": "pending",
            "depends_on": [f"{base_id}a"],
            "reference": task.get("reference")
        })

        return sub_tasks


def main():
    """Test splitting strategies"""

    splitter = TaskSplitter()

    # Test task
    task = {
        "id": "TASK-042",
        "title": "Job submission form with validation and file upload",
        "description": "User can submit jobs with parameters, validation, and attach input files",
        "type": "frontend",
        "depends_on": ["TASK-001"]
    }

    print("Original task:")
    print(f"  {task['id']}: {task['title']}")
    print()

    for strategy in ["vertical", "horizontal", "dependency", "simplify"]:
        print(f"{strategy.upper()} SPLIT:")
        sub_tasks = splitter.split(task, strategy)
        for st in sub_tasks:
            print(f"  {st['id']}: {st['title']}")
            if st['depends_on']:
                print(f"    Depends on: {', '.join(st['depends_on'])}")
        print()


if __name__ == "__main__":
    main()
