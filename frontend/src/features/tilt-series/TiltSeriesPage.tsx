/**
 * Tilt-series table page.
 *
 * Displays and manages the tilt-series data for a selected project.
 * Uses @tanstack/react-table for a sortable, filterable table.
 *
 * Features:
 *  - Sortable and filterable table of tilt series
 *  - Color-coded status badges (aligned / CTF estimated / reconstructed)
 *  - Row selection with batch operations toolbar
 *  - Empty state when no tilt series are available
 *
 * API calls:
 *   GET  /api/v1/projects/{project_id}/tilt-series  – list tilt series
 *   POST /api/v1/workflow/{project_id}/run          – execute batch command
 */
import { useState, useCallback, useMemo } from 'react'
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
// Types
// ---------------------------------------------------------------------------

interface TiltSeriesItem {
  name: string
  stack_path: string | null
  rawtlt_path: string | null
  aligned: boolean
  ctf_estimated: boolean
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

type TiltSeriesStatus = 'unprocessed' | 'aligned' | 'ctf_estimated' | 'reconstructed'

// ---------------------------------------------------------------------------
// Status helpers
// ---------------------------------------------------------------------------

function getTiltSeriesStatus(item: TiltSeriesItem): TiltSeriesStatus {
  if (item.ctf_estimated) return 'ctf_estimated'
  if (item.aligned) return 'aligned'
  return 'unprocessed'
}

interface StatusBadgeConfig {
  label: string
  className: string
}

const STATUS_BADGE: Record<TiltSeriesStatus, StatusBadgeConfig> = {
  unprocessed: {
    label: 'Unprocessed',
    className:
      'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ' +
      'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300',
  },
  aligned: {
    label: 'Aligned',
    className:
      'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ' +
      'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
  },
  ctf_estimated: {
    label: 'CTF Estimated',
    className:
      'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ' +
      'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300',
  },
  reconstructed: {
    label: 'Reconstructed',
    className:
      'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ' +
      'bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-300',
  },
}

// ---------------------------------------------------------------------------
// StatusBadge component
// ---------------------------------------------------------------------------

function StatusBadge({ status }: { status: TiltSeriesStatus }) {
  const config = STATUS_BADGE[status]
  return <span className={config.className}>{config.label}</span>
}

// ---------------------------------------------------------------------------
// EmptyState component
// ---------------------------------------------------------------------------

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-8 text-center">
      {/* File icon */}
      <svg
        className="w-12 h-12 text-gray-300 dark:text-gray-600 mb-4"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"
        />
      </svg>
      <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-2">
        No tilt series found
      </h3>
      <p className="text-sm text-gray-500 dark:text-gray-400 max-w-sm">
        Add <code className="font-mono bg-gray-100 dark:bg-gray-800 px-1 py-0.5 rounded text-xs">.st</code> tilt-series
        stack files to the <code className="font-mono bg-gray-100 dark:bg-gray-800 px-1 py-0.5 rounded text-xs">rawData/</code> directory
        of your project to get started.
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// ProjectSelector component
// ---------------------------------------------------------------------------

interface ProjectSelectorProps {
  projectId: string
  onProjectIdChange: (id: string) => void
}

function ProjectSelector({ projectId, onProjectIdChange }: ProjectSelectorProps) {
  const [inputValue, setInputValue] = useState(projectId)

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault()
      const trimmed = inputValue.trim()
      if (trimmed) {
        onProjectIdChange(trimmed)
      }
    },
    [inputValue, onProjectIdChange],
  )

  return (
    <form onSubmit={handleSubmit} className="flex items-center gap-2">
      <input
        type="text"
        value={inputValue}
        onChange={(e) => setInputValue(e.target.value)}
        placeholder="Enter project ID"
        aria-label="Project ID"
        className={
          'block rounded-md border border-gray-300 px-3 py-1.5 text-sm shadow-sm ' +
          'focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 ' +
          'dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 ' +
          'placeholder:text-gray-400 dark:placeholder:text-gray-500 w-72'
        }
      />
      <button
        type="submit"
        className={
          'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium ' +
          'bg-blue-600 text-white hover:bg-blue-700 active:bg-blue-800 ' +
          'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 ' +
          'disabled:opacity-50 disabled:cursor-not-allowed transition-colors'
        }
      >
        Load
      </button>
    </form>
  )
}

// ---------------------------------------------------------------------------
// BatchOperationsToolbar component
// ---------------------------------------------------------------------------

interface BatchOperationsToolbarProps {
  selectedCount: number
  projectId: string
  selectedNames: string[]
  onSuccess: (message: string) => void
  onError: (message: string) => void
}

function BatchOperationsToolbar({
  selectedCount,
  projectId,
  selectedNames,
  onSuccess,
  onError,
}: BatchOperationsToolbarProps) {
  const [runningCommand, setRunningCommand] = useState<string | null>(null)

  const handleRunCommand = useCallback(
    async (command: string) => {
      setRunningCommand(command)
      try {
        const result = await apiClient.post<RunCommandResponse>(
          `/api/v1/workflow/${projectId}/run`,
          { command, tilt_series: selectedNames },
        )
        onSuccess(result.message || `Command '${command}' started successfully.`)
      } catch (err) {
        const message =
          err instanceof ApiError
            ? `Failed to run '${command}': ${err.statusText}`
            : `Failed to run '${command}'. Please try again.`
        onError(message)
      } finally {
        setRunningCommand(null)
      }
    },
    [projectId, selectedNames, onSuccess, onError],
  )

  const buttonClass = (disabled: boolean) =>
    'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium ' +
    'border border-gray-300 dark:border-gray-600 ' +
    'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 ' +
    'hover:bg-gray-50 dark:hover:bg-gray-700 ' +
    'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 ' +
    'transition-colors ' +
    (disabled ? 'opacity-50 cursor-not-allowed' : '')

  return (
    <div
      className={
        'flex items-center gap-3 px-4 py-2.5 ' +
        'bg-blue-50 dark:bg-blue-900/20 ' +
        'border border-blue-200 dark:border-blue-800 rounded-lg'
      }
      role="toolbar"
      aria-label="Batch operations"
    >
      <span className="text-sm font-medium text-blue-800 dark:text-blue-300 mr-1">
        {selectedCount} selected
      </span>
      <span className="w-px h-5 bg-blue-200 dark:bg-blue-700" aria-hidden="true" />
      <span className="text-xs text-blue-600 dark:text-blue-400 mr-2">Batch operations:</span>

      <button
        type="button"
        className={buttonClass(runningCommand !== null)}
        disabled={runningCommand !== null}
        onClick={() => handleRunCommand('autoAlign')}
        title="Run autoAlign on selected tilt series"
      >
        {runningCommand === 'autoAlign' ? (
          <svg
            className="w-4 h-4 animate-spin text-gray-400"
            viewBox="0 0 24 24"
            fill="none"
            aria-hidden="true"
          >
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
            />
          </svg>
        ) : (
          <svg
            className="w-4 h-4"
            viewBox="0 0 20 20"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fillRule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zM9.555 7.168A1 1 0 008 8v4a1 1 0 001.555.832l3-2a1 1 0 000-1.664l-3-2z"
              clipRule="evenodd"
            />
          </svg>
        )}
        Run autoAlign
      </button>

      <button
        type="button"
        className={buttonClass(runningCommand !== null)}
        disabled={runningCommand !== null}
        onClick={() => handleRunCommand('ctf estimate')}
        title="Run ctf estimate on selected tilt series"
      >
        {runningCommand === 'ctf estimate' ? (
          <svg
            className="w-4 h-4 animate-spin text-gray-400"
            viewBox="0 0 24 24"
            fill="none"
            aria-hidden="true"
          >
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
            />
          </svg>
        ) : (
          <svg
            className="w-4 h-4"
            viewBox="0 0 20 20"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fillRule="evenodd"
              d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z"
              clipRule="evenodd"
            />
          </svg>
        )}
        Run CTF Estimate
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Column helper
// ---------------------------------------------------------------------------

const columnHelper = createColumnHelper<TiltSeriesItem>()

// ---------------------------------------------------------------------------
// TiltSeriesTable component
// ---------------------------------------------------------------------------

interface TiltSeriesTableProps {
  data: TiltSeriesItem[]
  projectId: string
  onSuccess: (message: string) => void
  onError: (message: string) => void
}

function TiltSeriesTable({ data, projectId, onSuccess, onError }: TiltSeriesTableProps) {
  const [sorting, setSorting] = useState<SortingState>([])
  const [globalFilter, setGlobalFilter] = useState('')
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({})

  const columns = useMemo(
    () => [
      // Checkbox column
      columnHelper.display({
        id: 'select',
        header: ({ table }) => (
          <input
            type="checkbox"
            checked={table.getIsAllPageRowsSelected()}
            ref={(el) => {
              if (el) {
                el.indeterminate = table.getIsSomePageRowsSelected()
              }
            }}
            onChange={table.getToggleAllPageRowsSelectedHandler()}
            aria-label="Select all rows"
            className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800"
          />
        ),
        cell: ({ row }) => (
          <input
            type="checkbox"
            checked={row.getIsSelected()}
            onChange={row.getToggleSelectedHandler()}
            aria-label={`Select ${row.original.name}`}
            className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800"
          />
        ),
        enableSorting: false,
        size: 40,
      }),

      // Name column
      columnHelper.accessor('name', {
        header: 'Name',
        cell: (info) => (
          <span className="font-mono text-sm font-medium text-gray-900 dark:text-gray-100">
            {info.getValue()}
          </span>
        ),
        sortingFn: 'alphanumeric',
      }),

      // Status column (derived from aligned + ctf_estimated)
      columnHelper.accessor(
        (row) => getTiltSeriesStatus(row),
        {
          id: 'status',
          header: 'Status',
          cell: (info) => <StatusBadge status={info.getValue() as TiltSeriesStatus} />,
          sortingFn: (rowA, rowB) => {
            const order: Record<TiltSeriesStatus, number> = {
              reconstructed: 3,
              ctf_estimated: 2,
              aligned: 1,
              unprocessed: 0,
            }
            return (
              order[getTiltSeriesStatus(rowA.original)] -
              order[getTiltSeriesStatus(rowB.original)]
            )
          },
          filterFn: (row, _id, filterValue: string) => {
            if (!filterValue) return true
            const status = getTiltSeriesStatus(row.original)
            const label = STATUS_BADGE[status].label.toLowerCase()
            return label.includes(filterValue.toLowerCase())
          },
        },
      ),

      // File path column
      columnHelper.accessor('stack_path', {
        header: 'File Path',
        cell: (info) => {
          const val = info.getValue()
          return val ? (
            <span
              className="font-mono text-xs text-gray-600 dark:text-gray-400 truncate max-w-xs block"
              title={val}
            >
              {val}
            </span>
          ) : (
            <span className="text-xs text-gray-400 dark:text-gray-600 italic">—</span>
          )
        },
        sortingFn: 'alphanumeric',
      }),
    ],
    [],
  )

  const table = useReactTable({
    data,
    columns,
    state: {
      sorting,
      globalFilter,
      rowSelection,
    },
    enableRowSelection: true,
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    onRowSelectionChange: setRowSelection,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  })

  const selectedRows = table.getSelectedRowModel().rows
  const selectedNames = selectedRows.map((r) => r.original.name)

  return (
    <div className="space-y-3">
      {/* Filter input */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <svg
            className="absolute left-2.5 top-2.5 w-4 h-4 text-gray-400 pointer-events-none"
            viewBox="0 0 20 20"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fillRule="evenodd"
              d="M9 3.5a5.5 5.5 0 100 11 5.5 5.5 0 000-11zM2 9a7 7 0 1112.452 4.391l3.328 3.329a.75.75 0 11-1.06 1.06l-3.329-3.328A7 7 0 012 9z"
              clipRule="evenodd"
            />
          </svg>
          <input
            type="text"
            value={globalFilter}
            onChange={(e) => setGlobalFilter(e.target.value)}
            placeholder="Filter tilt series…"
            aria-label="Filter tilt series"
            className={
              'block w-full rounded-md border border-gray-300 pl-8 pr-3 py-1.5 text-sm shadow-sm ' +
              'focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 ' +
              'dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 ' +
              'placeholder:text-gray-400 dark:placeholder:text-gray-500'
            }
          />
        </div>
        <span className="text-sm text-gray-500 dark:text-gray-400">
          {table.getFilteredRowModel().rows.length} of {data.length} tilt series
        </span>
      </div>

      {/* Batch operations toolbar – visible only when rows are selected */}
      {selectedRows.length > 0 && (
        <BatchOperationsToolbar
          selectedCount={selectedRows.length}
          projectId={projectId}
          selectedNames={selectedNames}
          onSuccess={onSuccess}
          onError={onError}
        />
      )}

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700 shadow-sm">
        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
          <thead className="bg-gray-50 dark:bg-gray-800">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    scope="col"
                    className={[
                      'px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider',
                      'text-gray-500 dark:text-gray-400',
                      header.column.getCanSort()
                        ? 'cursor-pointer select-none hover:text-gray-700 dark:hover:text-gray-200'
                        : '',
                    ].join(' ')}
                    style={{ width: header.getSize() !== 150 ? header.getSize() : undefined }}
                    onClick={header.column.getToggleSortingHandler()}
                    aria-sort={
                      header.column.getIsSorted() === 'asc'
                        ? 'ascending'
                        : header.column.getIsSorted() === 'desc'
                          ? 'descending'
                          : undefined
                    }
                  >
                    <span className="flex items-center gap-1">
                      {header.isPlaceholder
                        ? null
                        : flexRender(header.column.columnDef.header, header.getContext())}
                      {header.column.getCanSort() && (
                        <span aria-hidden="true" className="text-gray-300 dark:text-gray-600">
                          {header.column.getIsSorted() === 'asc' ? (
                            <svg className="w-3 h-3" viewBox="0 0 20 20" fill="currentColor">
                              <path
                                fillRule="evenodd"
                                d="M10 3a.75.75 0 01.55.24l3.25 3.5a.75.75 0 11-1.1 1.02L10 4.852 7.3 7.76a.75.75 0 01-1.1-1.02l3.25-3.5A.75.75 0 0110 3z"
                                clipRule="evenodd"
                              />
                            </svg>
                          ) : header.column.getIsSorted() === 'desc' ? (
                            <svg className="w-3 h-3" viewBox="0 0 20 20" fill="currentColor">
                              <path
                                fillRule="evenodd"
                                d="M10 17a.75.75 0 01-.55-.24l-3.25-3.5a.75.75 0 111.1-1.02L10 15.148l2.7-2.908a.75.75 0 111.1 1.02l-3.25 3.5A.75.75 0 0110 17z"
                                clipRule="evenodd"
                              />
                            </svg>
                          ) : (
                            <svg className="w-3 h-3 opacity-40" viewBox="0 0 20 20" fill="currentColor">
                              <path
                                fillRule="evenodd"
                                d="M10 3a.75.75 0 01.55.24l3.25 3.5a.75.75 0 11-1.1 1.02L10 4.852 7.3 7.76a.75.75 0 01-1.1-1.02l3.25-3.5A.75.75 0 0110 3zm-3.806 9.691a.75.75 0 011.06.053L10 15.147l2.747-2.403a.75.75 0 111.012 1.108l-3.25 2.85a.75.75 0 01-1.012 0l-3.25-2.85a.75.75 0 01.053-1.061z"
                                clipRule="evenodd"
                              />
                            </svg>
                          )}
                        </span>
                      )}
                    </span>
                  </th>
                ))}
              </tr>
            ))}
          </thead>

          <tbody className="divide-y divide-gray-100 dark:divide-gray-800 bg-white dark:bg-gray-900">
            {table.getRowModel().rows.length === 0 ? (
              <tr>
                <td
                  colSpan={columns.length}
                  className="px-4 py-8 text-center text-sm text-gray-400 dark:text-gray-500"
                >
                  No results match your filter.
                </td>
              </tr>
            ) : (
              table.getRowModel().rows.map((row) => (
                <tr
                  key={row.id}
                  className={[
                    'transition-colors',
                    row.getIsSelected()
                      ? 'bg-blue-50 dark:bg-blue-900/20'
                      : 'hover:bg-gray-50 dark:hover:bg-gray-800/50',
                  ].join(' ')}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-4 py-3 whitespace-nowrap">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// TiltSeriesContent – handles data loading for a given project
// ---------------------------------------------------------------------------

interface TiltSeriesContentProps {
  projectId: string
}

function TiltSeriesContent({ projectId }: TiltSeriesContentProps) {
  const [notification, setNotification] = useState<{ type: 'success' | 'error'; message: string } | null>(null)

  const handleSuccess = useCallback((message: string) => {
    setNotification({ type: 'success', message })
    setTimeout(() => setNotification(null), 5000)
  }, [])

  const handleError = useCallback((message: string) => {
    setNotification({ type: 'error', message })
    setTimeout(() => setNotification(null), 8000)
  }, [])

  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
  } = useApiQuery<TiltSeriesListResponse>(
    ['tilt-series', projectId],
    `/api/v1/projects/${projectId}/tilt-series`,
  )

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <svg
          className="w-6 h-6 animate-spin text-blue-500"
          viewBox="0 0 24 24"
          fill="none"
          aria-hidden="true"
        >
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
          />
        </svg>
        <span className="ml-3 text-sm text-gray-500 dark:text-gray-400">Loading tilt series…</span>
      </div>
    )
  }

  if (isError) {
    const statusCode = error instanceof ApiError ? error.status : null
    const isNotFound = statusCode === 404

    return (
      <div className="rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 p-6">
        <div className="flex items-start gap-3">
          <svg
            className="w-5 h-5 text-red-500 shrink-0 mt-0.5"
            viewBox="0 0 20 20"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fillRule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z"
              clipRule="evenodd"
            />
          </svg>
          <div>
            <p className="text-sm font-medium text-red-800 dark:text-red-300">
              {isNotFound
                ? `Project '${projectId}' not found.`
                : 'Failed to load tilt series.'}
            </p>
            {!isNotFound && (
              <button
                type="button"
                onClick={() => void refetch()}
                className="mt-2 text-sm text-red-700 dark:text-red-400 underline hover:no-underline"
              >
                Retry
              </button>
            )}
          </div>
        </div>
      </div>
    )
  }

  const tiltSeries = data?.tilt_series ?? []

  return (
    <div className="space-y-4">
      {/* Notification banner */}
      {notification && (
        <div
          role="alert"
          className={[
            'rounded-lg border px-4 py-3 text-sm flex items-center justify-between gap-3',
            notification.type === 'success'
              ? 'border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/20 text-green-800 dark:text-green-300'
              : 'border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 text-red-800 dark:text-red-300',
          ].join(' ')}
        >
          <span>{notification.message}</span>
          <button
            type="button"
            onClick={() => setNotification(null)}
            aria-label="Dismiss"
            className="shrink-0 opacity-70 hover:opacity-100"
          >
            <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
            </svg>
          </button>
        </div>
      )}

      {/* Table or empty state */}
      {tiltSeries.length === 0 ? (
        <EmptyState />
      ) : (
        <TiltSeriesTable
          data={tiltSeries}
          projectId={projectId}
          onSuccess={handleSuccess}
          onError={handleError}
        />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// TiltSeriesPage – exported page component
// ---------------------------------------------------------------------------

export function TiltSeriesPage() {
  const [projectId, setProjectId] = useState('')
  const [activeProjectId, setActiveProjectId] = useState('')

  const handleLoad = useCallback((id: string) => {
    setActiveProjectId(id)
  }, [])

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">Tilt Series</h2>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            View and manage tilt-series data sets. Select rows to run batch processing operations.
          </p>
        </div>

        <ProjectSelector
          projectId={projectId}
          onProjectIdChange={(id) => {
            setProjectId(id)
            handleLoad(id)
          }}
        />
      </div>

      {/* Content area */}
      {activeProjectId ? (
        <TiltSeriesContent projectId={activeProjectId} />
      ) : (
        <div className="rounded-lg border border-dashed border-gray-300 dark:border-gray-700 p-12 text-center">
          <svg
            className="mx-auto w-10 h-10 text-gray-300 dark:text-gray-600 mb-3"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.5}
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z"
            />
          </svg>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Enter a project ID above to view tilt series.
          </p>
        </div>
      )}
    </div>
  )
}
