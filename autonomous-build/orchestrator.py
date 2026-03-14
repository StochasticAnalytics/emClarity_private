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
        return self.config.get("model", "sonnet")

    @property
    def effort(self) -> str:
        return self.config.get("effort", "medium")

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

    def __init__(self, project_root: Path, stream_output: bool = False, model: str = "", effort: str = "medium"):
        self.project_root = project_root
        self.stream_output = stream_output
        self.model = model
        self.effort = effort

    def run(
        self,
        system_prompt: str,
        user_message: str,
        max_turns: int = 50,
        timeout: int = 600,
        agent_label: str = "",
        task_id: str = "",
    ) -> Dict[str, Any]:
        """Run a Claude Code CLI session and return structured results.

        Returns dict with keys:
            success (bool): True if CLI exited 0
            text (str): Full conversation text from the model
            input_tokens (int): Tokens consumed by input
            output_tokens (int): Tokens produced as output
            context_usage (float): Reserved (context managed by CLI)
            cost_usd (float): Session cost in USD (if reported)
            raw (dict | None): Full parsed JSON from CLI
        """
        # Build command — stream-json for real-time output, json for buffered
        if self.stream_output:
            output_fmt = "stream-json"
        else:
            output_fmt = "json"

        cmd = [
            "claude",
            "--print",
            "--output-format", output_fmt,
            "--dangerously-skip-permissions",
            "--chrome",
            "--effort", self.effort,
            "--verbose",
            "--max-turns", str(max_turns),
        ]

        if self.model:
            cmd.extend(["--model", self.model])

        if system_prompt:
            cmd.extend(["--system-prompt", system_prompt])

        logger.debug("ClaudeCodeRunner cmd: %s (format=%s model=%s)", " ".join(cmd[:6]) + " ...", output_fmt, self.model or "default")
        logger.debug("ClaudeCodeRunner cwd: %s", self.project_root)

        if self.stream_output:
            return self._run_streaming(cmd, user_message, timeout, agent_label, task_id)

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

    def _run_streaming(
        self, cmd: List[str], user_message: str, timeout: int,
        agent_label: str = "", task_id: str = "",
    ) -> Dict[str, Any]:
        """Run CLI with ``--output-format stream-json`` for real-time output.

        stream-json produces one JSON object per line on **stdout**:
          {"type":"system", ...}     — session init
          {"type":"assistant", ...}  — model output (text & tool_use)
          {"type":"user", ...}       — tool results fed back
          {"type":"result", ...}     — final summary (same schema as json mode)

        We read stdout line-by-line, display events to the console in
        real time, and capture the final ``type=result`` event for
        ``_parse_result()``.
        """
        import threading

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(self.project_root),
            )
        except FileNotFoundError:
            logger.error("'claude' CLI binary not found")
            return self._error_result("claude CLI not found")

        # Send user message to stdin then close it
        try:
            proc.stdin.write(user_message)
            proc.stdin.close()
        except BrokenPipeError:
            pass

        # Drain stderr in background thread (usually empty, but prevents deadlock)
        stderr_parts: List[str] = []

        def _drain_stderr():
            try:
                for line in proc.stderr:
                    stderr_parts.append(line)
            except Exception:
                pass

        stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
        stderr_thread.start()

        # Read stdout line-by-line — each line is one stream-json event
        result_event: Optional[Dict] = None
        event_count = 0
        start_time = time.time()

        try:
            for line in proc.stdout:
                elapsed = time.time() - start_time
                if elapsed > timeout:
                    proc.kill()
                    proc.wait()
                    stderr_thread.join(timeout=5)
                    logger.error("Claude Code session timed out after %ds", timeout)
                    return self._error_result("Session timed out")

                line = line.strip()
                if not line:
                    continue

                event_count += 1
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    logger.debug("[STREAM] non-JSON line: %s", line[:200])
                    continue

                etype = event.get("type", "?")

                # Display events to console for real-time visibility
                self._display_stream_event(event, elapsed, agent_label, task_id)

                # Capture the final result event
                if etype == "result":
                    result_event = event

        except Exception as exc:
            logger.warning("[STREAM] Error reading stdout: %s", exc)

        proc.wait()
        stderr_thread.join(timeout=10)

        total_elapsed = time.time() - start_time
        logger.info(
            "[STREAM] Done: rc=%d events=%d %.0fs",
            proc.returncode, event_count, total_elapsed,
        )

        # Build a result that _parse_result can handle.
        # The result event has the same schema as --output-format json
        # single-object output, so we serialize it back to JSON.
        if result_event:
            stdout_json = json.dumps(result_event)
        else:
            stdout_json = ""
            logger.warning(
                "[STREAM] No type=result event found in %d events", event_count
            )

        result = subprocess.CompletedProcess(
            args=cmd,
            returncode=proc.returncode,
            stdout=stdout_json,
            stderr="".join(stderr_parts),
        )
        return self._parse_result(result)

    @staticmethod
    def _display_stream_event(
        event: Dict, elapsed: float, agent_label: str = "", task_id: str = "",
    ):
        """Display a stream-json event to stderr for user visibility."""
        etype = event.get("type", "?")

        # Build prefix: e.g. "[DEV ] [TASK-002c] "
        tag = ""
        if agent_label:
            tag += f"[{agent_label:<4s}] "
        if task_id:
            tag += f"[{task_id}] "

        if etype == "system":
            sid = event.get("session_id", "?")[:8]
            sys.stderr.write(f"  [{elapsed:6.1f}s] {tag}[INIT] session={sid}\n")

        elif etype == "assistant":
            msg = event.get("message", {})
            for block in (msg.get("content") or []):
                if not isinstance(block, dict):
                    continue
                btype = block.get("type", "?")
                if btype == "text":
                    text = block.get("text", "")
                    # Show first 150 chars of text output
                    preview = text[:150] + ("..." if len(text) > 150 else "")
                    sys.stderr.write(f"  [{elapsed:6.1f}s] {tag}[TEXT] {preview}\n")
                elif btype == "tool_use":
                    name = block.get("name", "?")
                    inp = str(block.get("input", ""))[:80]
                    sys.stderr.write(f"  [{elapsed:6.1f}s] {tag}[TOOL] {name}({inp})\n")

        elif etype == "result":
            result_text = event.get("result", "")[:100]
            cost = event.get("total_cost_usd", 0)
            turns = event.get("num_turns", "?")
            sys.stderr.write(
                f"  [{elapsed:6.1f}s] {tag}[DONE] turns={turns} "
                f"cost=${cost:.4f} result='{result_text}'\n"
            )

        # Skip rate_limit_event and user (tool result) events — too noisy

        sys.stderr.flush()

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
            # Verbose mode: array of event objects with "type" field.
            # Look for the "result" event first (has final text),
            # fall back to extracting from "assistant" events.
            for msg in raw:
                if isinstance(msg, dict) and msg.get("type") == "result":
                    parsed["text"] = msg.get("result", "")
                    usage = msg.get("usage", {})
                    parsed["input_tokens"] = usage.get("input_tokens", 0)
                    parsed["output_tokens"] = usage.get("output_tokens", 0)
                    parsed["cost_usd"] = msg.get("total_cost_usd", 0.0)
                    break
            else:
                # No result event — concatenate assistant text blocks
                texts = []
                for msg in raw:
                    if not isinstance(msg, dict):
                        continue
                    # Verbose format: type=assistant, content in msg["message"]["content"]
                    if msg.get("type") == "assistant":
                        content = msg.get("message", {}).get("content", [])
                        if isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    texts.append(block.get("text", ""))
                    # Legacy format: role=assistant, content at top level
                    elif msg.get("role") == "assistant":
                        content = msg.get("content", "")
                        if isinstance(content, str):
                            texts.append(content)
                        elif isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    texts.append(block.get("text", ""))
                parsed["text"] = "\n".join(texts)

        # context_usage left at 0.0 — context limits managed by the CLI itself

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

    def preflight(self) -> bool:
        """Run a minimal CLI invocation to verify config is correct.

        Prints orchestrator config, then asks the agent to report its
        model, effort level, and what context/tools it can see.
        """
        # Print local config
        sys.stderr.write("\n")
        sys.stderr.write("=" * 60 + "\n")
        sys.stderr.write("  Orchestrator Preflight\n")
        sys.stderr.write("=" * 60 + "\n")
        sys.stderr.write(f"  model:   {self.model}\n")
        sys.stderr.write(f"  effort:  {self.effort}\n")
        sys.stderr.write(f"  cwd:     {self.project_root}\n")
        sys.stderr.write(f"  stream:  {self.stream_output}\n")
        sys.stderr.write("-" * 60 + "\n")
        sys.stderr.write("  Asking agent to confirm...\n")
        sys.stderr.flush()

        result = self.run(
            system_prompt="",
            user_message=(
                "Report the following on separate lines, no other text:\n"
                "MODEL: <your model name/ID>\n"
                "TOOLS: <count of tools available>\n"
                "CWD: <your current working directory>\n"
            ),
            max_turns=1,
            timeout=30,
            agent_label="PRE",
        )
        text = result.get("text", "")
        success = result.get("success", False)

        if success and text.strip():
            sys.stderr.write("  Agent reports:\n")
            for line in text.strip().splitlines():
                sys.stderr.write(f"    {line}\n")
        else:
            sys.stderr.write(f"  Agent failed (success={success}, text={len(text)} chars)\n")

        sys.stderr.write("=" * 60 + "\n\n")
        sys.stderr.flush()

        if not success:
            logger.error("[PREFLIGHT] CLI invocation failed — check model and auth")
        return success


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

    def set_checkpoint(self, task_id: str, stage: str, retry: int, baseline_tag: str):
        """Record that a pipeline stage completed for a specific retry attempt.

        Uses the task's baseline bookmark tag (autobuild/{task_id}/start) as
        the anchor — not HEAD, which drifts when the user commits alongside
        the orchestrator.  The checkpoint is only valid when both the retry
        count AND the baseline tag SHA match.
        """
        for task in self.prd["tasks"]:
            if task["id"] == task_id:
                task["_checkpoint"] = {
                    "stage": stage,
                    "retry": retry,
                    "baseline_tag": baseline_tag,
                    "timestamp": datetime.now().isoformat(),
                }
                self.save()
                return
        logger.warning("set_checkpoint: task %s not found", task_id)

    def get_checkpoint(self, task_id: str, retry: int, baseline_tag: str) -> Optional[str]:
        """Get the last completed stage if checkpoint matches current state.

        Returns the stage name (e.g. "dev", "qa", "oracle") if the checkpoint
        is valid for this retry attempt and baseline tag. Returns None if no
        checkpoint exists or if the retry/tag don't match.
        """
        for task in self.prd["tasks"]:
            if task["id"] == task_id:
                cp = task.get("_checkpoint")
                if not cp:
                    return None
                if cp.get("retry") != retry:
                    return None
                if cp.get("baseline_tag") != baseline_tag:
                    return None
                return cp.get("stage")
        return None

    def clear_checkpoint(self, task_id: str):
        """Remove checkpoint after task completes or is reset."""
        for task in self.prd["tasks"]:
            if task["id"] == task_id:
                task.pop("_checkpoint", None)
                self.save()
                return

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

    def __init__(self, config: OrchestratorConfig, phase: str, stream: bool = False):
        self.config = config
        self.phase = phase
        self.task_mgr = TaskManager()
        self.progress = ProgressLogger()
        self.splitter = TaskSplitter()
        self.runner = ClaudeCodeRunner(
            project_root=config.project_root,
            stream_output=stream,
            model=config.model,
            effort=config.effort,
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
            # Leave task as in_progress — the checkpoint (if any) tells
            # the next run where to resume.  get_next_task() prioritises
            # in_progress tasks, so it will be picked up first.
            self.progress.log(
                f"Interrupted by {sig_name} — left in_progress with checkpoint",
                self._current_task_id,
            )
            logger.info(
                "Task %s left in_progress for checkpoint resume",
                self._current_task_id,
            )

        self._generate_report()
        sys.exit(0)

    # -- main loop ---------------------------------------------------------

    def run(self, max_iterations: int, resume: bool = False):
        """Execute orchestration loop"""
        self._install_signal_handlers()

        # Preflight: verify CLI works before committing to a long run
        if not self.runner.preflight():
            logger.error("Preflight failed — aborting")
            sys.exit(1)

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
        """Execute single task through Dev -> QA -> Oracle pipeline.

        Checkpoints after each stage so a crash/restart can resume
        without re-running completed stages.  A checkpoint is only
        valid when the retry count AND HEAD SHA both match — this
        prevents stale checkpoints from accidentally skipping stages
        after the repo state has changed.
        """
        task_start = time.time()
        tid = task["id"]

        self._current_task_id = tid
        self.task_mgr.mark_in_progress(tid)
        retry_count = self.task_mgr.get_retry_count(tid)
        logger.info("  Task %s retry_count=%d", tid, retry_count)

        # Bookmark the starting point for traceability.
        # The tag is idempotent (git tag -f), so re-tagging on resume is safe.
        baseline_sha = self._git_head_sha()
        start_tag = f"autobuild/{tid}/start"
        self._git_bookmark(tid, "start")

        # Resolve the tag SHA — this is stable even if HEAD moves
        # (e.g., user commits alongside orchestrator).
        tag_sha = self._git_resolve_ref(start_tag)

        # Check for a valid checkpoint from a prior interrupted run
        checkpoint = self.task_mgr.get_checkpoint(tid, retry_count, tag_sha)
        if checkpoint:
            logger.info(
                "  [RESUME] Found valid checkpoint for %s: stage=%s (retry=%d, tag=%s)",
                tid, checkpoint, retry_count, tag_sha[:8],
            )
            self.progress.log(f"Resuming from checkpoint: stage={checkpoint}", tid)

        # ── 1. Developer ─────────────────────────────────────────────
        context_pct = 0.0
        diff = ""

        if checkpoint in ("dev", "qa", "oracle"):
            logger.info("  [DEV] Skipping — checkpoint=%s", checkpoint)
            # Recapture diff from git for QA (if needed)
            diff = self._git_diff()
        else:
            dev_start = time.time()
            logger.info("  [DEV] Starting developer agent for %s ...", tid)
            dev_result = self._launch_developer(task)
            dev_elapsed = time.time() - dev_start

            if not dev_result or not dev_result.get("success", False):
                fail_reason = (dev_result or {}).get("text", "unknown")[:300]
                self.progress.log(
                    f"Developer FAILED ({dev_elapsed:.0f}s): {fail_reason}", tid
                )
                logger.warning(
                    "[DEV] %s failed after %.0fs — %s", tid, dev_elapsed, fail_reason
                )
                return False

            context_pct = dev_result.get("context_usage", 0.0)
            in_tok = dev_result.get("input_tokens", 0)
            out_tok = dev_result.get("output_tokens", 0)
            cost = dev_result.get("cost_usd", 0.0)
            commit_sha = dev_result.get("commit_sha", "?")[:8]
            diff = dev_result.get("diff", "")

            logger.info(
                "[DEV] %s done in %.0fs — tokens=%d/%d ctx=%.0f%% "
                "cost=$%.4f commit=%s diff=%d chars",
                tid, dev_elapsed, in_tok, out_tok,
                context_pct * 100, cost, commit_sha, len(diff),
            )
            self.progress.log(
                f"Developer done ({dev_elapsed:.0f}s) "
                f"tokens={in_tok}/{out_tok} ctx={context_pct:.0%} "
                f"cost=${cost:.4f} commit={commit_sha} diff={len(diff)}ch",
                tid,
            )

            # Checkpoint: dev stage complete
            self.task_mgr.set_checkpoint(
                tid, "dev", retry_count, tag_sha,
            )

        # ── 2. QA Review ─────────────────────────────────────────────
        if checkpoint in ("qa", "oracle"):
            logger.info("  [QA] Skipping — checkpoint=%s", checkpoint)
        else:
            qa_start = time.time()
            logger.info("  [QA] Starting QA agent for %s ...", tid)
            qa_result = self._launch_qa(task, diff)
            qa_elapsed = time.time() - qa_start

            if not qa_result:
                # QA session completely failed — fall through to oracle
                self.progress.log(
                    f"QA session FAILED ({qa_elapsed:.0f}s) — deferring to oracle",
                    tid,
                )
                logger.warning(
                    "[QA] %s session failed after %.0fs — deferring to oracle",
                    tid, qa_elapsed,
                )
            else:
                verdict = qa_result.get("verdict", "BLOCKED")
                verdict_parsed = qa_result.get("verdict_parsed", True)
                defects = qa_result.get("defects", [])
                qa_round = qa_result.get("round", 1)

                logger.info(
                    "[QA] %s verdict=%s parsed=%s round=%d defects=%d (%.0fs)",
                    tid, verdict, verdict_parsed, qa_round, len(defects), qa_elapsed,
                )
                self.progress.log(
                    f"QA verdict={verdict} parsed={verdict_parsed} "
                    f"round={qa_round} defects={len(defects)} ({qa_elapsed:.0f}s)",
                    tid,
                )

                if verdict == "UNPARSEABLE":
                    logger.warning(
                        "[QA] %s output unparseable — deferring to oracle. "
                        "Review orchestrator.log for raw QA output.", tid,
                    )
                    self.progress.log(
                        "QA output unparseable — deferring to oracle", tid,
                    )
                elif verdict == "PASS":
                    logger.info("[QA] %s PASSED QA review", tid)
                else:
                    # QA found real issues (NEEDS_WORK or BLOCKED)
                    for defect in defects:
                        self.progress.log(f"  DEFECT: {defect}", tid)
                        logger.info("[QA] %s defect: %s", tid, defect)

                    # Soft rollback: revert dev commits so next retry starts clean
                    self._git_soft_rollback(tid, baseline_sha)
                    self.task_mgr.clear_checkpoint(tid)

                    if context_pct > self.config.context_split_threshold or retry_count >= 3:
                        logger.info(
                            "[QA] Splitting %s (context=%.0f%%, retries=%d)",
                            tid, context_pct * 100, retry_count,
                        )
                        self._split_task(task)
                        self._log_task_summary(tid, task_start, "SPLIT")
                        return False
                    else:
                        new_retry = self.task_mgr.increment_retry(tid)
                        self.progress.log(
                            f"Retry {new_retry} scheduled (QA: {verdict})", tid,
                        )
                        logger.info(
                            "[QA] %s scheduling retry %d", tid, new_retry,
                        )
                        self._log_task_summary(tid, task_start, f"RETRY({verdict})")
                        return False

            # Checkpoint: qa stage complete
            self.task_mgr.set_checkpoint(
                tid, "qa", retry_count, tag_sha,
            )

        # ── 3. Oracle Validation ──────────────────────────────────────
        if checkpoint == "oracle":
            logger.info("  [ORACLE] Skipping — checkpoint=%s", checkpoint)
        else:
            oracle_start = time.time()
            logger.info("  [ORACLE] Running oracle for %s ...", tid)
            oracle_passed = self._run_oracle(tid)
            oracle_elapsed = time.time() - oracle_start

            logger.info(
                "[ORACLE] %s result=%s (%.0fs)",
                tid, "PASS" if oracle_passed else "FAIL", oracle_elapsed,
            )
            self.progress.log(
                f"Oracle {'PASSED' if oracle_passed else 'FAILED'} ({oracle_elapsed:.0f}s)",
                tid,
            )

            if not oracle_passed:
                # Soft rollback before retry
                self._git_soft_rollback(tid, baseline_sha)
                self.task_mgr.clear_checkpoint(tid)

                if context_pct > self.config.context_split_threshold or retry_count >= 3:
                    logger.info(
                        "[ORACLE] Splitting %s after oracle failure "
                        "(context=%.0f%%, retries=%d)",
                        tid, context_pct * 100, retry_count,
                    )
                    self._split_task(task)
                    self._log_task_summary(tid, task_start, "SPLIT(oracle)")
                else:
                    new_retry = self.task_mgr.increment_retry(tid)
                    logger.info(
                        "[ORACLE] %s scheduling retry %d", tid, new_retry,
                    )
                    self._log_task_summary(tid, task_start, "RETRY(oracle)")

                return False

            # Checkpoint: oracle stage complete
            self.task_mgr.set_checkpoint(
                tid, "oracle", retry_count, tag_sha,
            )

        # ── 4. Success — Historian + completion ───────────────────────
        self._run_historian(tid)
        self._git_bookmark(tid, "verified")
        self.task_mgr.clear_checkpoint(tid)
        self._log_task_summary(tid, task_start, "COMPLETE")
        return True

    def _log_task_summary(self, task_id: str, start_time: float, outcome: str):
        """Log a one-line summary of the task execution for quick scanning."""
        elapsed = time.time() - start_time
        logger.info(
            "  ╰── %s %s (%.0fs total)", task_id, outcome, elapsed,
        )
        self.progress.log(
            f"Task outcome: {outcome} ({elapsed:.0f}s total)", task_id,
        )

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
        logger.debug(
            "[DEV] User message length: %d chars", len(user_message),
        )
        logger.debug(
            "[DEV] System prompt length: %d chars", len(system_prompt),
        )

        # Run Claude Code session
        result = self.runner.run(
            system_prompt=system_prompt,
            user_message=user_message,
            max_turns=50,
            timeout=600,
            agent_label="DEV",
            task_id=task["id"],
        )

        logger.debug(
            "[DEV] CLI exit success=%s, text_len=%d, rc=%s",
            result.get("success"),
            len(result.get("text", "")),
            result["raw"].get("returncode") if isinstance(result.get("raw"), dict) else "?",
        )

        if not result["success"]:
            logger.warning(
                "[DEV] CLI session failed (text=%d chars): %s",
                len(result.get("text", "")),
                result["text"][:300],
            )
            return result

        # Capture git diff after developer finishes
        diff = self._git_diff()
        result["diff"] = diff
        logger.debug("[DEV] Git diff captured: %d chars", len(diff))

        # Capture commit SHA
        sha = self._git_head_sha()
        result["commit_sha"] = sha
        logger.debug("[DEV] HEAD commit: %s", sha[:12] if sha else "none")

        # Log developer text output for review
        dev_text = result.get("text", "")
        if dev_text:
            logger.debug(
                "[DEV] Output (first 500 chars): %s", dev_text[:500],
            )

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
        logger.debug(
            "[QA] User message length: %d chars (diff=%d chars)",
            len(user_message), len(diff),
        )

        # Run Claude Code session (QA)
        result = self.runner.run(
            system_prompt=system_prompt,
            user_message=user_message,
            max_turns=30,
            timeout=600,
            agent_label="QA",
            task_id=task["id"],
        )

        logger.debug(
            "[QA] CLI exit success=%s, text_len=%d",
            result.get("success"),
            len(result.get("text", "")),
        )

        if not result["success"]:
            qa_text = result.get("text", "")
            logger.warning(
                "[QA] CLI session failed (text=%d chars): %s",
                len(qa_text), qa_text[:300],
            )
            return {
                "verdict": "BLOCKED",
                "defects": [f"QA session failed: {qa_text[:200]}"],
                "round": 0,
                "verdict_parsed": False,
            }

        # Log full QA output for debugging
        qa_text = result.get("text", "")
        logger.info(
            "[QA] Full output (%d chars):\n%s",
            len(qa_text),
            qa_text[:2000] + ("..." if len(qa_text) > 2000 else ""),
        )

        # Parse QA output for verdict and defects
        parsed = self._parse_qa_output(qa_text)
        logger.info(
            "[QA] Parsed: verdict=%s parsed=%s defects=%d round=%d",
            parsed.get("verdict"),
            parsed.get("verdict_parsed"),
            len(parsed.get("defects", [])),
            parsed.get("round", 0),
        )
        return parsed

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
        """Extract verdict and defect list from QA markdown output.

        The parser tries multiple patterns to find the verdict.  If no
        verdict is found the result is tagged ``verdict_parsed=False``
        so the caller can decide how to handle it.
        """
        verdict = None
        defects: List[str] = []
        qa_round = 1

        # Log raw QA output for debugging (truncated)
        logger.debug("QA raw output (%d chars): %s", len(text), text[:500])

        # Pattern 1: Exact markdown  **VERDICT:** PASS
        verdict_match = re.search(
            r"\*\*VERDICT:\*\*\s*(PASS|NEEDS_WORK|BLOCKED)", text, re.IGNORECASE
        )
        if verdict_match:
            verdict = verdict_match.group(1).upper()

        # Pattern 2: Plain text  VERDICT: PASS  or  Verdict: PASS
        if verdict is None:
            verdict_match = re.search(
                r"VERDICT\s*:\s*(PASS|NEEDS_WORK|BLOCKED)", text, re.IGNORECASE
            )
            if verdict_match:
                verdict = verdict_match.group(1).upper()

        # Pattern 3: Markdown heading  ## ... PASS
        if verdict is None:
            verdict_match = re.search(
                r"#+\s*.*?(PASS|NEEDS_WORK|BLOCKED)\b", text, re.IGNORECASE
            )
            if verdict_match:
                verdict = verdict_match.group(1).upper()

        verdict_parsed = verdict is not None
        if verdict is None:
            logger.warning(
                "QA output did not contain a recognizable verdict. "
                "First 300 chars: %s", text[:300]
            )
            verdict = "UNPARSEABLE"

        # Extract ROUND
        round_match = re.search(r"\*\*ROUND:\*\*\s*(\d+)", text)
        if not round_match:
            round_match = re.search(r"ROUND\s*:\s*(\d+)", text, re.IGNORECASE)
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

        return {
            "verdict": verdict,
            "defects": defects,
            "round": qa_round,
            "verdict_parsed": verdict_parsed,
        }

    # -- historian ---------------------------------------------------------

    def _run_historian(self, task_id: str):
        """Run the Historian agent to clean up git history for a completed task.

        The Historian reviews commits since the task's start tag, squashes
        revert+fix pairs, ensures meaningful commit messages, and maintains
        a minimum of one commit per sub-agent per task.
        """
        start_tag = f"autobuild/{task_id}/start"

        # Check if the start tag exists
        tag_check = subprocess.run(
            ["git", "rev-parse", "--verify", f"refs/tags/{start_tag}"],
            capture_output=True, text=True, timeout=10,
            cwd=str(self.config.project_root),
        )
        if tag_check.returncode != 0:
            logger.info("[HIST] No start tag found for %s — skipping historian", task_id)
            return

        # Load historian prompt
        prompt_path = Path("prompts/historian-prompt.md")
        try:
            system_prompt = prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.warning("[HIST] Historian prompt not found: %s — skipping", prompt_path)
            return

        user_message = (
            f"Clean up the git history for task {task_id}.\n\n"
            f"Start reference: tag '{start_tag}'\n"
            f"Current HEAD: {self._git_head_sha()[:12]}\n\n"
            f"Review the commits between the start tag and HEAD. "
            f"Squash revert+fix pairs, ensure meaningful commit messages "
            f"with format '[{task_id}] <what and why>', and maintain "
            f"minimum 1 commit for dev work + 1 for QA fixes (if any). "
            f"Do NOT squash across task boundaries. Preserve commits from "
            f"other agents or the user."
        )

        hist_start = time.time()
        logger.info("  [HIST] Starting historian for %s ...", task_id)

        result = self.runner.run(
            system_prompt=system_prompt,
            user_message=user_message,
            max_turns=10,
            timeout=120,
            agent_label="HIST",
            task_id=task_id,
        )

        hist_elapsed = time.time() - hist_start
        success = result.get("success", False)
        logger.info(
            "[HIST] %s done in %.0fs — success=%s",
            task_id, hist_elapsed, success,
        )
        if not success:
            logger.warning(
                "[HIST] Historian failed for %s — history left as-is", task_id,
            )

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

            # Always log oracle output — it's the ground truth
            if result.stdout:
                logger.info("[ORACLE] stdout:\n%s", result.stdout.strip())
            if result.stderr:
                logger.info("[ORACLE] stderr:\n%s", result.stderr[:500])

            # Also try to parse and log the ci-results.json
            try:
                ci_path = Path(__file__).parent / "templates" / "ci-results.json"
                if ci_path.exists():
                    with open(ci_path) as f:
                        ci_data = json.load(f)
                    # Get the latest result
                    latest = ci_data[-1] if isinstance(ci_data, list) else ci_data
                    checks = latest.get("checks", [])
                    for check in checks:
                        name = check.get("name", "?")
                        passed = check.get("passed", False)
                        skipped = check.get("skipped", False)
                        if skipped:
                            logger.debug("[ORACLE] %s: SKIPPED", name)
                        elif passed:
                            dur = check.get("duration_ms", "?")
                            logger.info("[ORACLE] %s: PASS (%sms)", name, dur)
                        else:
                            err = check.get("error", "unknown")[:200]
                            logger.warning("[ORACLE] %s: FAIL — %s", name, err)
            except Exception:
                pass  # Non-critical — stdout already logged

            return result.returncode == 0
        except subprocess.TimeoutExpired:
            logger.error("[ORACLE] timed out after 300s")
            return False
        except Exception as exc:
            logger.error("[ORACLE] error: %s", exc)
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

    def _git_resolve_ref(self, ref: str) -> str:
        """Resolve a git ref (tag, branch, SHA) to its commit SHA."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--verify", ref],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=str(self.config.project_root),
            )
            return result.stdout.strip() if result.returncode == 0 else ""
        except Exception:
            return ""

    def _git_bookmark(self, task_id: str, suffix: str, force: bool = False):
        """Create a lightweight bookmark tag for traceability.

        Tags are informational only — never used as reset targets.
        If the tag already exists and force=False, it is left as-is
        (preserving the original commit it points to for checkpoint
        validation).
        Examples: autobuild/TASK-002c/start, autobuild/TASK-002c/verified
        """
        tag_name = f"autobuild/{task_id}/{suffix}"

        if not force:
            # Check if tag already exists — don't overwrite
            existing = self._git_resolve_ref(f"refs/tags/{tag_name}")
            if existing:
                logger.info("[GIT] Tag %s already exists at %s — keeping", tag_name, existing[:8])
                return

        try:
            subprocess.run(
                ["git", "tag", "-f", tag_name],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=str(self.config.project_root),
            )
            logger.info("[GIT] Tagged HEAD as %s", tag_name)
        except Exception as exc:
            logger.warning("[GIT] Failed to create tag %s: %s", tag_name, exc)

    def _git_soft_rollback(self, task_id: str, baseline_sha: str):
        """Revert commits since baseline via git revert (non-destructive).

        Creates a new revert commit instead of using git reset --hard.
        Safe to use in a shared working tree.
        """
        head_sha = self._git_head_sha()
        if not head_sha or head_sha == baseline_sha:
            logger.info("[GIT] Nothing to revert for %s", task_id)
            return

        cwd = str(self.config.project_root)

        try:
            # Revert all commits between baseline and HEAD (staged, not committed)
            revert_result = subprocess.run(
                ["git", "revert", "--no-commit", f"{baseline_sha}..HEAD"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=cwd,
            )
            if revert_result.returncode != 0:
                logger.warning(
                    "[GIT] git revert failed (rc=%d): %s",
                    revert_result.returncode,
                    revert_result.stderr[:300],
                )
                # Fall back to leaving the commits in place — safer than forcing
                return

            # Commit the revert
            commit_result = subprocess.run(
                [
                    "git", "commit", "-m",
                    f"[{task_id}] Revert failed attempt (QA: NEEDS_WORK)\n\n"
                    f"Reverted commits {baseline_sha[:8]}..{head_sha[:8]}",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=cwd,
            )
            if commit_result.returncode == 0:
                logger.info(
                    "[GIT] Soft rollback: reverted %s..%s for %s",
                    baseline_sha[:8], head_sha[:8], task_id,
                )
            else:
                logger.warning(
                    "[GIT] Revert commit failed: %s",
                    commit_result.stderr[:300],
                )
        except Exception as exc:
            logger.warning("[GIT] Soft rollback failed for %s: %s", task_id, exc)

    # -- reporting ---------------------------------------------------------

    def _generate_report(self):
        """Generate summary report with per-status breakdown."""
        tasks = self.task_mgr.prd["tasks"]
        by_status: Dict[str, int] = {}
        total_retries = 0
        for t in tasks:
            s = t["status"]
            by_status[s] = by_status.get(s, 0) + 1
            total_retries += t.get("retry_count", 0)

        completed = by_status.get("complete", 0)
        total = len(tasks)

        lines = [
            "\n" + "=" * 60,
            "  Orchestrator Run Summary",
            "=" * 60,
            f"  Phase:            {self.phase}",
            f"  Iterations used:  {self.iteration}",
            f"  Tasks completed:  {completed}/{total}",
            f"  Total retries:    {total_retries}",
            "",
            "  Status breakdown:",
        ]
        for status in ["complete", "in_progress", "pending", "deferred"]:
            count = by_status.get(status, 0)
            if count:
                lines.append(f"    {status:14s} {count}")

        lines.append("")
        lines.append("  Per-task detail:")
        for t in tasks:
            retry = t.get("retry_count", 0)
            split = t.get("split_into")
            extra = ""
            if retry:
                extra += f" retry={retry}"
            if split:
                extra += f" → {','.join(split)}"
            lines.append(f"    {t['id']:12s} {t['status']:12s} {t['title']}{extra}")

        lines.append("=" * 60 + "\n")
        report = "\n".join(lines)

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
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Stream agent stderr output in real time for verbose monitoring",
    )

    args = parser.parse_args()

    _setup_logging()

    config = OrchestratorConfig(Path(args.config))

    orch = Orchestrator(config, args.phase, stream=args.stream)
    orch.run(args.max_iterations, args.resume)


if __name__ == "__main__":
    main()
