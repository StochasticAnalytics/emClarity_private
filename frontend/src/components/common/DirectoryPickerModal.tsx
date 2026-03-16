/**
 * DirectoryPickerModal.tsx — TASK-002b-Aa-i-c
 *
 * Error branch, retry engine, lastAttemptedPath tracking, and returnFocusRef
 * null-guard.
 *
 * This sub-task extends TASK-002b-Aa-i-b-2 (portal, ARIA, focus trap,
 * loading UI, Up button) by adding:
 *   - Structural response validation (AC: null body, missing fields, bad types)
 *   - Error state UI: role='alert' container with message + Retry button (AC1)
 *   - lastAttemptedPathRef (distinct useRef) and retry engine (AC2/AC8)
 *   - currentPath display edge-case: '' → '/' (AC3)
 *   - errorKey in state for re-mount on repeated failures (AC5)
 *   - Retry button focus on error-state entry (AC10)
 *   - Empty-entries state: data-testid='empty-directory-message' (AC9)
 *   - returnFocusRef null-guard in handleClose (AC6/AC7)
 *   - Escape calls handleClose (abort + focus-restore + onClose) (AC7)
 *   - Loading indicator moved inside data-testid='directory-listing' with
 *     data-testid='loading-indicator' (AC8)
 *
 * @requires React 18 — uses useId() (React 18+; installed version is React 19, compatible)
 *
 * NOTE: Not SSR-compatible. Requires document.body to be non-null at render time
 * (browser or jsdom environment). The portal root is appended as a direct child
 * of document.body.
 *
 * aria-hidden assumption: Host application root element selector is '#root'
 * (default Vite React scaffold). Update the aria-hidden effect selector if the
 * host application uses a different root element ID.
 *
 * Deferred to other tasks:
 *   - Entry rendering: <li> items in directory listing (TASK-002b-Aa-ii)
 *   - Select button wiring (TASK-002b-Ab)
 *   - document.body scroll-lock (TASK-002b-Ab)
 */

import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';
import type { ReactPortal, RefObject } from 'react';
import { createPortal } from 'react-dom';
import { browseDirectory } from '@/api/filesystem';

// ---------------------------------------------------------------------------
// Re-exported types (consumed by sub-tasks Aa-ii and Ab without re-defining)
// ---------------------------------------------------------------------------

export type { BrowseDirectoryResponse, DirectoryEntry } from '@/api/filesystem';
import type { BrowseDirectoryResponse, DirectoryEntry } from '@/api/filesystem';

// ---------------------------------------------------------------------------
// State machine types
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
  /** trimmedInitialPath before first response; response.path after first success. */
  currentPath: string;
  /**
   * Most recently *requested* path, set on dispatch before response arrives.
   * Distinct from currentPath: currentPath is updated only on success;
   * lastAttemptedPath records what was asked for.
   * Mirrored from lastAttemptedPathRef (useRef) for state-snapshot inspection.
   */
  lastAttemptedPath: string;
  /** Non-null iff status === 'error'. */
  error: Error | null;
  /**
   * Increments on each error state entry (including repeated failures).
   * Used as a React key on the error container to guarantee DOM remount and
   * screen-reader re-announcement of role='alert' on consecutive failures.
   */
  errorKey: number;
}

// ---------------------------------------------------------------------------
// Props interface
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
   * Used by the internal close handler to restore focus with null-guard:
   * if the element is null, removed from DOM, disabled, hidden, inert, or
   * aria-hidden, document.body receives focus instead.
   */
  returnFocusRef: RefObject<HTMLButtonElement>;
}

// ---------------------------------------------------------------------------
// Focusable element query selector
// ---------------------------------------------------------------------------

/**
 * CSS selector for keyboard-focusable descendants of the modal root.
 * Queried fresh on every Tab keydown so newly added <li> items from
 * TASK-002b-Aa-ii are automatically included in the trap boundary.
 */
const FOCUSABLE_QUERY =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

// ---------------------------------------------------------------------------
// Response validation helpers
// ---------------------------------------------------------------------------

/**
 * Type guard for a single directory entry.
 *
 * An entry is valid iff:
 *   - It is a non-null object
 *   - `name` is a non-empty string
 *   - `type` is exactly 'directory' or 'file'
 *
 * A single invalid entry fails the entire response (no partial rendering).
 */
function isValidEntry(entry: unknown): entry is DirectoryEntry {
  if (entry === null || typeof entry !== 'object') return false;
  const e = entry as Record<string, unknown>;
  const name = e['name'];
  const type = e['type'];
  if (typeof name !== 'string' || name === '') return false;
  if (type !== 'directory' && type !== 'file') return false;
  return true;
}

/**
 * Type guard for a browse-directory response body.
 *
 * A response is valid iff:
 *   - It is a non-null object
 *   - `path` is a non-empty string (null and '' are both invalid)
 *   - `parent` is present and is either null or a string
 *   - `entries` is a non-null array where every element passes isValidEntry
 *
 * Per AC: one invalid entry fails the entire response — no partial rendering.
 */
function isValidBrowseResponse(response: unknown): response is BrowseDirectoryResponse {
  if (response === null || typeof response !== 'object') return false;
  const r = response as Record<string, unknown>;

  // path: must be a non-empty string (null, undefined, and '' are all invalid)
  const path = r['path'];
  if (typeof path !== 'string' || path === '') return false;

  // parent: must be present; null (root) or a string are both valid;
  // undefined (missing field) and non-string non-null values are invalid.
  const parent = r['parent'];
  if (parent !== null && typeof parent !== 'string') return false;

  // entries: must be a non-null array
  const entries = r['entries'];
  if (!Array.isArray(entries)) return false;

  // every entry must be valid — one invalid entry fails the whole response
  for (const entry of entries as unknown[]) {
    if (!isValidEntry(entry)) return false;
  }

  return true;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Directory browser modal.
 *
 * Renders via ReactDOM.createPortal into document.body.
 *
 * @requires React 18 — uses useId() (React 18+; installed version is React 19,
 * which is compatible — the JSDoc version floor remains 18)
 *
 * Not SSR-compatible: requires document.body to be non-null at render time
 * (browser or jsdom environment).
 *
 * aria-hidden assumption: Host application root is '#root'.
 */
export function DirectoryPickerModal({
  initialPath,
  onSelect: _onSelect,        // wired in TASK-002b-Ab
  onClose,
  returnFocusRef,
}: DirectoryPickerModalProps): ReactPortal | null {
  // ── initialPathRef: capture mount-time initialPath ────────────────────────
  const initialPathRef = useRef(initialPath);

  // ── AC3: Single useState with lazy initializer ────────────────────────────
  const [state, setState] = useState<DirectoryPickerState>(() => {
    const trimmedInitialPath = (initialPath ?? '').trim();
    return {
      status: 'idle',
      isLoading: false,
      entries: [],
      parent: null,
      currentPath: trimmedInitialPath,
      lastAttemptedPath: trimmedInitialPath,
      error: null,
      errorKey: 0,
    };
  });

  // ── stateRef: current state value at event time ───────────────────────────
  // Updated on every render so click handlers always read the latest state.
  const stateRef = useRef(state);
  stateRef.current = state;

  // ── lastAttemptedPathRef: dedicated ref per AC2 ───────────────────────────
  // Assigned the exact path string passed to browseDirectory at the moment
  // each new navigation begins — BEFORE the setState call.  Distinct from
  // state.currentPath (which is updated only from response.path on success).
  // The Retry handler reads this ref so it always re-issues the failed path
  // even when the component has re-rendered since the error occurred.
  const lastAttemptedPathRef = useRef<string>('');

  // ── AbortController stored in ref, not state ─────────────────────────────
  const controllerRef = useRef<AbortController | null>(null);

  // ── ARIA / DOM refs ───────────────────────────────────────────────────────
  /** The modal root div: role="dialog", tabIndex={-1}. */
  const containerRef = useRef<HTMLDivElement | null>(null);
  /**
   * Focus target before the modal opened.
   * Captured synchronously in useLayoutEffect on mount.
   * Restored in the useLayoutEffect cleanup unless handleClose already ran.
   */
  const prevFocusRef = useRef<HTMLElement | null>(null);
  /**
   * Set to true by handleClose after it handles focus restoration, preventing
   * the useLayoutEffect cleanup from performing a second (redundant) focus call.
   */
  const focusRestoredRef = useRef(false);

  /** Ref to the Retry button — used to focus it on error-state entry (AC10). */
  const retryButtonRef = useRef<HTMLButtonElement | null>(null);

  // ── useId: unique, stable ID for aria-labelledby ──────────────────────────
  const titleId = useId();

  // ── navigate: stable identity via useCallback([]) ─────────────────────────
  //
  // CRITICAL — functional update form:
  //   Because useCallback(fn, []) closes over the *initial* render's state,
  //   reading state.entries directly would always see [] (stale closure).
  //   The setState(prev => ...) functional form reads prev at dispatch time.
  const navigate = useCallback((requestedPath: string | undefined): void => {
    // Step 1: record the path being requested in the dedicated ref (AC2).
    // Must be set BEFORE setState so any synchronous reader sees the new value.
    lastAttemptedPathRef.current = requestedPath ?? '';

    // Step 2: abort any prior in-flight request
    controllerRef.current?.abort();

    // Step 3: create new controller; capture signal in local closure.
    // IMPORTANT: signal is captured here — never read from controllerRef.current.signal
    // inside .then()/.catch(), because the ref may be reassigned by a subsequent call.
    const controller = new AbortController();
    controllerRef.current = controller;
    const signal = controller.signal;

    // Step 4: dispatch functional state update
    setState(prev => ({
      status: prev.entries.length === 0 ? 'initial-loading' : 'loading',
      isLoading: true,
      entries: prev.entries,
      parent: prev.parent,
      currentPath: prev.currentPath,
      lastAttemptedPath: requestedPath ?? '',
      error: null,
      errorKey: prev.errorKey,
    }));

    // Step 5: issue request with locally-captured signal
    void browseDirectory(requestedPath, signal).then(
      // Step 6: success handler — validate before committing to state
      (rawResponse: BrowseDirectoryResponse) => {
        if (signal.aborted) return;

        // Cast to unknown for runtime structural validation.
        // browseDirectory is typed but the server (or test stub) may return
        // structurally invalid data.  Catching all invalid shapes here prevents
        // partial / undefined-access errors downstream and satisfies AC1.
        const responseAsUnknown: unknown = rawResponse;
        if (!isValidBrowseResponse(responseAsUnknown)) {
          setState(prev => ({
            status: 'error',
            isLoading: false,
            entries: prev.entries,
            parent: prev.parent,
            currentPath: prev.currentPath,
            lastAttemptedPath: prev.lastAttemptedPath,
            error: new Error('Invalid response from server'),
            errorKey: prev.errorKey + 1,
          }));
          return;
        }

        // rawResponse is now narrowed to BrowseDirectoryResponse
        setState(prev => ({
          status: 'success',
          isLoading: false,
          entries: rawResponse.entries,
          parent: rawResponse.parent ?? null,
          currentPath: rawResponse.path,
          lastAttemptedPath: prev.lastAttemptedPath,
          error: null,
          errorKey: prev.errorKey,
        }));
      },

      // Step 7: rejection handler
      (error: unknown) => {
        // Abort errors are intentional (user navigated away or component unmounted).
        // Do not transition to error state for these.
        if (signal.aborted || (error instanceof Error && error.name === 'AbortError')) {
          return;
        }

        const storedError =
          error instanceof Error ? error : new Error(String(error ?? 'Unknown error'));

        setState(prev => ({
          status: 'error',
          isLoading: false,
          entries: prev.entries,
          parent: prev.parent,
          currentPath: prev.currentPath,
          lastAttemptedPath: prev.lastAttemptedPath,
          error: storedError,
          errorKey: prev.errorKey + 1,
        }));
      },
    );
  }, []); // empty deps: navigate never needs to close over reactive render values

  // ── handleClose: abort + returnFocusRef null-guard + onClose ─────────────
  //
  // Called by Escape keydown and any other close path.
  // Performs focus restoration BEFORE the portal unmounts (per AC6/AC7) so
  // the focus call reaches the DOM element while it is still connected.
  //
  // Null-guard conditions per AC7 (any true → fall back to document.body):
  //   - returnFocusRef.current is null
  //   - document.contains(returnFocusRef.current) returns false
  //   - element has the disabled attribute
  //   - element has the hidden attribute
  //   - element.closest('[inert]') !== null
  //   - element.getAttribute('aria-hidden') === 'true'
  const handleClose = useCallback((): void => {
    // Abort any in-flight navigation request (AC7).
    controllerRef.current?.abort();

    // Focus restoration with null-guard (AC6/AC7).
    const target = returnFocusRef.current;
    const canFocus =
      target !== null &&
      document.contains(target) &&
      !target.disabled &&
      !target.hidden &&
      target.closest('[inert]') === null &&
      target.getAttribute('aria-hidden') !== 'true';

    if (canFocus) {
      // `target` is non-null here by the canFocus condition above.
      // The non-null assertion is safe: `target !== null` is the first operand.
      target.focus();
    } else {
      document.body.focus();
    }

    // Mark focus as handled so the useLayoutEffect cleanup does not attempt a
    // second (redundant) focus call when the portal is unmounted.
    focusRestoredRef.current = true;
    onClose();
  }, [onClose, returnFocusRef]);

  // ── handleRetry: re-issue the last failed navigation (AC2/AC8) ────────────
  //
  // Reads from lastAttemptedPathRef.current (the dedicated ref), NOT from
  // state.currentPath.  This is the core guarantee of AC2: Retry always
  // re-issues the path that failed, even if currentPath differs (e.g., last
  // successful path is /home, failed attempt was /home/foo → Retry calls /home/foo).
  const handleRetry = useCallback((): void => {
    const path = lastAttemptedPathRef.current;
    // An empty string means the attempted path was the root (undefined/'' both
    // map to root in browseDirectory).  Pass undefined for root to match the
    // original navigate(undefined) call from the mount effect.
    navigate(path !== '' ? path : undefined);
  }, [navigate]);

  // ── Mount effect — initial navigation ────────────────────────────────────
  useEffect(() => {
    const trimmed = (initialPathRef.current ?? '').trim();
    navigate(trimmed !== '' ? trimmed : undefined);

    return () => {
      controllerRef.current?.abort();
    };
  }, [navigate]); // navigate is stable (useCallback with []) — effect runs only once

  // ── Retry-button focus effect (AC10) ──────────────────────────────────────
  // Fires whenever errorKey increments (i.e., on each new error state entry,
  // including repeated consecutive failures).  By the time this effect runs,
  // the error container has been (re-)mounted with the new key, and
  // retryButtonRef.current points to the new Retry button DOM node.
  useEffect(() => {
    if (state.status === 'error' && retryButtonRef.current !== null) {
      retryButtonRef.current.focus();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.errorKey]); // intentionally omits state.status: errorKey only changes on error entry

  // ── useLayoutEffect — focus management ───────────────────────────────────
  // useLayoutEffect fires synchronously after DOM mutations, before paint,
  // preventing a visible flash where the dialog is rendered but focus hasn't moved.
  //
  // StrictMode: mount → unmount → remount.  On first cleanup, focusRestoredRef
  // is false (handleClose was not called), so we restore to prevFocusRef.  On
  // remount, prevFocusRef re-captures the (now restored) element.  On the final
  // unmount (user dismiss via handleClose), focusRestoredRef is true and the
  // cleanup is a no-op, preventing a double focus call.
  useLayoutEffect(() => {
    prevFocusRef.current = document.activeElement as HTMLElement;
    containerRef.current?.focus();

    return () => {
      if (!focusRestoredRef.current) {
        // handleClose has not run — restore focus ourselves.
        if (prevFocusRef.current !== null && document.contains(prevFocusRef.current)) {
          prevFocusRef.current.focus();
        } else {
          document.body.focus();
        }
      }
      // If focusRestoredRef.current is true, handleClose already handled focus.
    };
  }, []); // empty deps: runs once on mount, cleanup runs once on unmount

  // ── useEffect — keyboard handlers (Escape + Tab focus trap) ──────────────
  // Escape calls handleClose (abort + returnFocusRef null-guard + onClose).
  // Tab/Shift+Tab cycles through focusable descendants without escaping.
  // Re-registered when handleClose changes (i.e., when onClose changes).
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const handleKeyDown = (event: KeyboardEvent): void => {
      // ── Escape: abort, restore focus, close modal ──────────────────────
      // Closes even when isLoading=true — refusing dismissal during loading
      // would constitute a WCAG 2.1.2 (No Keyboard Trap) failure.
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        handleClose();
        return;
      }

      // ── Tab: focus trap ───────────────────────────────────────────────
      // Query runs on every keydown (not cached) so newly added <li> items
      // from TASK-002b-Aa-ii are automatically included in the trap boundary.
      if (event.key === 'Tab') {
        const focusable = Array.from(
          container.querySelectorAll<HTMLElement>(FOCUSABLE_QUERY),
        );

        // Zero focusable descendants: block Tab, keep focus on container.
        if (focusable.length === 0) {
          event.preventDefault();
          return;
        }

        const first = focusable[0] as HTMLElement;
        const last = focusable[focusable.length - 1] as HTMLElement;
        const active = document.activeElement;

        if (event.shiftKey) {
          // Shift+Tab: wrap backwards from first (or container) to last
          if (active === first || active === container) {
            event.preventDefault();
            last.focus();
          }
        } else {
          // Tab: wrap forwards from last (or container) to first
          if (active === last || active === container) {
            event.preventDefault();
            first.focus();
          }
        }
      }
    };

    container.addEventListener('keydown', handleKeyDown);
    return () => {
      container.removeEventListener('keydown', handleKeyDown);
    };
  }, [handleClose]); // handleClose captures onClose + returnFocusRef

  // ── useEffect — aria-hidden on #root ─────────────────────────────────────
  // Prevents NVDA virtual-cursor navigation outside the modal in Firefox.
  useEffect(() => {
    const root = document.getElementById('root');
    if (!root) return;

    root.setAttribute('aria-hidden', 'true');
    return () => {
      root.removeAttribute('aria-hidden');
    };
  }, []);

  // ── Up button: render condition and click handler ─────────────────────────
  const showUpButton =
    state.parent != null && !/^\s*$/.test(state.parent);

  const handleUpClick = (): void => {
    const current = stateRef.current;
    if (current.isLoading) return;
    if (current.parent != null && !/^\s*$/.test(current.parent)) {
      navigate(current.parent);
    }
  };

  // ── displayPath: '' → '/' per AC3 ────────────────────────────────────────
  // When the very first navigation fails and currentPath is still '' (no
  // initialPath was provided), the path display must show '/' not blank.
  // If initialPath was a non-empty string that failed, currentPath already
  // reflects the trimmed initialPath value from the lazy initializer.
  const displayPath = state.currentPath !== '' ? state.currentPath : '/';

  // ── Guard: not SSR-compatible ─────────────────────────────────────────────
  if (!document.body) return null;

  // ── Portal render ─────────────────────────────────────────────────────────
  const dialog = (
    <div
      role="dialog"
      aria-modal="true"
      tabIndex={-1}
      ref={containerRef}
      aria-labelledby={titleId}
    >
      {/*
       * Title: accessible name = "Browse Directories: <displayPath>"
       *
       * The visually-hidden span is read by AT but invisible on screen.
       * data-testid='current-path-display' is on the inner span so that
       * textContent assertions see only the path value (e.g. '/', '/home'),
       * not the visually-hidden prefix text.
       */}
      <h2 id={titleId}>
        <span className="visually-hidden">Browse Directories: </span>
        <span data-testid="current-path-display">{displayPath}</span>
      </h2>

      {/*
       * Up button: absent from DOM (not just hidden) when parent is null/empty.
       * Disabled during loading to prevent concurrent navigations.
       * Enabled in error state to allow upward navigation as an escape path.
       */}
      {showUpButton && (
        <button
          type="button"
          aria-label={'Up \u2013 Go to parent directory'}
          disabled={state.isLoading}
          onClick={handleUpClick}
        >
          Up
        </button>
      )}

      {/*
       * Directory listing container: unconditional in all state branches.
       *
       * Changed from <ul> to <div> so that non-list children (error container,
       * loading indicator, empty message) can be valid HTML descendants.
       * Entry list items from TASK-002b-Aa-ii will be rendered inside a <ul>
       * nested within this div.
       *
       * aria-busy='true' during loading; attribute removed entirely (undefined)
       * when not loading. React removes DOM attributes when value is undefined.
       */}
      <div
        data-testid="directory-listing"
        aria-label="Directory contents"
        aria-busy={state.isLoading ? 'true' : undefined}
      >
        {/*
         * Loading indicator: conditional mount (not CSS visibility toggle).
         *
         * Moved inside data-testid='directory-listing' per AC8.
         * data-testid='loading-indicator' allows direct test query.
         *
         * role='status' creates an ARIA live region.  Conditional mounting
         * (not CSS toggling) forces AT to re-announce 'Loading…' on each new
         * navigation.
         */}
        {state.isLoading && (
          <div data-testid="loading-indicator" role="status">Loading…</div>
        )}

        {/*
         * Error state container (AC1/AC5).
         *
         * role='alert' causes AT to announce the content immediately upon
         * mount — suitable for error messages that need immediate attention.
         *
         * key={state.errorKey}: React unmounts and remounts this div on each
         * new errorKey value.  This guarantees a fresh role='alert' insertion
         * into the DOM on repeated consecutive failures, triggering a new
         * screen-reader announcement even when the error message text is
         * unchanged.
         *
         * The error container is unmounted during loading (state.isLoading is
         * true, state.status is not 'error'), so the conditional rendering
         * also provides structural removal of data-testid='retry-button'
         * during in-flight retries — a second click is structurally impossible.
         */}
        {state.status === 'error' && (
          <div role="alert" key={state.errorKey}>
            {/*
             * Error message: single element with exact textContent.
             * Not split across child nodes per AC1.
             */}
            <p>Failed to load directory. Please try again.</p>
            {/*
             * Retry button (AC1/AC8):
             *   - visible text and accessible name are both 'Retry'
             *   - data-testid='retry-button' for test queries
             *   - ref={retryButtonRef} so the focus effect (AC10) can focus it
             *   - onClick calls handleRetry which reads lastAttemptedPathRef.current
             */}
            <button
              type="button"
              data-testid="retry-button"
              ref={retryButtonRef}
              onClick={handleRetry}
            >
              Retry
            </button>
          </div>
        )}

        {/*
         * Empty directory state (AC9).
         * Shown only after a successful navigation that returned zero entries.
         * Absent in all other states (loading, error, initial-loading, idle).
         */}
        {state.status === 'success' && state.entries.length === 0 && (
          <p data-testid="empty-directory-message">This directory is empty.</p>
        )}

        {/*
         * Entry list items are rendered here in TASK-002b-Aa-ii.
         * Deferred: entry rendering (directory + file items with navigation).
         */}
      </div>
    </div>
  );

  return createPortal(dialog, document.body);
}
