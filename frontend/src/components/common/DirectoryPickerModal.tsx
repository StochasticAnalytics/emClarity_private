/**
 * DirectoryPickerModal.tsx — TASK-002b-Aa-i-b-1
 *
 * State and lifecycle core of the Directory Picker Modal.
 *
 * This sub-task defines:
 *   - Props interface (AC1)
 *   - browseDirectory API contract and type exports (AC2)
 *   - Typed 5-branch DirectoryPickerState discriminated struct (AC3)
 *   - useRef-based AbortController lifecycle, StrictMode-safe (AC6)
 *   - Mount-time initialPath bootstrap via initialPathRef (AC5)
 *   - navigate() with functional setState to avoid stale closure (AC7)
 *   - Non-AbortError error transitions that clear isLoading (AC8)
 *
 * Component returns null in this sub-task.
 * Sub-task b-2 replaces `return null` with the full portal + UI,
 * consuming the state shape defined here.
 *
 * Deferred to other tasks:
 *   - Portal and DOM structure (TASK-002b-Aa-i-b-2)
 *   - Error display / Retry onClick (TASK-002b-Aa-i-c)
 *   - Focus trap and Escape handler (TASK-002b-Aa-3)
 *   - returnFocusRef call-site / Select button (TASK-002b-Ab)
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import type { RefObject } from 'react';
import { browseDirectory } from '@/api/filesystem';

// ---------------------------------------------------------------------------
// Re-exported types (consumed by sub-tasks Aa-ii and Ab without re-defining)
// ---------------------------------------------------------------------------

export type { BrowseDirectoryResponse, DirectoryEntry } from '@/api/filesystem';
import type { BrowseDirectoryResponse, DirectoryEntry } from '@/api/filesystem';

// ---------------------------------------------------------------------------
// State machine types (AC3)
// ---------------------------------------------------------------------------

/**
 * The five statuses of the directory picker state machine.
 *
 * Invariants (enforced by navigate() and the mount effect, never broken):
 *   - isLoading === true  iff  status is 'initial-loading' or 'loading'
 *   - error !== null       iff  status === 'error'
 */
export type PickerStatus = 'idle' | 'initial-loading' | 'loading' | 'success' | 'error';

/**
 * Single state object for the directory picker modal.
 *
 * Five branches (see PickerStatus):
 *
 * idle            — initial value before mount effect fires
 * initial-loading — first request dispatched; no prior entries to display
 * loading         — subsequent navigation in-flight; stale entries preserved
 * success         — most recent request resolved successfully
 * error           — most recent request failed; entries/parent from last success
 */
export interface DirectoryPickerState {
  status: PickerStatus;
  /** Invariant: true iff status is 'initial-loading' or 'loading'. */
  isLoading: boolean;
  /** [] before first success; preserved across loading/error transitions. */
  entries: DirectoryEntry[];
  /** null until first success; from last resolved response's parent field. */
  parent: string | null;
  /** trimmedInitialPath before first response; response.path after. */
  currentPath: string;
  /**
   * Most recently *requested* path, set on dispatch before response arrives.
   * Distinct from currentPath: currentPath is updated only from server's
   * response.path on success; lastAttemptedPath records what was asked for.
   * Used by the Retry button (TASK-002b-Aa-i-c) to re-issue the last request.
   */
  lastAttemptedPath: string;
  /** Non-null iff status === 'error'. */
  error: Error | null;
}

// ---------------------------------------------------------------------------
// Props interface (AC1)
// ---------------------------------------------------------------------------

/**
 * Props for DirectoryPickerModal.
 *
 * initialPath is a mount-time-only prop: it is captured once into a ref and
 * never referenced inside any useEffect dependency array.  Parent re-renders
 * that pass a different initialPath after mount have zero effect on the
 * mounted modal's navigation state.
 */
export interface DirectoryPickerModalProps {
  /**
   * Initial directory path to open.  Trimmed before use.
   * Defaults to root (browseDirectory(undefined, signal)) when absent,
   * empty, or whitespace-only.
   *
   * Mount-time-only: captured into a ref; subsequent prop changes ignored.
   */
  initialPath?: string;
  /**
   * Called with the confirmed path when the user clicks Select.
   * Wired up in TASK-002b-Ab; this sub-task declares the prop type only.
   */
  onSelect: (path: string) => void;
  /** Called when the user dismisses the modal without selecting a path. */
  onClose: () => void;
  /**
   * Ref to the element that triggered this modal.
   * returnFocusRef.current may be null at focus-return time; the null-guard
   * and fallback focus target are implemented in TASK-002b-Ab.
   * This sub-task declares the prop type only.
   */
  returnFocusRef: RefObject<HTMLButtonElement>;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Directory browser modal.
 *
 * In this sub-task (TASK-002b-Aa-i-b-1) the component manages state and
 * lifecycle but renders nothing (returns null).  Sub-task b-2 replaces the
 * null return with the full portal + UI.
 */
export function DirectoryPickerModal({
  initialPath,
  onSelect: _onSelect,     // wired in TASK-002b-Ab
  onClose: _onClose,       // wired in TASK-002b-Ab
  returnFocusRef: _returnFocusRef, // focus restoration deferred to TASK-002b-Ab
}: DirectoryPickerModalProps): null {
  // ── AC3/AC5: initialPathRef BEFORE useState ───────────────────────────────
  // Capturing initialPath into a ref before the useState call satisfies two
  // requirements simultaneously:
  //   (a) the ref is available inside the lazy initializer body if needed
  //   (b) subsequent parent re-renders with a different initialPath prop are
  //       silently ignored — initialPathRef.current always holds the mount-time value
  const initialPathRef = useRef(initialPath);

  // ── AC3: Single useState with lazy initializer ────────────────────────────
  // The lazy form () => { ... } guarantees single execution at mount.
  // Reading the `initialPath` prop directly here is safe because the lazy
  // initializer runs only once (at mount), before any re-render can change it.
  // Do NOT use initialPathRef.current here (requires declaration-order dep).
  const [, setState] = useState<DirectoryPickerState>(() => {
    const trimmedInitialPath = (initialPath ?? '').trim();
    return {
      status: 'idle',
      isLoading: false,
      entries: [],
      parent: null,
      currentPath: trimmedInitialPath,
      lastAttemptedPath: trimmedInitialPath,
      error: null,
    };
  });

  // ── AC6: AbortController stored in ref, not state ─────────────────────────
  // Guarantees controllerRef.current?.abort() is synchronous and not deferred
  // by React's render cycle.
  const controllerRef = useRef<AbortController | null>(null);

  // ── AC7: navigate — stable identity via useCallback([]) ──────────────────
  //
  // CRITICAL — functional update form:
  //   Because useCallback(fn, []) closes over the *initial* render's state,
  //   reading state.entries directly would always see [] (stale closure),
  //   causing every post-first-success navigate call to dispatch 'initial-loading'
  //   instead of 'loading'.  The setState(prev => ...) functional form reads
  //   prev.entries at dispatch time (current state), not at closure-creation time.
  //
  // Step order (per AC7):
  //   1. Synchronously abort prior controller (no-op if null — first call)
  //   2. Create new AbortController; assign to ref; capture signal locally
  //   3. Dispatch functional state update (initial-loading vs loading)
  //   4. Call browseDirectory with captured signal (NOT controllerRef.current.signal)
  //   5. In .then: check signal.aborted; if false, transition to success
  //   6. In .catch: check signal.aborted || AbortError; if false, transition to error
  const navigate = useCallback((requestedPath: string | undefined): void => {
    // Step 1: abort any prior in-flight request
    controllerRef.current?.abort();

    // Step 2: create new controller; capture signal in local closure
    // IMPORTANT: signal is captured here at call time — never read from
    // controllerRef.current.signal inside .then()/.catch(), because the ref
    // may have been reassigned by a subsequent navigate() call by then.
    const controller = new AbortController();
    controllerRef.current = controller;
    const signal = controller.signal;

    // Step 3: dispatch functional state update
    // prev.entries.length === 0 → 'initial-loading' (no stale data to show)
    // prev.entries.length > 0   → 'loading'         (stale entries available)
    setState(prev => ({
      status: prev.entries.length === 0 ? 'initial-loading' : 'loading',
      isLoading: true,
      entries: prev.entries,
      parent: prev.parent,
      currentPath: prev.currentPath,
      lastAttemptedPath: requestedPath ?? '',
      error: null,
    }));

    // Step 4: issue request with locally-captured signal
    void browseDirectory(requestedPath, signal).then(
      // Step 5: success handler
      (response: BrowseDirectoryResponse) => {
        // Abort guard: if signal was aborted between dispatch and resolution,
        // skip all setState calls (prevents stale state updates after cleanup).
        if (signal.aborted) return;

        // Transition to success; preserve lastAttemptedPath from prev.
        // response.parent ?? null: coerce undefined (key absent) to null,
        // keeping state.parent typed as string | null (never | undefined).
        setState(prev => ({
          status: 'success',
          isLoading: false,
          entries: response.entries,
          parent: response.parent ?? null,
          currentPath: response.path,
          lastAttemptedPath: prev.lastAttemptedPath, // unchanged on success
          error: null,
        }));
      },

      // Step 6: error handler
      (error: unknown) => {
        // Abort guards (two forms to cover all environments):
        //   signal.aborted        — reliable backstop across all JS runtimes
        //   error.name==='AbortError' — fast path for environments that surface
        //                              abort as a named Error (e.g., DOMException)
        if (signal.aborted || (error instanceof Error && error.name === 'AbortError')) {
          return; // silent ignore — no UI change
        }

        // Non-AbortError: wrap to guarantee state.error is always an Error instance.
        // Storing a raw unknown value into Error | null would be a TypeScript error
        // under strict mode.  String rejections ('timeout'), plain objects ({code:429}),
        // and undefined all become Error instances here (NEG-1).
        const storedError =
          error instanceof Error ? error : new Error(String(error ?? 'Unknown error'));

        // Transition to error; preserve entries/parent/currentPath from last success.
        // isLoading MUST be cleared to false — this removes aria-busy and the loading
        // indicator (added in sub-task b-2) and prevents permanent UI lockup (AC8).
        setState(prev => ({
          status: 'error',
          isLoading: false,
          entries: prev.entries,      // preserved from last success
          parent: prev.parent,        // preserved from last success
          currentPath: prev.currentPath, // preserved from last success
          lastAttemptedPath: prev.lastAttemptedPath, // unchanged on error
          error: storedError,
        }));
      },
    );
  }, []); // empty deps: navigate never needs to close over reactive render values

  // ── AC5: Mount effect ─────────────────────────────────────────────────────
  // Reads initialPathRef.current (not the prop) so react-hooks/exhaustive-deps
  // does not require initialPath in the dependency array.  Refs are excluded
  // from the exhaustive-deps rule — they are mutable containers, not reactive
  // values, so ESLint emits zero warnings for this effect.
  //
  // StrictMode safety: React 18 StrictMode mounts → unmounts → remounts.
  //   First mount:   navigate() fires, new AbortController created
  //   Cleanup:       controllerRef.current?.abort() fires, first controller aborted
  //   Second mount:  navigate() fires again with state.entries === [] (back to idle),
  //                  dispatching 'initial-loading' correctly
  // After the full double-mount cycle, exactly one in-flight request exists.
  useEffect(() => {
    const trimmed = (initialPathRef.current ?? '').trim();
    // Pass trimmed string if non-empty; undefined to request filesystem root.
    navigate(trimmed !== '' ? trimmed : undefined);

    return () => {
      controllerRef.current?.abort();
    };
  }, [navigate]); // navigate is stable (useCallback with []) — effect runs only once

  // Sub-task b-2 replaces this null with the full portal + UI.
  return null;
}
