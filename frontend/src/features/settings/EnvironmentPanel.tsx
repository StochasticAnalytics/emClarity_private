/**
 * EnvironmentPanel – Environment tab in Settings.
 *
 * Sections:
 *   1. Executable Paths  – path inputs + Validate buttons for emClarity binary and IMOD
 *   2. Dependencies      – table of Name / Path / Status / Version with "Check All"
 *   3. SSH Connections   – derived from run profiles; shows Test button per entry
 *   4. Run Profile Validation – "Validate All Profiles" + per-profile status badges
 *
 * Sections 1–3 are wired to real backend API endpoints (TASK-029).
 * Section 4 remains a stub (deferred).
 */

import { useState, useCallback, useEffect, useRef, useMemo } from 'react'
import { CheckCircle, XCircle, Circle, Terminal, Network, Server, ShieldCheck } from 'lucide-react'
import type { RunProfile } from '@/types/runProfile'
import { apiClient } from '@/api/client'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ValidationStatus = 'untested' | 'valid' | 'invalid'

interface ExecutablePath {
  id: string
  label: string
  placeholder: string
  ariaLabel: string
}

interface Dependency {
  name: string
  path: string
  status: ValidationStatus
  version: string
}

interface ValidatePathResponse {
  valid: boolean
  version: string | null
  error: string | null
}

interface DependencyResult {
  name: string
  path: string | null
  found: boolean
  version: string | null
}

interface CheckDepsResponse {
  dependencies: DependencyResult[]
}

interface TestSSHResponse {
  connected: boolean
  error: string | null
  latency_ms: number | null
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Small status badge showing untested / valid / invalid state. */
function StatusBadge({ status }: { status: ValidationStatus }) {
  if (status === 'valid') {
    return (
      <span
        className="inline-flex items-center gap-1 rounded-full bg-green-100 dark:bg-green-900/30 px-2 py-0.5 text-xs font-medium text-green-700 dark:text-green-300"
        aria-label="Valid"
      >
        <CheckCircle className="h-3 w-3" aria-hidden="true" />
        valid
      </span>
    )
  }
  if (status === 'invalid') {
    return (
      <span
        className="inline-flex items-center gap-1 rounded-full bg-red-100 dark:bg-red-900/30 px-2 py-0.5 text-xs font-medium text-red-700 dark:text-red-300"
        aria-label="Invalid"
      >
        <XCircle className="h-3 w-3" aria-hidden="true" />
        invalid
      </span>
    )
  }
  // untested
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full bg-gray-100 dark:bg-gray-700 px-2 py-0.5 text-xs font-medium text-gray-600 dark:text-gray-300"
      aria-label="Untested"
    >
      <Circle className="h-3 w-3" aria-hidden="true" />
      untested
    </span>
  )
}

/** Inline "Not yet implemented" notice that auto-dismisses.
 *
 * The aria-live region must always be present in the DOM so that screen
 * readers register it before any content is injected. Mounting with content
 * already present (by returning null then a populated span) means the
 * announcement is skipped. We keep the element mounted at all times and only
 * swap its text content. */
function StubNotice({ visible }: { visible: boolean }) {
  return (
    <span
      role="status"
      aria-live="polite"
      className="ml-2 text-xs text-amber-600 dark:text-amber-400 font-medium"
    >
      {visible ? 'Not yet implemented' : ''}
    </span>
  )
}

/** Inline spinner for loading states. */
function Spinner() {
  return (
    <svg
      className="animate-spin h-3 w-3 text-current"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
      />
    </svg>
  )
}

// ---------------------------------------------------------------------------
// Section: Executable Paths
// ---------------------------------------------------------------------------

const EXECUTABLE_PATHS: ExecutablePath[] = [
  {
    id: 'emclarity-binary',
    label: 'emClarity Binary',
    placeholder: '/usr/local/bin/emClarity',
    ariaLabel: 'emClarity binary path',
  },
  {
    id: 'imod-imodinfo',
    label: 'IMOD (imodinfo)',
    placeholder: '/usr/local/IMOD/bin/imodinfo',
    ariaLabel: 'IMOD imodinfo path',
  },
]

/** Mapping from executable path IDs to server-side environment variable names. */
const EXEC_PATH_ENV_VARS: Record<string, string> = {
  'emclarity-binary': 'EMCLARITY_PATH',
  'imod-imodinfo': 'IMOD_DIR',
}

interface ResolveEnvResponse {
  value: string | null
  found: boolean
}

interface EnvResolveState {
  loading: boolean
  value: string | null
  found: boolean | null
  error: string | null
}

interface ProjectSettingsResponse {
  executable_paths: Record<string, string> | null
}

interface ExecutableRowState {
  path: string
  status: ValidationStatus
  loading: boolean
  version: string | null
  error: string | null
  envResolve: EnvResolveState
}

function buildEmptyRow(): ExecutableRowState {
  return {
    path: '',
    status: 'untested',
    loading: false,
    version: null,
    error: null,
    envResolve: { loading: false, value: null, found: null, error: null },
  }
}

function buildRows(paths: Record<string, string>): Record<string, ExecutableRowState> {
  return Object.fromEntries(
    EXECUTABLE_PATHS.map((ep) => [
      ep.id,
      {
        ...buildEmptyRow(),
        path: paths[ep.id] ?? '',
      },
    ]),
  )
}

interface ExecutablePathsSectionProps {
  projectId: string | null
}

function ExecutablePathsSection({ projectId }: ExecutablePathsSectionProps) {
  const [rows, setRows] = useState<Record<string, ExecutableRowState>>(() => buildRows({}))
  const [initialLoading, setInitialLoading] = useState(!!projectId)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)

  // Track the latest paths for saving without stale closures
  const rowsRef = useRef(rows)
  rowsRef.current = rows

  const getCurrentPaths = useCallback((): Record<string, string> => {
    const paths: Record<string, string> = {}
    for (const ep of EXECUTABLE_PATHS) {
      const row = rowsRef.current[ep.id]
      if (row && row.path) {
        paths[ep.id] = row.path
      }
    }
    return paths
  }, [])

  // Debounce timer for saving paths to server
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      if (saveTimerRef.current !== null) clearTimeout(saveTimerRef.current)
    }
  }, [])

  // Fetch settings from server and migrate from localStorage if needed
  useEffect(() => {
    if (!projectId) {
      setInitialLoading(false)
      return
    }

    const fetchAndMigrate = async () => {
      setInitialLoading(true)
      setFetchError(null)
      try {
        const settings = await apiClient.get<ProjectSettingsResponse>(
          `/api/v1/projects/${projectId}/settings`,
        )

        // Check if migration from localStorage is needed
        const localPaths: Record<string, string> = {}
        for (const ep of EXECUTABLE_PATHS) {
          const val = localStorage.getItem(`env-path-${ep.id}`)
          if (val) localPaths[ep.id] = val
        }

        const serverPaths = settings.executable_paths ?? {}
        const serverEmpty = Object.keys(serverPaths).length === 0

        if (Object.keys(localPaths).length > 0 && serverEmpty) {
          // Migrate localStorage values to server
          await apiClient.patch(`/api/v1/projects/${projectId}/settings`, {
            executable_paths: localPaths,
          })
          // Clear localStorage keys after successful migration
          for (const ep of EXECUTABLE_PATHS) {
            localStorage.removeItem(`env-path-${ep.id}`)
          }
          setRows(buildRows(localPaths))
        } else {
          // Use server paths; clear any stale localStorage keys
          setRows(buildRows(serverPaths))
          for (const ep of EXECUTABLE_PATHS) {
            localStorage.removeItem(`env-path-${ep.id}`)
          }
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to load settings'
        setFetchError(message)
      } finally {
        setInitialLoading(false)
      }
    }

    void fetchAndMigrate()
  }, [projectId])

  const savePaths = useCallback(
    (updatedPaths: Record<string, string>) => {
      if (!projectId) return
      setSaveError(null)

      if (saveTimerRef.current !== null) clearTimeout(saveTimerRef.current)
      saveTimerRef.current = setTimeout(() => {
        const doSave = async () => {
          try {
            await apiClient.patch(`/api/v1/projects/${projectId}/settings`, {
              executable_paths: updatedPaths,
            })
          } catch (err) {
            const message = err instanceof Error ? err.message : 'Failed to save path'
            setSaveError(message)
          }
        }
        void doSave()
      }, 500)
    },
    [projectId],
  )

  const handlePathChange = useCallback(
    (id: string, value: string) => {
      setRows((prev) => {
        const updated = {
          ...prev,
          [id]: {
            ...prev[id],
            path: value,
            status: 'untested' as ValidationStatus,
            version: null,
            error: null,
          },
        }
        // Build paths from updated rows for saving
        const paths: Record<string, string> = {}
        for (const ep of EXECUTABLE_PATHS) {
          const row = updated[ep.id]
          if (row && row.path) {
            paths[ep.id] = row.path
          }
        }
        savePaths(paths)
        return updated
      })
    },
    [savePaths],
  )

  const handleValidate = useCallback(
    async (id: string) => {
      const path = rowsRef.current[id]?.path ?? ''
      setRows((prev) => ({
        ...prev,
        [id]: { ...prev[id], loading: true },
      }))
      try {
        const result = await apiClient.post<ValidatePathResponse>(
          '/api/v1/environment/validate-path',
          { path },
        )
        setRows((prev) => {
          if (prev[id]?.path !== path) {
            return { ...prev, [id]: { ...prev[id], loading: false } }
          }
          return {
            ...prev,
            [id]: {
              ...prev[id],
              loading: false,
              status: result.valid ? 'valid' : 'invalid',
              version: result.version,
              error: result.error,
            },
          }
        })
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Validation failed'
        setRows((prev) => {
          if (prev[id]?.path !== path) {
            return { ...prev, [id]: { ...prev[id], loading: false } }
          }
          return {
            ...prev,
            [id]: { ...prev[id], loading: false, status: 'invalid', version: null, error: message },
          }
        })
      }
    },
    [],
  )

  const handleResolveEnv = useCallback(
    async (id: string) => {
      const envVar = EXEC_PATH_ENV_VARS[id]
      if (!envVar) return

      setRows((prev) => ({
        ...prev,
        [id]: {
          ...prev[id],
          envResolve: { loading: true, value: null, found: null, error: null },
        },
      }))

      try {
        const result = await apiClient.get<ResolveEnvResponse>(
          `/api/v1/environment/resolve-env?var=${encodeURIComponent(envVar)}`,
        )
        setRows((prev) => ({
          ...prev,
          [id]: {
            ...prev[id],
            envResolve: {
              loading: false,
              value: result.value,
              found: result.found,
              error: null,
            },
          },
        }))
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to resolve environment variable'
        setRows((prev) => ({
          ...prev,
          [id]: {
            ...prev[id],
            envResolve: { loading: false, value: null, found: null, error: message },
          },
        }))
      }
    },
    [],
  )

  const handleUseEnvPath = useCallback(
    (id: string, value: string) => {
      handlePathChange(id, value)
      // Clear the env resolve state after using the value
      setRows((prev) => ({
        ...prev,
        [id]: {
          ...prev[id],
          envResolve: { loading: false, value: null, found: null, error: null },
        },
      }))
    },
    [handlePathChange],
  )

  if (initialLoading) {
    return (
      <section aria-labelledby="exec-paths-heading" className="mb-6">
        <div className="flex items-center gap-2 mb-3">
          <Terminal className="h-4 w-4 text-gray-500 dark:text-gray-400" aria-hidden="true" />
          <h3
            id="exec-paths-heading"
            className="text-sm font-semibold text-gray-900 dark:text-gray-100"
          >
            Executable Paths
          </h3>
        </div>
        <p role="status" className="text-sm text-gray-500 dark:text-gray-400">
          Loading executable paths…
        </p>
      </section>
    )
  }

  return (
    <section aria-labelledby="exec-paths-heading" className="mb-6">
      <div className="flex items-center gap-2 mb-3">
        <Terminal className="h-4 w-4 text-gray-500 dark:text-gray-400" aria-hidden="true" />
        <h3
          id="exec-paths-heading"
          className="text-sm font-semibold text-gray-900 dark:text-gray-100"
        >
          Executable Paths
        </h3>
      </div>

      {fetchError !== null && (
        <div role="alert" className="mb-3 rounded border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 px-3 py-2 text-xs text-red-700 dark:text-red-300">
          <span className="font-medium">Failed to load:</span> {fetchError}
        </div>
      )}

      {saveError !== null && (
        <div role="alert" className="mb-3 rounded border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
          <span className="font-medium">Save failed:</span> {saveError}
        </div>
      )}

      <div className="space-y-3">
        {EXECUTABLE_PATHS.map((ep) => {
          const row = rows[ep.id]
          const envVar = EXEC_PATH_ENV_VARS[ep.id]
          const envResolve = row.envResolve
          return (
            <div key={ep.id} className="space-y-1">
              <div className="flex items-center gap-3">
                <label
                  htmlFor={`exec-path-${ep.id}`}
                  className="w-36 flex-shrink-0 text-xs font-medium text-gray-700 dark:text-gray-300"
                >
                  {ep.label}
                </label>
                <input
                  id={`exec-path-${ep.id}`}
                  type="text"
                  value={row.path}
                  onChange={(e) => handlePathChange(ep.id, e.target.value)}
                  placeholder={ep.placeholder}
                  aria-label={ep.ariaLabel}
                  className="flex-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-1.5 text-sm text-gray-900 dark:text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono"
                />
                <StatusBadge status={row.status} />
                {/* aria-live region: always mounted so screen readers register it before content is injected */}
                <span
                  role="status"
                  aria-live="polite"
                  aria-atomic="true"
                  className="sr-only"
                >
                  {row.status !== 'untested'
                    ? `${ep.label}: ${row.status}${row.error ? `. ${row.error}` : row.version ? `. ${row.version}` : ''}`
                    : ''}
                </span>
                {row.status === 'valid' && row.version !== null && (
                  <span className="text-xs text-gray-500 dark:text-gray-400 font-mono">
                    {row.version}
                  </span>
                )}
                <button
                  type="button"
                  onClick={() => { void handleValidate(ep.id) }}
                  disabled={row.loading}
                  aria-label={`Validate ${ep.label} path`}
                  className="rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2.5 py-1 text-xs font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-colors flex-shrink-0 inline-flex items-center gap-1.5 disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  {row.loading ? (
                    <>
                      <Spinner />
                      Validating…
                    </>
                  ) : (
                    'Validate'
                  )}
                </button>
                {envVar !== undefined && (
                  <button
                    type="button"
                    onClick={() => { void handleResolveEnv(ep.id) }}
                    disabled={envResolve.loading}
                    aria-label={`Get ${ep.label} path from environment variable ${envVar}`}
                    className="rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2.5 py-1 text-xs font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-colors flex-shrink-0 inline-flex items-center gap-1.5 disabled:opacity-60 disabled:cursor-not-allowed"
                  >
                    {envResolve.loading ? (
                      <>
                        <Spinner />
                        Checking…
                      </>
                    ) : (
                      'Get from environment'
                    )}
                  </button>
                )}
              </div>
              {row.status === 'invalid' && row.error !== null && (
                <span
                  role="alert"
                  className="block ml-36 pl-3 text-xs text-red-600 dark:text-red-400"
                >
                  {row.error}
                </span>
              )}
              {/* Env resolve result */}
              {envResolve.error !== null && (
                <span
                  role="alert"
                  className="block ml-36 pl-3 text-xs text-red-600 dark:text-red-400"
                >
                  {envResolve.error}
                </span>
              )}
              {envResolve.found === true && envResolve.value !== null && (
                <div className="ml-36 pl-3 flex items-center gap-2">
                  <span className="text-xs text-gray-600 dark:text-gray-400 font-mono truncate max-w-md">
                    {envResolve.value}
                  </span>
                  <button
                    type="button"
                    onClick={() => handleUseEnvPath(ep.id, envResolve.value!)}
                    aria-label={`Use environment value for ${ep.label}`}
                    className="rounded border border-green-300 dark:border-green-700 bg-green-50 dark:bg-green-900/30 px-2 py-0.5 text-xs font-medium text-green-700 dark:text-green-300 hover:bg-green-100 dark:hover:bg-green-900/50 focus:outline-none focus:ring-1 focus:ring-green-500 transition-colors"
                  >
                    Use this path
                  </button>
                </div>
              )}
              {envResolve.found === false && (
                <span className="block ml-36 pl-3 text-xs text-gray-500 dark:text-gray-400 italic">
                  Environment variable not set
                </span>
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Section: Dependencies
// ---------------------------------------------------------------------------

const INITIAL_DEPENDENCIES: Dependency[] = [
  { name: 'emClarity', path: '', status: 'untested', version: '' },
  { name: 'IMOD', path: '', status: 'untested', version: '' },
  { name: 'CUDA Toolkit', path: '', status: 'untested', version: '' },
]

function DependenciesSection() {
  const [deps, setDeps] = useState<Dependency[]>(INITIAL_DEPENDENCIES)
  const [checkAllLoading, setCheckAllLoading] = useState(false)
  const [checkAllError, setCheckAllError] = useState<string | null>(null)
  const [checkAllAnnouncement, setCheckAllAnnouncement] = useState<string>('')

  const handleCheckAll = useCallback(async () => {
    setCheckAllLoading(true)
    setCheckAllError(null)
    setCheckAllAnnouncement('')
    try {
      const result = await apiClient.get<CheckDepsResponse>('/api/v1/environment/check-dependencies')
      const depMap = new Map(result.dependencies.map((d) => [d.name, d]))
      setDeps((prev) =>
        prev.map((dep) => {
          const found = depMap.get(dep.name)
          if (found === undefined) return dep
          return {
            name: dep.name,
            path: found.path ?? '',
            status: (found.found ? 'valid' : 'invalid') as ValidationStatus,
            version: found.version ?? '',
          }
        }),
      )
      const foundCount = result.dependencies.filter((d) => d.found).length
      const totalCount = result.dependencies.length
      setCheckAllAnnouncement(
        `Dependency check complete: ${foundCount} of ${totalCount} found.`,
      )
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error'
      setCheckAllError(message)
      setCheckAllAnnouncement(`Dependency check failed: ${message}`)
    } finally {
      setCheckAllLoading(false)
    }
  }, [])

  return (
    <section aria-labelledby="deps-heading" className="mb-6">
      <div className="flex items-center gap-2 mb-3">
        <Server className="h-4 w-4 text-gray-500 dark:text-gray-400" aria-hidden="true" />
        <h3
          id="deps-heading"
          className="text-sm font-semibold text-gray-900 dark:text-gray-100"
        >
          Dependencies
        </h3>
      </div>
      <div className="rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
        <table className="w-full text-sm" aria-label="Dependencies table">
          <thead className="bg-gray-50 dark:bg-gray-800/50">
            <tr>
              <th
                scope="col"
                className="px-4 py-2 text-left text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider"
              >
                Name
              </th>
              <th
                scope="col"
                className="px-4 py-2 text-left text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider"
              >
                Path
              </th>
              <th
                scope="col"
                className="px-4 py-2 text-left text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider"
              >
                Status
              </th>
              <th
                scope="col"
                className="px-4 py-2 text-left text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider"
              >
                Version
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200 dark:divide-gray-700 bg-white dark:bg-gray-900">
            {deps.map((dep) => (
              <tr key={dep.name} className="hover:bg-gray-50 dark:hover:bg-gray-800/30 transition-colors">
                <td className="px-4 py-2.5 font-medium text-gray-900 dark:text-gray-100">
                  {dep.name}
                </td>
                <td className="px-4 py-2.5 font-mono text-gray-500 dark:text-gray-400 text-xs">
                  {dep.path || <span className="italic text-gray-500 dark:text-gray-400">not set</span>}
                </td>
                <td className="px-4 py-2.5">
                  <StatusBadge status={dep.status} />
                </td>
                <td className="px-4 py-2.5 text-gray-500 dark:text-gray-400 text-xs">
                  {dep.version || <span className="italic text-gray-500 dark:text-gray-400">—</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-2 flex items-center gap-2">
        <button
          type="button"
          onClick={() => { void handleCheckAll() }}
          disabled={checkAllLoading}
          aria-label="Check all dependencies"
          className="rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-colors inline-flex items-center gap-1.5 disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {checkAllLoading ? (
            <>
              <Spinner />
              Checking…
            </>
          ) : (
            'Check All'
          )}
        </button>
        {checkAllError !== null && (
          <span
            role="alert"
            className="text-xs text-red-600 dark:text-red-400"
          >
            {checkAllError}
          </span>
        )}
        {/* aria-live region announces completion to screen readers */}
        <span
          role="status"
          aria-live="polite"
          aria-atomic="true"
          className="sr-only"
        >
          {checkAllAnnouncement}
        </span>
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Section: SSH Connections
// ---------------------------------------------------------------------------

interface SSHConnectionsSectionProps {
  profiles: RunProfile[]
}

interface ParsedSSH {
  host: string
  user: string | null
  port: number
}

/** Parse SSH connection parameters from a commandTemplate string.
 *
 * Handles patterns like:
 *   ssh user@host
 *   ssh -p 2222 user@host
 *   ssh host
 */
function parseSSHParams(commandTemplate: string): ParsedSSH | null {
  // Find the ssh invocation - grab everything after "ssh" up to the next
  // shell metacharacter or end of string
  const sshMatch = commandTemplate.match(/\bssh\s+(.*?)(?:\s*(?:&&|\||;|$))/i)
  if (sshMatch === null) return null

  const args = sshMatch[1].trim()
  let remaining = args
  let port = 22
  let userAtHost = ''

  // Extract -p PORT
  const portMatch = remaining.match(/-p\s+(\d+)/)
  if (portMatch !== null) {
    port = parseInt(portMatch[1], 10)
    remaining = remaining.replace(portMatch[0], '').trim()
  }

  // SSH flags that consume a value argument (one token follows the flag).
  // -p and -l are handled explicitly below, so they are excluded here.
  const VALUE_FLAGS = new Set(['-b', '-c', '-D', '-E', '-e', '-F', '-I', '-i', '-J', '-L', '-m', '-o', '-Q', '-R', '-S', '-W', '-w'])

  // Walk tokens sequentially so that value-consuming flags skip their argument
  // and do not accidentally promote a file path or option string to user@host.
  // -l <user> is captured as the login user (equivalent to user@host).
  const tokens = remaining.split(/\s+/)
  let skipNext = false
  let captureLoginUser = false
  let loginUser: string | null = null
  for (const token of tokens) {
    if (captureLoginUser) {
      captureLoginUser = false
      loginUser = token
      continue
    }
    if (skipNext) {
      skipNext = false
      continue
    }
    if (token.startsWith('-')) {
      if (token === '-l') {
        captureLoginUser = true
      } else if (VALUE_FLAGS.has(token)) {
        skipNext = true
      }
      continue
    }
    userAtHost = token
    break
  }

  if (userAtHost === '') return null

  const atIndex = userAtHost.indexOf('@')
  if (atIndex !== -1) {
    // user@host form takes precedence over -l flag
    return {
      user: userAtHost.slice(0, atIndex),
      host: userAtHost.slice(atIndex + 1),
      port,
    }
  }

  // Plain host — use login user from -l flag if present
  return { host: userAtHost, user: loginUser, port }
}

function SSHConnectionsSection({ profiles }: SSHConnectionsSectionProps) {
  // Derive SSH-capable profiles: those whose commandTemplate contains "ssh"
  const sshProfiles = profiles.filter((p) =>
    p.commandTemplate.toLowerCase().includes('ssh'),
  )

  const [connectionStatuses, setConnectionStatuses] = useState<Record<string, ValidationStatus>>({})
  const [loading, setLoading] = useState<Record<string, boolean>>({})
  const [latency, setLatency] = useState<Record<string, number | null>>({})
  const [errorMessages, setErrorMessages] = useState<Record<string, string | null>>({})

  const handleTest = useCallback(async (profileId: string, commandTemplate: string) => {
    const parsed = parseSSHParams(commandTemplate)
    if (parsed === null) {
      setConnectionStatuses((prev) => ({ ...prev, [profileId]: 'invalid' }))
      setErrorMessages((prev) => ({ ...prev, [profileId]: 'Could not parse SSH host from command template' }))
      return
    }

    setLoading((prev) => ({ ...prev, [profileId]: true }))
    setErrorMessages((prev) => ({ ...prev, [profileId]: null }))

    try {
      const result = await apiClient.post<TestSSHResponse>(
        '/api/v1/environment/test-ssh',
        { host: parsed.host, user: parsed.user, port: parsed.port },
      )
      setConnectionStatuses((prev) => ({
        ...prev,
        [profileId]: result.connected ? 'valid' : 'invalid',
      }))
      setLatency((prev) => ({ ...prev, [profileId]: result.latency_ms }))
      if (result.error !== null) {
        setErrorMessages((prev) => ({ ...prev, [profileId]: result.error }))
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Connection failed'
      setConnectionStatuses((prev) => ({ ...prev, [profileId]: 'invalid' }))
      setErrorMessages((prev) => ({ ...prev, [profileId]: message }))
      setLatency((prev) => ({ ...prev, [profileId]: null }))
    } finally {
      setLoading((prev) => ({ ...prev, [profileId]: false }))
    }
  }, [])

  return (
    <section aria-labelledby="ssh-heading" className="mb-6">
      <div className="flex items-center gap-2 mb-3">
        <Network className="h-4 w-4 text-gray-500 dark:text-gray-400" aria-hidden="true" />
        <h3
          id="ssh-heading"
          className="text-sm font-semibold text-gray-900 dark:text-gray-100"
        >
          SSH Connections
        </h3>
      </div>
      {sshProfiles.length === 0 ? (
        <p className="text-sm text-gray-500 dark:text-gray-400 italic">
          No SSH connections configured. Run profiles using SSH command templates will appear here.
        </p>
      ) : (
        <ul aria-label="SSH connection profiles" className="space-y-2">
          {sshProfiles.map((profile) => {
            const isLoading = loading[profile.id] ?? false
            const profileLatency = latency[profile.id]
            const errorMsg = errorMessages[profile.id] ?? null
            const status = connectionStatuses[profile.id] ?? 'untested'
            return (
              <li
                key={profile.id}
                className="flex items-center gap-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-4 py-2.5"
              >
                <span className="flex-1 min-w-0">
                  <span className="block text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                    {profile.name}
                  </span>
                  <span className="block text-xs font-mono text-gray-500 dark:text-gray-400 truncate">
                    {profile.commandTemplate}
                  </span>
                  {errorMsg !== null && (
                    <span
                      role="alert"
                      className="block text-xs text-red-600 dark:text-red-400 mt-0.5"
                    >
                      {errorMsg}
                    </span>
                  )}
                </span>
                {/* aria-live region: always mounted so screen readers register it before content is injected */}
                <span
                  role="status"
                  aria-live="polite"
                  aria-atomic="true"
                  className="sr-only"
                >
                  {status !== 'untested'
                    ? `${profile.name}: ${status}${status === 'valid' && profileLatency !== null ? `. Latency ${profileLatency.toFixed(1)} ms` : errorMsg ? `. ${errorMsg}` : ''}`
                    : ''}
                </span>
                <StatusBadge status={status} />
                {status === 'valid' && profileLatency !== null && profileLatency !== undefined && (
                  <span className="text-xs text-gray-500 dark:text-gray-400">
                    {profileLatency.toFixed(1)} ms
                  </span>
                )}
                <button
                  type="button"
                  onClick={() => { void handleTest(profile.id, profile.commandTemplate) }}
                  disabled={isLoading}
                  aria-label={`Test SSH connection for profile "${profile.name}"`}
                  className="rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2.5 py-1 text-xs font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-colors flex-shrink-0 inline-flex items-center gap-1.5 disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  {isLoading ? (
                    <>
                      <Spinner />
                      Testing…
                    </>
                  ) : (
                    'Test'
                  )}
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

// ---------------------------------------------------------------------------
// Section: Run Profile Validation
// ---------------------------------------------------------------------------

interface RunProfileValidationSectionProps {
  profiles: RunProfile[]
}

function RunProfileValidationSection({ profiles }: RunProfileValidationSectionProps) {
  const profileStatuses = useMemo<Record<string, ValidationStatus>>(
    () => Object.fromEntries(profiles.map((p) => [p.id, 'untested' as ValidationStatus])),
    [profiles],
  )
  const [validateAllStub, setValidateAllStub] = useState(false)
  const validateAllTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => { if (validateAllTimer.current !== null) clearTimeout(validateAllTimer.current) }
  }, [])

  const handleValidateAll = useCallback(() => {
    if (validateAllTimer.current !== null) clearTimeout(validateAllTimer.current)
    setValidateAllStub(true)
    validateAllTimer.current = setTimeout(() => {
      setValidateAllStub(false)
      validateAllTimer.current = null
    }, 3000)
  }, [])

  const statusForProfile = (id: string): ValidationStatus =>
    profileStatuses[id] ?? 'untested'

  return (
    <section aria-labelledby="profile-validation-heading" className="mb-6">
      <div className="flex items-center gap-2 mb-3">
        <ShieldCheck className="h-4 w-4 text-gray-500 dark:text-gray-400" aria-hidden="true" />
        <h3
          id="profile-validation-heading"
          className="text-sm font-semibold text-gray-900 dark:text-gray-100"
        >
          Run Profile Validation
        </h3>
      </div>
      <div className="flex items-center gap-2 mb-3">
        <button
          type="button"
          onClick={handleValidateAll}
          aria-label="Validate all run profiles"
          className="rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-colors"
        >
          Validate All Profiles
        </button>
        <StubNotice visible={validateAllStub} />
      </div>
      {profiles.length === 0 ? (
        <p className="text-sm text-gray-500 dark:text-gray-400 italic">
          No run profiles defined. Create one in the Run Profiles tab.
        </p>
      ) : (
        <ul aria-label="Run profile validation statuses" className="space-y-1.5">
          {profiles.map((profile) => (
            <li
              key={profile.id}
              className="flex items-center gap-3 rounded border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2"
            >
              <span className="flex-1 text-sm text-gray-800 dark:text-gray-200 truncate">
                {profile.name}
              </span>
              <StatusBadge status={statusForProfile(profile.id)} />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

// ---------------------------------------------------------------------------
// EnvironmentPanel (exported)
// ---------------------------------------------------------------------------

interface EnvironmentPanelProps {
  profiles: RunProfile[]
  projectId: string | null
}

export function EnvironmentPanel({ profiles, projectId }: EnvironmentPanelProps) {
  return (
    <div className="overflow-y-auto h-full px-6 py-5">
      <ExecutablePathsSection projectId={projectId} />
      <DependenciesSection />
      <SSHConnectionsSection profiles={profiles} />
      <RunProfileValidationSection profiles={profiles} />
    </div>
  )
}
