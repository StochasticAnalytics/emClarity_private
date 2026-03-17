/**
 * filesystem.ts — API for browsing the server filesystem.
 *
 * Calls GET /api/v1/filesystem/browse?path=... on the backend.
 * When called without a path (or with undefined / ''), the backend
 * defaults to the server's home directory.
 *
 * NOTE: Node ≥ 17 is required (or a DOMException polyfill must be provided)
 * because `DOMException` is not a built-in global in older Node versions.
 * Failing to satisfy this in CI produces:
 *   ReferenceError: DOMException is not defined
 * rather than a test failure.
 */

import { apiClient, ApiError } from './client.ts'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/**
 * A single filesystem entry returned by the browse API.
 */
export interface DirectoryEntry {
  name: string
  /** Filesystem type — the backend only returns 'directory' entries. */
  type: 'directory' | 'file'
  /** Absolute path to this entry on the server. */
  path: string
}

/**
 * Response shape for a successful browseDirectory call.
 *
 * - `path`    the canonical absolute path of the directory that was listed
 * - `parent`  the parent directory's absolute path, or null if this is root
 * - `entries` child entries (subdirectories) in this directory
 *
 * Note: `parent` may be absent in malformed server responses; all consumers
 * must treat `undefined` the same as `null` by coercing with `?? null`.
 */
export interface FilesystemBrowseResponse {
  path: string
  parent: string | null
  entries: DirectoryEntry[]
}

// Re-export for consumers that only import from this module.
export { ApiError }

// ---------------------------------------------------------------------------
// browseDirectory
// ---------------------------------------------------------------------------

/**
 * Browse a server-side directory via GET /api/v1/filesystem/browse.
 *
 * @param path   Absolute path to browse. `undefined` and `''` both omit the
 *               query parameter, which causes the backend to return the
 *               server's home directory.
 *
 * @param signal Optional AbortSignal for request cancellation. When the
 *               signal fires, `fetch` rejects with an AbortError whose
 *               `name === 'AbortError'`. Consumers should check
 *               `error.name === 'AbortError'` (not instanceof DOMException)
 *               for cross-runtime compatibility.
 *
 * @returns The parsed FilesystemBrowseResponse from the backend.
 * @throws  ApiError on any non-2xx HTTP status.
 */
export async function browseDirectory(
  path?: string,
  signal?: AbortSignal,
): Promise<FilesystemBrowseResponse> {
  let endpoint = '/api/v1/filesystem/browse'
  if (path !== undefined && path !== '') {
    endpoint += `?path=${encodeURIComponent(path)}`
  }
  return apiClient.get<FilesystemBrowseResponse>(endpoint, signal)
}
