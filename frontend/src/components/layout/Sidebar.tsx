/**
 * Sidebar navigation rail.
 *
 * Mimics the cisTEM MenuBook (wxListbook with wxLB_LEFT orientation):
 * a fixed vertical strip on the left with icons and text labels.
 *
 * When a project is active (/project/:projectId/*), all 7 section items are
 * rendered as active NavLinks. When no project is loaded (/), the items are
 * shown as disabled placeholders and the user is directed to open a project
 * first.
 *
 * Navigation items (matching cisTEM MenuBook order):
 *   Overview · Assets · Actions · Results · Settings · Jobs · Expert
 */
import { NavLink, useMatch, Link } from 'react-router-dom'
import {
  LayoutDashboard,
  Database,
  Zap,
  BarChart3,
  Settings,
  Activity,
  FlaskConical,
} from 'lucide-react'

// ---------------------------------------------------------------------------
// Nav item definitions
// ---------------------------------------------------------------------------

const NAV_ITEMS = [
  { path: 'overview', label: 'Overview', icon: LayoutDashboard },
  { path: 'assets', label: 'Assets', icon: Database },
  { path: 'actions', label: 'Actions', icon: Zap },
  { path: 'results', label: 'Results', icon: BarChart3 },
  { path: 'settings', label: 'Settings', icon: Settings },
  { path: 'jobs', label: 'Jobs', icon: Activity },
  { path: 'expert', label: 'Expert', icon: FlaskConical },
] as const

// ---------------------------------------------------------------------------
// Style helpers
// ---------------------------------------------------------------------------

const ACTIVE_CLASS =
  'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors ' +
  'bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300'

const INACTIVE_CLASS =
  'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors ' +
  'text-gray-600 hover:bg-gray-100 hover:text-gray-900 ' +
  'dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200'

const DISABLED_CLASS =
  'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium ' +
  'text-gray-300 dark:text-gray-600 cursor-not-allowed select-none'

function navLinkClass({ isActive }: { isActive: boolean }): string {
  return isActive ? ACTIVE_CLASS : INACTIVE_CLASS
}

// ---------------------------------------------------------------------------
// Sidebar component
// ---------------------------------------------------------------------------

/**
 * Sidebar navigation listing the major sections of the application.
 */
export function Sidebar() {
  // Detect project context from URL
  const projectMatch = useMatch('/project/:projectId/*')
  const projectId = projectMatch?.params.projectId ?? null

  return (
    <aside
      className="flex w-56 flex-col border-r border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900"
      aria-label="Application navigation"
    >
      {/* Branding header – clicking always goes to the landing page */}
      <div className="flex h-14 items-center border-b border-gray-200 px-4 dark:border-gray-800">
        <Link
          to="/"
          className="text-lg font-semibold tracking-tight text-gray-900 dark:text-gray-100 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
          aria-label="emClarity – go to home"
        >
          emClarity
        </Link>
      </div>

      <nav className="flex-1 space-y-1 p-2" aria-label="Main navigation">
        {NAV_ITEMS.map(({ path, label, icon: Icon }) =>
          projectId ? (
            // Active project: render navigable links
            <NavLink
              key={path}
              to={`/project/${projectId}/${path}`}
              className={navLinkClass}
            >
              <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
              <span>{label}</span>
            </NavLink>
          ) : (
            // No project: render disabled placeholders
            <span
              key={path}
              className={DISABLED_CLASS}
              title="Open a project to access this section"
              aria-disabled="true"
            >
              <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
              <span>{label}</span>
            </span>
          ),
        )}
      </nav>

      {/* Footer hint when no project is loaded */}
      {!projectId && (
        <div className="border-t border-gray-100 dark:border-gray-800 p-3">
          <p className="text-xs text-gray-400 dark:text-gray-600 text-center">
            Open a project to begin
          </p>
        </div>
      )}
    </aside>
  )
}
