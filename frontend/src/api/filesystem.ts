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
 *                          entries: [alpha (dir), readme.txt (file)] }
 *   '/error'          → rejection: new Error('Simulated network error')
 *                        (non-AbortError; exercises the error-state UI path)
 *   <any other path>  → root response (fallback, same as undefined / '')
 *
 * AbortSignal takes priority over all canned outcomes:
 *   - Pre-aborted signal → DOMException('Aborted', 'AbortError'), synchronous.
 *   - Mid-flight abort   → DOMException('Aborted', 'AbortError'), via listener.
 * ---------------------------------------------------------------------------
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface FilesystemBrowseResponse {
  path: string;
  parent: string | null;
  entries: Array<{ name: string; type: 'directory' | 'file' }>;
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
 * '/error' is intentionally absent — it is handled as a rejection case below.
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
// browseDirectory
// ---------------------------------------------------------------------------

/**
 * Browse a server-side directory.
 *
 * @param path   Absolute path to browse. `undefined` and `''` are both
 *               equivalent and return the root response. Matching is exact
 *               and case-sensitive — no normalization is applied.
 * @param signal Optional AbortSignal. Abort is checked at two points:
 *               (1) Synchronously on call, before the macrotask delay.
 *                   If already aborted, rejects with DOMException('AbortError')
 *                   without entering setTimeout.
 *               (2) Mid-flight, via `signal.addEventListener('abort', …, { once: true })`.
 *                   If the signal fires during the setTimeout delay, the
 *                   promise rejects with DOMException('AbortError') before the
 *                   canned response is resolved.
 *
 * @returns A **deep copy** of the matching canned response, so that callers
 *          mutating the returned `entries` array do not affect subsequent calls.
 */
export function browseDirectory(
  path?: string,
  signal?: AbortSignal,
): Promise<FilesystemBrowseResponse> {
  // ── Checkpoint 1: pre-delay abort check (synchronous) ────────────────────
  // Runs before any async work. Takes priority over all canned outcomes,
  // including the '/error' rejection path.
  if (signal?.aborted === true) {
    return Promise.reject(new DOMException('Aborted', 'AbortError'));
  }

  // ── Resolve the canned outcome for this path ──────────────────────────────
  // Exact string matching — undefined and '' both map to the root key '/'.
  const key = path === undefined || path === '' ? '/' : path;

  // ── Build and return the deferred Promise ─────────────────────────────────
  return new Promise<FilesystemBrowseResponse>((resolve, reject) => {
    // ── Checkpoint 2: mid-flight abort listener ───────────────────────────
    // Registered with { once: true } so it auto-removes when the abort event
    // fires. The resolve branch also calls removeEventListener explicitly to
    // ensure no listener accumulation on repeated successful calls with the
    // same signal.
    const rejectHandler = (): void => {
      reject(new DOMException('Aborted', 'AbortError'));
    };
    signal?.addEventListener('abort', rejectHandler, { once: true });

    // ── Macrotask delay (simulates network latency) ───────────────────────
    // setTimeout (macrotask) ensures React StrictMode cleanup fires before
    // the promise settles. Promise.resolve() (microtask) is not acceptable
    // because it makes the mid-flight abort path non-exercisable.
    setTimeout(() => {
      // Remove the abort listener before settling the promise on every
      // outcome (both resolve and reject). This is required because { once }
      // only cleans up when the abort event fires — it does NOT clean up on
      // a successful resolution. Without explicit removal here, repeated
      // successful calls accumulate listeners on the same signal.
      signal?.removeEventListener('abort', rejectHandler);

      // '/error' → non-AbortError rejection (exercises error-state UI path)
      if (key === '/error') {
        reject(new Error('Simulated network error'));
        return;
      }

      // All other keys: look up the canned map, fall back to root response.
      // CANNED_MAP['/'] is always present; the non-null assertion silences
      // the noUncheckedIndexedAccess widening to `| undefined`.
      const canned = CANNED_MAP[key] ?? (CANNED_MAP['/'] as FilesystemBrowseResponse);
      resolve(deepCopy(canned));
    }, 0);
  });
}
