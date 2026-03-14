/**
 * Sidebar – cisTEM-style vertical navigation rail.
 *
 * When no project is active (URL is `/`) a brief prompt is shown.
 * When inside a `/project/:projectId/*` route the 7 main nav items are shown
 * and the active item is highlighted.
 *
 * Nav items mirror the cisTEM MenuBook order:
 *   Overview · Assets · Actions · Results · Settings · Jobs · Expert
 */
import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  Database,
  Play,
  BarChart3,
  SlidersHorizontal,
  Activity,
  FlaskConical,
} from 'lucide-react'
import { useProject } from '@/context/ProjectContext.tsx'

const NAV_ITEMS = [
  { tab: 'overview', label: 'Overview', icon: LayoutDashboard },
  { tab: 'assets', label: 'Assets', icon: Database },
  { tab: 'actions', label: 'Actions', icon: Play },
  { tab: 'results', label: 'Results', icon: BarChart3 },
  { tab: 'settings', label: 'Settings', icon: SlidersHorizontal },
  { tab: 'jobs', label: 'Jobs', icon: Activity },
  { tab: 'expert', label: 'Expert', icon: FlaskConical },
] as const

/**
 * Sidebar navigation listing the major sections of the application.
 * Uses `useProject()` to obtain the active `projectId` for building hrefs.
 */
export function Sidebar() {
  const { projectId } = useProject()

  return (
    <aside className="flex w-56 flex-col border-r border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
      {/* Brand header */}
      <div className="flex h-14 items-center border-b border-gray-200 px-4 dark:border-gray-800">
        <h1 className="text-lg font-semibold tracking-tight">emClarity</h1>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 p-2" aria-label="Main navigation">
        {projectId ? (
          NAV_ITEMS.map(({ tab, label, icon: Icon }) => (
            <NavLink
              key={tab}
              to={`/project/${projectId}/${tab}`}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300'
                    : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200'
                }`
              }
            >
              <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
              {label}
            </NavLink>
          ))
        ) : (
          /* No active project – disabled nav placeholder */
          <div className="space-y-1">
            {NAV_ITEMS.map(({ tab, label, icon: Icon }) => (
              <div
                key={tab}
                className="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-gray-300 dark:text-gray-600 cursor-not-allowed select-none"
                title="Open a project to enable navigation"
              >
                <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                {label}
              </div>
            ))}
            <p className="mt-3 px-3 text-xs text-gray-400 dark:text-gray-600">
              Open a project to enable navigation
            </p>
          </div>
        )}
      </nav>
    </aside>
  )
}
