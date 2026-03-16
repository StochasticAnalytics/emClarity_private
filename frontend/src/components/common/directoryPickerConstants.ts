/**
 * directoryPickerConstants.ts — TASK-002b-Aa-α-1 / TASK-002b-Aa-α-2
 *
 * Shared string constants for the DirectoryPickerModal component family.
 * Exporting from a dedicated module prevents hard-coded string duplication
 * across DirectoryPickerModal.tsx and any consumer that needs to assert
 * against these values (e.g., test files, sibling components).
 */

/**
 * Empty-state message rendered inside `data-testid="directory-listing"` when
 * the listing contains no navigable subdirectories after whitespace filtering.
 *
 * Present simultaneously with file `<div>` elements when the directory
 * contains only files (communicates that no directory navigation is possible).
 */
export const NO_SUBDIRECTORIES = 'No subdirectories';
