/**
 * DirectoryPickerModal — simple server-side directory browser.
 *
 * Shows the current directory as breadcrumb segments, lists subdirectories
 * as clickable entries, and provides Select / Cancel actions.
 *
 * Props:
 *   isOpen      — whether the modal is visible
 *   onSelect    — called with the chosen absolute path when Select is clicked
 *   onClose     — called when the modal should be dismissed
 *   initialPath — optional starting path (defaults to server home)
 *   mode        — 'directory' (default) shows only directories;
 *                 'file' shows all entries returned by the backend
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { browseDirectory, type FilesystemBrowseResponse } from '@/api/filesystem.ts'
import { ApiError } from '@/api/client.ts'

export interface DirectoryPickerModalProps {
  isOpen: boolean
  onSelect: (path: string) => void
  onClose: () => void
  initialPath?: string
  mode?: 'directory' | 'file'
}

// ---------------------------------------------------------------------------
// Breadcrumb helpers
// ---------------------------------------------------------------------------

interface BreadcrumbSegment {
  label: string
  path: string
}

/**
 * Split an absolute path into clickable breadcrumb segments.
 *
 * '/home/user/projects' → [
 *   { label: '/', path: '/' },
 *   { label: 'home', path: '/home' },
 *   { label: 'user', path: '/home/user' },
 *   { label: 'projects', path: '/home/user/projects' },
 * ]
 */
function buildBreadcrumbs(absPath: string): BreadcrumbSegment[] {
  const parts = absPath.split('/').filter((p) => p !== '')
  const segments: BreadcrumbSegment[] = [{ label: '/', path: '/' }]
  for (let i = 0; i < parts.length; i++) {
    const path = '/' + parts.slice(0, i + 1).join('/')
    segments.push({ label: parts[i] ?? '', path })
  }
  return segments
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function DirectoryPickerModal({
  isOpen,
  onSelect,
  onClose,
  initialPath,
  mode = 'directory',
}: DirectoryPickerModalProps) {
  const [data, setData] = useState<FilesystemBrowseResponse | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const dialogRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  const navigate = useCallback((path?: string) => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setIsLoading(true)
    setError(null)

    browseDirectory(path, controller.signal)
      .then((result) => {
        setData(result)
        setIsLoading(false)
      })
      .catch((err: unknown) => {
        if (err instanceof Error && err.name === 'AbortError') return

        let message: string
        if (err instanceof ApiError) {
          // Extract the structured `detail` field from the response body when available.
          const rawBody = err.body
          const detail =
            rawBody !== null &&
            typeof rawBody === 'object' &&
            'detail' in rawBody &&
            typeof (rawBody as Record<string, unknown>).detail === 'string'
              ? ((rawBody as Record<string, unknown>).detail as string)
              : null
          message = detail ?? err.message
        } else if (err instanceof TypeError) {
          // Network / connection error — fetch() itself threw before receiving a response.
          message = 'Cannot connect to server — is the backend running?'
        } else if (err instanceof Error) {
          message = err.message
        } else {
          message = 'An unexpected error occurred'
        }

        setError(message)
        setIsLoading(false)
      })
  }, [])

  // Load initial directory when modal opens
  useEffect(() => {
    if (!isOpen) return
    navigate(initialPath)
    return () => {
      abortRef.current?.abort()
    }
  }, [isOpen, initialPath, navigate])

  // Escape key + focus trap
  useEffect(() => {
    if (!isOpen) return

    if (dialogRef.current) {
      dialogRef.current.focus()
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
        return
      }
      if (e.key !== 'Tab') return

      const el = dialogRef.current
      if (!el) return
      const focusable = Array.from(
        el.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), input, textarea, select, [tabindex]:not([tabindex="-1"])',
        ),
      )
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (!first || !last) return
      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault()
          last.focus()
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  if (!isOpen) return null

  // In directory mode show only directories; in file mode show all entries.
  const visibleEntries =
    mode === 'directory'
      ? (data?.entries ?? []).filter((e) => e.type === 'directory')
      : (data?.entries ?? [])

  const breadcrumbs = data?.path ? buildBreadcrumbs(data.path) : []

  return (
    /* Backdrop */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      {/* Dialog panel */}
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="dir-picker-title"
        tabIndex={-1}
        className="relative flex w-full max-w-lg flex-col rounded-xl border border-gray-200 bg-white shadow-2xl focus:outline-none dark:border-gray-700 dark:bg-gray-900"
        style={{ maxHeight: '80vh' }}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3 dark:border-gray-700">
          <h2
            id="dir-picker-title"
            className="text-base font-semibold text-gray-900 dark:text-gray-100"
          >
            Browse Directory
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close directory picker"
            className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:hover:bg-gray-800 dark:hover:text-gray-300"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Breadcrumb navigation */}
        <div className="flex flex-wrap items-center gap-0.5 border-b border-gray-100 px-4 py-2 dark:border-gray-800">
          {breadcrumbs.length > 0 ? (
            breadcrumbs.map((seg, idx) => (
              <span key={seg.path} className="flex items-center">
                {idx > 0 && (
                  <svg
                    className="mx-0.5 h-3 w-3 shrink-0 text-gray-400"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    aria-hidden="true"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                )}
                {idx === breadcrumbs.length - 1 ? (
                  /* Current segment — not clickable */
                  <span className="max-w-[120px] truncate font-mono text-xs font-medium text-gray-700 dark:text-gray-300">
                    {seg.label}
                  </span>
                ) : (
                  <button
                    type="button"
                    onClick={() => navigate(seg.path)}
                    aria-label={`Navigate to ${seg.path}`}
                    className="max-w-[120px] truncate rounded px-1 font-mono text-xs text-blue-600 hover:bg-gray-100 hover:underline focus:outline-none focus:ring-2 focus:ring-blue-500 dark:text-blue-400 dark:hover:bg-gray-800"
                  >
                    {seg.label}
                  </button>
                )}
              </span>
            ))
          ) : (
            <span className="font-mono text-xs text-gray-400 dark:text-gray-500">…</span>
          )}
        </div>

        {/* Directory listing */}
        <div className="flex-1 overflow-y-auto">
          {isLoading && (
            <p className="px-4 py-6 text-center text-sm text-gray-400 dark:text-gray-500">
              Loading…
            </p>
          )}

          {!isLoading && error !== null && (
            <div className="px-4 py-4">
              <p className="mb-2 text-sm text-red-600 dark:text-red-400">{error}</p>
              <button
                type="button"
                onClick={() => navigate(data?.path ?? initialPath)}
                className="rounded bg-gray-100 px-3 py-1 text-xs font-medium text-gray-700 hover:bg-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
              >
                Retry
              </button>
            </div>
          )}

          {!isLoading && error === null && visibleEntries.length === 0 && data !== null && (
            <p className="px-4 py-6 text-center text-sm text-gray-400 dark:text-gray-500">
              No subdirectories
            </p>
          )}

          {!isLoading && error === null && visibleEntries.length > 0 && (
            <ul>
              {visibleEntries.map((entry) => (
                <li key={entry.path}>
                  <button
                    type="button"
                    onClick={() => navigate(entry.path)}
                    className="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-gray-800 hover:bg-gray-50 focus:bg-gray-50 focus:outline-none dark:text-gray-200 dark:hover:bg-gray-800 dark:focus:bg-gray-800"
                  >
                    <svg
                      className="h-4 w-4 shrink-0 text-yellow-500"
                      fill="currentColor"
                      viewBox="0 0 20 20"
                      aria-hidden="true"
                    >
                      <path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" />
                    </svg>
                    <span className="truncate">{entry.name}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Footer: Select + Cancel */}
        <div className="flex justify-end gap-2 border-t border-gray-200 px-4 py-3 dark:border-gray-700">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => {
              if (data?.path) {
                onSelect(data.path)
              }
            }}
            disabled={data === null || isLoading}
            className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-blue-500 dark:hover:bg-blue-600"
          >
            Select
          </button>
        </div>
      </div>
    </div>
  )
}
