/**
 * DirectoryPickerModal.tsx — TASK-002b-Aa-i-b-2
 *
 * Portal, ARIA skeleton, focus trap, loading UI, and Up button.
 *
 * This sub-task extends TASK-002b-Aa-i-b-1 (state/lifecycle core) by replacing
 * the `return null` stub with the full portal and structural UI.
 *
 * This sub-task defines:
 *   - ReactDOM.createPortal wrapping the dialog into document.body (AC1)
 *   - ARIA dialog skeleton: role, aria-modal, tabIndex, ref, aria-labelledby (AC2)
 *   - visually-hidden title span + data-testid='current-path-display' (AC2)
 *   - useLayoutEffect focus assignment and return-focus restoration on unmount (AC3)
 *   - Keyboard focus trap for Tab / Shift+Tab (AC4)
 *   - Escape handler calling onClose(), with preventDefault+stopPropagation (AC5)
 *   - <ul data-testid='directory-listing'> unconditional, aria-busy lifecycle (AC6/AC8)
 *   - Loading indicator: role='status' sibling, conditional mount (AC7)
 *   - Up button: conditional render, disabled-when-loading, stale-closure guard (AC9)
 *   - aria-hidden='true' on #root while modal is mounted (AC10)
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
 * Informational (not acceptance criteria): The portal places the modal outside
 * any ancestor's DOM subtree so outer focus traps and Escape listeners of
 * ancestor components cannot intercept events from within this portal subtree.
 *
 * Deferred to other tasks:
 *   - Entry rendering: <li> items in directory listing (TASK-002b-Aa-ii)
 *   - Error display / Retry onClick (TASK-002b-Aa-i-c)
 *   - Select button wiring / returnFocusRef prop usage (TASK-002b-Ab)
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
  onSelect: _onSelect,              // wired in TASK-002b-Ab
  onClose,
  returnFocusRef: _returnFocusRef,  // prop wiring deferred to TASK-002b-Ab
}: DirectoryPickerModalProps): ReactPortal | null {
  // ── AC3/AC5: initialPathRef BEFORE useState ───────────────────────────────
  // Capturing initialPath into a ref before the useState call satisfies two
  // requirements simultaneously:
  //   (a) the ref is available inside the lazy initializer body if needed
  //   (b) subsequent parent re-renders with a different initialPath prop are
  //       silently ignored — initialPathRef.current always holds the mount-time value
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
    };
  });

  // ── stateRef: current state value at event time ───────────────────────────
  // Updated on every render so click handlers and keydown handlers always
  // read the latest state without closing over a stale render-time value.
  const stateRef = useRef(state);
  stateRef.current = state;

  // ── AC6: AbortController stored in ref, not state ─────────────────────────
  const controllerRef = useRef<AbortController | null>(null);

  // ── ARIA / DOM refs ───────────────────────────────────────────────────────
  /** The modal root div: role="dialog", tabIndex={-1}. */
  const containerRef = useRef<HTMLDivElement | null>(null);
  /**
   * Focus target before the modal opened.
   * Restored to document.activeElement on mount; returned to on unmount.
   * (Distinct from the returnFocusRef prop, which is wired in TASK-002b-Ab.)
   */
  const prevFocusRef = useRef<HTMLElement | null>(null);

  // ── useId: unique, stable ID for aria-labelledby ──────────────────────────
  // No two simultaneously-mounted instances share this id (React 18+ guarantee).
  const titleId = useId();

  // ── AC7: navigate — stable identity via useCallback([]) ──────────────────
  //
  // CRITICAL — functional update form:
  //   Because useCallback(fn, []) closes over the *initial* render's state,
  //   reading state.entries directly would always see [] (stale closure).
  //   The setState(prev => ...) functional form reads prev at dispatch time.
  const navigate = useCallback((requestedPath: string | undefined): void => {
    // Step 1: abort any prior in-flight request
    controllerRef.current?.abort();

    // Step 2: create new controller; capture signal in local closure
    // IMPORTANT: signal is captured here — never read from controllerRef.current.signal
    // inside .then()/.catch(), because the ref may be reassigned by a subsequent call.
    const controller = new AbortController();
    controllerRef.current = controller;
    const signal = controller.signal;

    // Step 3: dispatch functional state update
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
        if (signal.aborted) return;

        setState(prev => ({
          status: 'success',
          isLoading: false,
          entries: response.entries,
          parent: response.parent ?? null,
          // If response.path is nullish (malformed server response), fall back to
          // lastAttemptedPath so currentPath is never null/undefined (prevents AT
          // from announcing the '…' fallback after a successful navigation).
          currentPath: response.path ?? prev.lastAttemptedPath,
          lastAttemptedPath: prev.lastAttemptedPath,
          error: null,
        }));
      },

      // Step 6: error handler
      (error: unknown) => {
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
        }));
      },
    );
  }, []); // empty deps: navigate never needs to close over reactive render values

  // ── AC5: Mount effect — initial navigation ────────────────────────────────
  useEffect(() => {
    const trimmed = (initialPathRef.current ?? '').trim();
    navigate(trimmed !== '' ? trimmed : undefined);

    return () => {
      controllerRef.current?.abort();
    };
  }, [navigate]); // navigate is stable (useCallback with []) — effect runs only once

  // ── AC3 (b-2): useLayoutEffect — focus management ─────────────────────────
  // useLayoutEffect fires synchronously after DOM mutations, before paint,
  // preventing a visible flash where the dialog is rendered but focus hasn't moved.
  // (useEffect would fire after paint and is not acceptable per the spec.)
  //
  // StrictMode: mount → unmount → remount.  On unmount, cleanup restores focus
  // to prevFocusRef.current.  On remount, prevFocusRef re-captures the restored
  // element.  Final unmount (user dismiss) correctly returns to the original target.
  useLayoutEffect(() => {
    // Capture currently-focused element for return on unmount
    prevFocusRef.current = document.activeElement as HTMLElement;
    // Move focus inside the dialog (tabIndex={-1} makes it programmatically focusable)
    containerRef.current?.focus();

    return () => {
      // Restore focus: prefer the captured element if still in DOM; fall back to body
      if (prevFocusRef.current && document.contains(prevFocusRef.current)) {
        prevFocusRef.current.focus();
      } else {
        document.body.focus();
      }
    };
  }, []); // empty deps: runs once on mount, cleanup runs once on unmount

  // ── AC4 + AC5 (b-2): useEffect — keyboard handlers ───────────────────────
  // Handles both Escape (close) and Tab/Shift+Tab (focus trap).
  // Registered on containerRef.current so the listener is scoped to the dialog.
  // Runs fresh when onClose changes to avoid stale closure on the callback.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const handleKeyDown = (event: KeyboardEvent): void => {
      // ── Escape: close the modal ───────────────────────────────────────────
      // Closes even when isLoading=true — refusing dismissal during loading
      // would constitute a WCAG 2.1.2 (No Keyboard Trap) failure.
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        onClose();
        return;
      }

      // ── Tab: focus trap ───────────────────────────────────────────────────
      // Query runs on every keydown (not cached) so newly added <li> items
      // from TASK-002b-Aa-ii are automatically included in the trap boundary.
      if (event.key === 'Tab') {
        const focusable = Array.from(
          container.querySelectorAll<HTMLElement>(FOCUSABLE_QUERY),
        );

        // Zero focusable descendants: block Tab, keep focus on container.
        // Do not throw or move focus outside the dialog.
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
          // else: Shift+Tab inside the modal — propagate normally
        } else {
          // Tab: wrap forwards from last (or container) to first
          if (active === last || active === container) {
            event.preventDefault();
            first.focus();
          }
          // else: Tab inside the modal — propagate normally
        }
      }
    };

    container.addEventListener('keydown', handleKeyDown);
    return () => {
      container.removeEventListener('keydown', handleKeyDown);
    };
  }, [onClose]);

  // ── AC10 (b-2): useEffect — aria-hidden on #root ─────────────────────────
  // Prevents NVDA virtual-cursor navigation outside the modal in Firefox.
  // Assumption: host application root element selector is '#root'
  // (default Vite React scaffold). Update if the host uses a different root ID.
  useEffect(() => {
    const root = document.getElementById('root');
    if (!root) return; // no-op if root element is absent

    root.setAttribute('aria-hidden', 'true');
    return () => {
      root.removeAttribute('aria-hidden');
    };
  }, []);

  // ── Up button: render condition and click handler ─────────────────────────
  // `!= null` covers both null and undefined via abstract equality, handling
  // malformed API responses where the `parent` field is absent from JSON.
  // Note: \s may not match \u00A0 (non-breaking space) in all environments;
  // use .trim().length > 0 instead if NBSP is a realistic parent value.
  const showUpButton =
    state.parent != null && !/^\s*$/.test(state.parent);

  const handleUpClick = (): void => {
    // Read state via ref at event time to prevent stale-closure navigation.
    const current = stateRef.current;
    // Double-guard: disabled attribute prevents most invocations, but this
    // functional guard handles any React render-cycle gap between click and
    // the disabled-attribute render.
    if (current.isLoading) return;
    if (current.parent != null && !/^\s*$/.test(current.parent)) {
      navigate(current.parent);
    }
  };

  // ── Guard: not SSR-compatible ─────────────────────────────────────────────
  // document.body is always non-null in browser/jsdom environments.
  // This guard satisfies TypeScript's nullable type without crashing in SSR.
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
       * Title: accessible name = "Browse Directories: <currentPath>"
       *
       * The visually-hidden span is read by AT but invisible on screen.
       * The ?? '\u2026' fallback prevents AT from announcing 'null' or empty
       * text during idle/initial-loading states (e.g., when the test injects
       * state with currentPath: null).
       *
       * data-testid='current-path-display' is the test query target for
       * path-display assertions.
       */}
      <h2 id={titleId} data-testid="current-path-display">
        <span className="visually-hidden">Browse Directories: </span>
        {state.currentPath ?? '\u2026'}
      </h2>

      {/*
       * Up button: absent from DOM (not just hidden) when parent is null/empty.
       *
       * Disabled during loading to prevent concurrent navigations.
       * Enabled in error state to allow upward navigation as an escape path.
       *
       * aria-label includes visible text 'Up' as a substring of the accessible
       * name, satisfying WCAG 2.5.3 Label in Name.
       * '\u2013' = en dash (U+2013).
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
       * Directory listing: unconditional in all state branches.
       *
       * aria-label='Directory contents' gives AT a meaningful name even when
       * the list is empty (avoids announcing confusing 'list, 0 items').
       *
       * aria-busy='true' during loading; attribute removed entirely (undefined)
       * when not loading. React removes DOM attributes when value is undefined.
       * Passing boolean false or string 'false' leaves aria-busy="false" in the
       * DOM, which some AT implementations treat as a distinct state from absence.
       *
       * Children (<li> entry items) are added in TASK-002b-Aa-ii.
       */}
      <ul
        data-testid="directory-listing"
        aria-label="Directory contents"
        aria-busy={state.isLoading ? 'true' : undefined}
      />

      {/*
       * Loading indicator: conditional mount (not CSS visibility toggle).
       *
       * Rendered as a SIBLING of <ul>, never a child.
       *
       * role='status' creates an ARIA live region. Text content 'Loading\u2026'
       * (U+2026 HORIZONTAL ELLIPSIS, not three period characters) is the
       * announced value. aria-label-only does not create a live region.
       *
       * Conditional mounting (not CSS toggling) forces AT to re-announce
       * 'Loading…' on each new navigation — a CSS-toggled element whose text
       * content doesn't change would not trigger a live-region announcement
       * on repeat navigations.
       *
       * JAWS trade-off: JAWS may miss live-region announcements when element
       * and content appear simultaneously on mount. If JAWS support is required,
       * always-render the element with conditional text instead:
       *   <div role='status'>{state.isLoading ? 'Loading\u2026' : ''}</div>
       * Resolve this trade-off with the team before shipping.
       */}
      {state.isLoading && (
        <div role="status">Loading…</div>
      )}
    </div>
  );

  return createPortal(dialog, document.body);
}
