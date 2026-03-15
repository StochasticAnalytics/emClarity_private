/**
 * DirectoryPickerActions.tsx
 *
 * Action buttons row for the DirectoryPickerModal (Cancel + Select).
 *
 * This is a stub for TASK-002b-Aa-Ab.  The Select button's enabled/disabled
 * logic and the call to onSelect are implemented in that task.  The Cancel
 * button wires onClose directly so the modal can be dismissed at any time.
 *
 * Deferred to TASK-002b-Ab:
 *   - Enabling the Select button when a path is confirmed
 *   - Calling onSelect(currentPath) from the Select button
 *   - returnFocusRef.current?.focus() on close
 */

export interface DirectoryPickerActionsProps {
  /** Forwarded from DirectoryPickerModal; called by the Select button (Aa-Ab). */
  onSelect: (path: string) => void;
  /** Forwarded from DirectoryPickerModal; called by the Cancel button. */
  onClose: () => void;
  /** The current navigation path from the hook; needed by Aa-Ab to call onSelect. */
  currentPath: string | null;
  /** Mirrors the hook's isLoading flag so the Select button can be disabled. */
  isLoading: boolean;
}

/**
 * Renders the Cancel and Select action buttons for the directory picker dialog.
 *
 * Select is always disabled in this stub; Aa-Ab enables it and wires onSelect.
 */
export function DirectoryPickerActions({
  onSelect: _onSelect,
  onClose,
  currentPath: _currentPath,
  isLoading: _isLoading,
}: DirectoryPickerActionsProps) {
  return (
    <div>
      <button type="button" onClick={onClose}>
        Cancel
      </button>
      {/* Select button — enabled and wired to onSelect in TASK-002b-Ab */}
      <button type="button" disabled>
        Select
      </button>
    </div>
  );
}
