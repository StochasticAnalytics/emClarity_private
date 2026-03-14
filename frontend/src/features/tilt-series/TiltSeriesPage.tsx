/**
 * Tilt-series manager page.
 *
 * Displays a sortable, filterable table of tilt series for an emClarity project.
 * Each row shows: name, status badges (Aligned / CTF Estimated / Reconstructed),
 * and file path.  Selected rows enable a batch-operation toolbar for running
 * autoAlign and ctf estimate on the chosen tilt series.
 *
 * API calls:
 *   GET  /api/v1/projects/{project_id}/tilt-series  – list all tilt series
 *   POST /api/v1/workflow/{project_id}/run           – execute a batch command
 */
import { useState, useCallback, useMemo, useEffect } from 'react'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
  type RowSelectionState,
} from '@tanstack/react-table'
import { apiClient, ApiError } from '@/api/client.ts'
import { useApiQuery } from '@/hooks/useApi.ts'

// ---------------------------------------------------------------------------
// Types mirroring the backend response models
// ---------------------------------------------------------------------------

interface TiltSeriesItem {
  name: string
  stack_path?: string
  rawtlt_path?: string
  aligned: boolean
  ctf_estimated: boolean
  reconstructed?: boolean
}

interface TiltSeriesListResponse {
  tilt_series: TiltSeriesItem[]
}

interface RunCommandResponse {
  project_id: string
  command: string
  status: string
  message: string
}

// ---------------------------------------------------------------------------
// StatusBadge – color-coded completion indicator
// ---------------------------------------------------------------------------

interface StatusBadgeProps {
  done: boolean
  label: string
}

function StatusBadge({ done, label }: StatusBadgeProps) {
  return (
    <span
      className={[
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium',
        done
          ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300'
          : 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-500',
      ].join(' ')}
    >
      <span aria-hidden="true">{done ? '●' : '○'}</span>
      {label}
    </span>
  )
}

// ---------------------------------------------------------------------------
// SortIcon
// ---------------------------------------------------------------------------

function SortIcon({ direction }: { direction: 'asc' | 'desc' | false }) {
  if (direction === 'asc') return <span aria-hidden="true"> ↑</span>
  if (direction === 'desc') return <span aria-hidden="true"> ↓</span>
  return (
    <span aria-hidden="true" className="opacity-30">
      {' '}
      ↕
    </span>
  )
}

// ---------------------------------------------------------------------------
// Column definitions
// ---------------------------------------------------------------------------

const columnHelper = createColumnHelper<TiltSeriesItem>()

const COLUMNS = [
  // Row-selection checkbox
  columnHelper.display({
    id: 'select',
    header: ({ table }) => (
      <input
        type="checkbox"
        checked={table.getIsAllPageRowsSelected()}
        ref={(el) => {
          if (el) el.indeterminate = table.getIsSomePageRowsSelected()
        }}
        onChange={table.getToggleAllPageRowsSelectedHandler()}
        aria-label="Select all rows"
        className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500 dark:border-gray-600"
      />
    ),
    cell: ({ row }) => (
      <input
        type="checkbox"
        checked={row.getIsSelected()}
        onChange={row.getToggleSelectedHandler()}
        aria-label={`Select ${row.original.name}`}
        className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500 dark:border-gray-600"
      />
    ),
    size: 40,
    enableSorting: false,
  }),

  // Name – sortable and filterable
  columnHelper.accessor('name', {
    header: 'Name',
    cell: (info) => (
      <span className="font-mono text-sm text-gray-900 dark:text-gray-100">{info.getValue()}</span>
    ),
    enableSorting: true,
    enableColumnFilter: true,
  }),

  // Status – three color-coded badges
  columnHelper.display({
    id: 'status',
    header: 'Status',
    cell: ({ row }) => {
      const { aligned, ctf_estimated, reconstructed } = row.original
      return (
        <div className="flex flex-wrap gap-1">
          <StatusBadge done={aligned} label="Aligned" />
          <StatusBadge done={ctf_estimated} label="CTF Estimated" />
          <StatusBadge done={reconstructed ?? false} label="Reconstructed" />
        </div>
      )
    },
    enableSorting: false,
  }),

  // File path (prefer stack_path, fall back to rawtlt_path)
  columnHelper.accessor((row) => row.stack_path ?? row.rawtlt_path ?? '—', {
    id: 'file_path',
    header: 'File Path',
    cell: (info) => (
      <span className="break-all font-mono text-xs text-gray-600 dark:text-gray-400">
        {info.getValue()}
      </span>
    ),
    enableSorting: true,
  }),
]

// ---------------------------------------------------------------------------
// TiltSeriesTable – react-table with sorting, filtering, and row selection
// ---------------------------------------------------------------------------

interface TiltSeriesTableProps {
  data: TiltSeriesItem[]
  projectId: string
  onBatchSuccess: (msg: string) => void
}

function TiltSeriesTable({ data, projectId, onBatchSuccess }: TiltSeriesTableProps) {
  const [sorting, setSorting] = useState<SortingState>([])
  const [globalFilter, setGlobalFilter] = useState('')
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({})
  const [batchLoading, setBatchLoading] = useState<string | null>(null)
  const [batchError, setBatchError] = useState<string | null>(null)

  const table = useReactTable({
    data,
    columns: COLUMNS,
    state: { sorting, globalFilter, rowSelection },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    onRowSelectionChange: setRowSelection,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    enableRowSelection: true,
  })

  const selectedRows = table.getSelectedRowModel().rows
  const hasSelection = selectedRows.length > 0

  const runBatchCommand = useCallback(
    async (command: string) => {
      if (!hasSelection) return
      setBatchError(null)
      setBatchLoading(command)
      try {
        const selectedNames = selectedRows.map((r) => r.original.name)
        const resp = await apiClient.post<RunCommandResponse>(
          `/api/v1/workflow/${projectId}/run`,
          { command, args: { tilt_series: selectedNames } },
        )
        onBatchSuccess(
          resp.message ||
            `'${command}' submitted for ${String(selectedNames.length)} tilt series`,
        )
        setRowSelection({})
      } catch (err) {
        if (err instanceof ApiError) {
          const detail =
            typeof err.body === 'object' && err.body !== null && 'detail' in err.body
              ? String((err.body as { detail: unknown }).detail)
              : err.message
          setBatchError(detail)
        } else {
          setBatchError('Unexpected error. Is the backend running?')
        }
      } finally {
        setBatchLoading(null)
      }
    },
    [hasSelection, selectedRows, projectId, onBatchSuccess],
  )

  return (
    <div className="space-y-3">
      {/* Filter / search bar */}
      <div className="flex items-center gap-3">
        <input
          type="search"
          value={globalFilter}
          onChange={(e) => setGlobalFilter(e.target.value)}
          placeholder="Filter tilt series…"
          aria-label="Filter tilt series"
          className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
        />
        <span className="shrink-0 text-xs text-gray-500 dark:text-gray-400">
          {String(table.getFilteredRowModel().rows.length)} / {String(data.length)} rows
        </span>
      </div>

      {/* Batch operations toolbar – visible only when rows are selected */}
      {hasSelection && (
        <div
          role="toolbar"
          aria-label="Batch operations"
          className="flex flex-wrap items-center gap-3 rounded-lg border border-blue-200 bg-blue-50 px-4 py-2 dark:border-blue-700 dark:bg-blue-900/20"
        >
          <span className="text-sm font-medium text-blue-800 dark:text-blue-200">
            {String(selectedRows.length)} selected
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => {
                void runBatchCommand('autoAlign')
              }}
              disabled={batchLoading !== null}
              className="rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-blue-500 dark:hover:bg-blue-600"
            >
              {batchLoading === 'autoAlign' ? 'Submitting…' : 'Auto Align'}
            </button>
            <button
              type="button"
              onClick={() => {
                void runBatchCommand('ctf estimate')
              }}
              disabled={batchLoading !== null}
              className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-indigo-500 dark:hover:bg-indigo-600"
            >
              {batchLoading === 'ctf estimate' ? 'Submitting…' : 'CTF Estimate'}
            </button>
          </div>

          {batchError && (
            <p className="ml-1 text-xs text-red-600 dark:text-red-400">{batchError}</p>
          )}

          <button
            type="button"
            onClick={() => setRowSelection({})}
            className="ml-auto text-xs text-blue-600 hover:underline dark:text-blue-400"
          >
            Clear selection
          </button>
        </div>
      )}

      {/* Table */}
      <div className="overflow-hidden rounded-lg border border-gray-200 dark:border-gray-700">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-800">
              {table.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id}>
                  {headerGroup.headers.map((header) => (
                    <th
                      key={header.id}
                      scope="col"
                      className={[
                        'px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400',
                        header.column.getCanSort()
                          ? 'cursor-pointer select-none hover:text-gray-700 dark:hover:text-gray-200'
                          : '',
                      ].join(' ')}
                      onClick={header.column.getToggleSortingHandler()}
                      aria-sort={
                        header.column.getIsSorted() === 'asc'
                          ? 'ascending'
                          : header.column.getIsSorted() === 'desc'
                            ? 'descending'
                            : undefined
                      }
                    >
                      {header.isPlaceholder ? null : (
                        <span className="inline-flex items-center">
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          {header.column.getCanSort() && (
                            <SortIcon direction={header.column.getIsSorted()} />
                          )}
                        </span>
                      )}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody className="divide-y divide-gray-200 bg-white dark:divide-gray-700 dark:bg-gray-900">
              {table.getRowModel().rows.map((row) => (
                <tr
                  key={row.id}
                  className={[
                    'transition-colors',
                    row.getIsSelected()
                      ? 'bg-blue-50 dark:bg-blue-900/20'
                      : 'hover:bg-gray-50 dark:hover:bg-gray-800',
                  ].join(' ')}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-4 py-3 align-middle">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Selection summary */}
      {table.getFilteredRowModel().rows.length > 0 && (
        <p className="text-xs text-gray-500 dark:text-gray-400">
          {String(Object.keys(rowSelection).length)} of{' '}
          {String(table.getFilteredRowModel().rows.length)} row(s) selected
        </p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// EmptyState – shown when the project has no tilt series
// ---------------------------------------------------------------------------

function EmptyState() {
  return (
    <div className="rounded-lg border border-dashed border-gray-300 p-12 text-center dark:border-gray-600">
      <p className="mb-3 text-2xl" aria-hidden="true">
        🗂
      </p>
      <h3 className="text-base font-medium text-gray-700 dark:text-gray-300">
        No tilt series found
      </h3>
      <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
        Add <code className="font-mono">.st</code> tilt-series stack files to the{' '}
        <code className="font-mono">rawData/</code> directory, then reload.
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// ProjectIdGate – prompts for a project ID before showing data
// ---------------------------------------------------------------------------

interface ProjectIdGateProps {
  onConfirm: (id: string) => void
}

function ProjectIdGate({ onConfirm }: ProjectIdGateProps) {
  const [input, setInput] = useState('')

  const handleSubmit = useCallback(() => {
    const trimmed = input.trim()
    if (trimmed) onConfirm(trimmed)
  }, [input, onConfirm])

  return (
    <div className="max-w-md space-y-4 rounded-xl border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-900">
      <div>
        <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">Open Project</h3>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Enter a project ID to view its tilt series.
        </p>
      </div>
      <div className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleSubmit()
          }}
          placeholder="Enter project ID…"
          aria-label="Project ID"
          className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
        />
        <button
          type="button"
          onClick={handleSubmit}
          disabled={!input.trim()}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:cursor-not-allowed disabled:opacity-60"
        >
          Load
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// TiltSeriesContent – fetches data and renders table / empty state
// ---------------------------------------------------------------------------

interface TiltSeriesContentProps {
  projectId: string
  onBack: () => void
}

function TiltSeriesContent({ projectId, onBack }: TiltSeriesContentProps) {
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  const { data, isLoading, error, refetch } = useApiQuery<TiltSeriesListResponse>(
    ['tilt-series', projectId],
    `/api/v1/projects/${projectId}/tilt-series`,
  )

  // Auto-dismiss success notification after 5 s
  useEffect(() => {
    if (!successMessage) return
    const timer = setTimeout(() => setSuccessMessage(null), 5000)
    return () => clearTimeout(timer)
  }, [successMessage])

  const handleBatchSuccess = useCallback(
    (msg: string) => {
      setSuccessMessage(msg)
      void refetch()
    },
    [refetch],
  )

  const tiltSeries = useMemo(() => data?.tilt_series ?? [], [data])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
        <span className="ml-3 text-gray-500 dark:text-gray-400">Loading tilt series…</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-3 rounded-lg border border-red-200 bg-red-50 p-6 dark:border-red-800 dark:bg-red-900/20">
        <h3 className="font-semibold text-red-800 dark:text-red-200">
          Failed to load tilt series
        </h3>
        <p className="text-sm text-red-600 dark:text-red-400">{error.message}</p>
        <button
          type="button"
          onClick={onBack}
          className="text-sm text-red-600 underline hover:text-red-800 dark:text-red-400"
        >
          ← Change project
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Project header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
            Project
          </p>
          <p className="font-mono text-sm text-gray-700 dark:text-gray-300">{projectId}</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => void refetch()}
            className="text-sm text-blue-600 hover:underline dark:text-blue-400"
          >
            ↻ Refresh
          </button>
          <button
            type="button"
            onClick={onBack}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
          >
            ← Back
          </button>
        </div>
      </div>

      {/* Success notification */}
      {successMessage && (
        <div
          role="status"
          aria-live="polite"
          className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700 dark:border-green-700 dark:bg-green-900/20 dark:text-green-300"
        >
          ✓ {successMessage}
        </div>
      )}

      {/* Status badge legend */}
      <div className="flex flex-wrap gap-3 text-xs text-gray-500 dark:text-gray-400">
        <div className="flex items-center gap-1.5">
          <span className="inline-block h-2 w-2 rounded-full bg-green-500" aria-hidden="true" />
          Completed
        </div>
        <div className="flex items-center gap-1.5">
          <span
            className="inline-block h-2 w-2 rounded-full bg-gray-300 dark:bg-gray-600"
            aria-hidden="true"
          />
          Not yet completed
        </div>
      </div>

      {/* Table or empty state */}
      {tiltSeries.length === 0 ? (
        <EmptyState />
      ) : (
        <TiltSeriesTable data={tiltSeries} projectId={projectId} onBatchSuccess={handleBatchSuccess} />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// TiltSeriesPage – main exported component
// ---------------------------------------------------------------------------

export function TiltSeriesPage() {
  const [projectId, setProjectId] = useState<string | null>(null)

  const handleBack = useCallback(() => {
    setProjectId(null)
  }, [])

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold">Tilt Series</h2>
        <p className="mt-2 text-gray-500 dark:text-gray-400">
          View, filter, and manage tilt-series data sets. Select rows to run batch operations.
        </p>
      </div>

      {projectId ? (
        <TiltSeriesContent projectId={projectId} onBack={handleBack} />
      ) : (
        <ProjectIdGate onConfirm={setProjectId} />
      )}
    </div>
  )
}
