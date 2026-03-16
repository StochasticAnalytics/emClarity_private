/**
 * Assets Panel — cisTEM-style asset management with 6 data-type tabs.
 *
 * Layout (per tab):
 *   Left sidebar  — Groups list with counts
 *   Main area     — Sortable, filterable data table
 *   Bottom bar    — Import, Remove, Display buttons + item count
 *
 * Tabs (matching emClarity project directory structure):
 *   1. Tilt Series        → fixedStacks/*.fixed + alignment files
 *   2. CTF Data           → fixedStacks/ctf/ (power spectra, defocus fits)
 *   3. Tomograms          → cache/*.rec
 *   4. Particle Positions → convmap/*.csv + .mod files
 *   5. Reference Volumes  → cycle*_*_REF_ODD/EVE.mrc half-map pairs
 *   6. FSC Curves         → FSC/*_fsc_GLD.txt / .pdf
 *
 * The Tilt Series tab refactors the existing TiltSeriesPage logic.
 * Other tabs show correct column headers with placeholder data.
 */
import { useState, useCallback, useMemo, useRef, useEffect } from 'react'
import { useParams, Navigate } from 'react-router-dom'
import { DEMO_PROJECT_ID } from '@/constants'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
  type RowSelectionState,
  type ColumnDef,
} from '@tanstack/react-table'
import { apiClient, ApiError } from '@/api/client.ts'
import { useApiQuery } from '@/hooks/useApi.ts'

// ---------------------------------------------------------------------------
// Tab identifiers
// ---------------------------------------------------------------------------

type AssetTabId =
  | 'tilt-series'
  | 'ctf-data'
  | 'tomograms'
  | 'particle-positions'
  | 'reference-volumes'
  | 'fsc-curves'

interface AssetTab {
  id: AssetTabId
  label: string
  description: string
}

const ASSET_TABS: AssetTab[] = [
  {
    id: 'tilt-series',
    label: 'Tilt Series',
    description: 'fixedStacks/*.fixed — aligned tilt-series stacks and metadata',
  },
  {
    id: 'ctf-data',
    label: 'CTF Data',
    description: 'fixedStacks/ctf/ — power spectra and defocus estimates',
  },
  {
    id: 'tomograms',
    label: 'Tomograms',
    description: 'cache/*.rec — 3D reconstructions at various binnings',
  },
  {
    id: 'particle-positions',
    label: 'Particle Positions',
    description: 'convmap/*.csv — template search coordinates and .mod files',
  },
  {
    id: 'reference-volumes',
    label: 'Reference Volumes',
    description: 'cycle*_*_REF_ODD/EVE.mrc — half-map pairs for FSC',
  },
  {
    id: 'fsc-curves',
    label: 'FSC Curves',
    description: 'FSC/*_fsc_GLD.txt — Fourier Shell Correlation statistics',
  },
]

// ---------------------------------------------------------------------------
// Tilt-series types (from existing TiltSeriesPage)
// ---------------------------------------------------------------------------

interface TiltSeriesItem {
  name: string
  stack_path: string | null
  rawtlt_path: string | null
  aligned: boolean
  ctf_estimated: boolean
  pixel_size?: number | null
  tilt_range?: string | null
  n_views?: number | null
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
    label: 'Imported',
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
    label: 'CTF Est.',
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

function StatusBadge({ status }: { status: TiltSeriesStatus }) {
  const config = STATUS_BADGE[status]
  return <span className={config.className}>{config.label}</span>
}

// ---------------------------------------------------------------------------
// Group definition
// ---------------------------------------------------------------------------

interface AssetGroup {
  id: string
  label: string
  count: number
}

// ---------------------------------------------------------------------------
// Shared layout components
// ---------------------------------------------------------------------------

/** Left sidebar: groups list with counts */
function GroupsSidebar({
  groups,
  activeGroup,
  onGroupChange,
}: {
  groups: AssetGroup[]
  activeGroup: string
  onGroupChange: (id: string) => void
}) {
  return (
    <div
      className="w-44 shrink-0 border-r border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 flex flex-col"
      aria-label="Asset groups"
    >
      <div className="px-3 py-2 border-b border-gray-200 dark:border-gray-700">
        <span className="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
          Groups
        </span>
      </div>
      <ul className="flex-1 overflow-y-auto py-1" aria-label="Filter by group">
        {groups.map((group) => {
          const isActive = group.id === activeGroup
          return (
            <li key={group.id}>
              <button
                type="button"
                onClick={() => onGroupChange(group.id)}
                aria-pressed={isActive}
                className={[
                  'w-full flex items-center justify-between px-3 py-1.5 text-sm text-left transition-colors',
                  isActive
                    ? 'bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-200 font-medium'
                    : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700/50',
                ].join(' ')}
              >
                <span className="truncate">{group.label}</span>
                <span
                  className={[
                    'ml-2 shrink-0 rounded-full px-1.5 py-0.5 text-xs font-medium',
                    isActive
                      ? 'bg-blue-200 dark:bg-blue-800 text-blue-800 dark:text-blue-200'
                      : 'bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-400',
                  ].join(' ')}
                >
                  {group.count}
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

/** Bottom action bar with Import, Remove, Display buttons */
function AssetBottomBar({
  selectedCount,
  totalCount,
  onImport,
  onRemove,
  onDisplay,
}: {
  selectedCount: number
  totalCount: number
  onImport?: () => void
  onRemove?: () => void
  onDisplay?: () => void
}) {
  const btnBase =
    'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium ' +
    'border border-gray-300 dark:border-gray-600 ' +
    'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 ' +
    'hover:bg-gray-50 dark:hover:bg-gray-700 ' +
    'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 ' +
    'transition-colors'

  const btnDisabled = btnBase + ' opacity-40 cursor-not-allowed pointer-events-none'

  return (
    <div className="flex items-center justify-between px-3 py-2 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50">
      <div className="flex items-center gap-2">
        <button
          type="button"
          className={btnBase}
          onClick={onImport}
          title="Import assets from disk"
        >
          Import
        </button>
        <button
          type="button"
          className={selectedCount === 0 ? btnDisabled : btnBase}
          onClick={onRemove}
          disabled={selectedCount === 0}
          title={selectedCount === 0 ? 'Select items to remove' : `Remove ${selectedCount} selected`}
        >
          Remove
        </button>
        <button
          type="button"
          className={selectedCount === 0 ? btnDisabled : btnBase}
          onClick={onDisplay}
          disabled={selectedCount === 0}
          title={selectedCount === 0 ? 'Select items to display' : `Display ${selectedCount} selected`}
        >
          Display
        </button>
      </div>
      <span className="text-xs text-gray-500 dark:text-gray-400">
        {selectedCount > 0 ? `${selectedCount} of ${totalCount} selected` : `${totalCount} item${totalCount !== 1 ? 's' : ''}`}
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sorting icon helper
// ---------------------------------------------------------------------------

function SortIcon({ state }: { state: false | 'asc' | 'desc' }) {
  if (state === 'asc') {
    return (
      <svg className="w-3 h-3" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
        <path fillRule="evenodd" d="M10 3a.75.75 0 01.55.24l3.25 3.5a.75.75 0 11-1.1 1.02L10 4.852 7.3 7.76a.75.75 0 01-1.1-1.02l3.25-3.5A.75.75 0 0110 3z" clipRule="evenodd" />
      </svg>
    )
  }
  if (state === 'desc') {
    return (
      <svg className="w-3 h-3" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
        <path fillRule="evenodd" d="M10 17a.75.75 0 01-.55-.24l-3.25-3.5a.75.75 0 111.1-1.02L10 15.148l2.7-2.908a.75.75 0 111.1 1.02l-3.25 3.5A.75.75 0 0110 17z" clipRule="evenodd" />
      </svg>
    )
  }
  return (
    <svg className="w-3 h-3 opacity-40" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <path fillRule="evenodd" d="M10 3a.75.75 0 01.55.24l3.25 3.5a.75.75 0 11-1.1 1.02L10 4.852 7.3 7.76a.75.75 0 01-1.1-1.02l3.25-3.5A.75.75 0 0110 3zm-3.806 9.691a.75.75 0 011.06.053L10 15.147l2.747-2.403a.75.75 0 111.012 1.108l-3.25 2.85a.75.75 0 01-1.012 0l-3.25-2.85a.75.75 0 01.053-1.061z" clipRule="evenodd" />
    </svg>
  )
}

// ---------------------------------------------------------------------------
// Generic sortable/filterable table
// ---------------------------------------------------------------------------

interface GenericTableProps<TData extends object> {
  data: TData[]
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  columns: ColumnDef<TData, any>[]
  filterPlaceholder?: string
  onSelectionChange?: (selectedIndices: number[]) => void
}

function GenericTable<TData extends object>({
  data,
  columns,
  filterPlaceholder = 'Filter…',
  onSelectionChange,
}: GenericTableProps<TData>) {
  const [sorting, setSorting] = useState<SortingState>([])
  const [globalFilter, setGlobalFilter] = useState('')
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({})

  const handleRowSelection = useCallback(
    (updater: RowSelectionState | ((old: RowSelectionState) => RowSelectionState)) => {
      setRowSelection((prev) => {
        const next = typeof updater === 'function' ? updater(prev) : updater
        onSelectionChange?.(Object.keys(next).map(Number))
        return next
      })
    },
    [onSelectionChange],
  )

  const table = useReactTable({
    data,
    columns,
    state: { sorting, globalFilter, rowSelection },
    enableRowSelection: true,
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    onRowSelectionChange: handleRowSelection,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  })

  const filteredCount = table.getFilteredRowModel().rows.length

  return (
    <div className="flex flex-col flex-1 min-h-0 space-y-2 p-3">
      {/* Filter input */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <svg
            className="absolute left-2.5 top-2.5 w-4 h-4 text-gray-400 pointer-events-none"
            viewBox="0 0 20 20"
            fill="currentColor"
            aria-hidden="true"
          >
            <path fillRule="evenodd" d="M9 3.5a5.5 5.5 0 100 11 5.5 5.5 0 000-11zM2 9a7 7 0 1112.452 4.391l3.328 3.329a.75.75 0 11-1.06 1.06l-3.329-3.328A7 7 0 012 9z" clipRule="evenodd" />
          </svg>
          <input
            type="text"
            value={globalFilter}
            onChange={(e) => setGlobalFilter(e.target.value)}
            placeholder={filterPlaceholder}
            aria-label={filterPlaceholder}
            className={
              'block w-full rounded-md border border-gray-300 pl-8 pr-3 py-1.5 text-sm shadow-sm ' +
              'focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 ' +
              'dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 ' +
              'placeholder:text-gray-400 dark:placeholder:text-gray-500'
            }
          />
        </div>
        {globalFilter && (
          <span className="text-xs text-gray-500 dark:text-gray-400">
            {filteredCount} of {data.length} shown
          </span>
        )}
      </div>

      {/* Table */}
      <div className="overflow-x-auto overflow-y-auto flex-1 rounded-lg border border-gray-200 dark:border-gray-700 shadow-sm">
        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
          <thead className="bg-gray-50 dark:bg-gray-800 sticky top-0 z-10">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    scope="col"
                    className={[
                      'px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider',
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
                      {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
                      {header.column.getCanSort() && (
                        <span aria-hidden="true" className="text-gray-300 dark:text-gray-600">
                          <SortIcon state={header.column.getIsSorted()} />
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
                  className="px-4 py-10 text-center text-sm text-gray-400 dark:text-gray-500"
                >
                  {globalFilter ? 'No results match your filter.' : 'No data available.'}
                </td>
              </tr>
            ) : (
              table.getRowModel().rows.map((row) => (
                <tr
                  key={row.id}
                  className={[
                    'transition-colors cursor-pointer',
                    row.getIsSelected()
                      ? 'bg-blue-50 dark:bg-blue-900/20'
                      : 'hover:bg-gray-50 dark:hover:bg-gray-800/50',
                  ].join(' ')}
                  onClick={() => row.toggleSelected()}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td
                      key={cell.id}
                      className="px-4 py-2.5 whitespace-nowrap"
                      onClick={
                        cell.column.id === 'select'
                          ? (e) => e.stopPropagation()
                          : undefined
                      }
                    >
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
// Checkbox column helper (shared)
// ---------------------------------------------------------------------------

function makeCheckboxColumn<T>() {
  return {
    id: 'select',
    header: ({ table }: { table: ReturnType<typeof useReactTable<T>> }) => (
      <input
        type="checkbox"
        checked={table.getIsAllPageRowsSelected()}
        ref={(el) => {
          if (el) el.indeterminate = table.getIsSomePageRowsSelected()
        }}
        onChange={table.getToggleAllPageRowsSelectedHandler()}
        aria-label="Select all rows"
        className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800"
      />
    ),
    cell: ({ row }: { row: ReturnType<typeof useReactTable<T>>['getRowModel']['rows'][0] }) => (
      <input
        type="checkbox"
        checked={row.getIsSelected()}
        onChange={row.getToggleSelectedHandler()}
        aria-label="Select row"
        className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800"
      />
    ),
    enableSorting: false,
    size: 40,
  }
}

// ---------------------------------------------------------------------------
// TILT SERIES TAB
// ---------------------------------------------------------------------------

const tiltSeriesColumnHelper = createColumnHelper<TiltSeriesItem>()

function useTiltSeriesColumns() {
  return useMemo(
    () => [
      tiltSeriesColumnHelper.display(makeCheckboxColumn<TiltSeriesItem>()),

      tiltSeriesColumnHelper.accessor('name', {
        header: 'Name',
        cell: (info) => (
          <span className="font-mono text-sm font-medium text-gray-900 dark:text-gray-100">
            {info.getValue()}
          </span>
        ),
        sortingFn: 'alphanumeric',
      }),

      tiltSeriesColumnHelper.accessor(
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
            return order[getTiltSeriesStatus(rowA.original)] - order[getTiltSeriesStatus(rowB.original)]
          },
        },
      ),

      tiltSeriesColumnHelper.accessor('pixel_size', {
        header: 'Pixel Size',
        cell: (info) => {
          const v = info.getValue()
          return v != null ? (
            <span className="text-sm text-gray-700 dark:text-gray-300">{v.toFixed(2)} Å</span>
          ) : (
            <span className="text-xs text-gray-400 dark:text-gray-600 italic">—</span>
          )
        },
        sortingFn: 'basic',
      }),

      tiltSeriesColumnHelper.accessor('tilt_range', {
        header: 'Tilt Range',
        cell: (info) => {
          const v = info.getValue()
          return v ? (
            <span className="text-sm text-gray-700 dark:text-gray-300">{v}</span>
          ) : (
            <span className="text-xs text-gray-400 dark:text-gray-600 italic">—</span>
          )
        },
      }),

      tiltSeriesColumnHelper.accessor('n_views', {
        header: '# Views',
        cell: (info) => {
          const v = info.getValue()
          return v != null ? (
            <span className="text-sm text-gray-700 dark:text-gray-300">{v}</span>
          ) : (
            <span className="text-xs text-gray-400 dark:text-gray-600 italic">—</span>
          )
        },
        sortingFn: 'basic',
      }),
    ],
    [],
  )
}

function useTiltSeriesGroups(items: TiltSeriesItem[]): AssetGroup[] {
  return useMemo(() => {
    const all = items.length
    const aligned = items.filter((i) => i.aligned).length
    const ctfEst = items.filter((i) => i.ctf_estimated).length
    const reconstructed = items.filter((i) => getTiltSeriesStatus(i) === 'reconstructed').length
    return [
      { id: 'all', label: 'All', count: all },
      { id: 'aligned', label: 'Aligned', count: aligned },
      { id: 'ctf-est', label: 'CTF Est.', count: ctfEst },
      { id: 'reconstructed', label: 'Reconstructed', count: reconstructed },
    ]
  }, [items])
}

function filterTiltSeriesByGroup(items: TiltSeriesItem[], groupId: string): TiltSeriesItem[] {
  switch (groupId) {
    case 'aligned':
      return items.filter((i) => i.aligned)
    case 'ctf-est':
      return items.filter((i) => i.ctf_estimated)
    case 'reconstructed':
      return items.filter((i) => getTiltSeriesStatus(i) === 'reconstructed')
    default:
      return items
  }
}

// Batch operations toolbar (preserved from original TiltSeriesPage)
function TiltSeriesBatchBar({
  projectId,
  selectedNames,
  onSuccess,
  onError,
}: {
  projectId: string
  selectedNames: string[]
  onSuccess: (msg: string) => void
  onError: (msg: string) => void
}) {
  const [running, setRunning] = useState<string | null>(null)

  const run = useCallback(
    async (command: string) => {
      setRunning(command)
      try {
        const result = await apiClient.post<RunCommandResponse>(
          `/api/v1/workflow/${projectId}/run`,
          { command, tilt_series: selectedNames },
        )
        onSuccess(result.message || `Command '${command}' started successfully.`)
      } catch (err) {
        onError(
          err instanceof ApiError
            ? `Failed to run '${command}': ${err.statusText}`
            : `Failed to run '${command}'. Please try again.`,
        )
      } finally {
        setRunning(null)
      }
    },
    [projectId, selectedNames, onSuccess, onError],
  )

  const btn =
    'inline-flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium ' +
    'border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 ' +
    'text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors'

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 bg-blue-50 dark:bg-blue-900/20 border-b border-blue-200 dark:border-blue-800">
      <span className="text-xs font-medium text-blue-800 dark:text-blue-300">
        {selectedNames.length} selected — batch:
      </span>
      <button
        type="button"
        className={btn}
        disabled={running !== null}
        onClick={() => run('autoAlign')}
      >
        {running === 'autoAlign' ? 'Running…' : 'autoAlign'}
      </button>
      <button
        type="button"
        className={btn}
        disabled={running !== null}
        onClick={() => run('ctf estimate')}
      >
        {running === 'ctf estimate' ? 'Running…' : 'CTF Estimate'}
      </button>
    </div>
  )
}

interface TiltSeriesTabContentProps {
  projectId: string
  isDemo: boolean
  onSuccess: (msg: string) => void
  onError: (msg: string) => void
}

function TiltSeriesTabContent({ projectId, isDemo, onSuccess, onError }: TiltSeriesTabContentProps) {
  const [activeGroup, setActiveGroup] = useState('all')
  const [selectedNames, setSelectedNames] = useState<string[]>([])

  const { data, isLoading, isError, error, refetch } = useApiQuery<TiltSeriesListResponse>(
    ['tilt-series', projectId],
    `/api/v1/projects/${projectId}/tilt-series`,
  )

  const allItems = data?.tilt_series ?? []
  const groups = useTiltSeriesGroups(allItems)
  const filteredItems = filterTiltSeriesByGroup(allItems, activeGroup)
  const columns = useTiltSeriesColumns()

  const handleSelectionChange = useCallback(
    (indices: number[]) => {
      setSelectedNames(indices.map((i) => filteredItems[i]?.name ?? '').filter(Boolean))
    },
    [filteredItems],
  )

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16 flex-1">
        <svg className="w-6 h-6 animate-spin text-blue-500" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        <span className="ml-3 text-sm text-gray-500">Loading tilt series…</span>
      </div>
    )
  }

  if (isError) {
    const isNotFound = error instanceof ApiError && error.status === 404
    return (
      <div className="m-4 rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 p-4">
        <p className="text-sm font-medium text-red-800 dark:text-red-300">
          {isNotFound ? `Project '${projectId}' not found.` : 'Failed to load tilt series.'}
        </p>
        {!isNotFound && (
          <button type="button" onClick={() => void refetch()} className="mt-2 text-sm text-red-700 dark:text-red-400 underline">
            Retry
          </button>
        )}
      </div>
    )
  }

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {selectedNames.length > 0 && !isDemo && (
        <TiltSeriesBatchBar
          projectId={projectId}
          selectedNames={selectedNames}
          onSuccess={onSuccess}
          onError={onError}
        />
      )}
      <div className="flex flex-1 min-h-0">
        <GroupsSidebar groups={groups} activeGroup={activeGroup} onGroupChange={setActiveGroup} />
        <div className="flex flex-col flex-1 min-h-0">
          <GenericTable
            data={filteredItems}
            columns={columns}
            filterPlaceholder="Filter tilt series…"
            onSelectionChange={handleSelectionChange}
          />
        </div>
      </div>
      <AssetBottomBar
        selectedCount={selectedNames.length}
        totalCount={filteredItems.length}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// CTF DATA TAB
// ---------------------------------------------------------------------------

interface CtfDataItem {
  name: string
  tilt_series: string
  defocus_u: number
  defocus_v: number
  astigmatism_angle: number
  b_factor: number | null
}

const CTF_PLACEHOLDER: CtfDataItem[] = []

const ctfHelper = createColumnHelper<CtfDataItem>()

function CtfDataTabContent() {
  const [activeGroup, setActiveGroup] = useState('all')

  const groups: AssetGroup[] = [
    { id: 'all', label: 'All', count: CTF_PLACEHOLDER.length },
  ]

  const columns = useMemo(
    () => [
      ctfHelper.display(makeCheckboxColumn<CtfDataItem>()),
      ctfHelper.accessor('name', {
        header: 'Name',
        cell: (info) => <span className="font-mono text-sm font-medium text-gray-900 dark:text-gray-100">{info.getValue()}</span>,
      }),
      ctfHelper.accessor('tilt_series', {
        header: 'Tilt Series',
        cell: (info) => <span className="text-sm text-gray-700 dark:text-gray-300">{info.getValue()}</span>,
      }),
      ctfHelper.accessor('defocus_u', {
        header: 'Defocus U (µm)',
        cell: (info) => <span className="text-sm text-gray-700 dark:text-gray-300">{info.getValue()?.toFixed(3)}</span>,
      }),
      ctfHelper.accessor('defocus_v', {
        header: 'Defocus V (µm)',
        cell: (info) => <span className="text-sm text-gray-700 dark:text-gray-300">{info.getValue()?.toFixed(3)}</span>,
      }),
      ctfHelper.accessor('astigmatism_angle', {
        header: 'Astigmatism (°)',
        cell: (info) => <span className="text-sm text-gray-700 dark:text-gray-300">{info.getValue()?.toFixed(1)}</span>,
      }),
      ctfHelper.accessor('b_factor', {
        header: 'B-factor',
        cell: (info) => {
          const v = info.getValue()
          return v != null
            ? <span className="text-sm text-gray-700 dark:text-gray-300">{v.toFixed(1)}</span>
            : <span className="text-xs text-gray-400 italic">—</span>
        },
      }),
    ],
    [],
  )

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <div className="flex flex-1 min-h-0">
        <GroupsSidebar groups={groups} activeGroup={activeGroup} onGroupChange={setActiveGroup} />
        <div className="flex flex-col flex-1 min-h-0">
          <GenericTable data={CTF_PLACEHOLDER} columns={columns} filterPlaceholder="Filter CTF data…" />
        </div>
      </div>
      <AssetBottomBar selectedCount={0} totalCount={CTF_PLACEHOLDER.length} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// TOMOGRAMS TAB
// ---------------------------------------------------------------------------

interface TomogramItem {
  name: string
  tilt_series: string
  bin_factor: number
  dimensions: string
  file_size: string
}

const TOMO_PLACEHOLDER: TomogramItem[] = []

const tomoHelper = createColumnHelper<TomogramItem>()

function TomogramsTabContent() {
  const [activeGroup, setActiveGroup] = useState('all')

  const groups: AssetGroup[] = [
    { id: 'all', label: 'All', count: TOMO_PLACEHOLDER.length },
  ]

  const columns = useMemo(
    () => [
      tomoHelper.display(makeCheckboxColumn<TomogramItem>()),
      tomoHelper.accessor('name', {
        header: 'Name',
        cell: (info) => <span className="font-mono text-sm font-medium text-gray-900 dark:text-gray-100">{info.getValue()}</span>,
      }),
      tomoHelper.accessor('tilt_series', {
        header: 'Tilt Series',
        cell: (info) => <span className="text-sm text-gray-700 dark:text-gray-300">{info.getValue()}</span>,
      }),
      tomoHelper.accessor('bin_factor', {
        header: 'Bin Factor',
        cell: (info) => <span className="text-sm text-gray-700 dark:text-gray-300">{info.getValue()}</span>,
      }),
      tomoHelper.accessor('dimensions', {
        header: 'Dimensions',
        cell: (info) => <span className="text-sm text-gray-700 dark:text-gray-300">{info.getValue()}</span>,
      }),
      tomoHelper.accessor('file_size', {
        header: 'File Size',
        cell: (info) => <span className="text-sm text-gray-700 dark:text-gray-300">{info.getValue()}</span>,
      }),
    ],
    [],
  )

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <div className="flex flex-1 min-h-0">
        <GroupsSidebar groups={groups} activeGroup={activeGroup} onGroupChange={setActiveGroup} />
        <div className="flex flex-col flex-1 min-h-0">
          <GenericTable data={TOMO_PLACEHOLDER} columns={columns} filterPlaceholder="Filter tomograms…" />
        </div>
      </div>
      <AssetBottomBar selectedCount={0} totalCount={TOMO_PLACEHOLDER.length} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// PARTICLE POSITIONS TAB
// ---------------------------------------------------------------------------

interface ParticlePositionItem {
  name: string
  tilt_series: string
  n_particles: number
  template: string
  score_threshold: number
}

const PARTICLES_PLACEHOLDER: ParticlePositionItem[] = []

const particlesHelper = createColumnHelper<ParticlePositionItem>()

function ParticlePositionsTabContent() {
  const [activeGroup, setActiveGroup] = useState('all')

  const groups: AssetGroup[] = [
    { id: 'all', label: 'All', count: PARTICLES_PLACEHOLDER.length },
  ]

  const columns = useMemo(
    () => [
      particlesHelper.display(makeCheckboxColumn<ParticlePositionItem>()),
      particlesHelper.accessor('name', {
        header: 'Name',
        cell: (info) => <span className="font-mono text-sm font-medium text-gray-900 dark:text-gray-100">{info.getValue()}</span>,
      }),
      particlesHelper.accessor('tilt_series', {
        header: 'Tilt Series',
        cell: (info) => <span className="text-sm text-gray-700 dark:text-gray-300">{info.getValue()}</span>,
      }),
      particlesHelper.accessor('n_particles', {
        header: '# Particles',
        cell: (info) => <span className="text-sm text-gray-700 dark:text-gray-300">{info.getValue()?.toLocaleString()}</span>,
      }),
      particlesHelper.accessor('template', {
        header: 'Template',
        cell: (info) => <span className="text-sm text-gray-700 dark:text-gray-300">{info.getValue()}</span>,
      }),
      particlesHelper.accessor('score_threshold', {
        header: 'Score Threshold',
        cell: (info) => <span className="text-sm text-gray-700 dark:text-gray-300">{info.getValue()?.toFixed(3)}</span>,
      }),
    ],
    [],
  )

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <div className="flex flex-1 min-h-0">
        <GroupsSidebar groups={groups} activeGroup={activeGroup} onGroupChange={setActiveGroup} />
        <div className="flex flex-col flex-1 min-h-0">
          <GenericTable data={PARTICLES_PLACEHOLDER} columns={columns} filterPlaceholder="Filter particle positions…" />
        </div>
      </div>
      <AssetBottomBar selectedCount={0} totalCount={PARTICLES_PLACEHOLDER.length} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// REFERENCE VOLUMES TAB
// ---------------------------------------------------------------------------

interface ReferenceVolumeItem {
  name: string
  cycle: number
  half_map_odd: string
  half_map_even: string
  pixel_size: number
  box_size: number
}

const REFS_PLACEHOLDER: ReferenceVolumeItem[] = []

const refsHelper = createColumnHelper<ReferenceVolumeItem>()

function ReferenceVolumesTabContent() {
  const [activeGroup, setActiveGroup] = useState('all')

  const groups: AssetGroup[] = [
    { id: 'all', label: 'All', count: REFS_PLACEHOLDER.length },
  ]

  const columns = useMemo(
    () => [
      refsHelper.display(makeCheckboxColumn<ReferenceVolumeItem>()),
      refsHelper.accessor('name', {
        header: 'Name',
        cell: (info) => <span className="font-mono text-sm font-medium text-gray-900 dark:text-gray-100">{info.getValue()}</span>,
      }),
      refsHelper.accessor('cycle', {
        header: 'Cycle',
        cell: (info) => <span className="text-sm text-gray-700 dark:text-gray-300">{info.getValue()}</span>,
      }),
      refsHelper.accessor('half_map_odd', {
        header: 'Half-map (ODD)',
        cell: (info) => <span className="font-mono text-xs text-gray-600 dark:text-gray-400 truncate max-w-xs block" title={info.getValue()}>{info.getValue()}</span>,
      }),
      refsHelper.accessor('half_map_even', {
        header: 'Half-map (EVE)',
        cell: (info) => <span className="font-mono text-xs text-gray-600 dark:text-gray-400 truncate max-w-xs block" title={info.getValue()}>{info.getValue()}</span>,
      }),
      refsHelper.accessor('pixel_size', {
        header: 'Pixel Size',
        cell: (info) => <span className="text-sm text-gray-700 dark:text-gray-300">{info.getValue()?.toFixed(2)} Å</span>,
      }),
      refsHelper.accessor('box_size', {
        header: 'Box Size',
        cell: (info) => <span className="text-sm text-gray-700 dark:text-gray-300">{info.getValue()} px</span>,
      }),
    ],
    [],
  )

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <div className="flex flex-1 min-h-0">
        <GroupsSidebar groups={groups} activeGroup={activeGroup} onGroupChange={setActiveGroup} />
        <div className="flex flex-col flex-1 min-h-0">
          <GenericTable data={REFS_PLACEHOLDER} columns={columns} filterPlaceholder="Filter reference volumes…" />
        </div>
      </div>
      <AssetBottomBar selectedCount={0} totalCount={REFS_PLACEHOLDER.length} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// FSC CURVES TAB
// ---------------------------------------------------------------------------

interface FscCurveItem {
  name: string
  cycle: number
  resolution_a: number
  n_particles: number
  mask_type: string
}

const FSC_PLACEHOLDER: FscCurveItem[] = []

const fscHelper = createColumnHelper<FscCurveItem>()

function FscCurvesTabContent() {
  const [activeGroup, setActiveGroup] = useState('all')

  const groups: AssetGroup[] = [
    { id: 'all', label: 'All', count: FSC_PLACEHOLDER.length },
  ]

  const columns = useMemo(
    () => [
      fscHelper.display(makeCheckboxColumn<FscCurveItem>()),
      fscHelper.accessor('name', {
        header: 'Name',
        cell: (info) => <span className="font-mono text-sm font-medium text-gray-900 dark:text-gray-100">{info.getValue()}</span>,
      }),
      fscHelper.accessor('cycle', {
        header: 'Cycle',
        cell: (info) => <span className="text-sm text-gray-700 dark:text-gray-300">{info.getValue()}</span>,
      }),
      fscHelper.accessor('resolution_a', {
        header: 'Resolution (Å)',
        cell: (info) => <span className="text-sm text-gray-700 dark:text-gray-300">{info.getValue()?.toFixed(2)}</span>,
      }),
      fscHelper.accessor('n_particles', {
        header: '# Particles',
        cell: (info) => <span className="text-sm text-gray-700 dark:text-gray-300">{info.getValue()?.toLocaleString()}</span>,
      }),
      fscHelper.accessor('mask_type', {
        header: 'Mask Type',
        cell: (info) => <span className="text-sm text-gray-700 dark:text-gray-300">{info.getValue()}</span>,
      }),
    ],
    [],
  )

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <div className="flex flex-1 min-h-0">
        <GroupsSidebar groups={groups} activeGroup={activeGroup} onGroupChange={setActiveGroup} />
        <div className="flex flex-col flex-1 min-h-0">
          <GenericTable data={FSC_PLACEHOLDER} columns={columns} filterPlaceholder="Filter FSC curves…" />
        </div>
      </div>
      <AssetBottomBar selectedCount={0} totalCount={FSC_PLACEHOLDER.length} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tab bar
// ---------------------------------------------------------------------------

function AssetTabBar({
  tabs,
  activeTab,
  onTabChange,
}: {
  tabs: AssetTab[]
  activeTab: AssetTabId
  onTabChange: (id: AssetTabId) => void
}) {
  return (
    <div
      className="flex border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-2 shrink-0"
      role="tablist"
      aria-label="Asset types"
    >
      {tabs.map((tab) => {
        const isActive = tab.id === activeTab
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={isActive}
            aria-controls={`tabpanel-${tab.id}`}
            id={`tab-${tab.id}`}
            onClick={() => onTabChange(tab.id)}
            className={[
              'relative px-4 py-2.5 text-sm font-medium whitespace-nowrap transition-colors',
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1',
              isActive
                ? 'text-blue-700 dark:text-blue-400 border-b-2 border-blue-600 dark:border-blue-400 -mb-px'
                : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 border-b-2 border-transparent',
            ].join(' ')}
          >
            {tab.label}
          </button>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Notification banner
// ---------------------------------------------------------------------------

function NotificationBanner({
  notification,
  onDismiss,
}: {
  notification: { type: 'success' | 'error'; message: string } | null
  onDismiss: () => void
}) {
  if (!notification) return null
  return (
    <div
      role="alert"
      className={[
        'mx-4 mt-3 rounded-lg border px-4 py-3 text-sm flex items-center justify-between gap-3 shrink-0',
        notification.type === 'success'
          ? 'border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/20 text-green-800 dark:text-green-300'
          : 'border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 text-red-800 dark:text-red-300',
      ].join(' ')}
    >
      <span>{notification.message}</span>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss"
        className="shrink-0 opacity-70 hover:opacity-100"
      >
        <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
        </svg>
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// AssetsPage — exported page component
// ---------------------------------------------------------------------------

export function AssetsPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const isDemo = projectId === DEMO_PROJECT_ID
  const [activeTab, setActiveTab] = useState<AssetTabId>('tilt-series')
  const [notification, setNotification] = useState<{ type: 'success' | 'error'; message: string } | null>(null)
  const notificationTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      if (notificationTimerRef.current !== null) clearTimeout(notificationTimerRef.current)
    }
  }, [])

  const handleSuccess = useCallback((message: string) => {
    if (notificationTimerRef.current !== null) clearTimeout(notificationTimerRef.current)
    setNotification({ type: 'success', message })
    notificationTimerRef.current = setTimeout(() => {
      notificationTimerRef.current = null
      setNotification(null)
    }, 5000)
  }, [])

  const handleError = useCallback((message: string) => {
    if (notificationTimerRef.current !== null) clearTimeout(notificationTimerRef.current)
    setNotification({ type: 'error', message })
    notificationTimerRef.current = setTimeout(() => {
      notificationTimerRef.current = null
      setNotification(null)
    }, 8000)
  }, [])

  if (!projectId) {
    return <Navigate to="/" replace />
  }

  const activeTabMeta = ASSET_TABS.find((t) => t.id === activeTab)!

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Page header */}
      <div className="px-6 pt-6 pb-3 shrink-0">
        <h2 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">Assets</h2>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          {activeTabMeta.description}
        </p>
      </div>

      {/* Notification */}
      <NotificationBanner notification={notification} onDismiss={() => setNotification(null)} />

      {/* Tab bar + panel */}
      <div
        className="mx-6 mb-6 mt-3 flex flex-col flex-1 min-h-0 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-sm overflow-hidden"
      >
        <AssetTabBar tabs={ASSET_TABS} activeTab={activeTab} onTabChange={setActiveTab} />

        {/* Tab panel */}
        <div
          role="tabpanel"
          id={`tabpanel-${activeTab}`}
          aria-labelledby={`tab-${activeTab}`}
          className="flex flex-col flex-1 min-h-0"
        >
          {activeTab === 'tilt-series' && (
            <TiltSeriesTabContent
              projectId={projectId}
              isDemo={isDemo}
              onSuccess={handleSuccess}
              onError={handleError}
            />
          )}
          {activeTab === 'ctf-data' && <CtfDataTabContent />}
          {activeTab === 'tomograms' && <TomogramsTabContent />}
          {activeTab === 'particle-positions' && <ParticlePositionsTabContent />}
          {activeTab === 'reference-volumes' && <ReferenceVolumesTabContent />}
          {activeTab === 'fsc-curves' && <FscCurvesTabContent />}
        </div>
      </div>
    </div>
  )
}
