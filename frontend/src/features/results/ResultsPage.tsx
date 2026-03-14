/**
 * Results viewer page.
 *
 * Displays:
 *   1. FSC (Fourier Shell Correlation) curve with 0.143 gold-standard threshold
 *   2. Particle statistics: count, class distribution, CCC score histogram
 *   3. System info panel: CPU, RAM, GPU status
 *
 * API calls:
 *   GET /api/v1/results/fsc          – FSC curve data (returns 404 if not available)
 *   GET /api/v1/results/particles    – Particle statistics (returns 404 if not available)
 *   GET /api/v1/system/info          – System hardware information
 */

import { useState, useEffect, useCallback } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  BarChart,
  Bar,
} from 'recharts'
import { apiClient, ApiError } from '@/api/client.ts'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface GpuInfo {
  index: number
  name: string
  memory_total_mb: number
  memory_used_mb: number
  memory_free_mb: number
  driver_version: string
  cuda_version: string
}

interface SystemInfo {
  cpu_count: number
  cpu_count_physical: number
  memory_total_gb: number
  memory_available_gb: number
  hostname: string
  gpus: GpuInfo[]
}

interface FscPoint {
  /** Spatial frequency in 1/Å */
  spatial_frequency: number
  /** FSC value between 0.0 and 1.0 */
  fsc: number
}

interface FscData {
  /** FSC curve between the two half-datasets */
  half1_half2: FscPoint[]
  /** Estimated resolution in Ångströms at the 0.143 criterion */
  resolution_angstroms: number | null
}

interface ClassCount {
  class_label: string
  count: number
}

interface CccBin {
  bin_center: number
  count: number
}

interface ParticleStats {
  total_count: number
  class_distribution: ClassCount[]
  ccc_histogram: CccBin[]
  mean_ccc: number | null
}

// ---------------------------------------------------------------------------
// Fetch helpers
// ---------------------------------------------------------------------------

type FetchState<T> =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'not_available' }
  | { status: 'error'; message: string }
  | { status: 'success'; data: T }

// ---------------------------------------------------------------------------
// FSC Curve Section
// ---------------------------------------------------------------------------

const FSC_THRESHOLD = 0.143
const FSC_THRESHOLD_LABEL = '0.143 criterion'

interface FscChartProps {
  data: FscPoint[]
  resolutionAngstroms: number | null
}

function FscChart({ data, resolutionAngstroms }: FscChartProps) {
  // Format spatial frequency as resolution in Å for tooltip
  const formatFrequency = (value: number): string => {
    if (value === 0) return '∞'
    return `${(1 / value).toFixed(1)} Å`
  }

  const formatFsc = (value: number): string => value.toFixed(3)

  return (
    <div className="space-y-3">
      {resolutionAngstroms !== null && (
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-600 dark:text-gray-400">Estimated resolution:</span>
          <span className="text-sm font-semibold text-blue-600 dark:text-blue-400">
            {resolutionAngstroms.toFixed(2)} Å
          </span>
          <span className="text-xs text-gray-400 dark:text-gray-500">(at FSC = 0.143)</span>
        </div>
      )}
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 24, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
          <XAxis
            dataKey="spatial_frequency"
            tickFormatter={formatFrequency}
            label={{
              value: 'Resolution (Å)',
              position: 'insideBottom',
              offset: -16,
              style: { fontSize: 12, fill: 'currentColor' },
            }}
            tick={{ fontSize: 11 }}
          />
          <YAxis
            domain={[0, 1]}
            tickFormatter={formatFsc}
            label={{
              value: 'FSC',
              angle: -90,
              position: 'insideLeft',
              style: { fontSize: 12, fill: 'currentColor' },
            }}
            tick={{ fontSize: 11 }}
          />
          <Tooltip
            formatter={(value, name) => [
              typeof value === 'number' ? formatFsc(value) : '',
              String(name),
            ]}
            labelFormatter={(label) =>
              typeof label === 'number' ? `Resolution: ${formatFrequency(label)}` : String(label)
            }
            contentStyle={{ fontSize: 12 }}
          />
          <Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
          {/* Gold-standard 0.143 threshold line */}
          <ReferenceLine
            y={FSC_THRESHOLD}
            stroke="#f59e0b"
            strokeDasharray="6 3"
            strokeWidth={2}
            label={{
              value: FSC_THRESHOLD_LABEL,
              position: 'right',
              style: { fontSize: 11, fill: '#f59e0b' },
            }}
          />
          <Line
            type="monotone"
            dataKey="fsc"
            name="FSC (half1 / half2)"
            stroke="#3b82f6"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

function FscSection() {
  const [state, setState] = useState<FetchState<FscData>>({ status: 'loading' })

  const fetchFsc = useCallback(async () => {
    setState({ status: 'loading' })
    try {
      const data = await apiClient.get<FscData>('/api/v1/results/fsc')
      setState({ status: 'success', data })
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setState({ status: 'not_available' })
      } else {
        const message =
          err instanceof ApiError
            ? `Failed to load FSC data (${err.status}): ${err.statusText}`
            : 'Failed to load FSC data.'
        setState({ status: 'error', message })
      }
    }
  }, [])

  useEffect(() => {
    void fetchFsc()
  }, [fetchFsc])

  return (
    <section
      className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-sm overflow-hidden"
      aria-labelledby="fsc-heading"
    >
      <div className="px-5 py-4 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
        <div>
          <h3 id="fsc-heading" className="text-base font-semibold text-gray-900 dark:text-gray-100">
            FSC Curve
          </h3>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            Fourier Shell Correlation between independent half-datasets
          </p>
        </div>
        <button
          type="button"
          onClick={() => void fetchFsc()}
          disabled={state.status === 'loading'}
          aria-label="Refresh FSC data"
          className={
            'inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium ' +
            'border border-gray-300 dark:border-gray-600 ' +
            'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 ' +
            'hover:bg-gray-50 dark:hover:bg-gray-700 ' +
            'focus:outline-none focus:ring-2 focus:ring-blue-500 ' +
            'transition-colors disabled:opacity-50'
          }
        >
          <svg
            className={`w-3.5 h-3.5 ${state.status === 'loading' ? 'animate-spin' : ''}`}
            viewBox="0 0 20 20"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fillRule="evenodd"
              d="M15.312 11.424a5.5 5.5 0 01-9.201 2.466l-.312-.311h2.433a.75.75 0 000-1.5H3.989a.75.75 0 00-.75.75v4.242a.75.75 0 001.5 0v-2.43l.31.31a7 7 0 0011.712-3.138.75.75 0 00-1.449-.39zm1.23-3.723a.75.75 0 00.219-.53V2.929a.75.75 0 00-1.5 0V5.36l-.31-.31A7 7 0 003.239 8.188a.75.75 0 101.448.389A5.5 5.5 0 0113.89 6.11l.311.31h-2.432a.75.75 0 000 1.5h4.243a.75.75 0 00.53-.219z"
              clipRule="evenodd"
            />
          </svg>
          Refresh
        </button>
      </div>

      <div className="p-5">
        {state.status === 'loading' && (
          <div className="flex items-center justify-center py-12">
            <svg
              className="w-5 h-5 animate-spin text-blue-500"
              viewBox="0 0 24 24"
              fill="none"
              aria-hidden="true"
            >
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <span className="ml-2 text-sm text-gray-500 dark:text-gray-400">Loading FSC data…</span>
          </div>
        )}

        {state.status === 'not_available' && (
          <FscPlaceholder />
        )}

        {state.status === 'error' && (
          <div className="rounded-md bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 p-4">
            <p className="text-sm text-red-700 dark:text-red-400">{state.message}</p>
            <button
              type="button"
              onClick={() => void fetchFsc()}
              className="mt-2 text-sm text-red-600 dark:text-red-400 underline hover:no-underline"
            >
              Retry
            </button>
          </div>
        )}

        {state.status === 'success' && (
          <FscChart
            data={state.data.half1_half2}
            resolutionAngstroms={state.data.resolution_angstroms}
          />
        )}
      </div>
    </section>
  )
}

function FscPlaceholder() {
  return (
    <div className="flex flex-col items-center justify-center py-14 text-center">
      <svg
        className="w-12 h-12 text-gray-300 dark:text-gray-600 mb-3"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z"
        />
      </svg>
      <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">
        No FSC data available
      </h4>
      <p className="text-sm text-gray-500 dark:text-gray-400 max-w-xs">
        FSC curves will appear here after running the <code className="font-mono text-xs">avg</code> step in the
        workflow. The 0.143 gold-standard threshold will be shown on the plot.
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Particle Statistics Section
// ---------------------------------------------------------------------------

function ParticleStatsSection() {
  const [state, setState] = useState<FetchState<ParticleStats>>({ status: 'loading' })

  const fetchStats = useCallback(async () => {
    setState({ status: 'loading' })
    try {
      const data = await apiClient.get<ParticleStats>('/api/v1/results/particles')
      setState({ status: 'success', data })
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setState({ status: 'not_available' })
      } else {
        const message =
          err instanceof ApiError
            ? `Failed to load particle statistics (${err.status}): ${err.statusText}`
            : 'Failed to load particle statistics.'
        setState({ status: 'error', message })
      }
    }
  }, [])

  useEffect(() => {
    void fetchStats()
  }, [fetchStats])

  return (
    <section
      className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-sm overflow-hidden"
      aria-labelledby="particle-stats-heading"
    >
      <div className="px-5 py-4 border-b border-gray-200 dark:border-gray-700">
        <h3
          id="particle-stats-heading"
          className="text-base font-semibold text-gray-900 dark:text-gray-100"
        >
          Particle Statistics
        </h3>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
          Particle counts, class distribution, and cross-correlation scores
        </p>
      </div>

      <div className="p-5">
        {state.status === 'loading' && (
          <div className="flex items-center justify-center py-12">
            <svg
              className="w-5 h-5 animate-spin text-blue-500"
              viewBox="0 0 24 24"
              fill="none"
              aria-hidden="true"
            >
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <span className="ml-2 text-sm text-gray-500 dark:text-gray-400">
              Loading particle statistics…
            </span>
          </div>
        )}

        {state.status === 'not_available' && <ParticleStatsPlaceholder />}

        {state.status === 'error' && (
          <div className="rounded-md bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 p-4">
            <p className="text-sm text-red-700 dark:text-red-400">{state.message}</p>
            <button
              type="button"
              onClick={() => void fetchStats()}
              className="mt-2 text-sm text-red-600 dark:text-red-400 underline hover:no-underline"
            >
              Retry
            </button>
          </div>
        )}

        {state.status === 'success' && <ParticleStatsContent stats={state.data} />}
      </div>
    </section>
  )
}

function ParticleStatsContent({ stats }: { stats: ParticleStats }) {
  return (
    <div className="space-y-6">
      {/* Summary stat cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
        <StatCard
          label="Total Particles"
          value={stats.total_count.toLocaleString()}
        />
        <StatCard
          label="Classes"
          value={stats.class_distribution.length.toString()}
        />
        {stats.mean_ccc !== null && (
          <StatCard
            label="Mean CCC Score"
            value={stats.mean_ccc.toFixed(4)}
          />
        )}
      </div>

      {/* Class distribution chart */}
      {stats.class_distribution.length > 0 && (
        <div>
          <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
            Class Distribution
          </h4>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart
              data={stats.class_distribution}
              margin={{ top: 4, right: 16, bottom: 8, left: 8 }}
            >
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
              <XAxis dataKey="class_label" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip contentStyle={{ fontSize: 12 }} />
              <Bar dataKey="count" name="Particles" fill="#3b82f6" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* CCC score histogram */}
      {stats.ccc_histogram.length > 0 && (
        <div>
          <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
            CCC Score Histogram
          </h4>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart
              data={stats.ccc_histogram}
              margin={{ top: 4, right: 16, bottom: 8, left: 8 }}
            >
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
              <XAxis
                dataKey="bin_center"
                tickFormatter={(v: number) => v.toFixed(2)}
                tick={{ fontSize: 11 }}
                label={{
                  value: 'CCC Score',
                  position: 'insideBottom',
                  offset: -4,
                  style: { fontSize: 11, fill: 'currentColor' },
                }}
              />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip
                formatter={(value) => [typeof value === 'number' ? value : 0, 'Particles']}
                labelFormatter={(label) =>
                  typeof label === 'number' ? `CCC: ${label.toFixed(3)}` : String(label)
                }
                contentStyle={{ fontSize: 12 }}
              />
              <Bar dataKey="count" name="Particles" fill="#10b981" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

function ParticleStatsPlaceholder() {
  return (
    <div className="flex flex-col items-center justify-center py-14 text-center">
      <svg
        className="w-12 h-12 text-gray-300 dark:text-gray-600 mb-3"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25"
        />
      </svg>
      <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">
        No particle statistics available
      </h4>
      <p className="text-sm text-gray-500 dark:text-gray-400 max-w-xs">
        Particle statistics will appear here after running particle alignment (
        <code className="font-mono text-xs">alignRaw</code>) or averaging (
        <code className="font-mono text-xs">avg</code>).
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// System Info Section
// ---------------------------------------------------------------------------

function SystemInfoSection() {
  const [state, setState] = useState<FetchState<SystemInfo>>({ status: 'loading' })

  const fetchSystemInfo = useCallback(async () => {
    setState({ status: 'loading' })
    try {
      const data = await apiClient.get<SystemInfo>('/api/v1/system/info')
      setState({ status: 'success', data })
    } catch (err) {
      const message =
        err instanceof ApiError
          ? `Failed to load system information (${err.status}): ${err.statusText}`
          : 'Failed to load system information.'
      setState({ status: 'error', message })
    }
  }, [])

  useEffect(() => {
    void fetchSystemInfo()
  }, [fetchSystemInfo])

  return (
    <section
      className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-sm overflow-hidden"
      aria-labelledby="system-info-heading"
    >
      <div className="px-5 py-4 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
        <div>
          <h3
            id="system-info-heading"
            className="text-base font-semibold text-gray-900 dark:text-gray-100"
          >
            System Info
          </h3>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            CPU, memory, and GPU availability
          </p>
        </div>
        <button
          type="button"
          onClick={() => void fetchSystemInfo()}
          disabled={state.status === 'loading'}
          aria-label="Refresh system info"
          className={
            'inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium ' +
            'border border-gray-300 dark:border-gray-600 ' +
            'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 ' +
            'hover:bg-gray-50 dark:hover:bg-gray-700 ' +
            'focus:outline-none focus:ring-2 focus:ring-blue-500 ' +
            'transition-colors disabled:opacity-50'
          }
        >
          <svg
            className={`w-3.5 h-3.5 ${state.status === 'loading' ? 'animate-spin' : ''}`}
            viewBox="0 0 20 20"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fillRule="evenodd"
              d="M15.312 11.424a5.5 5.5 0 01-9.201 2.466l-.312-.311h2.433a.75.75 0 000-1.5H3.989a.75.75 0 00-.75.75v4.242a.75.75 0 001.5 0v-2.43l.31.31a7 7 0 0011.712-3.138.75.75 0 00-1.449-.39zm1.23-3.723a.75.75 0 00.219-.53V2.929a.75.75 0 00-1.5 0V5.36l-.31-.31A7 7 0 003.239 8.188a.75.75 0 101.448.389A5.5 5.5 0 0113.89 6.11l.311.31h-2.432a.75.75 0 000 1.5h4.243a.75.75 0 00.53-.219z"
              clipRule="evenodd"
            />
          </svg>
          Refresh
        </button>
      </div>

      <div className="p-5">
        {state.status === 'loading' && (
          <div className="flex items-center justify-center py-8">
            <svg
              className="w-5 h-5 animate-spin text-blue-500"
              viewBox="0 0 24 24"
              fill="none"
              aria-hidden="true"
            >
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <span className="ml-2 text-sm text-gray-500 dark:text-gray-400">
              Loading system info…
            </span>
          </div>
        )}

        {state.status === 'error' && (
          <div className="rounded-md bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 p-4">
            <p className="text-sm text-red-700 dark:text-red-400">{state.message}</p>
            <button
              type="button"
              onClick={() => void fetchSystemInfo()}
              className="mt-2 text-sm text-red-600 dark:text-red-400 underline hover:no-underline"
            >
              Retry
            </button>
          </div>
        )}

        {state.status === 'success' && <SystemInfoContent info={state.data} />}
      </div>
    </section>
  )
}

function SystemInfoContent({ info }: { info: SystemInfo }) {
  const hasGpus = info.gpus.length > 0

  return (
    <div className="space-y-5">
      {/* Host */}
      {info.hostname && (
        <div className="flex items-center gap-2">
          <svg
            className="w-4 h-4 text-gray-400 dark:text-gray-500 shrink-0"
            viewBox="0 0 20 20"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fillRule="evenodd"
              d="M2 5a2 2 0 012-2h12a2 2 0 012 2v10a2 2 0 01-2 2H4a2 2 0 01-2-2V5zm3.293 1.293a1 1 0 011.414 0l3 3a1 1 0 010 1.414l-3 3a1 1 0 01-1.414-1.414L7.586 10 5.293 7.707a1 1 0 010-1.414zM11 12a1 1 0 100 2h3a1 1 0 100-2h-3z"
              clipRule="evenodd"
            />
          </svg>
          <span className="text-sm text-gray-600 dark:text-gray-400">Host:</span>
          <span className="text-sm font-mono font-medium text-gray-900 dark:text-gray-100">
            {info.hostname}
          </span>
        </div>
      )}

      {/* CPU + RAM summary */}
      <div className="grid grid-cols-2 gap-4">
        <StatCard
          label="CPU Cores"
          value={`${info.cpu_count_physical} / ${info.cpu_count}`}
          sub="physical / logical"
        />
        <StatCard
          label="System RAM"
          value={`${info.memory_total_gb.toFixed(0)} GB`}
          sub={`${info.memory_available_gb.toFixed(0)} GB available`}
        />
      </div>

      {/* GPU section */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300">GPUs</h4>
          {hasGpus ? (
            <span
              className={
                'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ' +
                'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
              }
            >
              {info.gpus.length} detected
            </span>
          ) : (
            <span
              className={
                'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ' +
                'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400'
              }
            >
              None detected
            </span>
          )}
        </div>

        {hasGpus ? (
          <div className="space-y-3">
            {info.gpus.map((gpu) => (
              <GpuCard key={gpu.index} gpu={gpu} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 rounded-md px-4 py-3 border border-amber-200 dark:border-amber-800">
            No NVIDIA GPU detected. emClarity requires a CUDA-capable GPU for processing.
            Ensure the NVIDIA driver and <code className="font-mono text-xs">nvidia-smi</code> are
            installed.
          </p>
        )}
      </div>
    </div>
  )
}

function GpuCard({ gpu }: { gpu: GpuInfo }) {
  const usedPercent = gpu.memory_total_mb > 0
    ? Math.round((gpu.memory_used_mb / gpu.memory_total_mb) * 100)
    : 0

  const formatMb = (mb: number): string => {
    if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`
    return `${mb} MB`
  }

  return (
    <div className="rounded-md border border-gray-200 dark:border-gray-700 p-3 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span
            className={
              'shrink-0 inline-flex items-center rounded px-1.5 py-0.5 text-xs font-mono font-medium ' +
              'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400'
            }
          >
            GPU {gpu.index}
          </span>
          <span className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
            {gpu.name}
          </span>
        </div>
        {gpu.cuda_version && (
          <span className="text-xs text-gray-500 dark:text-gray-400 shrink-0">
            CUDA {gpu.cuda_version}
          </span>
        )}
      </div>

      {/* Memory bar */}
      <div>
        <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400 mb-1">
          <span>VRAM</span>
          <span>
            {formatMb(gpu.memory_used_mb)} / {formatMb(gpu.memory_total_mb)} ({usedPercent}%)
          </span>
        </div>
        <div className="h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${
              usedPercent > 80
                ? 'bg-red-500'
                : usedPercent > 60
                ? 'bg-amber-500'
                : 'bg-blue-500'
            }`}
            style={{ width: `${usedPercent}%` }}
            aria-label={`GPU ${gpu.index} memory: ${usedPercent}% used`}
          />
        </div>
      </div>

      {gpu.driver_version && (
        <p className="text-xs text-gray-400 dark:text-gray-500">
          Driver: {gpu.driver_version}
        </p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Shared StatCard component
// ---------------------------------------------------------------------------

interface StatCardProps {
  label: string
  value: string
  sub?: string
}

function StatCard({ label, value, sub }: StatCardProps) {
  return (
    <div className="rounded-md bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 px-4 py-3">
      <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
        {label}
      </p>
      <p className="mt-1 text-xl font-semibold text-gray-900 dark:text-gray-100">{value}</p>
      {sub && (
        <p className="mt-0.5 text-xs text-gray-400 dark:text-gray-500">{sub}</p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// ResultsPage – exported page component
// ---------------------------------------------------------------------------

export function ResultsPage() {
  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h2 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">Results</h2>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          View FSC curves, resolution metrics, particle statistics, and system status.
        </p>
      </div>

      {/* Main content: 2-column layout on large screens */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left column: FSC curve (spans 2 cols) */}
        <div className="lg:col-span-2">
          <FscSection />
        </div>

        {/* Right column: System info */}
        <div className="lg:col-span-1">
          <SystemInfoSection />
        </div>
      </div>

      {/* Particle statistics (full width) */}
      <ParticleStatsSection />
    </div>
  )
}
