/**
 * Overview page – project dashboard.
 *
 * Displays a summary of the active project: name, state, current cycle,
 * tilt-series count, particle count, and current resolution estimate.
 * Also shows a pipeline progress stepper (matching tutorial Figure 1)
 * and the last 5 recent jobs with status badges.
 *
 * API calls:
 *   GET /api/v1/projects/{id}                       – project state / cycle
 *   GET /api/v1/projects/{id}/statistics            – particle count, resolution
 *   GET /api/v1/workflow/{id}/available-commands    – current workflow state
 *   GET /api/v1/jobs?project_id={id}                – recent jobs list
 */
import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useProject } from '@/context/ProjectContext.tsx'
import { useApiQuery } from '@/hooks/useApi.ts'
import { useRecentProjects } from '@/hooks/useRecentProjects.ts'
import { DEMO_PROJECT_ID } from '@/constants'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ProjectDetails {
  id: string
  name: string
  directory: string
  state: string
  current_cycle: number
}

interface ProjectStatistics {
  project_id: string
  particle_count: number | null
  resolution_angstrom: number | null
  tilt_series_count: number
}

interface AvailableCommandsResponse {
  project_id: string
  state: string
  commands: { name: string; description: string }[]
}

type JobStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED'

interface Job {
  id: string
  project_id: string
  command: string
  status: JobStatus
  created_at: string
  updated_at: string
}

// ---------------------------------------------------------------------------
// Pipeline step definitions — 11 steps from emClarity tutorial Figure 1
// ---------------------------------------------------------------------------

interface PipelineStep {
  id: string
  label: string
  subtitle: string
  optional?: boolean
  /**
   * The minimum pipeline state index at which this step is considered "active"
   * when no job history is available.
   */
  activeFromStateIdx: number
  /** The minimum pipeline state index at which this step is considered "completed" */
  completedFromStateIdx: number
  /**
   * If set, this step is part of the iterative CYCLE_N phase.
   * Only one iterative step is shown as "active" at a time (determined by job history).
   */
  cycleStep?: boolean
  /**
   * The emClarity CLI command(s) associated with this step.
   * Used to match against recent jobs during CYCLE_N to find the active step.
   */
  commands?: string[]
}

/** Ordered states in the state machine, mapped to numeric indices for comparison. */
const STATE_ORDER: ReadonlyArray<string> = [
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

function stateIndex(state: string): number {
  const idx = STATE_ORDER.indexOf(state.toUpperCase())
  return idx === -1 ? 0 : idx
}

/**
 * 11-step pipeline from emClarity tutorial Figure 1.
 */
const TUTORIAL_PIPELINE_STEPS: ReadonlyArray<PipelineStep> = [
  {
    id: 'align-ts',
    label: 'Align Tilt-Series',
    subtitle: 'autoAlign',
    commands: ['autoAlign'],
    activeFromStateIdx: 0,
    completedFromStateIdx: 1,
  },
  {
    id: 'ctf-est',
    label: 'Estimate CTF',
    subtitle: 'ctf estimate',
    commands: ['ctf estimate'],
    activeFromStateIdx: 1,
    completedFromStateIdx: 2,
  },
  {
    id: 'sub-regions',
    label: 'Select Sub-regions',
    subtitle: 'segment',
    commands: ['segment'],
    activeFromStateIdx: 2,
    completedFromStateIdx: 3,
  },
  {
    id: 'pick',
    label: 'Pick Particles',
    subtitle: 'templateSearch',
    commands: ['templateSearch'],
    activeFromStateIdx: 3,
    completedFromStateIdx: 4,
  },
  {
    id: 'init',
    label: 'Initialize Project',
    subtitle: 'init',
    commands: ['init'],
    activeFromStateIdx: 4,
    completedFromStateIdx: 5,
  },
  {
    id: 'recon',
    label: 'Reconstruct Tomograms',
    subtitle: 'ctf 3d',
    commands: ['ctf 3d'],
    activeFromStateIdx: 5,
    completedFromStateIdx: 6,
  },
  {
    id: 'avg',
    label: 'Subtomogram Averaging',
    subtitle: 'avg',
    commands: ['avg'],
    activeFromStateIdx: 6,
    completedFromStateIdx: 7,
    cycleStep: true,
  },
  {
    id: 'align',
    label: 'Subtomogram Alignment',
    subtitle: 'alignRaw',
    commands: ['alignRaw'],
    activeFromStateIdx: 6,
    completedFromStateIdx: 7,
    cycleStep: true,
  },
  {
    id: 'tomocpr',
    label: 'Tilt-Series Refinement',
    subtitle: 'tomoCPR',
    commands: ['tomoCPR'],
    optional: true,
    activeFromStateIdx: 6,
    completedFromStateIdx: 7,
    cycleStep: true,
  },
  {
    id: 'classify',
    label: 'Classification',
    subtitle: 'pca / cluster',
    commands: ['pca', 'cluster'],
    optional: true,
    activeFromStateIdx: 6,
    completedFromStateIdx: 7,
    cycleStep: true,
  },
  {
    id: 'final',
    label: 'Final Reconstruction',
    subtitle: 'reconstruct',
    commands: ['reconstruct'],
    activeFromStateIdx: 7,
    completedFromStateIdx: 8,
  },
]

// ---------------------------------------------------------------------------
// Determine the active cycle step from recent jobs
// ---------------------------------------------------------------------------

/**
 * During CYCLE_N, determine which iterative step is "currently active"
 * by inspecting the most recent completed/running job.
 *
 * Logic:
 *  - If a job is currently RUNNING or PENDING, that command is active.
 *  - If the most recent COMPLETED job was `avg`, the next step is `alignRaw`.
 *  - If the most recent COMPLETED job was `alignRaw`, the next step is `avg`.
 *  - Default to `avg` (first step in the iteration) if no job history.
 *
 * Returns the step ID (from TUTORIAL_PIPELINE_STEPS) that should be "active".
 */
function getActiveCycleStepId(jobs: Job[]): string {
  if (jobs.length === 0) return 'avg'

  // Find the most recent job that is a cycle-relevant command
  const cycleCommands = new Set(['avg', 'alignRaw', 'tomoCPR', 'pca', 'cluster', 'fsc'])

  for (const job of jobs) {
    const cmd = job.command
    if (!cycleCommands.has(cmd)) continue

    if (job.status === 'RUNNING' || job.status === 'PENDING') {
      // Whichever command is currently running is the active step
      const stepId = commandToStepId(cmd)
      if (stepId !== null) return stepId
      continue
    }

    if (job.status === 'COMPLETED') {
      // The most recently completed step tells us what's next
      if (cmd === 'avg') return 'align'
      if (cmd === 'alignRaw') return 'avg'
      // For other completed commands, default to avg
      return 'avg'
    }
  }

  // Default: averaging is the first step in each cycle
  return 'avg'
}

function commandToStepId(command: string): string | null {
  switch (command) {
    // Pre-cycle linear steps
    case 'autoAlign': return 'align-ts'
    case 'ctf estimate': return 'ctf-est'
    case 'segment': return 'sub-regions'
    case 'templateSearch': return 'pick'
    case 'init': return 'init'
    case 'ctf 3d': return 'recon'
    // Iterative cycle steps
    case 'avg': return 'avg'
    case 'alignRaw': return 'align'
    case 'tomoCPR': return 'tomocpr'
    case 'pca':
    case 'cluster': return 'classify'
    // FSC — maps to avg step (resolution check performed alongside averaging)
    case 'fsc': return 'avg'
    // Post-cycle step
    case 'reconstruct': return 'final'
    default:
      return null
  }
}

// ---------------------------------------------------------------------------
// Status badge config for jobs
// ---------------------------------------------------------------------------

interface BadgeConfig {
  label: string
  className: string
}

const JOB_STATUS_BADGE: Record<JobStatus, BadgeConfig> = {
  PENDING: {
    label: 'Pending',
    className:
      'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ' +
      'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300',
  },
  RUNNING: {
    label: 'Running',
    className:
      'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ' +
      'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300',
  },
  COMPLETED: {
    label: 'Completed',
    className:
      'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ' +
      'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
  },
  FAILED: {
    label: 'Failed',
    className:
      'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ' +
      'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
  },
  CANCELLED: {
    label: 'Cancelled',
    className:
      'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ' +
      'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400',
  },
}

// ---------------------------------------------------------------------------
// StatCard
// ---------------------------------------------------------------------------

interface StatCardProps {
  label: string
  value: string
  sub?: string
  accent?: 'default' | 'blue' | 'green' | 'amber'
}

function StatCard({ label, value, sub, accent = 'default' }: StatCardProps) {
  const valueClass =
    accent === 'blue'
      ? 'text-blue-600 dark:text-blue-400'
      : accent === 'green'
        ? 'text-green-600 dark:text-green-400'
        : accent === 'amber'
          ? 'text-amber-600 dark:text-amber-400'
          : 'text-gray-900 dark:text-gray-100'

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900">
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
        {label}
      </p>
      <p className={`mt-1 text-lg font-semibold ${valueClass}`}>{value}</p>
      {sub && (
        <p className="mt-0.5 text-xs text-gray-400 dark:text-gray-500 truncate">{sub}</p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// PipelineProgressStepper – 11-step tutorial Figure 1 stepper
// ---------------------------------------------------------------------------

interface PipelineProgressStepperProps {
  /** Current workflow state string (e.g. "TILT_ALIGNED", "CYCLE_N") */
  currentState: string
  /** Recent jobs, used to determine which iterative step is active during CYCLE_N */
  recentJobs: Job[]
}

function PipelineProgressStepper({ currentState, recentJobs }: PipelineProgressStepperProps) {
  const currentIdx = stateIndex(currentState)
  const isCycleN = currentIdx === stateIndex('CYCLE_N')

  // During CYCLE_N, determine which specific iterative step is active
  const activeCycleStepId = isCycleN ? getActiveCycleStepId(recentJobs) : null

  return (
    <div className="w-full">
      {/* Scrollable horizontal stepper */}
      <div className="overflow-x-auto pb-2">
        <ol
          aria-label="Pipeline progress"
          className="flex items-start min-w-max gap-0"
        >
          {TUTORIAL_PIPELINE_STEPS.map((step, idx) => {
            const isCompleted = currentIdx >= step.completedFromStateIdx

            let isActive: boolean
            if (step.cycleStep && isCycleN && !isCompleted) {
              // During CYCLE_N, only the determined active cycle step is shown as active
              isActive = step.id === activeCycleStepId
            } else {
              // For non-cycle steps, use the normal threshold logic
              isActive =
                !isCompleted &&
                currentIdx >= step.activeFromStateIdx &&
                (idx === 0 ||
                  currentIdx >= TUTORIAL_PIPELINE_STEPS[idx - 1].activeFromStateIdx)
            }

            const isLast = idx === TUTORIAL_PIPELINE_STEPS.length - 1

            return (
              <li
                key={step.id}
                className="flex items-start"
                aria-current={isActive ? 'step' : undefined}
              >
                {/* Step content */}
                <div className="flex flex-col items-center w-20">
                  {/* Circle */}
                  <div
                    className={[
                      'w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold border-2 z-10 transition-colors shrink-0',
                      isCompleted
                        ? 'bg-green-500 border-green-500 text-white'
                        : isActive
                          ? 'bg-blue-600 border-blue-600 text-white ring-4 ring-blue-100 dark:ring-blue-900/60'
                          : 'bg-white dark:bg-gray-800 border-gray-300 dark:border-gray-600 text-gray-400 dark:text-gray-500',
                    ].join(' ')}
                    title={`${step.label}${step.optional ? ' (optional)' : ''} — ${step.subtitle}`}
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
                      'mt-2 text-xs font-medium text-center leading-tight px-1',
                      isCompleted
                        ? 'text-green-600 dark:text-green-400'
                        : isActive
                          ? 'text-blue-600 dark:text-blue-400'
                          : 'text-gray-400 dark:text-gray-500',
                    ].join(' ')}
                  >
                    {step.label}
                  </span>

                  {/* Subtitle (command name) */}
                  <span
                    className={[
                      'mt-0.5 text-[10px] font-mono text-center leading-tight px-1',
                      isCompleted
                        ? 'text-green-500 dark:text-green-500'
                        : isActive
                          ? 'text-blue-400 dark:text-blue-500'
                          : 'text-gray-300 dark:text-gray-600',
                    ].join(' ')}
                  >
                    {step.optional ? `[${step.subtitle}]` : step.subtitle}
                  </span>
                </div>

                {/* Connector line */}
                {!isLast && (
                  <div
                    className={[
                      'w-4 h-0.5 mt-4 shrink-0',
                      isCompleted ? 'bg-green-400' : 'bg-gray-200 dark:bg-gray-700',
                    ].join(' ')}
                    aria-hidden="true"
                  />
                )}
              </li>
            )
          })}
        </ol>
      </div>

      {/* Legend */}
      <div className="mt-3 flex flex-wrap gap-4 text-xs text-gray-500 dark:text-gray-400">
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded-full bg-green-500 shrink-0" />
          Completed
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded-full bg-blue-600 ring-2 ring-blue-100 dark:ring-blue-900 shrink-0" />
          Current
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded-full bg-white dark:bg-gray-800 border-2 border-gray-300 dark:border-gray-600 shrink-0" />
          Upcoming
        </div>
        <div className="flex items-center gap-1.5">
          <span className="font-mono">[…]</span>
          Optional step
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// RecentJobsSection
// ---------------------------------------------------------------------------

interface RecentJobsSectionProps {
  projectId: string
  onJobsLoaded?: (jobs: Job[]) => void
}

function RecentJobsSection({ projectId, onJobsLoaded }: RecentJobsSectionProps) {
  const { data: allJobs, isLoading, isError } = useApiQuery<Job[]>(
    ['overview-recent-jobs', projectId],
    `/api/v1/jobs?project_id=${projectId}`,
  )

  const recentJobs = allJobs ? allJobs.slice(0, 5) : []

  // Notify parent of loaded jobs (for stepper)
  useEffect(() => {
    if (allJobs && onJobsLoaded) {
      onJobsLoaded(allJobs)
    }
  }, [allJobs, onJobsLoaded])

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-4 text-sm text-gray-500 dark:text-gray-400">
        <div className="h-4 w-4 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
        Loading recent jobs…
      </div>
    )
  }

  if (isError) {
    return (
      <p className="py-4 text-sm text-red-600 dark:text-red-400">
        Failed to load recent jobs. Check that the backend is running.
      </p>
    )
  }

  if (recentJobs.length === 0) {
    return (
      <p className="py-4 text-sm text-gray-500 dark:text-gray-400">
        No jobs yet. Run pipeline commands from the{' '}
        <Link
          to={`/project/${projectId}/actions`}
          className="text-blue-600 hover:underline dark:text-blue-400"
        >
          Actions
        </Link>{' '}
        page to see jobs here.
      </p>
    )
  }

  return (
    <div className="divide-y divide-gray-100 dark:divide-gray-800 rounded-lg border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
      {recentJobs.map((job) => {
        const badge = JOB_STATUS_BADGE[job.status] ?? JOB_STATUS_BADGE['PENDING']
        const timeAgo = formatRelativeTime(job.created_at)

        return (
          <div key={job.id} className="flex items-center justify-between gap-3 px-4 py-3">
            <div className="min-w-0 flex-1">
              <span className="block truncate font-mono text-sm font-medium text-gray-900 dark:text-gray-100">
                {job.command}
              </span>
              <span className="text-xs text-gray-400 dark:text-gray-500">{timeAgo}</span>
            </div>
            <span className={badge.className}>{badge.label}</span>
          </div>
        )
      })}
      <div className="px-4 py-2">
        <Link
          to={`/project/${projectId}/jobs`}
          className="text-xs text-blue-600 hover:underline dark:text-blue-400"
        >
          View all jobs →
        </Link>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatRelativeTime(iso: string): string {
  try {
    const ms = Date.now() - new Date(iso).getTime()
    const seconds = Math.floor(ms / 1000)
    if (seconds < 60) return 'just now'
    const minutes = Math.floor(seconds / 60)
    if (minutes < 60) return `${minutes}m ago`
    const hours = Math.floor(minutes / 60)
    if (hours < 24) return `${hours}h ago`
    const days = Math.floor(hours / 24)
    return `${days}d ago`
  } catch {
    return iso
  }
}

// ---------------------------------------------------------------------------
// OverviewPage component
// ---------------------------------------------------------------------------

export function OverviewPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const { activeProject } = useProject()
  const { addProject } = useRecentProjects()
  const isDemo = projectId === DEMO_PROJECT_ID

  // Jobs state for stepper (populated by RecentJobsSection)
  const [allJobs, setAllJobs] = useState<Job[]>([])

  const { data: project, isLoading: projectLoading, isError: projectError } = useApiQuery<ProjectDetails>(
    ['project-details', projectId ?? ''],
    `/api/v1/projects/${projectId ?? ''}`,
    { enabled: !!projectId && !isDemo },
  )

  const { data: statistics, isLoading: statsLoading, isError: statsError } = useApiQuery<ProjectStatistics>(
    ['project-statistics', projectId ?? ''],
    `/api/v1/projects/${projectId ?? ''}/statistics`,
    { enabled: !!projectId && !isDemo },
  )

  const { data: workflowData, isError: workflowError } = useApiQuery<AvailableCommandsResponse>(
    ['overview-workflow-state', projectId ?? ''],
    `/api/v1/workflow/${projectId ?? ''}/available-commands`,
    { enabled: !!projectId && !isDemo },
  )

  // Track this project in recent projects when it loads
  useEffect(() => {
    if (project && projectId) {
      addProject({
        id: projectId,
        name: project.name,
        directory: project.directory,
      })
    }
  }, [project, projectId, addProject])

  const isLoading = projectLoading || statsLoading
  const isError = projectError || statsError

  const displayName = activeProject?.name ?? project?.name ?? (isDemo ? null : projectId) ?? '—'
  const state = workflowData?.state ?? activeProject?.state ?? project?.state ?? 'UNINITIALIZED'
  const cycle = project?.current_cycle

  const tiltCount = statistics?.tilt_series_count
  const particleCount = statistics?.particle_count
  const resolution = statistics?.resolution_angstrom

  // State badge colour
  const stateBadgeClass =
    state === 'DONE'
      ? 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300'
      : state === 'CYCLE_N'
        ? 'bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-300'
        : state !== 'UNINITIALIZED'
          ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300'
          : 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300'

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h2 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">Overview</h2>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Project summary, pipeline progress, and recent activity.
        </p>
      </div>

      {isLoading ? (
        <div className="flex items-center gap-3 py-8">
          <div className="h-6 w-6 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
          <span className="text-gray-500 dark:text-gray-400">Loading project details…</span>
        </div>
      ) : isError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-6 dark:border-red-800 dark:bg-red-900/20">
          <h3 className="text-sm font-semibold text-red-800 dark:text-red-300">
            Failed to load project data
          </h3>
          <p className="mt-1 text-sm text-red-700 dark:text-red-400">
            Could not fetch project details from the server. Check that the backend is running and the project ID is valid.
          </p>
        </div>
      ) : (
        <>
          {/* Project identity card */}
          <div className="rounded-lg border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-900">
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div className="min-w-0">
                <h3 className="text-xl font-semibold text-gray-900 dark:text-gray-100 truncate">
                  {displayName}
                </h3>
                {project?.directory && (
                  <p className="mt-1 break-all font-mono text-xs text-gray-500 dark:text-gray-400">
                    {project.directory}
                  </p>
                )}
              </div>
              {/* State badge */}
              <span
                className={`inline-flex items-center rounded-full px-3 py-1 text-sm font-semibold shrink-0 ${stateBadgeClass}`}
              >
                {state}
              </span>
            </div>
          </div>

          {/* Quick stats */}
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
            <StatCard
              label="State"
              value={state}
              accent={
                state === 'DONE' ? 'green' : state !== 'UNINITIALIZED' ? 'blue' : 'default'
              }
            />
            <StatCard
              label="Current Cycle"
              value={cycle !== undefined ? String(cycle) : '—'}
            />
            <StatCard
              label="Tilt Series"
              value={tiltCount !== undefined ? String(tiltCount) : '—'}
            />
            <StatCard
              label="Particles"
              value={particleCount !== null && particleCount !== undefined ? String(particleCount) : '—'}
              sub={statistics !== undefined && particleCount === null ? 'Available after picking' : undefined}
            />
            <StatCard
              label="Resolution"
              value={resolution !== null && resolution !== undefined ? `${resolution} Å` : '—'}
              sub={statistics !== undefined && resolution === null ? 'Available after averaging' : undefined}
              accent={resolution !== null && resolution !== undefined ? 'green' : 'default'}
            />
          </div>

          {/* Pipeline progress stepper */}
          <section aria-labelledby="pipeline-heading">
            <div className="mb-3 flex items-center justify-between gap-4">
              <h3
                id="pipeline-heading"
                className="text-base font-semibold text-gray-900 dark:text-gray-100"
              >
                Pipeline Progress
              </h3>
              <Link
                to={`/project/${projectId ?? ''}/actions`}
                className="text-sm text-blue-600 hover:underline dark:text-blue-400"
              >
                Run commands →
              </Link>
            </div>
            <div className="rounded-xl border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-900">
              <PipelineProgressStepper currentState={state} recentJobs={allJobs} />
            </div>
          </section>

          {/* Recent jobs */}
          <section aria-labelledby="recent-jobs-heading">
            <div className="mb-3 flex items-center justify-between gap-4">
              <h3
                id="recent-jobs-heading"
                className="text-base font-semibold text-gray-900 dark:text-gray-100"
              >
                Recent Jobs
              </h3>
              <Link
                to={`/project/${projectId ?? ''}/jobs`}
                className="text-sm text-blue-600 hover:underline dark:text-blue-400"
              >
                View all →
              </Link>
            </div>
            {projectId && !isDemo && (
              <RecentJobsSection
                projectId={projectId}
                onJobsLoaded={setAllJobs}
              />
            )}
          </section>
        </>
      )}
    </div>
  )
}
