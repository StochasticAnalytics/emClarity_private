/**
 * Sidebar navigation rail.
 *
 * Mimics the cisTEM MenuBook (wxListbook with wxLB_LEFT orientation):
 * a fixed vertical strip on the left with icons and text labels.
 *
 * Features:
 * - Collapsed mode: icon-only rail (40px wide) with tooltip on hover
 * - Expanded mode: icon + label (224px wide) — default
 * - Toggle button at the bottom of the rail
 * - Disabled placeholders when no project is loaded
 * - Active highlight on the current route
 *
 * Navigation items (matching cisTEM MenuBook order):
 *   Overview · Assets · Actions · Results · Settings · Jobs · Expert
 */
import { useState } from 'react'
import { NavLink, useMatch, Link } from 'react-router-dom'
import {
  LayoutDashboard,
  Database,
  Zap,
  BarChart3,
  Settings,
  Activity,
  FlaskConical,
  ChevronLeft,
  ChevronRight,
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
// NavItem component — handles active/inactive/disabled states
// ---------------------------------------------------------------------------

interface NavItemProps {
  path: string
  label: string
  icon: React.ComponentType<{ className?: string; 'aria-hidden'?: boolean }>
  projectId: string | null
  collapsed: boolean
}

function NavItem({ path, label, icon: Icon, projectId, collapsed }: NavItemProps) {
  if (!projectId) {
    // No project: disabled placeholder
    return (
      <span
        className={[
          'flex items-center rounded-md text-sm font-medium',
          'text-gray-300 dark:text-gray-600 cursor-not-allowed select-none',
          collapsed ? 'justify-center p-2' : 'gap-3 px-3 py-2',
        ].join(' ')}
        title={collapsed ? label : 'Open a project to access this section'}
        aria-label={collapsed ? label : undefined}
        aria-disabled="true"
      >
        <Icon className="h-4 w-4 shrink-0" aria-hidden />
        {!collapsed && <span>{label}</span>}
      </span>
    )
  }

  return (
    <NavLink
      to={`/project/${projectId}/${path}`}
      title={collapsed ? label : undefined}
      aria-label={collapsed ? label : undefined}
      className={({ isActive }) =>
        [
          'flex items-center rounded-md text-sm font-medium transition-colors',
          collapsed ? 'justify-center p-2' : 'gap-3 px-3 py-2',
          isActive
            ? 'bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300'
            : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200',
        ].join(' ')
      }
    >
      <Icon className="h-4 w-4 shrink-0" aria-hidden />
      {!collapsed && <span>{label}</span>}
    </NavLink>
  )
}

// ---------------------------------------------------------------------------
// Sidebar component
// ---------------------------------------------------------------------------

/**
 * Sidebar navigation listing the major sections of the application.
 */
export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false)

  // Detect project context from URL
  const projectMatch = useMatch('/project/:projectId/*')
  const projectId = projectMatch?.params.projectId ?? null

  return (
    <aside
      className={[
        'flex flex-col border-r border-gray-200 bg-white transition-all duration-200',
        'dark:border-gray-800 dark:bg-gray-900',
        collapsed ? 'w-12' : 'w-56',
      ].join(' ')}
      aria-label="Application navigation"
    >
      {/* Branding header – clicking always goes to the landing page */}
      <div
        className={[
          'flex h-14 items-center border-b border-gray-200 dark:border-gray-800',
          collapsed ? 'justify-center px-1' : 'px-4',
        ].join(' ')}
      >
        {collapsed ? (
          <Link
            to="/"
            className="text-sm font-bold text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 transition-colors"
            aria-label="emClarity – go to home"
            title="emClarity"
          >
            eC
          </Link>
        ) : (
          <Link
            to="/"
            className="text-lg font-semibold tracking-tight text-gray-900 dark:text-gray-100 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
            aria-label="emClarity – go to home"
          >
            emClarity
          </Link>
        )}
      </div>

      {/* Navigation items */}
      <nav
        className={['flex-1 space-y-1 p-2', collapsed && 'flex flex-col items-center'].filter(Boolean).join(' ')}
        aria-label="Main navigation"
      >
        {NAV_ITEMS.map(({ path, label, icon }) => (
          <NavItem
            key={path}
            path={path}
            label={label}
            icon={icon}
            projectId={projectId}
            collapsed={collapsed}
          />
        ))}
      </nav>

      {/* Footer: footer hint + collapse toggle */}
      <div className="border-t border-gray-100 dark:border-gray-800">
        {/* Hint text – only when expanded and no project */}
        {!collapsed && !projectId && (
          <p className="px-3 pt-2 text-xs text-gray-400 dark:text-gray-600 text-center">
            Open a project to begin
          </p>
        )}

        {/* Collapse / expand toggle */}
        <div className={['p-2', !collapsed && 'flex justify-end'].filter(Boolean).join(' ')}>
          <button
            type="button"
            onClick={() => setCollapsed((c) => !c)}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            className={[
              'rounded-md p-1.5 text-gray-400 transition-colors',
              'hover:bg-gray-100 hover:text-gray-600',
              'focus:outline-none focus:ring-2 focus:ring-blue-500',
              'dark:hover:bg-gray-800 dark:hover:text-gray-300',
              collapsed && 'mx-auto block',
            ]
              .filter(Boolean)
              .join(' ')}
          >
            {collapsed ? (
              <ChevronRight className="h-4 w-4" />
            ) : (
              <ChevronLeft className="h-4 w-4" />
            )}
          </button>
        </div>
      </div>
    </aside>
  )
}
