/**
 * OverviewPage – project dashboard.
 *
 * Displays a high-level summary of the active project: pipeline progress,
 * recent job activity, and quick-access action buttons.
 *
 * This is the default landing page for a project route
 * (/project/:projectId/overview).
 */
import { useProject } from '@/context/ProjectContext.tsx'

export function OverviewPage() {
  const { activeProject, projectId } = useProject()

  const displayName = activeProject?.name ?? projectId ?? 'Unknown'
  const displayState = activeProject?.state ?? 'unknown'

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h2 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">Overview</h2>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Project dashboard for <span className="font-medium text-gray-700 dark:text-gray-300">{displayName}</span>
        </p>
      </div>

      {/* Status summary */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-sm px-5 py-4">
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
            Project ID
          </p>
          <p className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100 font-mono truncate">
            {projectId ?? '—'}
          </p>
        </div>

        <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-sm px-5 py-4">
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
            Status
          </p>
          <p className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100 capitalize">
            {displayState}
          </p>
        </div>

        <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-sm px-5 py-4">
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
            Project Name
          </p>
          <p className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100 truncate">
            {displayName}
          </p>
        </div>
      </div>

      {/* Pipeline progress placeholder */}
      <section
        className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-sm overflow-hidden"
        aria-labelledby="pipeline-heading"
      >
        <div className="px-5 py-4 border-b border-gray-200 dark:border-gray-700">
          <h3 id="pipeline-heading" className="text-base font-semibold text-gray-900 dark:text-gray-100">
            Pipeline Progress
          </h3>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            emClarity processing stages
          </p>
        </div>
        <div className="p-5">
          <ol className="space-y-2">
            {[
              'Align Tilt-Series',
              'Estimate CTF',
              'Select Sub-regions',
              'Pick Particles',
              'Initialize Project',
              'Reconstruct Tomograms',
              'Subtomogram Averaging',
              'Subtomogram Alignment',
              'Tilt-Series Refinement',
              'Classification',
              'Final Reconstruction',
            ].map((step, i) => (
              <li
                key={step}
                className="flex items-center gap-3 text-sm text-gray-600 dark:text-gray-400"
              >
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-gray-300 dark:border-gray-600 text-xs font-medium text-gray-500 dark:text-gray-400">
                  {i + 1}
                </span>
                {step}
              </li>
            ))}
          </ol>
        </div>
      </section>
    </div>
  )
}
