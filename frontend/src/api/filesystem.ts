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
 * trailing-slash collapsing, no leading-space trimming. Notable edge cases:
 *   '/Projects'       → root fallback  (capital P — case mismatch)
 *   '/projects/'      → root fallback  (trailing slash NOT stripped)
 *   '/projects '      → root fallback  (trailing space NOT trimmed)
 *   '//projects'      → root fallback  (double slash; no prefix matching)
 *   '/projects/alpha' → root fallback  (child path; no prefix matching)
 *   '/home'           → root fallback  (appears in root entries but has no
 *                                       dedicated canned entry)
 *   '/etc'            → root fallback  (same as /home above)
 *
 * Canned paths and their outcomes:
 *
 *   undefined / ''    → { path: '/', parent: null,
 *                          entries: [projects, home, etc] }  (root key)
 *   '/'               → same root response (explicit key in map)
 *   '/projects'       → { path: '/projects', parent: '/',
 *                          entries: [alpha, readme.txt] }
 *   <any other path>  → root response (cache miss → fallback)
 *
 * Cache-miss detection: on a cache miss the returned object's `path` field
 * is always `'/'` — NOT the originally requested path. Callers can detect a
 * fallback by comparing `result.path` to the requested path. This is
 * especially relevant for entries that appear in the root listing (`/home`,
 * `/etc`) but have no dedicated canned response.
 *
 * AbortSignal: pre-abort check uses STRICT EQUALITY (`signal.aborted === true`,
 * not merely truthy). `{ aborted: 1 }` does NOT trigger the guard because
 * `1 === true` is false.
 * ---------------------------------------------------------------------------
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/**
 * A single filesystem entry returned by the browse API.
 */
export interface DirectoryEntry {
  name: string
  /** Filesystem type — only 'directory' and 'file' are valid. */
  type: 'directory' | 'file'
}

/**
 * Response shape for a successful browseDirectory call.
 *
 * - `path`    the canonical absolute path of the directory that was listed
 * - `parent`  the parent directory's absolute path, or null if this is root
 * - `entries` child entries (both files and subdirectories) in this directory
 *
 * Note: `parent` may be absent in malformed server responses; all consumers
 * must treat `undefined` the same as `null` by coercing with `?? null`.
 */
export interface FilesystemBrowseResponse {
  path: string
  parent: string | null
  entries: DirectoryEntry[]
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
}

/**
 * Canned success responses keyed by exact path string.
 * Lookup is exact — no normalization is applied to the key.
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
}

// ---------------------------------------------------------------------------
// Deep-copy helper — ensures callers cannot mutate shared canned data
// ---------------------------------------------------------------------------

function deepCopy(response: FilesystemBrowseResponse): FilesystemBrowseResponse {
  return {
    path: response.path,
    parent: response.parent,
    entries: response.entries.map((e) => ({ name: e.name, type: e.type })),
  }
}

// ---------------------------------------------------------------------------
// browseDirectory
// ---------------------------------------------------------------------------

/**
 * Browse a server-side directory (development stub — returns canned data).
 *
 * @param path   Absolute path to browse. `undefined` and `''` are both
 *               equivalent and return the root response. Matching is exact
 *               and case-sensitive — no normalization is applied to `path`
 *               before the canned-map lookup.
 *
 * @param signal Optional AbortSignal. The pre-abort check uses STRICT EQUALITY
 *               (`signal.aborted === true`, not merely truthy). If already
 *               aborted at call time the stub rejects immediately via
 *               `Promise.reject()` — no event listener is attached and no
 *               timer is queued.
 *
 *               AbortError guard in consumers should check `error.name === 'AbortError'`
 *               (name-only, NOT `instanceof DOMException`) for cross-runtime
 *               compatibility (e.g., Node.js environments without a global DOMException).
 *
 * @returns A **deep copy** of the matching canned response. On a cache miss
 *          (any path not in the canned map) the returned object's `path` field
 *          is `'/'` — NOT the originally requested path. Callers can detect the
 *          fallback condition by comparing `result.path` to their requested path.
 *          This is especially relevant for entries that appear in the root listing
 *          (`/home`, `/etc`) but have no dedicated canned response — those paths
 *          are cache misses and return the root response with `path: '/'`.
 *
 * @example
 * const result = await browseDirectory('/home')
 * if (result.path !== '/home') {
 *   // cache miss — fell back to root response
 * }
 */
export function browseDirectory(
  path?: string,
  signal?: AbortSignal,
): Promise<FilesystemBrowseResponse> {
  // Pre-abort check — strict equality: `signal.aborted === true` (not truthy).
  // `{ aborted: 1 }` does NOT trigger this guard because `1 === true` is false.
  // No event listener is attached; this stub only checks at call time.
  if (signal?.aborted === true) {
    return Promise.reject(new DOMException('The operation was aborted.', 'AbortError'))
  }

  // Map undefined and '' to the root key '/'.
  // No normalization is applied — the path is used verbatim as the lookup key.
  const key = path === undefined || path === '' ? '/' : path

  // Exact lookup. On a cache miss fall back to the root response.
  // CANNED_MAP['/'] is always present; the type assertion silences the
  // `| undefined` widening introduced by noUncheckedIndexedAccess.
  const canned = CANNED_MAP[key] ?? (CANNED_MAP['/'] as FilesystemBrowseResponse)

  return Promise.resolve(deepCopy(canned))
}
