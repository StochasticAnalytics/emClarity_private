/**
 * filesystem.ts — stub API for browsing the server filesystem.
 *
 * NOTE: Node ≥ 17 is required (or a DOMException polyfill must be provided)
 * because `DOMException` is not a built-in global in older Node versions.
 * Failing to satisfy this in CI produces:
 *   ReferenceError: DOMException is not defined
 * rather than a test failure.
 *
 * ---------------------------------------------------------------------------
 * Canned fake-tree (development stub)
 *
 * Lookup uses EXACT STRING MATCHING — no normalization, no case folding, no
 * trailing-slash collapsing. Notable edge-case examples:
 *   '/PROJECTS'       → root fallback  (case mismatch)
 *   '/projects/'      → root fallback  (trailing slash NOT stripped)
 *   ' /projects'      → root fallback  (leading space NOT trimmed)
 *   '/projects/alpha' → root fallback  (child path; no prefix matching)
 *
 * Canned paths and their outcomes:
 *
 *   undefined / ''    → { path: '/', parent: null,
 *                          entries: [projects, home, etc] }  (root fallback key)
 *   '/'               → same root response (explicit key in map)
 *   '/projects'       → { path: '/projects', parent: '/',
 *                          entries: [alpha, readme.txt] }
 *   <any other path>  → root response (fallback, same as undefined / '')
 *
 * AbortSignal takes priority over all canned outcomes:
 *   - Pre-aborted signal → DOMException('The operation was aborted.', 'AbortError'),
 *                          via Promise.reject() — no setTimeout is queued.
 *   - Mid-flight abort   → DOMException('The operation was aborted.', 'AbortError'),
 *                          via listener; clearTimeout() cancels the pending timer.
 * ---------------------------------------------------------------------------
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/**
 * A single filesystem entry returned by the browse API.
 * Contains the entry name and its type on the server.
 */
export interface DirectoryEntry {
  name: string;
  /** Filesystem type — only 'directory' and 'file' are valid; other values fail validation. */
  type: 'directory' | 'file';
}

/**
 * Response shape for a successful browseDirectory call.
 *
 * - `path`: the canonical absolute path of the directory that was listed
 * - `parent`: the parent directory's absolute path, or null if this is the root
 * - `entries`: child entries (both files and subdirectories) within this directory
 *
 * Note: `parent` may be absent in malformed server responses; all consumers
 * must treat `undefined` the same as `null` by coercing with `?? null`.
 */
export interface FilesystemBrowseResponse {
  path: string;
  parent: string | null;
  entries: DirectoryEntry[];
}

// ---------------------------------------------------------------------------
// Canned data
// ---------------------------------------------------------------------------

const ROOT_RESPONSE: FilesystemBrowseResponse = {
  path: '/',
  parent: null, // root has no parent — never '/'
  entries: [
    { name: 'projects', type: 'directory' },
    { name: 'home', type: 'directory' },
    { name: 'etc', type: 'directory' },
  ],
};

/**
 * Canned success responses keyed by exact path string.
 */
const CANNED_MAP: Readonly<Record<string, FilesystemBrowseResponse>> = {
  '/': ROOT_RESPONSE,
  '/projects': {
    path: '/projects',
    parent: '/',
    entries: [
      { name: 'alpha', type: 'directory' },
      { name: 'readme.txt', type: 'file' },
    ],
  },
};

// ---------------------------------------------------------------------------
// Deep-copy helper — ensures callers cannot mutate shared canned data
// ---------------------------------------------------------------------------

function deepCopy(response: FilesystemBrowseResponse): FilesystemBrowseResponse {
  return {
    path: response.path,
    parent: response.parent,
    entries: response.entries.map((e) => ({ name: e.name, type: e.type })),
  };
}

// ---------------------------------------------------------------------------
// Test-only error injection
// ---------------------------------------------------------------------------

/** Module-level store for the injected stub error. null = no injection active. */
let stubError: Error | null = null;

/**
 * Inject an error to be thrown by the next non-aborted browseDirectory call.
 *
 * @testonly
 *
 * When set to a non-null Error, the **next non-aborted** browseDirectory call
 * (i.e., the first whose setTimeout callback fires without an abort) will reject
 * with that error and automatically reset the injection back to null. Only that
 * one call is affected; subsequent calls return canned data normally.
 *
 * Last-write-wins: calling __setStubError multiple times before any browseDirectory
 * call results in only the most recent value being active.
 *
 * Calling __setStubError(null) explicitly clears any pending injected error
 * without issuing a browseDirectory call.
 *
 * AbortSignal priority: if a call is aborted (either pre-abort or mid-flight),
 * the AbortError takes precedence and the injected error is NOT consumed —
 * it remains set for the next non-aborted call.
 *
 * Teardown: always call __setStubError(null) in afterEach to prevent cross-test
 * state pollution.
 */
export function __setStubError(error: Error | null): void {
  stubError = error;
}

// ---------------------------------------------------------------------------
// browseDirectory
// ---------------------------------------------------------------------------

/**
 * Browse a server-side directory.
 *
 * @param path   Absolute path to browse. `undefined` and `''` are both
 *               equivalent and return the root response. Matching is exact
 *               and case-sensitive — no normalization is applied.
 * @param signal Optional AbortSignal. Abort is checked at three points:
 *               (1) Synchronously on call, before any async work.
 *                   If already aborted, rejects immediately via Promise.reject()
 *                   — no setTimeout is queued for that call.
 *               (2) Mid-flight, via `signal.addEventListener('abort', …, { once: true })`.
 *                   If the signal fires during the setTimeout delay, the promise
 *                   rejects with DOMException('The operation was aborted.', 'AbortError')
 *                   and the pending timer is cancelled via clearTimeout().
 *               (3) Inside the setTimeout callback itself (race-window protection):
 *                   if the abort event fired and cleared the { once: true } listener
 *                   just before the macrotask ran, the callback re-checks signal.aborted
 *                   and rejects rather than resolving.
 *
 * @returns A **deep copy** of the matching canned response, so that callers
 *          mutating the returned `entries` array do not affect subsequent calls.
 */
export function browseDirectory(
  path?: string,
  signal?: AbortSignal,
): Promise<FilesystemBrowseResponse> {
  // ── Checkpoint 1: pre-delay abort check (synchronous) ────────────────────
  // If signal is already aborted at call time, reject immediately via
  // Promise.reject() — no setTimeout is queued for this call.
  if (signal?.aborted) {
    return Promise.reject(new DOMException('The operation was aborted.', 'AbortError'));
  }

  // ── Resolve the canned outcome for this path ──────────────────────────────
  // Exact string matching — undefined and '' both map to the root key '/'.
  const key = path === undefined || path === '' ? '/' : path;

  // ── Build and return the deferred Promise ─────────────────────────────────
  return new Promise<FilesystemBrowseResponse>((resolve, reject) => {
    // Declare handle before rejectHandler so the closure captures the binding.
    let handle: ReturnType<typeof setTimeout>;

    // ── Checkpoint 2: mid-flight abort listener ───────────────────────────
    // Registered with { once: true } so it auto-removes when the abort event
    // fires. clearTimeout() cancels the pending macrotask so the setTimeout
    // callback cannot fire after the Promise has already settled (which would
    // silently consume an injected __setStubError value).
    const rejectHandler = (): void => {
      clearTimeout(handle);
      reject(new DOMException('The operation was aborted.', 'AbortError'));
    };

    if (signal) {
      signal.addEventListener('abort', rejectHandler, { once: true });
    }

    // ── Macrotask delay (simulates network latency) ───────────────────────
    // setTimeout (macrotask) ensures React StrictMode cleanup fires before
    // the promise settles. Promise.resolve() (microtask) is not acceptable
    // because it makes the mid-flight abort path non-exercisable.
    handle = setTimeout(() => {
      // Remove the abort listener before settling the promise on every
      // outcome (both resolve and reject). This is required because { once }
      // only cleans up when the abort event fires — it does NOT clean up on
      // a successful resolution. Without explicit removal here, repeated
      // successful calls accumulate listeners on the same signal.
      if (signal) {
        signal.removeEventListener('abort', rejectHandler);
      }

      // ── Checkpoint 3: race-window protection ──────────────────────────
      // Handles the narrow window where the abort event fires (clearing the
      // { once: true } listener) and then the macrotask fires before
      // clearTimeout() had effect.
      if (signal?.aborted) {
        reject(new DOMException('The operation was aborted.', 'AbortError'));
        return;
      }

      // ── Test-only error injection ─────────────────────────────────────
      // Sample the injected error at macrotask-fire time. If set, consume it
      // (reset to null) and reject with it. The injected error is only consumed
      // by non-aborted calls (aborts return early before this point).
      const injected = stubError;
      if (injected !== null) {
        stubError = null;
        reject(injected);
        return;
      }

      // ── Canned response lookup ────────────────────────────────────────
      // All paths not in CANNED_MAP fall back to the root response.
      // CANNED_MAP['/'] is always present; the non-null assertion silences
      // the noUncheckedIndexedAccess widening to `| undefined`.
      const canned = CANNED_MAP[key] ?? (CANNED_MAP['/'] as FilesystemBrowseResponse);
      resolve(deepCopy(canned));
    }, 0);
  });
}
