/**
 * AssetsPage – asset management panel.
 *
 * Displays tilt-series groups, imported movies, and raw data files
 * associated with the active project.
 *
 * Route: /project/:projectId/assets
 */
import { useProject } from '@/context/ProjectContext.tsx'

export function AssetsPage() {
  const { projectId } = useProject()

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h2 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">Assets</h2>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Manage tilt-series, movies, and raw data files for this project.
        </p>
      </div>

      {/* Tilt-Series section */}
      <section
        className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-sm overflow-hidden"
        aria-labelledby="tilt-series-heading"
      >
        <div className="px-5 py-4 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
          <div>
            <h3 id="tilt-series-heading" className="text-base font-semibold text-gray-900 dark:text-gray-100">
              Tilt Series
            </h3>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
              Imported tilt-series for project{' '}
              <code className="font-mono text-xs">{projectId ?? '—'}</code>
            </p>
          </div>
          <button
            type="button"
            className={
              'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium ' +
              'border border-gray-300 dark:border-gray-600 ' +
              'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 ' +
              'hover:bg-gray-50 dark:hover:bg-gray-700 ' +
              'focus:outline-none focus:ring-2 focus:ring-blue-500 ' +
              'transition-colors'
            }
          >
            Import Tilt Series
          </button>
        </div>

        {/* Empty state */}
        <div className="p-5">
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
                d="M3.75 9.776c.112-.017.227-.026.344-.026h15.812c.117 0 .232.009.344.026m-16.5 0a2.25 2.25 0 00-1.883 2.542l.857 6a2.25 2.25 0 002.227 1.932H19.05a2.25 2.25 0 002.227-1.932l.857-6a2.25 2.25 0 00-1.883-2.542m-16.5 0V6A2.25 2.25 0 016 3.75h3.879a1.5 1.5 0 011.06.44l2.122 2.12a1.5 1.5 0 001.06.44H18A2.25 2.25 0 0120.25 9v.776"
              />
            </svg>
            <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">
              No tilt series imported
            </h4>
            <p className="text-sm text-gray-500 dark:text-gray-400 max-w-xs">
              Import tilt-series data to begin processing. Supported formats: MRC stack (.st),
              raw frames (.mrc, .tif).
            </p>
          </div>
        </div>
      </section>
    </div>
  )
}
