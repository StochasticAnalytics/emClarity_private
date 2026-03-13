#!/usr/bin/env python3
"""
Autonomous Build System Orchestrator

Main coordination loop for multi-agent autonomous development.
Manages Developer and QA agents, monitors context usage, handles task splitting.
"""

import json
import logging
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import argparse

from task_splitter import TaskSplitter

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logger = logging.getLogger("orchestrator")


def _setup_logging(log_path: Path = Path("orchestrator.log")):
    """Configure dual logging to file and stderr."""
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.INFO)
    stderr_handler.setFormatter(fmt)
    logger.addHandler(stderr_handler)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class OrchestratorConfig:
    """Configuration loaded from config.json"""

    def __init__(self, config_path: Path = Path("config.json")):
        try:
            with open(config_path) as f:
                self.config = json.load(f)
        except FileNotFoundError:
            logger.error(
                "Config file not found: %s  "
                "Copy config.example.json to config.json and fill in values.",
                config_path,
            )
            sys.exit(1)
        except json.JSONDecodeError as exc:
            logger.error("Invalid JSON in %s: %s", config_path, exc)
            sys.exit(1)

        self._validate()

    def _validate(self):
        """Validate required configuration fields."""
        key = self.config.get("claude_api_key", "")
        if not key or key == "your-api-key-here":
            logger.warning(
                "claude_api_key is not set in config.json. "
                "The Claude Code CLI uses its own auth, so this is only "
                "needed if you plan to call the API directly."
            )

        if shutil.which("claude") is None:
            logger.error(
                "'claude' CLI not found on PATH. "
                "Install it: npm install -g @anthropic-ai/claude-code"
            )
            sys.exit(1)

        project_root = self.project_root
        if not project_root.is_dir():
            logger.error(
                "project_root directory does not exist: %s", project_root
            )
            sys.exit(1)

    # -- properties --------------------------------------------------------

    @property
    def claude_api_key(self) -> str:
        return self.config.get("claude_api_key", "")

    @property
    def model(self) -> str:
        return self.config.get("model", "claude-sonnet-4-20250514")

    @property
    def max_context_tokens(self) -> int:
        return self.config.get("max_context_tokens", 200000)

    @property
    def context_warning_threshold(self) -> float:
        return self.config.get("context_warning_threshold", 0.70)

    @property
    def context_split_threshold(self) -> float:
        return self.config.get("context_split_threshold", 0.85)

    @property
    def project_root(self) -> Path:
        raw = self.config.get("project_root", ".")
        return Path(raw).resolve()

    @property
    def oracle_checks(self) -> Dict[str, bool]:
        return self.config.get(
            "oracle_checks",
            {
                "typescript": True,
                "backend_tests": True,
                "e2e_tests": True,
                "test_immutability": True,
                "assert_count": True,
                "coverage": True,
            },
        )


# ---------------------------------------------------------------------------
# Claude Code CLI runner
# ---------------------------------------------------------------------------


class ClaudeCodeRunner:
    """Launches Claude Code CLI sessions and parses structured output."""

    def __init__(self, project_root: Path, max_context_tokens: int):
        self.project_root = project_root
        self.max_context_tokens = max_context_tokens

    def run(
        self,
        system_prompt: str,
        user_message: str,
        max_turns: int = 50,
        timeout: int = 600,
    ) -> Dict[str, Any]:
        """Run a Claude Code CLI session and return structured results.

        Returns dict with keys:
            success (bool): True if CLI exited 0
            text (str): Full conversation text from the model
            input_tokens (int): Tokens consumed by input
            output_tokens (int): Tokens produced as output
            context_usage (float): Fraction of max_context_tokens used
            cost_usd (float): Session cost in USD (if reported)
            raw (dict | None): Full parsed JSON from CLI
        """
        cmd = [
            "claude",
            "--print",
            "--output-format", "json",
            "--dangerously-skip-permissions",
            "--chrome",
            "--effort", "high",
            "--max-turns", str(max_turns),
        ]

        if system_prompt:
            cmd.extend(["--system-prompt", system_prompt])


        logger.debug("ClaudeCodeRunner cmd: %s", " ".join(cmd[:6]) + " ...")
        logger.debug("ClaudeCodeRunner cwd: %s", self.project_root)

        try:
            result = subprocess.run(
                cmd,
                input=user_message,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.project_root),
            )
        except subprocess.TimeoutExpired:
            logger.error("Claude Code session timed out after %ds", timeout)
            return self._error_result("Session timed out")
        except FileNotFoundError:
            logger.error("'claude' CLI binary not found")
            return self._error_result("claude CLI not found")

        return self._parse_result(result)

    def _parse_result(self, result: subprocess.CompletedProcess) -> Dict[str, Any]:
        """Parse JSON output from claude --print --output-format json."""
        parsed: Dict[str, Any] = {
            "success": result.returncode == 0,
            "text": "",
            "input_tokens": 0,
            "output_tokens": 0,
            "context_usage": 0.0,
            "cost_usd": 0.0,
            "raw": None,
        }

        stdout = result.stdout.strip()
        if not stdout:
            logger.warning("Claude CLI produced no stdout (rc=%d)", result.returncode)
            if result.stderr:
                logger.warning("stderr: %s", result.stderr[:500])
            return parsed

        # The --output-format json flag produces a JSON object (or a
        # JSON-lines stream for streaming mode).  We try to parse the
        # whole thing first; if that fails we take the last line.
        raw = None
        try:
            raw = json.loads(stdout)
        except json.JSONDecodeError:
            # Try last non-empty line (streaming mode)
            for line in reversed(stdout.splitlines()):
                line = line.strip()
                if line:
                    try:
                        raw = json.loads(line)
                        break
                    except json.JSONDecodeError:
                        continue

        if raw is None:
            # Couldn't parse JSON at all — treat stdout as plain text
            logger.warning("Could not parse JSON from Claude CLI output")
            parsed["text"] = stdout
            return parsed

        parsed["raw"] = raw

        # Extract text — claude CLI JSON has a "result" field with the
        # final text, or may nest under "content".
        if isinstance(raw, dict):
            parsed["text"] = raw.get("result", raw.get("text", ""))

            # Token usage
            usage = raw.get("usage", {})
            parsed["input_tokens"] = usage.get("input_tokens", 0)
            parsed["output_tokens"] = usage.get("output_tokens", 0)
            parsed["cost_usd"] = raw.get("cost_usd", 0.0)
        elif isinstance(raw, list):
            # Array of messages — concatenate assistant text
            texts = []
            for msg in raw:
                if isinstance(msg, dict) and msg.get("role") == "assistant":
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        texts.append(content)
                    elif isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                texts.append(block.get("text", ""))
            parsed["text"] = "\n".join(texts)

        total_tokens = parsed["input_tokens"] + parsed["output_tokens"]
        if self.max_context_tokens > 0 and total_tokens > 0:
            parsed["context_usage"] = total_tokens / self.max_context_tokens

        return parsed

    @staticmethod
    def _error_result(msg: str) -> Dict[str, Any]:
        return {
            "success": False,
            "text": msg,
            "input_tokens": 0,
            "output_tokens": 0,
            "context_usage": 0.0,
            "cost_usd": 0.0,
            "raw": None,
        }


# ---------------------------------------------------------------------------
# Task Manager
# ---------------------------------------------------------------------------


class TaskManager:
    """Manages PRD (task list) operations"""

    def __init__(self, prd_path: Path = Path("templates/prd.json")):
        self.prd_path = prd_path
        self.prd = self._load_prd()

    def _load_prd(self) -> Dict:
        """Load PRD from disk"""
        if not self.prd_path.exists():
            return self._create_empty_prd()

        with open(self.prd_path) as f:
            return json.load(f)

    def _create_empty_prd(self) -> Dict:
        """Create empty PRD structure"""
        return {
            "_metadata": {
                "phase": "0",
                "created": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
            },
            "_current_task_id": None,
            "tasks": [],
        }

    def save(self):
        """Persist PRD to disk"""
        self.prd["_metadata"]["last_updated"] = datetime.now().isoformat()
        with open(self.prd_path, "w") as f:
            json.dump(self.prd, f, indent=2)

    def get_next_task(self) -> Optional[Dict]:
        """Get next unblocked task.

        Prioritises ``in_progress`` tasks (interrupted work from a prior
        run) over ``pending`` tasks.
        """
        completed_ids = {
            t["id"] for t in self.prd["tasks"] if t["status"] == "complete"
        }

        # First pass: look for in_progress (interrupted) tasks
        for task in self.prd["tasks"]:
            if task["status"] != "in_progress":
                continue
            deps = task.get("depends_on", [])
            if all(dep in completed_ids for dep in deps):
                return task

        # Second pass: look for pending tasks
        for task in self.prd["tasks"]:
            if task["status"] != "pending":
                continue
            deps = task.get("depends_on", [])
            if all(dep in completed_ids for dep in deps):
                return task

        return None

    def mark_complete(self, task_id: str):
        """Mark task as complete"""
        for task in self.prd["tasks"]:
            if task["id"] == task_id:
                task["status"] = "complete"
                task["completed_at"] = datetime.now().isoformat()
                break
        self.save()

    def mark_in_progress(self, task_id: str):
        """Mark task as in progress and record in _current_task_id"""
        self.prd["_current_task_id"] = task_id
        for task in self.prd["tasks"]:
            if task["id"] == task_id:
                task["status"] = "in_progress"
                task["last_attempt"] = datetime.now().isoformat()
                break
        self.save()

    def mark_pending(self, task_id: str):
        """Reset task back to pending (used on interrupted shutdown)"""
        for task in self.prd["tasks"]:
            if task["id"] == task_id:
                task["status"] = "pending"
                break
        self.prd["_current_task_id"] = None
        self.save()

    def increment_retry(self, task_id: str) -> int:
        """Increment retry count, return new count"""
        for task in self.prd["tasks"]:
            if task["id"] == task_id:
                count = task.get("retry_count", 0) + 1
                task["retry_count"] = count
                self.save()
                return count
        return 0

    def get_retry_count(self, task_id: str) -> int:
        """Get current retry count"""
        for task in self.prd["tasks"]:
            if task["id"] == task_id:
                return task.get("retry_count", 0)
        return 0

    def replace_task(self, task_id: str, sub_tasks: List[Dict]):
        """Replace task with sub-tasks"""
        for i, task in enumerate(self.prd["tasks"]):
            if task["id"] == task_id:
                task["status"] = "deferred"
                task["split_into"] = [st["id"] for st in sub_tasks]
                self.prd["tasks"][i + 1 : i + 1] = sub_tasks
                break
        self.save()


# ---------------------------------------------------------------------------
# Progress Logger
# ---------------------------------------------------------------------------


class ProgressLogger:
    """Manages progress.txt logging"""

    def __init__(self, log_path: Path = Path("templates/progress.txt")):
        self.log_path = log_path

    def log(self, message: str, task_id: Optional[str] = None):
        """Append to progress log"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if task_id:
            entry = f"[{timestamp}] [{task_id}] {message}\n"
        else:
            entry = f"[{timestamp}] {message}\n"

        with open(self.log_path, "a") as f:
            f.write(entry)

    def log_task_header(self, task: Dict):
        """Log task start header"""
        with open(self.log_path, "a") as f:
            f.write(f"\n=== {task['id']}: {task['title']} ===\n")
            f.write(f"Assigned: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class Orchestrator:
    """Main orchestration loop"""

    def __init__(self, config: OrchestratorConfig, phase: str):
        self.config = config
        self.phase = phase
        self.task_mgr = TaskManager()
        self.progress = ProgressLogger()
        self.splitter = TaskSplitter()
        self.runner = ClaudeCodeRunner(
            project_root=config.project_root,
            max_context_tokens=config.max_context_tokens,
        )
        self.iteration = 0
        self._current_task_id: Optional[str] = None
        self._shutting_down = False

    # -- signal handling ---------------------------------------------------

    def _install_signal_handlers(self):
        """Install handlers for graceful shutdown."""
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

    def _handle_shutdown(self, signum, frame):
        """Gracefully checkpoint on SIGTERM / SIGINT."""
        if self._shutting_down:
            # Second signal — force exit
            logger.warning("Forced exit on repeated signal")
            sys.exit(1)

        self._shutting_down = True
        sig_name = signal.Signals(signum).name
        logger.info("Received %s — checkpointing and shutting down", sig_name)

        if self._current_task_id:
            self.task_mgr.mark_pending(self._current_task_id)
            self.progress.log(
                f"Interrupted by {sig_name} — reset to pending",
                self._current_task_id,
            )
            logger.info(
                "Task %s reset to pending for next run", self._current_task_id
            )

        self._generate_report()
        sys.exit(0)

    # -- main loop ---------------------------------------------------------

    def run(self, max_iterations: int, resume: bool = False):
        """Execute orchestration loop"""
        self._install_signal_handlers()

        if not resume:
            self.progress.log("=== ORCHESTRATOR RUN STARTED ===")
            self.progress.log(f"Phase: {self.phase}")
            self.progress.log(f"Max iterations: {max_iterations}")
            logger.info("Orchestrator started — phase=%s, max_iter=%d",
                        self.phase, max_iterations)
        else:
            self.progress.log("=== ORCHESTRATOR RESUMED ===")
            logger.info("Orchestrator resumed — phase=%s", self.phase)

        while self.iteration < max_iterations:
            if self._shutting_down:
                break

            task = self.task_mgr.get_next_task()

            if task is None:
                self.progress.log("No unblocked tasks remaining. Stopping.")
                logger.info("No unblocked tasks remaining")
                break

            logger.info(
                "[Iter %d/%d] Processing: %s — %s",
                self.iteration + 1, max_iterations, task["id"], task["title"],
            )
            self.progress.log_task_header(task)

            success = self._execute_task(task)

            if success:
                self.task_mgr.mark_complete(task["id"])
                self.progress.log("Status: COMPLETE", task["id"])
                logger.info("%s complete", task["id"])

            self._current_task_id = None
            self.iteration += 1

        logger.info("Stopped after %d iterations", self.iteration)
        self._generate_report()

    # -- pipeline ----------------------------------------------------------

    def _execute_task(self, task: Dict) -> bool:
        """Execute single task through Dev -> QA -> Oracle pipeline"""

        self._current_task_id = task["id"]
        self.task_mgr.mark_in_progress(task["id"])

        # 1. Launch Developer
        logger.info("  Developer working on %s ...", task["id"])
        dev_result = self._launch_developer(task)

        if not dev_result or not dev_result.get("success", False):
            self.progress.log("Developer failed to complete", task["id"])
            logger.warning("Developer failed for %s", task["id"])
            return False

        context_pct = dev_result.get("context_usage", 0.0)
        self.progress.log(
            f"Developer context usage: {context_pct:.0%}", task["id"]
        )

        if context_pct > self.config.context_warning_threshold:
            logger.warning(
                "Context usage %.0f%% — approaching limit", context_pct * 100
            )

        # 2. Launch QA
        logger.info("  QA reviewing %s ...", task["id"])
        qa_result = self._launch_qa(task, dev_result.get("diff", ""))

        if not qa_result:
            self.progress.log("QA review failed", task["id"])
            logger.warning("QA review failed for %s", task["id"])
            return False

        verdict = qa_result.get("verdict", "BLOCKED")
        self.progress.log(f"QA verdict: {verdict}", task["id"])

        if verdict != "PASS":
            for defect in qa_result.get("defects", []):
                self.progress.log(f"  - {defect}", task["id"])

            retry_count = self.task_mgr.get_retry_count(task["id"])

            if context_pct > self.config.context_split_threshold or retry_count >= 3:
                logger.info(
                    "Splitting %s (context=%.0f%%, retries=%d)",
                    task["id"], context_pct * 100, retry_count,
                )
                self._split_task(task)
                return False
            else:
                self.task_mgr.increment_retry(task["id"])
                self.progress.log(f"Retry {retry_count + 1} scheduled", task["id"])
                return False

        # 3. Run Oracle
        logger.info("  Oracle validating %s ...", task["id"])
        oracle_passed = self._run_oracle(task["id"])

        if not oracle_passed:
            self.progress.log("Oracle validation FAILED", task["id"])
            logger.warning("Oracle failed for %s", task["id"])

            retry_count = self.task_mgr.get_retry_count(task["id"])

            if context_pct > self.config.context_split_threshold or retry_count >= 3:
                logger.info("Splitting %s after oracle failure", task["id"])
                self._split_task(task)
            else:
                self.task_mgr.increment_retry(task["id"])

            return False

        self.progress.log("Oracle validation PASSED", task["id"])
        return True

    # -- agent launchers ---------------------------------------------------

    def _launch_developer(self, task: Dict) -> Optional[Dict]:
        """Launch Developer agent via Claude Code CLI."""

        # Load system prompt
        prompt_path = Path("prompts/developer-prompt.md")
        try:
            system_prompt = prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.error("Developer prompt not found: %s", prompt_path)
            return None

        # Build user message with task context
        user_message = self._build_developer_message(task)

        # Run Claude Code session
        result = self.runner.run(
            system_prompt=system_prompt,
            user_message=user_message,
            max_turns=50,
            timeout=600,
        )

        if not result["success"]:
            logger.warning("Developer CLI session failed: %s", result["text"][:200])
            return result

        # Capture git diff after developer finishes
        diff = self._git_diff()
        result["diff"] = diff

        # Capture commit SHA
        sha = self._git_head_sha()
        result["commit_sha"] = sha

        return result

    def _launch_qa(self, task: Dict, diff: str) -> Optional[Dict]:
        """Launch QA agent via Claude Code CLI."""

        # Load system prompt
        prompt_path = Path("prompts/qa-prompt.md")
        try:
            system_prompt = prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.error("QA prompt not found: %s", prompt_path)
            return None

        # Build user message with task + diff
        user_message = self._build_qa_message(task, diff)

        # Run Claude Code session (QA)
        result = self.runner.run(
            system_prompt=system_prompt,
            user_message=user_message,
            max_turns=30,
            timeout=300,
        )

        if not result["success"]:
            logger.warning("QA CLI session failed: %s", result["text"][:200])
            return {"verdict": "BLOCKED", "defects": ["QA session failed"], "round": 0}

        # Parse QA output for verdict and defects
        return self._parse_qa_output(result["text"])

    # -- message builders --------------------------------------------------

    @staticmethod
    def _build_developer_message(task: Dict) -> str:
        """Construct the user message sent to the developer agent."""
        parts = [
            "## Current Task\n",
            f"**Task ID:** {task['id']}",
            f"**Title:** {task.get('title', '')}",
            f"**Description:** {task.get('description', '')}",
        ]

        criteria = task.get("acceptance_criteria")
        if criteria:
            parts.append("\n**Acceptance Criteria:**")
            for c in criteria:
                parts.append(f"- {c}")

        ref = task.get("reference")
        if ref:
            parts.append(f"\n**Reference:** {ref}")

        parts.append(
            "\nPlease implement this task. After implementation, "
            "run the local validation checks described in your instructions, "
            "then commit your changes."
        )

        return "\n".join(parts)

    @staticmethod
    def _build_qa_message(task: Dict, diff: str) -> str:
        """Construct the user message sent to the QA agent."""
        parts = [
            "## Task Under Review\n",
            f"**Task ID:** {task['id']}",
            f"**Title:** {task.get('title', '')}",
            f"**Description:** {task.get('description', '')}",
        ]

        criteria = task.get("acceptance_criteria")
        if criteria:
            parts.append("\n**Acceptance Criteria:**")
            for c in criteria:
                parts.append(f"- {c}")

        ref = task.get("reference")
        if ref:
            parts.append(f"\n**Reference:** {ref}")

        parts.append("\n## Git Diff (Developer's Changes)\n")
        if diff:
            parts.append(f"```diff\n{diff}\n```")
        else:
            parts.append("_No diff available — developer may not have committed._")

        parts.append(
            "\nPlease review this implementation per your QA instructions. "
            "Provide your verdict in the structured format described."
        )

        return "\n".join(parts)

    # -- QA output parser --------------------------------------------------

    @staticmethod
    def _parse_qa_output(text: str) -> Dict[str, Any]:
        """Extract verdict and defect list from QA markdown output."""
        verdict = "BLOCKED"
        defects: List[str] = []
        qa_round = 1

        # Extract VERDICT
        verdict_match = re.search(
            r"\*\*VERDICT:\*\*\s*(PASS|NEEDS_WORK|BLOCKED)", text, re.IGNORECASE
        )
        if verdict_match:
            verdict = verdict_match.group(1).upper()

        # Extract ROUND
        round_match = re.search(r"\*\*ROUND:\*\*\s*(\d+)", text)
        if round_match:
            qa_round = int(round_match.group(1))

        # Extract defects — numbered list items under DEFECTS section
        defects_section = re.search(
            r"\*\*DEFECTS:\*\*\s*\n(.*?)(?=\n\*\*[A-Z]|\Z)",
            text,
            re.DOTALL | re.IGNORECASE,
        )
        if defects_section:
            defect_lines = re.findall(
                r"^\d+\.\s+(.+)$", defects_section.group(1), re.MULTILINE
            )
            defects = defect_lines

        return {"verdict": verdict, "defects": defects, "round": qa_round}

    # -- oracle ------------------------------------------------------------

    def _run_oracle(self, task_id: str) -> bool:
        """Run external oracle validation."""
        try:
            result = subprocess.run(
                [sys.executable, "oracle.py", "--task-id", task_id],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(Path(__file__).parent),
            )

            if result.stdout:
                logger.debug("Oracle stdout:\n%s", result.stdout[:1000])
            if result.stderr:
                logger.debug("Oracle stderr:\n%s", result.stderr[:500])

            return result.returncode == 0
        except subprocess.TimeoutExpired:
            logger.error("Oracle timed out after 300s")
            return False
        except Exception as exc:
            logger.error("Oracle error: %s", exc)
            return False

    # -- task splitting ----------------------------------------------------

    def _split_task(self, task: Dict):
        """Split task into sub-tasks using TaskSplitter."""
        sub_tasks = self.splitter.split(task)

        if not sub_tasks:
            logger.warning("TaskSplitter returned no sub-tasks for %s", task["id"])
            self.progress.log("Task splitting produced no sub-tasks", task["id"])
            return

        sub_ids = [st["id"] for st in sub_tasks]
        logger.info(
            "Split %s into %d sub-tasks: %s",
            task["id"], len(sub_tasks), ", ".join(sub_ids),
        )
        self.progress.log(
            f"Split into sub-tasks: {', '.join(sub_ids)}", task["id"]
        )

        self.task_mgr.replace_task(task["id"], sub_tasks)

    # -- git helpers -------------------------------------------------------

    def _git_diff(self) -> str:
        """Capture git diff HEAD in the project root."""
        try:
            result = subprocess.run(
                ["git", "diff", "HEAD"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(self.config.project_root),
            )
            return result.stdout
        except Exception as exc:
            logger.warning("git diff failed: %s", exc)
            return ""

    def _git_head_sha(self) -> str:
        """Get the current HEAD commit SHA."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=str(self.config.project_root),
            )
            return result.stdout.strip()
        except Exception:
            return ""

    # -- reporting ---------------------------------------------------------

    def _generate_report(self):
        """Generate summary report"""
        completed = sum(
            1 for t in self.task_mgr.prd["tasks"] if t["status"] == "complete"
        )
        total = len(self.task_mgr.prd["tasks"])

        report = (
            f"\n=== Orchestrator Run Summary ===\n"
            f"Phase: {self.phase}\n"
            f"Iterations: {self.iteration}\n"
            f"Tasks completed: {completed}/{total}\n"
        )

        logger.info(report)
        self.progress.log(report)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Autonomous Build System Orchestrator"
    )
    parser.add_argument(
        "--phase",
        required=True,
        choices=["0", "1", "2"],
        help="Build phase (0=knowledge ingestion, 1=mirror build, 2=enhancement)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=100,
        help="Maximum iterations before stopping",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from last checkpoint",
    )
    parser.add_argument(
        "--config",
        default="config.json",
        help="Path to config file",
    )

    args = parser.parse_args()

    _setup_logging()

    config = OrchestratorConfig(Path(args.config))

    orch = Orchestrator(config, args.phase)
    orch.run(args.max_iterations, args.resume)


if __name__ == "__main__":
    main()
