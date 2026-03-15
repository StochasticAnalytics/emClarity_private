/**
 * useDirectoryNavigation.ts
 *
 * Custom hook containing all non-rendering logic for directory navigation.
 * Implements a 5-branch state machine with full AbortController lifecycle,
 * StrictMode safety, structural response validation, and stable callbacks.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { browseDirectory, type FilesystemBrowseResponse } from '@/api/filesystem';

// Re-export so consumers (Aa-2b, etc.) can type props without re-declaring shape.
export type { FilesystemBrowseResponse };

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ERROR_MESSAGE = 'Failed to load directory. Please try again.' as const;

// ---------------------------------------------------------------------------
// Structural response validation (AC9)
//
// Checks are ordered so each one precedes any property access that would
// throw if a prior check had failed.
// ---------------------------------------------------------------------------

function validateResponse(response: unknown): response is FilesystemBrowseResponse {
  // Zeroth check: must be a non-null object (catches null, primitives, undefined)
  if (response === null || typeof response !== 'object') {
    return false;
  }

  const r = response as Record<string, unknown>;

  // path must be a string (rejects missing key, numbers, null, etc.)
  const path: unknown = r['path'];
  if (typeof path !== 'string') {
    return false;
  }

  // parent must be exactly a string or null.
  // undefined (key absent or set to undefined) is explicitly rejected.
  const parent: unknown = r['parent'];
  if (parent !== null && typeof parent !== 'string') {
    return false;
  }

  // entries must be an array (rejects missing key, null, objects, etc.)
  const entries: unknown = r['entries'];
  if (!Array.isArray(entries)) {
    return false;
  }

  // Each entry must be a plain non-null object with valid name and type.
  // This check precedes any .name or .type access to prevent TypeError crashes.
  for (const entry of entries) {
    if (entry === null || typeof entry !== 'object') {
      return false;
    }
    const e = entry as Record<string, unknown>;

    // name: must be a string (null, undefined, and non-strings are all rejected
    // by the typeof check alone; no separate null guard is needed)
    const name: unknown = e['name'];
    if (typeof name !== 'string') {
      return false;
    }

    // type: case-sensitive exact match against the allowed set
    const type: unknown = e['type'];
    if (type !== 'directory' && type !== 'file') {
      return false;
    }
  }

  return true;
}

// ---------------------------------------------------------------------------
// Public interface
// ---------------------------------------------------------------------------

export interface UseDirectoryNavigationReturn {
  /** The path currently being shown (updated on successful navigation). */
  currentPath: string;
  /**
   * True while any non-retry navigation request is in-flight.  This includes
   * the initial mount-time request (branch 1) and every subsequent navigate()
   * call, regardless of whether lastGoodData is already populated.
   */
  isLoading: boolean;
  /** True only while a Retry request is in-flight (branch 5). */
  retryInFlight: boolean;
  /**
   * null when there is no error; 'Failed to load directory. Please try again.'
   * when the most recent navigation failed.  Never '' or undefined.
   */
  errorMessage: string | null;
  /** The full last-successful response, preserved through errors. null before first success. */
  lastGoodData: FilesystemBrowseResponse | null;
  /** response.path of the last success, substituting '/' for ''. null before first success. */
  successPath: string | null;
  /** response.entries.length of the last success. null before first success. */
  successItemCount: number | null;
  /** Navigate to a new path. Whitespace-only is a no-op; '' calls browseDirectory() with no arg. */
  navigate: (path: string) => void;
  /** Re-issue the last failed request. No-op when not in an error state. */
  retry: () => void;
}

// ---------------------------------------------------------------------------
// Hook implementation
// ---------------------------------------------------------------------------

export function useDirectoryNavigation(
  initialPath?: string | null,
): UseDirectoryNavigationReturn {
  // ── Resolve initialPath ──────────────────────────────────────────────────
  // Guard: null, undefined, or non-string are all treated as absent.
  const resolvedInitialPath: string =
    initialPath == null || typeof initialPath !== 'string'
      ? ''
      : initialPath.trim();

  // ── State ────────────────────────────────────────────────────────────────
  // isLoading starts true so branch 1 (initial-loading) is the first state.
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [retryInFlight, setRetryInFlight] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [lastGoodData, setLastGoodData] = useState<FilesystemBrowseResponse | null>(null);
  const [successPath, setSuccessPath] = useState<string | null>(null);
  const [successItemCount, setSuccessItemCount] = useState<number | null>(null);
  // currentPath is initialised to the trimmed prop value (never raw/null).
  const [currentPath, setCurrentPath] = useState<string>(resolvedInitialPath);

  // ── Refs ─────────────────────────────────────────────────────────────────
  // AbortController is stored in a ref (not state) so that StrictMode's
  // second-invocation effect sees the ref that was written by the *first*
  // invocation's cleanup, guaranteeing a fresh controller on re-mount.
  const currentAbortControllerRef = useRef<AbortController | null>(null);

  // Mirror the three guard values used by retry() as refs so that retry's
  // useCallback dependency array can remain [doNavigate] — a stable reference.
  // Without this, retry would need isLoading/retryInFlight/errorMessage in its
  // deps, causing a new function reference on every navigation state transition
  // and violating AC11's keyboard-listener-stability guarantee.
  const isLoadingRef = useRef<boolean>(true);
  const retryInFlightRef = useRef<boolean>(false);
  const errorMessageRef = useRef<string | null>(null);

  // retryPath is written before every browseDirectory call (AC6):
  //   null  → the call was made with no argument (mirrors empty/absent path)
  //   string → the trimmed path argument passed to the call
  const retryPathRef = useRef<string | null>(
    resolvedInitialPath !== '' ? resolvedInitialPath : null,
  );

  // ── Core navigation dispatcher ───────────────────────────────────────────
  // Called by both navigate() and retry().  All AbortController bookkeeping
  // and state transitions live here.
  //
  // pathArg: null  → call browseDirectory() with no argument
  //          string → call browseDirectory(pathArg, signal)
  // isRetry: false → regular navigation (transitions to branch 1 or similar)
  //          true  → retry (transitions to branch 5)
  const doNavigate = useCallback(
    (pathArg: string | null, isRetry: boolean): void => {
      // ── Synchronous abort of prior in-flight request ─────────────────────
      // This abort, the controller creation, and the state update all happen
      // in the same synchronous execution block — no render cycle in between.
      currentAbortControllerRef.current?.abort();

      const controller = new AbortController();
      currentAbortControllerRef.current = controller;
      const { signal } = controller;

      // ── Record retryPath before the call (AC6) ───────────────────────────
      retryPathRef.current = pathArg;

      // ── Synchronous state transition ─────────────────────────────────────
      if (isRetry) {
        // Branch 5: retryInFlight=true, isLoading stays false, error preserved.
        retryInFlightRef.current = true;
        setRetryInFlight(true);
        // errorMessage, lastGoodData, successPath, successItemCount: unchanged
      } else {
        // Branch 1 (or fresh re-navigation): isLoading=true, clear error.
        isLoadingRef.current = true;
        retryInFlightRef.current = false;
        errorMessageRef.current = null;
        setIsLoading(true);
        setRetryInFlight(false);
        setErrorMessage(null);
        // lastGoodData, successPath, successItemCount: preserved (AC7)
      }

      // ── Issue the request ─────────────────────────────────────────────────
      const promise: Promise<FilesystemBrowseResponse> =
        pathArg !== null
          ? browseDirectory(pathArg, signal)
          : browseDirectory(undefined, signal);

      // ── Handle success ────────────────────────────────────────────────────
      promise.then(
        (response: FilesystemBrowseResponse) => {
          // AC5: abort guard before ANY setState call.
          if (signal.aborted) return;

          // AC9: structural validation — invalid body → error state.
          if (!validateResponse(response)) {
            errorMessageRef.current = ERROR_MESSAGE;
            setErrorMessage(ERROR_MESSAGE);
            if (isRetry) {
              retryInFlightRef.current = false;
              setRetryInFlight(false);
            } else {
              isLoadingRef.current = false;
              setIsLoading(false);
            }
            // lastGoodData/successPath/successItemCount preserved (AC6/AC7)
            return;
          }

          // AC5: final abort guard before committing success state.
          if (signal.aborted) return;

          const newSuccessPath = response.path === '' ? '/' : response.path;
          const newSuccessItemCount = response.entries.length;

          // Commit all success state in one synchronous block (React batches these).
          errorMessageRef.current = null;
          setCurrentPath(response.path);
          setLastGoodData(response);
          setErrorMessage(null);
          setSuccessPath(newSuccessPath);
          setSuccessItemCount(newSuccessItemCount);
          if (isRetry) {
            retryInFlightRef.current = false;
            setRetryInFlight(false);
          } else {
            isLoadingRef.current = false;
            setIsLoading(false);
          }
        },
        (error: unknown) => {
          // AC4: AbortError → silently ignore, no state transition.
          if (error instanceof Error && error.name === 'AbortError') return;

          // AC5: abort guard — also catches any late-settling promises.
          if (signal.aborted) return;

          // Navigation failure: set error, preserve lastGoodData (AC6).
          errorMessageRef.current = ERROR_MESSAGE;
          setErrorMessage(ERROR_MESSAGE);
          if (isRetry) {
            retryInFlightRef.current = false;
            setRetryInFlight(false);
          } else {
            isLoadingRef.current = false;
            setIsLoading(false);
          }
          // lastGoodData, successPath, successItemCount: not cleared (AC6/AC7)
        },
      );
    },
    // State setters from useState are stable references; refs are also stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  // ── Mount effect ─────────────────────────────────────────────────────────
  // Fires once on mount.  Cleanup aborts any in-flight request on unmount,
  // preventing stale setState calls (AC4/AC5).
  useEffect(() => {
    const pathArg = resolvedInitialPath !== '' ? resolvedInitialPath : null;
    doNavigate(pathArg, false);

    return () => {
      currentAbortControllerRef.current?.abort();
    };
    // We intentionally omit resolvedInitialPath and doNavigate from deps:
    // - resolvedInitialPath is only consumed at mount time (AC1 contract).
    // - doNavigate is stable (useCallback with []).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── navigate callback ─────────────────────────────────────────────────────
  const navigate = useCallback(
    (path: string): void => {
      // AC8: whitespace-only path is a no-op (strictly whitespace, length > 0).
      if (path.length > 0 && path.trim() === '') return;

      // Map empty string to no-argument call (same semantics as mount with '').
      const trimmed = path.trim();
      const pathArg: string | null = trimmed === '' ? null : trimmed;

      doNavigate(pathArg, false);
    },
    [doNavigate],
  );

  // ── retry callback ────────────────────────────────────────────────────────
  // Reads guard values from refs (not state) so this callback's reference stays
  // stable across navigation state transitions — satisfying AC11.  The refs are
  // kept in sync with the corresponding state inside doNavigate.
  const retry = useCallback((): void => {
    // No-op when not in error state (AC6):
    //   - branch 1: isLoadingRef is true
    //   - branch 2: errorMessageRef is null
    //   - branch 5: retryInFlightRef is true
    if (isLoadingRef.current || retryInFlightRef.current || errorMessageRef.current === null) return;

    const storedRetryPath = retryPathRef.current;

    // Apply the same whitespace guard as navigate (AC6).
    if (storedRetryPath !== null && storedRetryPath.trim() === '') return;

    doNavigate(storedRetryPath, true);
  }, [doNavigate]);

  // ── Return value ──────────────────────────────────────────────────────────
  return {
    currentPath,
    isLoading,
    retryInFlight,
    errorMessage,
    lastGoodData,
    successPath,
    successItemCount,
    navigate,
    retry,
  };
}
