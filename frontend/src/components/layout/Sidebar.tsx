import { NavLink } from 'react-router-dom'
import {
  FolderOpen,
  Settings,
  Layers,
  GitBranch,
  Activity,
  BarChart3,
  Wrench,
} from 'lucide-react'

const navItems = [
  { to: '/', label: 'Project', icon: FolderOpen },
  { to: '/parameters', label: 'Parameters', icon: Settings },
  { to: '/tilt-series', label: 'Tilt Series', icon: Layers },
  { to: '/workflow', label: 'Workflow', icon: GitBranch },
  { to: '/jobs', label: 'Jobs', icon: Activity },
  { to: '/results', label: 'Results', icon: BarChart3 },
  { to: '/utilities', label: 'Utilities', icon: Wrench },
] as const

/**
 * Sidebar navigation listing the major sections of the application.
 */
export function Sidebar() {
  return (
    <aside className="flex w-56 flex-col border-r border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
      <div className="flex h-14 items-center border-b border-gray-200 px-4 dark:border-gray-800">
        <h1 className="text-lg font-semibold tracking-tight">emClarity</h1>
      </div>

      <nav className="flex-1 space-y-1 p-2">
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300'
                  : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200'
              }`
            }
          >
            <Icon className="h-4 w-4" />
            {label}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
