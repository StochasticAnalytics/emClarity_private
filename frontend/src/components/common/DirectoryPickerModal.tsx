/**
 * DirectoryPickerModal.tsx
 *
 * Structural and visual layer for the directory browser dialog.
 *
 * Implements (TASK-002b-Aa-2b-i):
 *   - React portal rendered to document.body (outside parent DOM subtree)
 *   - Portal null-body guard for SSR / jsdom environments
 *   - ARIA dialog shell: role='dialog', aria-modal='true', aria-labelledby
 *   - Stable title id via useId() — two instances always produce distinct ids
 *   - data-testid='modal-current-path' with '/' fallback for all falsy values
 *   - Three always-in-DOM live-region containers (text managed in Aa-2b-ii)
 *   - aria-busy on listing container; all interactive elements disabled while loading
 *   - Up button: in DOM only when parent is non-null, non-empty, non-whitespace-only
 *   - Directory entries as <button>; file entries as <div aria-disabled='true'>
 *   - Unicode-aware whitespace filter on entry names
 *   - 'No subdirectories' fallback when all directory entries are filtered out
 *   - Retry button: always in DOM, always disabled, no onClick (Aa-2b-ii adds those)
 *   - onSelect threaded to <DirectoryPickerActions>; never called directly here
 *
 * Deferred to other tasks:
 *   - Live-region text management (Aa-2b-ii)
 *   - Error-branch state machine / Retry onClick (Aa-2b-ii)
 *   - Focus trap and Escape handler (Aa-3)
 *   - returnFocusRef call-site / Select button (Aa-Ab)
 */

import { useId } from 'react';
import { createPortal } from 'react-dom';
import type { RefObject } from 'react';
import { useDirectoryNavigation } from '@/hooks/useDirectoryNavigation';
import { DirectoryPickerActions } from './DirectoryPickerActions';

// ---------------------------------------------------------------------------
// Constants — regex patterns
// ---------------------------------------------------------------------------

/**
 * Matches strings that consist entirely of invisible / whitespace code points:
 *   \s  — ASCII whitespace (space, \t, \n, \r, \f, \v) + Unicode whitespace
 *   \u200b — zero-width space (U+200B)
 *   \u200f — right-to-left mark (U+200F)
 *   \u00a0 — non-breaking space (U+00A0)
 *
 * The empty string matches (zero occurrences of the character class).
 * Emoji and other non-whitespace Unicode code points do NOT match.
 */
const INVISIBLE_ONLY_RE = /^[\s\u200b\u200f\u00a0]*$/;

/**
 * Same as INVISIBLE_ONLY_RE but also explicitly enumerates \t, \n, \r as
 * required by the AC for Up-button parent validation.
 * (\s already includes those, so this is a belt-and-suspenders form.)
 */
const PARENT_INVALID_RE = /^[\s\u200b\u200f\u00a0\t\n\r]*$/;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/**
 * A directory entry enriched with a computed absolute path.
 * The raw API response's entries lack a path field; we derive it from basePath.
 */
interface DirectoryEntry {
  name: string;
  type: 'directory' | 'file';
  /** Absolute path computed as basePath + '/' + name. */
  path: string;
}

/** Props for DirectoryPickerModal. */
export interface DirectoryPickerModalProps {
  /** Initial directory path to open. Defaults to root when absent or empty. */
  initialPath?: string;
  /**
   * Called with the confirmed path when the user clicks Select.
   * This prop is NOT called directly in this file — it is threaded to
   * <DirectoryPickerActions> to be wired up in TASK-002b-Ab.
   */
  onSelect: (path: string) => void;
  /** Called when the user dismisses the modal without selecting a path. */
  onClose: () => void;
  /**
   * Ref to the element that triggered this modal.
   * Focus restoration (returnFocusRef.current?.focus()) is deferred to
   * TASK-002b-Ab.  This file never calls returnFocusRef.current.focus().
   */
  returnFocusRef: RefObject<HTMLButtonElement>;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Compute an absolute path for a directory entry given the parent path.
 * Handles root ('/') and empty basePath so the result is never '//' or '/name'.
 */
function computeEntryPath(basePath: string, name: string): string {
  if (basePath === '' || basePath === '/') {
    return `/${name}`;
  }
  return `${basePath}/${name}`;
}

/**
 * Type guard: returns true iff parent is a non-null, non-empty,
 * non-whitespace-only string.  Uses PARENT_INVALID_RE which explicitly covers
 * \s, \u200b, \u200f, \u00a0, \t, \n, \r.
 */
function isValidParent(parent: string | null | undefined): parent is string {
  if (parent === null || parent === undefined) return false;
  return !PARENT_INVALID_RE.test(parent);
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Directory browser modal rendered via a React portal to document.body.
 *
 * Returns null (no output, no exception) when document.body is unavailable,
 * which guards against SSR and certain jsdom configurations.
 */
export function DirectoryPickerModal({
  initialPath,
  onSelect,
  onClose,
  returnFocusRef: _returnFocusRef, // Focus restoration deferred to TASK-002b-Ab
}: DirectoryPickerModalProps) {
  // ── Hooks — must be called before any conditional returns ─────────────────
  const titleId = useId();

  const {
    currentPath,
    isLoading,
    lastGoodData,
    navigate: browseDirectory,
  } = useDirectoryNavigation(initialPath);

  // ── Portal guard ───────────────────────────────────────────────────────────
  // Conditional return AFTER all hook calls to satisfy the Rules of Hooks.
  // Returns null (no UI, no exception) in SSR or jsdom-without-body contexts.
  if (typeof document === 'undefined' || !document.body) {
    return null;
  }

  // ── Build entry list ───────────────────────────────────────────────────────
  // Defensively handle null lastGoodData and non-array entries at runtime.
  // Both Array.isArray and typeof name === 'string' guards are required by AC
  // so that malformed API payloads (null/non-array entries, non-string names)
  // never cause a TypeError.
  const basePath: string = lastGoodData?.path ?? '';

  const rawEntries: Array<{ name: string; type: 'directory' | 'file' }> =
    lastGoodData != null && Array.isArray(lastGoodData.entries)
      ? lastGoodData.entries
      : [];

  // Filter out non-string names and invisible-only names, then enrich with path.
  const allEntries: DirectoryEntry[] = rawEntries
    .filter(
      (e): e is { name: string; type: 'directory' | 'file' } =>
        typeof e.name === 'string' && !INVISIBLE_ONLY_RE.test(e.name),
    )
    .map((e) => ({
      name: e.name,
      type: e.type,
      path: computeEntryPath(basePath, e.name),
    }));

  const dirEntries = allEntries.filter((e) => e.type === 'directory');
  const fileEntries = allEntries.filter((e) => e.type === 'file');

  // ── Current path display ───────────────────────────────────────────────────
  // Falsy check (!currentPath) catches '', null, and undefined across all three
  // phases: (a) initial loading, (b) initial error, (c) successful '' response.
  // Whitespace-only paths are NOT treated as empty — they render as-is.
  const displayPath: string = currentPath || '/';

  // ── Up button visibility ───────────────────────────────────────────────────
  // isValidParent is the sole guard; no additional runtime check in onClick.
  // browseDirectory is never called with a whitespace-only parent string.
  const parent: string | null = lastGoodData?.parent ?? null;

  // ── Modal content ──────────────────────────────────────────────────────────
  const modal = (
    <div role="dialog" aria-modal="true" aria-labelledby={titleId}>
      {/*
       * Title — fixed string per AC.  Never changes during navigation so screen
       * readers always announce a stable dialog name.  id is generated by
       * useId() which guarantees uniqueness across simultaneously-mounted
       * instances (React 18+ guarantee).
       */}
      <h2 id={titleId}>Browse for Directory</h2>

      {/*
       * Current path display.
       * Standard React text rendering — dangerouslySetInnerHTML is prohibited
       * here so path strings containing <, >, &, or script payloads render as
       * literal text.
       */}
      <div data-testid="modal-current-path">{displayPath}</div>

      {/*
       * Live-region scaffolding — all three containers are always in the DOM
       * from the very first paint, before any useEffect fires or request resolves.
       * Text content is managed in TASK-002b-Aa-2b-ii.
       *
       * (a) Loading indicator — role='status' (polite, non-intrusive)
       * (b) Error announcements — role='alert' (assertive, immediate)
       * (c) Success announcements — role='status' (polite)
       */}
      <div role="status" />
      <div role="alert" />
      <div role="status" />

      {/*
       * Up button — absent from DOM (not just CSS-hidden) when parent is
       * null, empty, or whitespace-only.  isValidParent is the type guard;
       * parent is narrowed to string in the truthy branch so the onClick
       * lambda never receives a null value.
       */}
      {isValidParent(parent) && (
        <button
          type="button"
          aria-label="Navigate to parent directory"
          disabled={isLoading}
          onClick={() => {
            browseDirectory(parent);
          }}
        >
          Up
        </button>
      )}

      {/*
       * Directory listing container.
       * aria-busy uses boolean coercion (!!isLoading) to prevent the invalid
       * attribute value aria-busy='undefined' if isLoading were ever undefined.
       */}
      <div data-testid="directory-listing" aria-busy={!!isLoading}>
        {/*
         * Retry button — always present in this task (Aa-2b-i), always disabled,
         * no onClick attached.  TASK-002b-Aa-2b-ii will add the onClick handler
         * and conditional visibility based on error state.
         */}
        <button type="button" aria-label="Retry loading directory" disabled>
          Retry
        </button>

        {/*
         * Directory entries.
         * Rendered as native <button> elements for keyboard accessibility.
         * Text is set via React's standard rendering (not dangerouslySetInnerHTML)
         * so names containing <, >, & render as literal text.
         * Keys incorporate both name and index to handle duplicate names safely.
         * onClick is set unconditionally; disabling during load is achieved via
         * the disabled attribute, not by conditional onClick omission.
         */}
        {dirEntries.length === 0 ? (
          <span>No subdirectories</span>
        ) : (
          dirEntries.map((entry, index) => (
            <button
              key={`${entry.name}-${index}`}
              type="button"
              disabled={isLoading}
              onClick={() => {
                browseDirectory(entry.path);
              }}
            >
              {entry.name}
            </button>
          ))
        )}

        {/*
         * File entries — purely presentational, no interaction.
         * Rendered as <div aria-disabled='true'>.  No onClick, no onKeyDown,
         * no tabIndex (omitted entirely, not -1) per AC.
         * No <ul>, <ol>, or <li> elements anywhere in the listing area.
         */}
        {fileEntries.map((entry, index) => (
          <div key={`${entry.name}-${index}`} aria-disabled="true">
            {entry.name}
          </div>
        ))}
      </div>

      {/*
       * Action buttons row.
       * onSelect is passed as a prop here and ONLY here — never called directly
       * in this file to avoid a double-invocation bug when Aa-Ab wires its
       * Select button.  isLoading is forwarded so Aa-Ab can disable Select.
       */}
      <DirectoryPickerActions
        onSelect={onSelect}
        onClose={onClose}
        currentPath={currentPath}
        isLoading={isLoading}
      />
    </div>
  );

  return createPortal(modal, document.body);
}
