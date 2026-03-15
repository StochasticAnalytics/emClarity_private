/**
 * filesystem.ts — stub API for browsing the server filesystem.
 *
 * NOTE: Node ≥ 17 is required (or a DOMException polyfill must be provided)
 * because `DOMException` is not a built-in global in older Node versions.
 * Failing to satisfy this in CI produces:
 *   ReferenceError: DOMException is not defined
 * rather than a test failure.
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
//
// Lookup rules (matching is EXACT and CASE-SENSITIVE — no normalization):
//   • undefined / '' / any path not listed below → root response ('/').
//   • '/projects'                                → /projects response.
//
// Notable edge cases (intentional, not bugs):
//   • '/PROJECTS'       → root (case mismatch falls through to root)
//   • '/projects/'      → root (trailing slash is NOT stripped)
//   • ' /projects'      → root (leading space is NOT trimmed)
//   • '/projects/alpha' → root (child path; only exact canned keys match,
//                               there is NO partial-prefix matching)
// ---------------------------------------------------------------------------

const CANNED_MAP: Readonly<Record<string, FilesystemBrowseResponse>> = {
  '/': {
    path: '/',
    parent: null, // root has no parent — never '/'
    entries: [
      { name: 'projects', type: 'directory' },
      { name: 'home', type: 'directory' },
      { name: 'etc', type: 'directory' },
    ],
  },
  '/projects': {
    path: '/projects',
    parent: '/',
    entries: [
      { name: 'alpha', type: 'directory' },
      { name: 'readme.txt', type: 'file' },
    ],
  },
};

/** Sentinel key for the root / fallback response. */
const ROOT_KEY = '/';

// ---------------------------------------------------------------------------
// Error-mode state (test seam — non-production only)
// ---------------------------------------------------------------------------

type ErrorMode = 'none' | 'network' | 'invalid-body';

let errorMode: ErrorMode = 'none';

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
 * @param signal Optional AbortSignal. Checked at two checkpoints:
 *               (1) Immediately on call, before the async delay. If already
 *                   aborted, rejects with DOMException('AbortError') without
 *                   entering the macrotask boundary.
 *               (2) After the macrotask delay. If aborted during the wait,
 *                   rejects with DOMException('AbortError') before resolving.
 *
 * @returns A **deep copy** of the matching canned response, so that callers
 *          mutating the returned `entries` array do not affect subsequent calls.
 */
export async function browseDirectory(
  path?: string,
  signal?: AbortSignal,
): Promise<FilesystemBrowseResponse> {
  // ── Checkpoint 1: pre-delay abort check ──────────────────────────────────
  // AbortSignal checkpoint 1 takes precedence over error mode.
  if (signal?.aborted === true) {
    throw new DOMException('The operation was aborted.', 'AbortError');
  }

  // ── Macrotask boundary ────────────────────────────────────────────────────
  // Must use setTimeout (macrotask), NOT Promise.resolve() (microtask).
  // setTimeout guarantees React StrictMode's useEffect cleanup fires before
  // the promise settles. A Promise.resolve()-based delay crosses only a
  // microtask boundary and fails the macrotask-ordering verification.
  await new Promise<void>((resolve) => setTimeout(resolve, 0));

  // ── Checkpoint 2: post-delay abort check ─────────────────────────────────
  // Also takes precedence over 'invalid-body' error mode.
  if (signal?.aborted === true) {
    throw new DOMException('The operation was aborted.', 'AbortError');
  }

  // ── Error-mode handling (non-production test seam) ────────────────────────
  if (errorMode === 'network') {
    throw new TypeError('Failed to fetch');
  }
  if (errorMode === 'invalid-body') {
    // Intentionally invalid payload — exercises parse-error code paths.
    return { path: 42, entries: null } as unknown as FilesystemBrowseResponse;
  }

  // ── Normal path ───────────────────────────────────────────────────────────
  const key = path === undefined || path === '' ? ROOT_KEY : path;
  // CANNED_MAP[ROOT_KEY] is always present by construction; the non-null
  // assertion silences the noUncheckedIndexedAccess widening to `| undefined`.
  const canned = CANNED_MAP[key] ?? (CANNED_MAP[ROOT_KEY] as FilesystemBrowseResponse);
  return deepCopy(canned);
}

// ---------------------------------------------------------------------------
// __setErrorMode — test seam (tree-shaken from production bundles)
//
// The type is `(...) | undefined` to reflect that the function is absent in
// production. Call sites in tests should null-check or use optional chaining:
//   __setErrorMode?.('none')
//
// Required teardown pattern (prevents state leakage across tests):
//   afterEach(() => __setErrorMode?.('none'))
//
// Note: whether module-level state (`errorMode`) persists across test *files*
// depends on the `resetModules` configuration. With `resetModules: false`
// (the Jest/Vitest default), `errorMode` is shared across all test files that
// import this module in the same worker. Use `afterEach` teardown explicitly.
// ---------------------------------------------------------------------------

/**
 * Configure the error mode for the `browseDirectory` stub.
 *
 * **Only defined when `process.env.NODE_ENV !== 'production'`** (undefined in
 * production builds). Always use optional chaining at call sites:
 * `__setErrorMode?.('none')`.
 *
 * @param mode
 *   - `'none'`         — normal canned-data behavior (default at module load)
 *   - `'network'`      — rejects with `TypeError('Failed to fetch')` after delay
 *   - `'invalid-body'` — resolves with a structurally invalid payload after delay
 *
 * AbortSignal checkpoint 1 (pre-delay) always takes precedence over error mode.
 * AbortSignal checkpoint 2 (post-delay) takes precedence over `'invalid-body'`.
 *
 * @example
 * // Required teardown to prevent state leakage across tests:
 * afterEach(() => __setErrorMode?.('none'));
 */
export const __setErrorMode: ((mode: 'none' | 'network' | 'invalid-body') => void) | undefined =
  process.env.NODE_ENV !== 'production'
    ? (mode: ErrorMode): void => {
        errorMode = mode;
      }
    : undefined;
