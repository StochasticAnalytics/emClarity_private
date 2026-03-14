/**
 * Main application shell with sidebar navigation and content area.
 * Wraps all routed pages via `<Outlet />`.
 *
 * Provides the ProjectContext so that any child page can broadcast the
 * currently loaded project, which the Header then reads to display the
 * project name and state badge.
 */
import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar.tsx'
import { Header } from './Header.tsx'
import { ProjectProvider } from '@/context/ProjectContext.tsx'

export function MainLayout() {
  return (
    <ProjectProvider>
      <div className="flex h-screen overflow-hidden bg-gray-50 text-gray-900 dark:bg-gray-950 dark:text-gray-100">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          <Header />
          <main className="flex-1 overflow-y-auto p-4 sm:p-6">
            <Outlet />
          </main>
        </div>
      </div>
    </ProjectProvider>
  )
}
