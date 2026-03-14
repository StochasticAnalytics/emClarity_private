/**
 * SettingsPage – run profile configuration.
 *
 * Allows the user to define and manage run profiles: sets of emClarity
 * parameter presets that can be applied to processing steps.
 *
 * Route: /project/:projectId/settings
 */
import { useProject } from '@/context/ProjectContext.tsx'

export function SettingsPage() {
  const { projectId } = useProject()

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h2 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">Settings</h2>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Configure run profiles and processing parameters for project{' '}
          <code className="font-mono text-xs font-medium">{projectId ?? '—'}</code>.
        </p>
      </div>

      {/* Run profiles section */}
      <section
        className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-sm overflow-hidden"
        aria-labelledby="run-profiles-heading"
      >
        <div className="px-5 py-4 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
          <div>
            <h3
              id="run-profiles-heading"
              className="text-base font-semibold text-gray-900 dark:text-gray-100"
            >
              Run Profiles
            </h3>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
              Saved parameter presets for emClarity processing steps
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
            New Profile
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
                d="M10.343 3.94c.09-.542.56-.94 1.11-.94h1.093c.55 0 1.02.398 1.11.94l.149.894c.07.424.384.764.78.93.398.164.855.142 1.205-.108l.737-.527a1.125 1.125 0 011.45.12l.773.774c.39.389.44 1.002.12 1.45l-.527.737c-.25.35-.272.806-.107 1.204.165.397.505.71.93.78l.893.15c.543.09.94.56.94 1.109v1.094c0 .55-.397 1.02-.94 1.11l-.893.149c-.425.07-.765.383-.93.78-.165.398-.143.854.107 1.204l.527.738c.32.447.269 1.06-.12 1.45l-.774.773a1.125 1.125 0 01-1.449.12l-.738-.527c-.35-.25-.806-.272-1.203-.107-.397.165-.71.505-.781.929l-.149.894c-.09.542-.56.94-1.11.94h-1.094c-.55 0-1.019-.398-1.11-.94l-.148-.894c-.071-.424-.384-.764-.781-.93-.398-.164-.854-.142-1.204.108l-.738.527c-.447.32-1.06.269-1.45-.12l-.773-.774a1.125 1.125 0 01-.12-1.45l.527-.737c.25-.35.273-.806.108-1.204-.165-.397-.505-.71-.93-.78l-.894-.15c-.542-.09-.94-.56-.94-1.109v-1.094c0-.55.398-1.02.94-1.11l.894-.149c.424-.07.765-.383.93-.78.165-.398.143-.854-.107-1.204l-.527-.738a1.125 1.125 0 01.12-1.45l.773-.773a1.125 1.125 0 011.45-.12l.737.527c.35.25.807.272 1.204.107.397-.165.71-.505.78-.929l.15-.894z"
              />
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
              />
            </svg>
            <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">
              No run profiles defined
            </h4>
            <p className="text-sm text-gray-500 dark:text-gray-400 max-w-xs">
              Create a run profile to save parameter presets for emClarity processing steps.
              Profiles can be applied when running actions from the Actions panel.
            </p>
          </div>
        </div>
      </section>

      {/* Project parameter file section */}
      <section
        className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-sm overflow-hidden"
        aria-labelledby="param-file-heading"
      >
        <div className="px-5 py-4 border-b border-gray-200 dark:border-gray-700">
          <h3
            id="param-file-heading"
            className="text-base font-semibold text-gray-900 dark:text-gray-100"
          >
            Parameter File
          </h3>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            emClarity parameter file (param.m) for this project
          </p>
        </div>
        <div className="p-5">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Upload or edit the emClarity parameter file to configure processing options.
          </p>
        </div>
      </section>
    </div>
  )
}
