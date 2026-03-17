/**
 * EnvironmentPanel – scaffold for the Environment tab in Settings.
 *
 * Sections:
 *   1. Executable Paths  – path inputs + Validate buttons for emClarity binary and IMOD
 *   2. Dependencies      – table of Name / Path / Status / Version with "Check All"
 *   3. SSH Connections   – derived from run profiles; shows Test button per entry
 *   4. Run Profile Validation – "Validate All Profiles" + per-profile status badges
 *
 * All validation actions are UI-only stubs in this task (TASK-028).
 * Backend wiring is deferred to TASK-029.
 */

import { useState, useCallback, useEffect, useRef, useMemo } from 'react'
import { CheckCircle, XCircle, Circle, Terminal, Network, Server, ShieldCheck } from 'lucide-react'
import type { RunProfile } from '@/types/runProfile'

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

interface ExecutableRowState {
  path: string
  status: ValidationStatus
  stubVisible: boolean
}

function ExecutablePathsSection() {
  const [rows, setRows] = useState<Record<string, ExecutableRowState>>(() =>
    Object.fromEntries(
      EXECUTABLE_PATHS.map((ep) => [
        ep.id,
        { path: '', status: 'untested' as ValidationStatus, stubVisible: false },
      ]),
    ),
  )
  const validateTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({})

  useEffect(() => {
    const timers = validateTimers.current
    return () => { Object.values(timers).forEach(clearTimeout) }
  }, [])

  const handlePathChange = useCallback((id: string, value: string) => {
    setRows((prev) => ({
      ...prev,
      [id]: { ...prev[id], path: value, status: 'untested', stubVisible: false },
    }))
  }, [])

  const handleValidate = useCallback((id: string) => {
    setRows((prev) => ({
      ...prev,
      [id]: { ...prev[id], stubVisible: true },
    }))
    // Cancel any pending timer for this row before starting a new one
    if (validateTimers.current[id] !== undefined) {
      clearTimeout(validateTimers.current[id])
    }
    validateTimers.current[id] = setTimeout(() => {
      setRows((prev) => ({
        ...prev,
        [id]: { ...prev[id], stubVisible: false },
      }))
      delete validateTimers.current[id]
    }, 3000)
  }, [])

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
      <div className="space-y-3">
        {EXECUTABLE_PATHS.map((ep) => {
          const row = rows[ep.id]
          return (
            <div key={ep.id} className="flex items-center gap-3">
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
              <button
                type="button"
                onClick={() => handleValidate(ep.id)}
                aria-label={`Validate ${ep.label} path`}
                className="rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2.5 py-1 text-xs font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-colors flex-shrink-0"
              >
                Validate
              </button>
              <StubNotice visible={row.stubVisible} />
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
  const [deps] = useState<Dependency[]>(INITIAL_DEPENDENCIES)
  const [checkAllStub, setCheckAllStub] = useState(false)
  const checkAllTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => { if (checkAllTimer.current !== null) clearTimeout(checkAllTimer.current) }
  }, [])

  const handleCheckAll = useCallback(() => {
    if (checkAllTimer.current !== null) clearTimeout(checkAllTimer.current)
    setCheckAllStub(true)
    checkAllTimer.current = setTimeout(() => {
      setCheckAllStub(false)
      checkAllTimer.current = null
    }, 3000)
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
          onClick={handleCheckAll}
          aria-label="Check all dependencies"
          className="rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-colors"
        >
          Check All
        </button>
        <StubNotice visible={checkAllStub} />
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

function SSHConnectionsSection({ profiles }: SSHConnectionsSectionProps) {
  // Derive SSH-capable profiles: those whose commandTemplate contains "ssh"
  const sshProfiles = profiles.filter((p) =>
    p.commandTemplate.toLowerCase().includes('ssh'),
  )

  const [connectionStatuses, setConnectionStatuses] = useState<Record<string, ValidationStatus>>({})
  const [testStubs, setTestStubs] = useState<Record<string, boolean>>({})
  const testTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({})

  useEffect(() => {
    const timers = testTimers.current
    return () => { Object.values(timers).forEach(clearTimeout) }
  }, [])

  const handleTest = useCallback((id: string) => {
    setTestStubs((prev) => ({ ...prev, [id]: true }))
    if (testTimers.current[id] !== undefined) clearTimeout(testTimers.current[id])
    testTimers.current[id] = setTimeout(() => {
      setTestStubs((prev) => ({ ...prev, [id]: false }))
      delete testTimers.current[id]
    }, 3000)
  }, [])

  // Expose setter for TASK-029 backend wiring; suppress unused-var lint in scaffold
  void setConnectionStatuses

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
          {sshProfiles.map((profile) => (
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
              </span>
              <StatusBadge status={connectionStatuses[profile.id] ?? 'untested'} />
              <button
                type="button"
                onClick={() => handleTest(profile.id)}
                aria-label={`Test SSH connection for profile "${profile.name}"`}
                className="rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2.5 py-1 text-xs font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-colors flex-shrink-0"
              >
                Test
              </button>
              <StubNotice visible={testStubs[profile.id] ?? false} />
            </li>
          ))}
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
}

export function EnvironmentPanel({ profiles }: EnvironmentPanelProps) {
  return (
    <div className="overflow-y-auto h-full px-6 py-5">
      <ExecutablePathsSection />
      <DependenciesSection />
      <SSHConnectionsSection profiles={profiles} />
      <RunProfileValidationSection profiles={profiles} />
    </div>
  )
}
