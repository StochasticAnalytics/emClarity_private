---
name: Claude CLI Patterns
description: Empirically verified patterns for invoking claude CLI as subprocess — output formats, flags, streaming, subprocess management
type: reference
---

# Claude CLI Invocation Patterns

## Output Formats

| Format | Flag | Stdout | Use Case |
|--------|------|--------|----------|
| `json` | `--output-format json` | Single JSON dict | Buffered, parse after exit |
| `stream-json` | `--output-format stream-json --verbose` | Newline-delimited JSON (one object/line) | Real-time monitoring |
| `text` | `--output-format text` | Plain text | Human-readable |

**stream-json requires `--verbose`** — errors without it: `Error: When using --print, --output-format=stream-json requires --verbose`

## Verified Flag Behavior

| Flag | Effect | Notes |
|------|--------|-------|
| `--verbose` | Outputs to **stdout** (NOT stderr) | Counterintuitive. In json mode, changes output from dict to array. |
| `--chrome` | Enables browser automation | Confirmed NO negative effect when Chrome extension unavailable. Keep for future GUI dev. |
| `--dangerously-skip-permissions` | Bypasses permission prompts | Works in subprocess mode. |
| `--effort high` | Sets reasoning effort | Valid values: low, medium, high, max |
| `--system-prompt` | Replaces system prompt | Supports long strings (6KB+ tested, ARG_MAX=3.2MB) |
| `--append-system-prompt` | Appends to default system prompt | Use for injecting memory/context without replacing defaults |
| `--max-turns N` | Limits agentic turns | Print mode only |

## stream-json Event Types

Each line is a JSON object with a `type` field:
```
{"type":"system", "subtype":"init", ...}     — session init, lists tools/model
{"type":"assistant", "message":{...}, ...}   — model output (text blocks, tool_use blocks)
{"type":"user", ...}                         — tool results fed back to model
{"type":"rate_limit_event", ...}             — rate limit status (skip/ignore)
{"type":"result", "subtype":"success", ...}  — final summary (same schema as json mode)
```

The `type=result` event contains: `result` (text), `total_cost_usd`, `num_turns`, `usage`, `stop_reason`.

## Subprocess Patterns

### Buffered (non-streaming)
```python
result = subprocess.run(
    cmd, input=user_message, capture_output=True, text=True,
    timeout=600, cwd=project_root,
)
# result.stdout = JSON string
```

### Streaming (real-time)
```python
proc = subprocess.Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE, text=True)
proc.stdin.write(message); proc.stdin.close()

# Background thread drains stderr (usually empty, prevents deadlock)
threading.Thread(target=lambda: proc.stderr.read(), daemon=True).start()

# Main thread reads stdout line-by-line
for line in proc.stdout:
    event = json.loads(line.strip())
    # Display/process event
```

### Caution: select() + readline() on stdout
```python
# This pattern caused a deadlock in our case — stdout was a buffered JSON blob
ready, _, _ = select.select([proc.stdout, proc.stderr], [], [], 1.0)
line = stream.readline()  # May block if no newline available yet
```

**What we observed:** `select()` reported data available, but `readline()` blocked waiting for `\n`. With `--output-format json`, stdout is one large JSON blob written at exit. The OS pipe buffer (64KB) filled, the writer blocked, and the process hung. The threading approach (background thread calls `.read()` on one pipe while main thread iterates the other) resolved this in our case. This may not apply to all subprocess scenarios, but it's worth considering when the child process buffers large output.
