/**
 * Overview page – project dashboard.
 *
 * Displays a summary of the active project: name, state, current cycle,
 * and tilt-series count. This is the default landing page for a project
 * (equivalent to cisTEM's MyOverviewPanel).
 *
 * The project data is already loaded by ProjectLayout via ProjectContext.
 * This page fetches additional details (tilt-series count) on its own.
 *
 * API calls:
 *   GET /api/v1/projects/{id}              – project state / cycle
 *   GET /api/v1/projects/{id}/tilt-series  – tilt-series list (for count)
 */
import { useParams, Link } from 'react-router-dom'
import { useProject } from '@/context/ProjectContext.tsx'
import { useApiQuery } from '@/hooks/useApi.ts'

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

interface TiltSeriesListResponse {
  tilt_series: { name: string }[]
}

// ---------------------------------------------------------------------------
// Stat card
// ---------------------------------------------------------------------------

interface StatCardProps {
  label: string
  value: string
  sub?: string
}

function StatCard({ label, value, sub }: StatCardProps) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900">
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
        {label}
      </p>
      <p className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100">{value}</p>
      {sub && (
        <p className="mt-0.5 text-xs text-gray-400 dark:text-gray-500 truncate">{sub}</p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Quick navigation cards
// ---------------------------------------------------------------------------

interface QuickNavCardProps {
  to: string
  title: string
  description: string
}

function QuickNavCard({ to, title, description }: QuickNavCardProps) {
  return (
    <Link
      to={to}
      className="group block rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900 hover:border-blue-300 dark:hover:border-blue-600 hover:shadow-sm transition-all"
    >
      <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
        {title} →
      </h4>
      <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{description}</p>
    </Link>
  )
}

// ---------------------------------------------------------------------------
// OverviewPage component
// ---------------------------------------------------------------------------

export function OverviewPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const { activeProject } = useProject()

  const {
    data: project,
    isLoading: projectLoading,
  } = useApiQuery<ProjectDetails>(
    ['project-details', projectId ?? ''],
    `/api/v1/projects/${projectId ?? ''}`,
    { enabled: !!projectId },
  )

  const {
    data: tiltsData,
    isLoading: tiltsLoading,
  } = useApiQuery<TiltSeriesListResponse>(
    ['project-tilt-series-count', projectId ?? ''],
    `/api/v1/projects/${projectId ?? ''}/tilt-series`,
    { enabled: !!projectId },
  )

  const isLoading = projectLoading || tiltsLoading
  const displayName = activeProject?.name ?? project?.name ?? projectId ?? '—'
  const state = activeProject?.state ?? project?.state ?? '—'
  const cycle = project?.current_cycle
  const tiltCount = tiltsData?.tilt_series.length

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h2 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">Overview</h2>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Project summary and quick navigation.
        </p>
      </div>

      {isLoading ? (
        <div className="flex items-center gap-3 py-8">
          <div className="h-6 w-6 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
          <span className="text-gray-500 dark:text-gray-400">Loading project details…</span>
        </div>
      ) : (
        <>
          {/* Project identity */}
          <div className="rounded-lg border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-900">
            <h3 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
              {displayName}
            </h3>
            {project?.directory && (
              <p className="mt-1 break-all font-mono text-xs text-gray-500 dark:text-gray-400">
                {project.directory}
              </p>
            )}
          </div>

          {/* Status summary cards */}
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            <StatCard label="State" value={state} />
            <StatCard
              label="Current Cycle"
              value={cycle !== undefined ? String(cycle) : '—'}
            />
            <StatCard
              label="Tilt Series"
              value={tiltCount !== undefined ? String(tiltCount) : '—'}
            />
          </div>

          {/* Quick navigation */}
          <section aria-labelledby="quick-nav-heading">
            <h3
              id="quick-nav-heading"
              className="mb-3 text-sm font-medium text-gray-700 dark:text-gray-300"
            >
              Quick Navigation
            </h3>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <QuickNavCard
                to={`/project/${projectId ?? ''}/assets`}
                title="Assets"
                description="View and manage tilt-series data sets"
              />
              <QuickNavCard
                to={`/project/${projectId ?? ''}/actions`}
                title="Actions"
                description="Run processing pipeline commands"
              />
              <QuickNavCard
                to={`/project/${projectId ?? ''}/results`}
                title="Results"
                description="View FSC curves and particle statistics"
              />
              <QuickNavCard
                to={`/project/${projectId ?? ''}/settings`}
                title="Settings"
                description="Configure processing parameters"
              />
              <QuickNavCard
                to={`/project/${projectId ?? ''}/jobs`}
                title="Jobs"
                description="Monitor running and completed jobs"
              />
              <QuickNavCard
                to={`/project/${projectId ?? ''}/expert`}
                title="Expert"
                description="Advanced tools and utilities"
              />
            </div>
          </section>
        </>
      )}
    </div>
  )
}
