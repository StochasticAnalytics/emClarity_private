/**
 * Job monitor page.
 *
 * Displays running, completed, and failed processing jobs in a table with
 * real-time auto-refresh. Selecting a job opens a log viewer panel below
 * the table. Running jobs can be cancelled via the DELETE endpoint.
 *
 * API calls:
 *   GET    /api/v1/jobs            – list all jobs (auto-refreshed every 5s)
 *   GET    /api/v1/jobs/{id}/log   – fetch log output for the selected job
 *   DELETE /api/v1/jobs/{id}       – cancel a running job
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { apiClient, ApiError } from '@/api/client.ts'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Status values as returned by the v1 backend (uppercase). */
type JobStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED'

interface JobV1 {
  id: string
  project_id: string
  command: string
  status: JobStatus
  created_at: string
  updated_at: string
  pid: number | null
  exit_code: number | null
  error_message: string | null
  log_path: string | null
}

interface JobLogResponse {
  job_id: string
  log: string
}

// ---------------------------------------------------------------------------
// Status badge configuration
// ---------------------------------------------------------------------------

interface BadgeConfig {
  label: string
  className: string
}

const STATUS_BADGE: Record<JobStatus, BadgeConfig> = {
  PENDING: {
    label: 'Pending',
    className:
      'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ' +
      'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300',
  },
  RUNNING: {
    label: 'Running',
    className:
      'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ' +
      'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300',
  },
  COMPLETED: {
    label: 'Completed',
    className:
      'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ' +
      'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
  },
  FAILED: {
    label: 'Failed',
    className:
      'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ' +
      'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
  },
  CANCELLED: {
    label: 'Cancelled',
    className:
      'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ' +
      'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400',
  },
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Format an ISO-8601 datetime string to a human-readable local time.
 * Returns '—' for null/empty values.
 */
function formatDateTime(iso: string | null): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: 'short',
      timeStyle: 'medium',
    })
  } catch {
    return iso
  }
}

/**
 * Compute the duration between two ISO timestamps (or from start to now).
 * Returns a human-readable string such as "1m 23s" or '—'.
 */
function computeDuration(startIso: string | null, endIso: string | null): string {
  if (!startIso) return '—'
  const start = new Date(startIso).getTime()
  const end = endIso ? new Date(endIso).getTime() : Date.now()
  const totalSeconds = Math.max(0, Math.floor((end - start) / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  if (minutes === 0) return `${seconds}s`
  return `${minutes}m ${seconds}s`
}

// ---------------------------------------------------------------------------
// StatusBadge component
// ---------------------------------------------------------------------------

function StatusBadge({ status }: { status: JobStatus }) {
  const config = STATUS_BADGE[status] ?? STATUS_BADGE['PENDING']
  return <span className={config.className}>{config.label}</span>
}

// ---------------------------------------------------------------------------
// EmptyState component
// ---------------------------------------------------------------------------

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-8 text-center">
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
          d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25zM6.75 12h.008v.008H6.75V12zm0 3h.008v.008H6.75V15zm0 3h.008v.008H6.75V18z"
        />
      </svg>
      <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-2">
        No jobs yet
      </h3>
      <p className="text-sm text-gray-500 dark:text-gray-400 max-w-sm">
        Jobs will appear here when you run emClarity commands from the Workflow page.
        The list refreshes automatically every 5 seconds.
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// LogViewer component
// ---------------------------------------------------------------------------

interface LogViewerProps {
  job: JobV1
  onClose: () => void
  onCancel: (jobId: string) => void
  isCancelling: boolean
}

function LogViewer({ job, onClose, onCancel, isCancelling }: LogViewerProps) {
  const [logText, setLogText] = useState<string>('')
  const [logError, setLogError] = useState<string | null>(null)
  const [isLoadingLog, setIsLoadingLog] = useState(false)
  const logEndRef = useRef<HTMLDivElement>(null)

  const fetchLog = useCallback(async () => {
    setIsLoadingLog(true)
    setLogError(null)
    try {
      const result = await apiClient.get<JobLogResponse>(
        `/api/v1/jobs/${job.id}/log?tail=200`,
      )
      setLogText(result.log)
    } catch (err) {
      const message =
        err instanceof ApiError
          ? `Failed to load log (${err.status}): ${err.statusText}`
          : 'Failed to load log output.'
      setLogError(message)
    } finally {
      setIsLoadingLog(false)
    }
  }, [job.id])

  // Initial fetch
  useEffect(() => {
    void fetchLog()
  }, [fetchLog])

  // Poll log every 3 seconds while job is running
  useEffect(() => {
    if (job.status !== 'RUNNING') return
    const interval = setInterval(() => void fetchLog(), 3000)
    return () => clearInterval(interval)
  }, [job.status, fetchLog])

  // Auto-scroll to bottom when log updates
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logText])

  const isRunning = job.status === 'RUNNING' || job.status === 'PENDING'

  return (
    <div
      className={
        'rounded-lg border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden'
      }
    >
      {/* Panel header */}
      <div
        className={
          'flex items-center justify-between px-4 py-3 ' +
          'bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700'
        }
      >
        <div className="flex items-center gap-3 min-w-0">
          <StatusBadge status={job.status} />
          <span className="text-sm font-mono font-medium text-gray-900 dark:text-gray-100 truncate">
            {job.command}
          </span>
          <span className="text-xs text-gray-400 dark:text-gray-500 shrink-0">
            {job.id.slice(0, 8)}…
          </span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {/* Refresh button */}
          <button
            type="button"
            onClick={() => void fetchLog()}
            disabled={isLoadingLog}
            title="Refresh log"
            aria-label="Refresh log"
            className={
              'inline-flex items-center rounded-md p-1.5 text-gray-500 hover:text-gray-700 ' +
              'dark:text-gray-400 dark:hover:text-gray-200 ' +
              'hover:bg-gray-100 dark:hover:bg-gray-700 ' +
              'focus:outline-none focus:ring-2 focus:ring-blue-500 ' +
              'transition-colors disabled:opacity-50'
            }
          >
            <svg
              className={`w-4 h-4 ${isLoadingLog ? 'animate-spin' : ''}`}
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
          </button>

          {/* Cancel button – only for running/pending jobs */}
          {isRunning && (
            <button
              type="button"
              onClick={() => onCancel(job.id)}
              disabled={isCancelling}
              title="Cancel job"
              aria-label="Cancel job"
              className={
                'inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium ' +
                'bg-red-100 text-red-700 hover:bg-red-200 ' +
                'dark:bg-red-900/30 dark:text-red-400 dark:hover:bg-red-900/50 ' +
                'focus:outline-none focus:ring-2 focus:ring-red-500 ' +
                'transition-colors disabled:opacity-50 disabled:cursor-not-allowed'
              }
            >
              {isCancelling ? (
                <svg
                  className="w-3 h-3 animate-spin"
                  viewBox="0 0 24 24"
                  fill="none"
                  aria-hidden="true"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                  />
                </svg>
              ) : (
                <svg
                  className="w-3 h-3"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                  aria-hidden="true"
                >
                  <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
                </svg>
              )}
              Cancel
            </button>
          )}

          {/* Close button */}
          <button
            type="button"
            onClick={onClose}
            title="Close log viewer"
            aria-label="Close log viewer"
            className={
              'inline-flex items-center rounded-md p-1.5 text-gray-500 hover:text-gray-700 ' +
              'dark:text-gray-400 dark:hover:text-gray-200 ' +
              'hover:bg-gray-100 dark:hover:bg-gray-700 ' +
              'focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors'
            }
          >
            <svg
              className="w-4 h-4"
              viewBox="0 0 20 20"
              fill="currentColor"
              aria-hidden="true"
            >
              <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
            </svg>
          </button>
        </div>
      </div>

      {/* Log metadata */}
      <div
        className={
          'flex items-center gap-6 px-4 py-2 text-xs text-gray-500 dark:text-gray-400 ' +
          'bg-white dark:bg-gray-900 border-b border-gray-100 dark:border-gray-800'
        }
      >
        <span>
          <span className="font-medium">Started:</span>{' '}
          {formatDateTime(job.created_at)}
        </span>
        <span>
          <span className="font-medium">Duration:</span>{' '}
          {computeDuration(job.created_at, job.updated_at)}
        </span>
        {job.error_message && (
          <span className="text-red-600 dark:text-red-400 font-medium">
            {job.error_message}
          </span>
        )}
      </div>

      {/* Log content */}
      <div
        className={
          'relative bg-gray-950 dark:bg-gray-950 ' +
          'h-64 overflow-y-auto font-mono text-xs leading-relaxed'
        }
        aria-label="Job log output"
        role="log"
        aria-live={job.status === 'RUNNING' ? 'polite' : 'off'}
      >
        {logError ? (
          <div className="p-4 text-red-400">{logError}</div>
        ) : logText ? (
          <pre className="p-4 text-gray-300 whitespace-pre-wrap break-words">
            {logText}
          </pre>
        ) : (
          <div className="flex items-center justify-center h-full text-gray-600">
            {isLoadingLog ? 'Loading log…' : 'No log output available.'}
          </div>
        )}
        <div ref={logEndRef} />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// JobTable component
// ---------------------------------------------------------------------------

interface JobTableProps {
  jobs: JobV1[]
  selectedJobId: string | null
  onSelectJob: (job: JobV1) => void
}

function JobTable({ jobs, selectedJobId, onSelectJob }: JobTableProps) {
  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700 shadow-sm">
      <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
        <thead className="bg-gray-50 dark:bg-gray-800">
          <tr>
            {['Command', 'Status', 'Start Time', 'Duration', 'Project'].map((col) => (
              <th
                key={col}
                scope="col"
                className={
                  'px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider ' +
                  'text-gray-500 dark:text-gray-400'
                }
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>

        <tbody className="divide-y divide-gray-100 dark:divide-gray-800 bg-white dark:bg-gray-900">
          {jobs.map((job) => {
            const isSelected = job.id === selectedJobId
            return (
              <tr
                key={job.id}
                className={[
                  'cursor-pointer transition-colors',
                  isSelected
                    ? 'bg-blue-50 dark:bg-blue-900/20'
                    : 'hover:bg-gray-50 dark:hover:bg-gray-800/50',
                ].join(' ')}
                onClick={() => onSelectJob(job)}
                aria-selected={isSelected}
              >
                {/* Command */}
                <td className="px-4 py-3 whitespace-nowrap">
                  <span className="font-mono text-sm font-medium text-gray-900 dark:text-gray-100">
                    {job.command}
                  </span>
                </td>

                {/* Status */}
                <td className="px-4 py-3 whitespace-nowrap">
                  <StatusBadge status={job.status} />
                </td>

                {/* Start time */}
                <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-400">
                  {formatDateTime(job.created_at)}
                </td>

                {/* Duration */}
                <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-400">
                  {computeDuration(
                    job.created_at,
                    job.status === 'RUNNING' ? null : job.updated_at,
                  )}
                </td>

                {/* Project ID (shortened) */}
                <td className="px-4 py-3 whitespace-nowrap">
                  <span
                    className="text-xs font-mono text-gray-500 dark:text-gray-500"
                    title={job.project_id}
                  >
                    {job.project_id.slice(0, 8)}…
                  </span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ---------------------------------------------------------------------------
// JobsPage – exported page component
// ---------------------------------------------------------------------------

const REFRESH_INTERVAL_MS = 5000

export function JobsPage() {
  const [jobs, setJobs] = useState<JobV1[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [selectedJob, setSelectedJob] = useState<JobV1 | null>(null)
  const [isCancelling, setIsCancelling] = useState(false)
  const [notification, setNotification] = useState<{
    type: 'success' | 'error'
    message: string
  } | null>(null)

  // ---------------------------------------------------------------------------
  // Fetch job list
  // ---------------------------------------------------------------------------

  const fetchJobs = useCallback(async () => {
    try {
      const data = await apiClient.get<JobV1[]>('/api/v1/jobs')
      setJobs(data)
      setFetchError(null)

      // Keep selected job in sync with latest data
      setSelectedJob((prev) => {
        if (!prev) return null
        const updated = data.find((j) => j.id === prev.id)
        return updated ?? null
      })
    } catch (err) {
      const message =
        err instanceof ApiError
          ? `Failed to load jobs (${err.status}): ${err.statusText}`
          : 'Failed to load jobs. Is the backend running?'
      setFetchError(message)
    } finally {
      setIsLoading(false)
    }
  }, [])

  // Initial load
  useEffect(() => {
    void fetchJobs()
  }, [fetchJobs])

  // Auto-refresh every 5 seconds
  useEffect(() => {
    const interval = setInterval(() => void fetchJobs(), REFRESH_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [fetchJobs])

  // ---------------------------------------------------------------------------
  // Cancel job
  // ---------------------------------------------------------------------------

  const handleCancelJob = useCallback(
    async (jobId: string) => {
      setIsCancelling(true)
      try {
        await apiClient.delete<JobV1>(`/api/v1/jobs/${jobId}`)
        setNotification({ type: 'success', message: 'Job cancelled successfully.' })
        // Refresh immediately
        await fetchJobs()
      } catch (err) {
        const message =
          err instanceof ApiError
            ? `Failed to cancel job (${err.status}): ${err.statusText}`
            : 'Failed to cancel job. Please try again.'
        setNotification({ type: 'error', message })
      } finally {
        setIsCancelling(false)
        setTimeout(() => setNotification(null), 5000)
      }
    },
    [fetchJobs],
  )

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">Jobs</h2>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Monitor active and completed processing jobs. Auto-refreshes every 5 seconds.
          </p>
        </div>

        {/* Manual refresh + job count */}
        <div className="flex items-center gap-3">
          {!isLoading && !fetchError && (
            <span className="text-sm text-gray-500 dark:text-gray-400">
              {jobs.length} {jobs.length === 1 ? 'job' : 'jobs'}
            </span>
          )}
          <button
            type="button"
            onClick={() => void fetchJobs()}
            disabled={isLoading}
            aria-label="Refresh job list"
            className={
              'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium ' +
              'border border-gray-300 dark:border-gray-600 ' +
              'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 ' +
              'hover:bg-gray-50 dark:hover:bg-gray-700 ' +
              'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 ' +
              'transition-colors disabled:opacity-50 disabled:cursor-not-allowed'
            }
          >
            <svg
              className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`}
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
      </div>

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
            aria-label="Dismiss notification"
            className="shrink-0 opacity-70 hover:opacity-100"
          >
            <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
            </svg>
          </button>
        </div>
      )}

      {/* Error state */}
      {fetchError && (
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
              <p className="text-sm font-medium text-red-800 dark:text-red-300">{fetchError}</p>
              <button
                type="button"
                onClick={() => void fetchJobs()}
                className="mt-2 text-sm text-red-700 dark:text-red-400 underline hover:no-underline"
              >
                Retry
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Loading spinner */}
      {isLoading && (
        <div className="flex items-center justify-center py-16">
          <svg
            className="w-6 h-6 animate-spin text-blue-500"
            viewBox="0 0 24 24"
            fill="none"
            aria-hidden="true"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
            />
          </svg>
          <span className="ml-3 text-sm text-gray-500 dark:text-gray-400">Loading jobs…</span>
        </div>
      )}

      {/* Content: table or empty state */}
      {!isLoading && !fetchError && (
        <>
          {jobs.length === 0 ? (
            <EmptyState />
          ) : (
            <JobTable
              jobs={jobs}
              selectedJobId={selectedJob?.id ?? null}
              onSelectJob={setSelectedJob}
            />
          )}
        </>
      )}

      {/* Log viewer panel – shown when a job is selected */}
      {selectedJob && (
        <LogViewer
          job={selectedJob}
          onClose={() => setSelectedJob(null)}
          onCancel={handleCancelJob}
          isCancelling={isCancelling}
        />
      )}
    </div>
  )
}
