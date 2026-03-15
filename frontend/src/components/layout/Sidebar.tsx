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
 * - Always-navigable items using a 'demo' sentinel when no project is loaded
 * - Active highlight on the current route
 *
 * Navigation items (matching cisTEM MenuBook order):
 *   Overview · Assets · Actions · Results · Settings · Jobs · Expert
 */
import { useState, useRef } from 'react'
import { NavLink, useMatch, useLocation, Link } from 'react-router-dom'
import { DEMO_PROJECT_ID } from '@/constants'
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
// NavItem component — handles active/inactive states
// ---------------------------------------------------------------------------

interface NavItemProps {
  path: string
  label: string
  icon: React.ComponentType<{ className?: string; 'aria-hidden'?: boolean }>
  projectId: string | null
  collapsed: boolean
}

function NavItem({ path, label, icon: Icon, projectId, collapsed }: NavItemProps) {
  // Use 'demo' as a sentinel project ID when no real project is loaded,
  // so all nav items are always navigable.
  const effectiveProjectId = projectId ?? DEMO_PROJECT_ID
  const targetPath = `/project/${effectiveProjectId}/${path}`
  const location = useLocation()

  // Track last navigation to deduplicate rapid clicks (e.g. double-click) even
  // when navigating FROM a different page. In that case both click events fire
  // synchronously before React re-renders, so location.pathname still reflects
  // the origin path on both events and the pathname check alone would miss it.
  const lastNavRef = useRef<{ path: string; time: number } | null>(null)

  return (
    <NavLink
      to={targetPath}
      title={collapsed ? label : undefined}
      aria-label={collapsed ? label : undefined}
      onClick={(e) => {
        // Prevent pushing a duplicate history entry when already on this page.
        if (location.pathname === targetPath) {
          e.preventDefault()
          return
        }
        // Deduplicate rapid double-clicks to the same target before React
        // re-renders (300 ms window covers OS double-click timing up to the
        // typical maximum configured interval, including accessibility settings).
        const now = Date.now()
        if (lastNavRef.current?.path === targetPath && now - lastNavRef.current.time < 300) {
          e.preventDefault()
          return
        }
        lastNavRef.current = { path: targetPath, time: now }
      }}
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

      {/* Footer: collapse toggle */}
      <div className="border-t border-gray-100 dark:border-gray-800">

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
