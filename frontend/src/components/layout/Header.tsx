/**
 * Top header bar displayed above the main content area.
 *
 * Shows:
 *  - Application subtitle / microscope icon on the left
 *  - Active project name + state badge in the centre (when a project is loaded)
 *  - Settings gear icon that opens the SystemInfoPanel on the right
 */
import { useState } from 'react'
import { Microscope, Settings } from 'lucide-react'
import { useProject } from '@/context/ProjectContext.tsx'
import { SystemInfoPanel } from './SystemInfoPanel.tsx'

// ---------------------------------------------------------------------------
// State badge colour mapping
// ---------------------------------------------------------------------------

const STATE_BADGE_CLASSES: Record<string, string> = {
  UNINITIALIZED:
    'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300',
  INITIALIZED:
    'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  TILT_ALIGNED:
    'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  CTF_ESTIMATED:
    'bg-teal-100 text-teal-700 dark:bg-teal-900/40 dark:text-teal-300',
  AVG_COMPLETE:
    'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
}

const DEFAULT_BADGE_CLASS =
  'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300'

function stateBadgeClass(state: string): string {
  return STATE_BADGE_CLASSES[state.toUpperCase()] ?? DEFAULT_BADGE_CLASS
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function Header() {
  const { activeProject } = useProject()
  const [showSystemInfo, setShowSystemInfo] = useState(false)

  return (
    <>
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-gray-200 bg-white px-6 dark:border-gray-800 dark:bg-gray-900">
        {/* Left: application subtitle */}
        <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
          <Microscope className="h-4 w-4 shrink-0" />
          <span className="hidden sm:inline">Cryo-EM Sub-Tomogram Averaging</span>
        </div>

        {/* Centre: active project name + state badge */}
        {activeProject ? (
          <div className="flex items-center gap-2 truncate">
            <span
              className="max-w-[140px] truncate text-sm font-medium text-gray-800 dark:text-gray-200 sm:max-w-xs"
              title={activeProject.name}
            >
              {activeProject.name}
            </span>
            <span
              className={`inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-xs font-medium ${stateBadgeClass(activeProject.state)}`}
            >
              {activeProject.state}
            </span>
            {activeProject.current_cycle !== undefined && activeProject.current_cycle > 0 && (
              <span
                className="inline-flex shrink-0 items-center rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300"
                title="Current refinement cycle"
              >
                Cycle {activeProject.current_cycle}
              </span>
            )}
          </div>
        ) : (
          <span className="text-xs text-gray-400 dark:text-gray-500">
            emClarity GUI
          </span>
        )}

        {/* Right: settings / system info */}
        <button
          type="button"
          onClick={() => setShowSystemInfo(true)}
          aria-label="Open system information"
          className="rounded-md p-1.5 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:hover:bg-gray-800 dark:hover:text-gray-300"
        >
          <Settings className="h-4 w-4" />
        </button>
      </header>

      {/* System info slide-in panel */}
      {showSystemInfo && (
        <SystemInfoPanel onClose={() => setShowSystemInfo(false)} />
      )}
    </>
  )
}
