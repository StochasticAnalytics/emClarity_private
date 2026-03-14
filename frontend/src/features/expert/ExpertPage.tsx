/**
 * ExpertPage – expert and experimental options.
 *
 * Exposes advanced emClarity configuration options that are not shown in the
 * main workflow panels. Intended for power users who need fine-grained
 * control over processing parameters.
 *
 * Route: /project/:projectId/expert
 */
import { useProject } from '@/context/ProjectContext.tsx'

export function ExpertPage() {
  const { projectId } = useProject()

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h2 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">Expert</h2>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Advanced options and experimental features for project{' '}
          <code className="font-mono text-xs font-medium">{projectId ?? '—'}</code>.
        </p>
      </div>

      {/* Warning banner */}
      <div className="rounded-lg border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20 p-4">
        <div className="flex gap-3">
          <svg
            className="w-5 h-5 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5"
            viewBox="0 0 20 20"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fillRule="evenodd"
              d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z"
              clipRule="evenodd"
            />
          </svg>
          <div>
            <h3 className="text-sm font-semibold text-amber-800 dark:text-amber-300">
              Expert Mode
            </h3>
            <p className="text-sm text-amber-700 dark:text-amber-400 mt-0.5">
              These options modify low-level emClarity behavior. Incorrect settings can produce
              scientifically invalid results. Only modify these parameters if you understand their
              effects.
            </p>
          </div>
        </div>
      </div>

      {/* Expert options sections */}
      <section
        className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-sm overflow-hidden"
        aria-labelledby="expert-gpu-heading"
      >
        <div className="px-5 py-4 border-b border-gray-200 dark:border-gray-700">
          <h3
            id="expert-gpu-heading"
            className="text-base font-semibold text-gray-900 dark:text-gray-100"
          >
            GPU & Memory
          </h3>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            GPU selection, memory limits, and parallel job settings
          </p>
        </div>
        <div className="p-5">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Advanced GPU and memory configuration options will be available here.
          </p>
        </div>
      </section>

      <section
        className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-sm overflow-hidden"
        aria-labelledby="expert-sampling-heading"
      >
        <div className="px-5 py-4 border-b border-gray-200 dark:border-gray-700">
          <h3
            id="expert-sampling-heading"
            className="text-base font-semibold text-gray-900 dark:text-gray-100"
          >
            Sampling & Resolution
          </h3>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            Angular sampling rates, resolution shells, and convergence criteria
          </p>
        </div>
        <div className="p-5">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Advanced sampling and resolution parameters will be available here.
          </p>
        </div>
      </section>

      <section
        className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-sm overflow-hidden"
        aria-labelledby="expert-debug-heading"
      >
        <div className="px-5 py-4 border-b border-gray-200 dark:border-gray-700">
          <h3
            id="expert-debug-heading"
            className="text-base font-semibold text-gray-900 dark:text-gray-100"
          >
            Diagnostics
          </h3>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            Debugging flags, verbose logging, and diagnostic output options
          </p>
        </div>
        <div className="p-5">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Diagnostic and debug options will be available here.
          </p>
        </div>
      </section>
    </div>
  )
}
