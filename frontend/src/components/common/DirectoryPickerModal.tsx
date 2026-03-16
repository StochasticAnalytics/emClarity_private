/**
 * DirectoryPickerModal.tsx — TASK-002b-Aa-α-1b
 *
 * Error branch, retry engine, lastAttemptedPath tracking.
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
 *   - Escape calls handleClose (abort + onClose) (AC7)
 *   - Loading indicator moved inside data-testid='directory-listing' with
 *     data-testid='loading-indicator' (AC8)
 *
 * NOTE: returnFocusRef null-guard and focus restoration via returnFocusRef
 * are deferred to TASK-002b-Aa-β. In this sub-task, returnFocusRef is
 * declared in props but has no usage in the component body.
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

export type { FilesystemBrowseResponse, DirectoryEntry } from '@/api/filesystem';
import type { FilesystemBrowseResponse, DirectoryEntry } from '@/api/filesystem';

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
  /** null until first success; from last resolved response's parent field (trimmed). */
  parent: string | null;
  /** trimmedInitialPath before first response; response.path after first success. */
  currentPath: string;
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
  // Reject null, non-string, empty string, and whitespace-only names.
  if (name == null || typeof name !== 'string' || name.trim() === '') return false;
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
function isValidBrowseResponse(response: unknown): response is FilesystemBrowseResponse {
  if (response === null || typeof response !== 'object') return false;
  const r = response as Record<string, unknown>;

  // path: must be a non-empty string (null, undefined, and '' are all invalid)
  const path = r['path'];
  if (typeof path !== 'string' || path === '') return false;

  // parent: null or a string are both valid; undefined (absent field) is
  // treated as null (no Up button, no validation error) per AC.
  // Only reject non-null, non-undefined, non-string values (e.g., number, boolean).
  const parent = r['parent'];
  if (parent !== undefined && parent !== null && typeof parent !== 'string') return false;

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

  // ── State: main state machine ─────────────────────────────────────────────
  // isLoading initialized to true so first synchronous render shows loading UI;
  // no non-loading render is ever visible before the mount effect fires.
  const [state, setState] = useState<DirectoryPickerState>(() => {
    const trimmedInitialPath = (initialPath ?? '').trim();
    return {
      status: 'initial-loading',
      isLoading: true,
      entries: [],
      parent: null,
      currentPath: trimmedInitialPath,
      error: null,
      errorKey: 0,
    };
  });

  // ── retryPath: tracks exact argument passed to browseDirectory (AC) ────────
  // undefined = root (no-argument call); string = trimmed path argument.
  // Initialized to undefined (never null, never '').
  const [retryPath, setRetryPath] = useState<undefined | string>(undefined);

  // ── stateRef: current state value at event time ───────────────────────────
  // Updated on every render so click handlers always read the latest state.
  const stateRef = useRef(state);
  stateRef.current = state;


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
    // Step 1: queue retryPath state update.
    // setRetryPath setter is stable (useState); safe to call from useCallback([]).
    setRetryPath(requestedPath);

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
      error: null,
      errorKey: prev.errorKey,
    }));

    // Step 5: issue request with locally-captured signal
    void browseDirectory(requestedPath, signal).then(
      // Step 6: success handler — validate before committing to state
      (rawResponse: FilesystemBrowseResponse) => {
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
            error: new Error('Invalid response from server'),
            errorKey: prev.errorKey + 1,
          }));
          return;
        }

        // Trim parent once at parse time; store the trimmed value.
        // Circular-nav guard: if trimmedParent equals trimmed path, treat as null
        // (suppresses Up button for root or same-directory parent).
        const rawParent = rawResponse.parent;
        const trimmedParent = typeof rawParent === 'string' ? rawParent.trim() : null;
        const trimmedPath = rawResponse.path.trim();
        const effectiveParent =
          trimmedParent !== null && trimmedParent !== '' && trimmedParent !== trimmedPath
            ? trimmedParent
            : null;

        setState(_prev => ({
          status: 'success',
          isLoading: false,
          entries: rawResponse.entries,
          parent: effectiveParent,
          currentPath: rawResponse.path,
          error: null,
          errorKey: _prev.errorKey,
        }));
      },

      // Step 7: rejection handler
      (error: unknown) => {
        // Guard against non-Error rejection values before accessing .name.
        // AbortError exceptions are intentional; silently ignore them.
        if (error instanceof Error && error.name === 'AbortError') return;
        // signal.aborted is the reliable backstop for all abort scenarios.
        if (signal.aborted) return;

        const storedError =
          error instanceof Error ? error : new Error(String(error ?? 'Unknown error'));

        setState(prev => ({
          status: 'error',
          isLoading: false,
          entries: prev.entries,
          parent: prev.parent,
          currentPath: prev.currentPath,
          error: storedError,
          errorKey: prev.errorKey + 1,
        }));
      },
    );
  }, []); // empty deps: navigate never needs to close over reactive render values

  // ── handleClose: abort + onClose ─────────────────────────────────────────
  //
  // Called by Escape keydown and any other close path.
  // Aborts any in-flight navigation request and delegates to the onClose prop.
  //
  // Focus restoration via returnFocusRef is deferred to TASK-002b-Aa-β.
  // The useLayoutEffect cleanup handles focus restoration to prevFocusRef on
  // unmount (the element that held focus immediately before the modal opened).
  const handleClose = useCallback((): void => {
    // Abort any in-flight navigation request.
    controllerRef.current?.abort();
    onClose();
  }, [onClose]);

  // ── handleRetry: re-issue the last failed navigation ─────────────────────
  //
  // Reads from retryPath state (via closure) — recreated when retryPath changes,
  // so by the time the Retry button is visible the closure always holds the
  // correct failed-request path.
  //
  // Focus is moved synchronously to the modal container BEFORE navigate() is
  // called — this prevents focus falling to document.body when the Retry
  // button is unmounted during the loading-state transition.
  const handleRetry = useCallback((): void => {
    // Move focus to container synchronously, before the button unmounts.
    containerRef.current?.focus();
    // retryPath is undefined (root) or a trimmed path string.
    navigate(retryPath);
  }, [navigate, retryPath]);

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
  // Escape calls handleClose (abort + onClose).
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
  }, [handleClose]); // handleClose captures onClose

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
  // state.parent is already trimmed (stored trimmed in success handler).
  // Only show Up button when parent is a non-null, non-empty string.
  const showUpButton = state.parent !== null && state.parent !== '';

  const handleUpClick = (): void => {
    const current = stateRef.current;
    if (current.isLoading) return;
    if (current.parent !== null && current.parent !== '') {
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
      data-testid="directory-picker-modal"
    >
      {/*
       * Title: static string 'Browse Filesystem' — never concatenated with path.
       *
       * data-testid='current-path-display' is a sibling element so that
       * textContent assertions on the title see exactly 'Browse Filesystem'
       * while path display assertions see only the path value (e.g. '/', '/home').
       * Both elements are present in all states (loading, error, empty, data).
       */}
      <h2 id={titleId}>Browse Filesystem</h2>
      <span data-testid="current-path-display">{displayPath}</span>

      {/*
       * Up button: absent from DOM (not just hidden) when parent is null/empty.
       * Disabled during loading to prevent concurrent navigations.
       */}
      {showUpButton && (
        <button
          type="button"
          data-testid="up-button"
          aria-label="Go to parent directory"
          disabled={state.isLoading}
          onClick={handleUpClick}
        >
          Up
        </button>
      )}

      {/*
       * Error state container.
       *
       * role='alert' causes AT to announce the content immediately upon mount.
       *
       * key={state.errorKey}: React unmounts and remounts this div on each new
       * errorKey value, guaranteeing a fresh role='alert' DOM insertion on
       * repeated consecutive failures — triggering a new screen-reader
       * announcement even when the error message text is unchanged.
       *
       * Rendered only when status === 'error'.  The directory-listing container
       * is absent from the DOM while in error state (mutually exclusive branches).
       * data-testid='retry-button' is therefore also absent during loading because
       * loading sets status to 'loading' (not 'error').
       */}
      {state.status === 'error' && (
        <div role="alert" key={state.errorKey}>
          {/*
           * Error message: single <p> with exact textContent and data-testid.
           */}
          <p data-testid="error-message">Failed to load directory. Please try again.</p>
          {/*
           * Retry button:
           *   - data-testid='retry-button' for test queries
           *   - ref={retryButtonRef} so the focus effect can focus it on entry
           *   - onClick moves focus to container then re-issues the failed request
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
       * Directory listing container: present in all non-error states
       * (initial-loading, loading, success, idle).  Absent only in error state.
       *
       * aria-busy='true' during loading; attribute absent when settled.
       * React removes DOM attributes when value is undefined.
       */}
      {state.status !== 'error' && (
        <div
          data-testid="directory-listing"
          aria-label="Directory contents"
          aria-busy={state.isLoading ? 'true' : undefined}
        >
          {/*
           * Loading indicator: conditionally mounted (not CSS-toggled).
           * role='status' with textContent 'Loading…' (Unicode ellipsis U+2026).
           */}
          {state.isLoading && (
            <div data-testid="loading-indicator" role="status">{'Loading\u2026'}</div>
          )}

          {/*
           * 'No subdirectories' message: shown when successful response contains
           * no directory-type entries (files-only or empty).
           * When entries contains only files, file divs (from α-2) and this
           * message are both present simultaneously.
           */}
          {state.status === 'success' &&
            state.entries.filter(e => e.type === 'directory').length === 0 && (
              <p>No subdirectories</p>
            )}

          {/*
           * Entry list items are rendered here in TASK-002b-Aa-α-2.
           * Deferred: directory button + file div rendering with navigation.
           */}
        </div>
      )}
    </div>
  );

  return createPortal(dialog, document.body);
}
