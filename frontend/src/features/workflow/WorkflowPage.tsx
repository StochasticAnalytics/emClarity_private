/**
 * Workflow runner page.
 *
 * Displays the emClarity pipeline as a visual stepper showing all pipeline
 * states.  The current state is highlighted.  Available commands are shown
 * as enabled buttons; unavailable commands are disabled with a tooltip
 * explaining which prerequisite state must be reached first.
 *
 * API calls:
 *   GET  /api/v1/workflow/state-machine                 – full state machine def
 *   GET  /api/v1/workflow/{project_id}/available-commands – commands for project
 *   POST /api/v1/workflow/{project_id}/run              – execute a command
 */
import { useState, useCallback, useEffect } from 'react'
import { useParams, Navigate } from 'react-router-dom'
import { apiClient, ApiError } from '@/api/client.ts'
import { useApiQuery } from '@/hooks/useApi.ts'
import { DEMO_PROJECT_ID } from '@/constants'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface StateMachineStateEntry {
  description: string
  available_commands: string[]
  transitions: Record<string, string>
}

interface StateMachine {
  states: Record<string, StateMachineStateEntry>
  initial_state: string
}

interface CommandEntry {
  name: string
  description: string
}

interface AvailableCommandsResponse {
  project_id: string
  state: string
  commands: CommandEntry[]
}

interface RunCommandResponse {
  project_id: string
  command: string
  status: string
  message: string
}

// ---------------------------------------------------------------------------
// Constants – ordered pipeline states and command metadata
// ---------------------------------------------------------------------------

/** States in pipeline execution order. */
const PIPELINE_STATES: ReadonlyArray<string> = [
  'UNINITIALIZED',
  'TILT_ALIGNED',
  'CTF_ESTIMATED',
  'RECONSTRUCTED',
  'PARTICLES_PICKED',
  'INITIALIZED',
  'CYCLE_N',
  'EXPORT',
  'DONE',
]

const STATE_LABELS: Record<string, string> = {
  UNINITIALIZED: 'Uninitialized',
  TILT_ALIGNED: 'Tilt Aligned',
  CTF_ESTIMATED: 'CTF Estimated',
  RECONSTRUCTED: 'Reconstructed',
  PARTICLES_PICKED: 'Particles Picked',
  INITIALIZED: 'Initialized',
  CYCLE_N: 'Iterative Cycle',
  EXPORT: 'Export',
  DONE: 'Done',
}

/** Ordered list of all pipeline commands for display purposes. */
const ALL_COMMANDS: ReadonlyArray<string> = [
  'autoAlign',
  'ctf estimate',
  'ctf 3d',
  'templateSearch',
  'init',
  'avg',
  'alignRaw',
  'tomoCPR',
  'pca',
  'cluster',
  'fsc',
  'reconstruct',
]

/** Human-readable labels for each command. */
const COMMAND_LABELS: Record<string, string> = {
  autoAlign: 'Auto Align',
  'ctf estimate': 'CTF Estimate',
  'ctf 3d': 'CTF 3D',
  templateSearch: 'Template Search',
  init: 'Initialize',
  avg: 'Average',
  alignRaw: 'Align Raw',
  tomoCPR: 'TomoCPR',
  pca: 'PCA',
  cluster: 'Cluster',
  fsc: 'FSC',
  reconstruct: 'Reconstruct',
}

/** The minimum pipeline state required before each command is unlocked. */
const COMMAND_PREREQUISITE_STATE: Record<string, string> = {
  autoAlign: 'UNINITIALIZED',
  'ctf estimate': 'TILT_ALIGNED',
  'ctf 3d': 'CTF_ESTIMATED',
  templateSearch: 'RECONSTRUCTED',
  init: 'PARTICLES_PICKED',
  avg: 'INITIALIZED',
  alignRaw: 'CYCLE_N',
  tomoCPR: 'CYCLE_N',
  pca: 'CYCLE_N',
  cluster: 'CYCLE_N',
  fsc: 'CYCLE_N',
  reconstruct: 'CYCLE_N',
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function stateIndex(state: string): number {
  return PIPELINE_STATES.indexOf(state.toUpperCase())
}

function prerequisiteLabel(command: string): string {
  const prereq = COMMAND_PREREQUISITE_STATE[command]
  if (!prereq) return 'Unknown prerequisite'
  const label = STATE_LABELS[prereq] ?? prereq
  return `Requires pipeline state: ${label}`
}

// ---------------------------------------------------------------------------
// PipelineStepper – visual state machine progress indicator
// ---------------------------------------------------------------------------

interface PipelineStepperProps {
  currentState: string
  stateMachine: StateMachine
}

function PipelineStepper({ currentState, stateMachine }: PipelineStepperProps) {
  const currentIdx = stateIndex(currentState)

  return (
    <div className="w-full">
      {/* Horizontal stepper for larger screens */}
      <ol aria-label="Pipeline progress" className="hidden sm:flex items-start gap-0">
        {PIPELINE_STATES.map((stateName, idx) => {
          const isCompleted = idx < currentIdx
          const isCurrent = idx === currentIdx
          const isLast = idx === PIPELINE_STATES.length - 1
          const stateInfo = stateMachine.states[stateName]
          const label = STATE_LABELS[stateName] ?? stateName

          return (
            <li
              key={stateName}
              className="flex-1 flex items-start"
              aria-current={isCurrent ? 'step' : undefined}
            >
              {/* Step content */}
              <div className="flex flex-col items-center flex-1 relative">
                {/* Circle indicator */}
                <div
                  className={[
                    'w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold border-2 z-10 transition-colors',
                    isCompleted
                      ? 'bg-green-500 border-green-500 text-white'
                      : isCurrent
                        ? 'bg-blue-600 border-blue-600 text-white ring-4 ring-blue-100 dark:ring-blue-900'
                        : 'bg-white dark:bg-gray-800 border-gray-300 dark:border-gray-600 text-gray-400 dark:text-gray-500',
                  ].join(' ')}
                  title={stateInfo?.description ?? label}
                >
                  {isCompleted ? (
                    <svg
                      className="w-4 h-4"
                      viewBox="0 0 20 20"
                      fill="currentColor"
                      aria-hidden="true"
                    >
                      <path
                        fillRule="evenodd"
                        d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                        clipRule="evenodd"
                      />
                    </svg>
                  ) : (
                    <span>{idx + 1}</span>
                  )}
                </div>
                {/* Label */}
                <span
                  className={[
                    'mt-2 text-xs font-medium text-center leading-tight max-w-[80px]',
                    isCurrent
                      ? 'text-blue-600 dark:text-blue-400'
                      : isCompleted
                        ? 'text-green-600 dark:text-green-400'
                        : 'text-gray-400 dark:text-gray-500',
                  ].join(' ')}
                >
                  {label}
                </span>
              </div>
              {/* Connector line */}
              {!isLast && (
                <div
                  className={[
                    'flex-none w-full max-w-[40px] h-0.5 mt-4 -mx-1',
                    isCompleted ? 'bg-green-400' : 'bg-gray-200 dark:bg-gray-700',
                  ].join(' ')}
                  aria-hidden="true"
                />
              )}
            </li>
          )
        })}
      </ol>

      {/* Compact vertical list for small screens */}
      <ol aria-label="Pipeline progress" className="sm:hidden flex flex-col gap-3">
        {PIPELINE_STATES.map((stateName, idx) => {
          const isCompleted = idx < currentIdx
          const isCurrent = idx === currentIdx
          const label = STATE_LABELS[stateName] ?? stateName
          const stateInfo = stateMachine.states[stateName]

          return (
            <li
              key={stateName}
              aria-current={isCurrent ? 'step' : undefined}
              className={[
                'flex items-center gap-3 px-3 py-2 rounded-lg border transition-colors',
                isCurrent
                  ? 'border-blue-500 bg-blue-50 dark:border-blue-600 dark:bg-blue-900/20'
                  : isCompleted
                    ? 'border-green-300 bg-green-50 dark:border-green-700 dark:bg-green-900/20'
                    : 'border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900',
              ].join(' ')}
            >
              <div
                className={[
                  'w-6 h-6 rounded-full flex items-center justify-center text-xs font-semibold border-2 shrink-0',
                  isCompleted
                    ? 'bg-green-500 border-green-500 text-white'
                    : isCurrent
                      ? 'bg-blue-600 border-blue-600 text-white'
                      : 'border-gray-300 dark:border-gray-600 text-gray-400',
                ].join(' ')}
              >
                {isCompleted ? '✓' : idx + 1}
              </div>
              <div className="min-w-0">
                <p
                  className={[
                    'text-sm font-medium',
                    isCurrent
                      ? 'text-blue-700 dark:text-blue-300'
                      : 'text-gray-700 dark:text-gray-300',
                  ].join(' ')}
                >
                  {label}
                </p>
                {stateInfo?.description && (
                  <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                    {stateInfo.description}
                  </p>
                )}
              </div>
            </li>
          )
        })}
      </ol>
    </div>
  )
}

// ---------------------------------------------------------------------------
// CommandDialog – modal for confirming and running a command
// ---------------------------------------------------------------------------

interface ArgDef {
  key: string
  label: string
  placeholder: string
}

interface CommandDialogProps {
  command: CommandEntry
  projectId: string
  onSuccess: (msg: string) => void
  onClose: () => void
}

function CommandDialog({ command, projectId, onSuccess, onClose }: CommandDialogProps) {
  const [isRunning, setIsRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [args, setArgs] = useState<Record<string, string>>({})

  const handleRun = useCallback(async () => {
    setError(null)
    setIsRunning(true)
    try {
      // Convert string args to appropriate types
      const typedArgs: Record<string, unknown> = {}
      for (const [key, value] of Object.entries(args)) {
        const trimmed = value.trim()
        if (trimmed !== '') {
          const num = Number(trimmed)
          typedArgs[key] = isNaN(num) ? trimmed : num
        }
      }
      const resp = await apiClient.post<RunCommandResponse>(
        `/api/v1/workflow/${projectId}/run`,
        { command: command.name, args: typedArgs },
      )
      onSuccess(resp.message || `Command '${command.name}' accepted`)
    } catch (err) {
      if (err instanceof ApiError) {
        const detail =
          typeof err.body === 'object' &&
          err.body !== null &&
          'detail' in err.body
            ? String((err.body as { detail: unknown }).detail)
            : err.message
        setError(detail)
      } else {
        setError('Unexpected error. Is the backend running?')
      }
    } finally {
      setIsRunning(false)
    }
  }, [command, projectId, args, onSuccess])

  // Extra optional arguments shown per command
  const extraArgDefs: ReadonlyArray<ArgDef> =
    command.name === 'avg' || command.name === 'alignRaw' || command.name === 'tomoCPR'
      ? [{ key: 'cycle', label: 'Cycle Number', placeholder: '1' }]
      : []

  return (
    /* Backdrop */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      role="dialog"
      aria-modal="true"
      aria-labelledby="cmd-dialog-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="bg-white dark:bg-gray-900 rounded-xl shadow-2xl w-full max-w-md mx-4 p-6 space-y-4">
        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3
              id="cmd-dialog-title"
              className="text-lg font-semibold text-gray-900 dark:text-gray-100"
            >
              Run: {COMMAND_LABELS[command.name] ?? command.name}
            </h3>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{command.description}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="shrink-0 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 text-xl leading-none"
            aria-label="Close dialog"
          >
            ✕
          </button>
        </div>

        {/* Optional arguments */}
        {extraArgDefs.length > 0 && (
          <div className="space-y-3">
            <p className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
              Parameters (optional)
            </p>
            {extraArgDefs.map((argDef) => (
              <div key={argDef.key}>
                <label
                  htmlFor={`arg-${argDef.key}`}
                  className="block text-sm font-medium text-gray-700 dark:text-gray-300"
                >
                  {argDef.label}
                </label>
                <input
                  id={`arg-${argDef.key}`}
                  type="text"
                  placeholder={argDef.placeholder}
                  value={args[argDef.key] ?? ''}
                  onChange={(e) =>
                    setArgs((prev) => ({ ...prev, [argDef.key]: e.target.value }))
                  }
                  className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
                />
              </div>
            ))}
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-3 dark:border-red-800 dark:bg-red-900/20">
            <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
          </div>
        )}

        {/* Actions */}
        <div className="flex justify-end gap-3 pt-2">
          <button
            type="button"
            onClick={onClose}
            disabled={isRunning}
            className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => {
              void handleRun()
            }}
            disabled={isRunning}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-blue-500 dark:hover:bg-blue-600"
          >
            {isRunning ? 'Submitting…' : 'Run Command'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// CommandGrid – grid of all pipeline commands, enabled/disabled per state
// ---------------------------------------------------------------------------

interface CommandGridProps {
  availableCommands: ReadonlyArray<CommandEntry>
  allDescriptions: Record<string, string>
  projectId: string
  onCommandSuccess: (msg: string) => void
}

function CommandGrid({
  availableCommands,
  allDescriptions,
  projectId,
  onCommandSuccess,
}: CommandGridProps) {
  const [selectedCommand, setSelectedCommand] = useState<CommandEntry | null>(null)
  const availableNames = new Set(availableCommands.map((c) => c.name))

  const handleCommandClick = useCallback(
    (name: string) => {
      const entry = availableCommands.find((c) => c.name === name)
      if (entry) {
        setSelectedCommand(entry)
      }
    },
    [availableCommands],
  )

  const handleSuccess = useCallback(
    (msg: string) => {
      setSelectedCommand(null)
      onCommandSuccess(msg)
    },
    [onCommandSuccess],
  )

  return (
    <>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
        {ALL_COMMANDS.map((name) => {
          const isAvailable = availableNames.has(name)
          const description = allDescriptions[name] ?? ''
          const tooltip = isAvailable ? description : prerequisiteLabel(name)
          const label = COMMAND_LABELS[name] ?? name

          return (
            <div key={name} className="relative group">
              <button
                type="button"
                disabled={!isAvailable}
                onClick={() => {
                  if (isAvailable) handleCommandClick(name)
                }}
                aria-label={`${label}${isAvailable ? '' : ` (${tooltip})`}`}
                className={[
                  'w-full rounded-lg border px-3 py-3 text-left text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2',
                  isAvailable
                    ? 'border-blue-200 bg-blue-50 text-blue-800 hover:bg-blue-100 focus:ring-blue-500 dark:border-blue-700 dark:bg-blue-900/30 dark:text-blue-200 dark:hover:bg-blue-900/50'
                    : 'cursor-not-allowed border-gray-200 bg-gray-50 text-gray-400 dark:border-gray-700 dark:bg-gray-800/40 dark:text-gray-600',
                ].join(' ')}
              >
                <span className="block truncate">{label}</span>
                <span
                  className={[
                    'mt-1 block text-xs truncate',
                    isAvailable
                      ? 'text-blue-500 dark:text-blue-400'
                      : 'text-gray-400 dark:text-gray-600',
                  ].join(' ')}
                >
                  {name}
                </span>
              </button>

              {/* Tooltip */}
              {tooltip && (
                <div
                  role="tooltip"
                  className="pointer-events-none absolute bottom-full left-1/2 z-20 mb-2 -translate-x-1/2 rounded bg-gray-800 px-2 py-1 text-xs text-white opacity-0 transition-opacity group-hover:opacity-100 dark:bg-gray-700 whitespace-nowrap max-w-[200px] text-center"
                >
                  {tooltip}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Command dialog */}
      {selectedCommand && (
        <CommandDialog
          command={selectedCommand}
          projectId={projectId}
          onSuccess={handleSuccess}
          onClose={() => setSelectedCommand(null)}
        />
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// WorkflowContent – main content when a project is loaded
// ---------------------------------------------------------------------------

interface WorkflowContentProps {
  projectId: string
  stateMachine: StateMachine
}

function WorkflowContent({ projectId, stateMachine }: WorkflowContentProps) {
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const [refreshCounter, setRefreshCounter] = useState(0)

  const {
    data: cmdData,
    isLoading,
    error,
    refetch,
  } = useApiQuery<AvailableCommandsResponse>(
    ['workflow-commands', projectId, refreshCounter],
    `/api/v1/workflow/${projectId}/available-commands`,
  )

  // Auto-clear success message after 5 seconds
  useEffect(() => {
    if (!successMessage) return
    const timer = setTimeout(() => setSuccessMessage(null), 5000)
    return () => clearTimeout(timer)
  }, [successMessage])

  const handleCommandSuccess = useCallback(
    (msg: string) => {
      setSuccessMessage(msg)
      // Refresh available commands after execution
      setRefreshCounter((n) => n + 1)
      void refetch()
    },
    [refetch],
  )

  const currentState = cmdData?.state ?? 'UNINITIALIZED'
  const availableCommands: ReadonlyArray<CommandEntry> = cmdData?.commands ?? []

  // Build description map from available commands
  const allDescriptions: Record<string, string> = {}
  for (const cmd of availableCommands) {
    allDescriptions[cmd.name] = cmd.description
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
        <span className="ml-3 text-gray-500 dark:text-gray-400">Loading workflow state…</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-6 dark:border-red-800 dark:bg-red-900/20 space-y-3">
        <h3 className="font-semibold text-red-800 dark:text-red-200">Failed to load workflow</h3>
        <p className="text-sm text-red-600 dark:text-red-400">{error.message}</p>
      </div>
    )
  }

  const stateLabel = STATE_LABELS[currentState] ?? currentState

  return (
    <div className="space-y-8">
      {/* Project header */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide font-medium">
            Project ID
          </p>
          <p className="mt-0.5 font-mono text-sm text-gray-700 dark:text-gray-300">{projectId}</p>
        </div>
        <div className="text-right">
          <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide font-medium">
            Current State
          </p>
          <span className="mt-0.5 inline-block rounded-full bg-blue-100 px-3 py-0.5 text-sm font-semibold text-blue-800 dark:bg-blue-900/40 dark:text-blue-200">
            {stateLabel}
          </span>
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

      {/* Pipeline stepper */}
      <section aria-label="Pipeline progress">
        <h3 className="mb-4 text-base font-semibold text-gray-900 dark:text-gray-100">
          Pipeline Progress
        </h3>
        <div className="rounded-xl border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-900 overflow-x-auto">
          <PipelineStepper currentState={currentState} stateMachine={stateMachine} />
        </div>
      </section>

      {/* Commands */}
      <section aria-label="Pipeline commands">
        <div className="mb-4 flex items-baseline justify-between gap-4 flex-wrap">
          <div>
            <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">
              Commands
            </h3>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {availableCommands.length > 0
                ? `${String(availableCommands.length)} command${availableCommands.length !== 1 ? 's' : ''} available in current state.`
                : 'No commands available in current state.'}
            </p>
          </div>
          <button
            type="button"
            onClick={() => void refetch()}
            className="text-sm text-blue-600 hover:underline dark:text-blue-400"
          >
            ↻ Refresh
          </button>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-900">
          {currentState === 'DONE' ? (
            <div className="py-8 text-center">
              <p className="text-2xl">🎉</p>
              <p className="mt-2 font-medium text-gray-700 dark:text-gray-300">
                Processing complete!
              </p>
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                All pipeline stages have been completed.
              </p>
            </div>
          ) : (
            <CommandGrid
              availableCommands={availableCommands}
              allDescriptions={allDescriptions}
              projectId={projectId}
              onCommandSuccess={handleCommandSuccess}
            />
          )}
        </div>
      </section>

      {/* Legend */}
      <div className="flex flex-wrap gap-4 text-xs text-gray-500 dark:text-gray-400">
        <div className="flex items-center gap-1.5">
          <span className="inline-block h-3 w-3 rounded-sm bg-blue-100 border border-blue-200 dark:bg-blue-900/30 dark:border-blue-700" />
          Available – click to run
        </div>
        <div className="flex items-center gap-1.5">
          <span className="inline-block h-3 w-3 rounded-sm bg-gray-100 border border-gray-200 dark:bg-gray-800 dark:border-gray-700" />
          Unavailable – hover for prerequisite
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// WorkflowPage – main exported component
// ---------------------------------------------------------------------------

export function WorkflowPage() {
  // Project ID comes from the URL (/project/:projectId/actions)
  const { projectId } = useParams<{ projectId: string }>()
  const isDemo = projectId === DEMO_PROJECT_ID

  // Fetch state machine once – it's static
  const {
    data: stateMachine,
    isLoading: smLoading,
    error: smError,
  } = useApiQuery<StateMachine>(['workflow-state-machine'], '/api/v1/workflow/state-machine')

  // Guard: redirect to root if projectId is missing (shouldn't happen with nested routing)
  if (!projectId) {
    return <Navigate to="/" replace />
  }

  // Loading state machine
  if (smLoading) {
    return (
      <div className="space-y-4">
        <h2 className="text-2xl font-semibold">Workflow</h2>
        <div className="flex items-center gap-3 py-8">
          <div className="h-6 w-6 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
          <span className="text-gray-500 dark:text-gray-400">Loading pipeline definition…</span>
        </div>
      </div>
    )
  }

  if (smError ?? !stateMachine) {
    return (
      <div className="space-y-4">
        <h2 className="text-2xl font-semibold">Workflow</h2>
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-6 dark:border-amber-700 dark:bg-amber-900/20">
          <h3 className="font-semibold text-amber-800 dark:text-amber-200">
            Could not load state machine
          </h3>
          <p className="mt-1 text-sm text-amber-600 dark:text-amber-400">
            {smError?.message ?? 'Unknown error. Is the backend running?'}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold">Workflow</h2>
        <p className="mt-2 text-gray-500 dark:text-gray-400">
          Visualize and execute the emClarity processing pipeline.
        </p>
      </div>

      {isDemo ? (
        <div className="rounded-lg border border-gray-200 bg-gray-50 p-8 text-center dark:border-gray-700 dark:bg-gray-800/50">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            No project selected. Open a project to run pipeline commands.
          </p>
        </div>
      ) : (
        <WorkflowContent projectId={projectId} stateMachine={stateMachine} />
      )}
    </div>
  )
}
