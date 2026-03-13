import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar.tsx'
import { Header } from './Header.tsx'

/**
 * Main application shell with sidebar navigation and content area.
 * Wraps all routed pages via `<Outlet />`.
 */
export function MainLayout() {
  return (
    <div className="flex h-screen overflow-hidden bg-gray-50 text-gray-900 dark:bg-gray-950 dark:text-gray-100">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
