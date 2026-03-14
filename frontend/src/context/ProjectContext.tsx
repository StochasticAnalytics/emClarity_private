/**
 * ProjectContext – shares the currently active project state across the app.
 *
 * The ProjectLayout reads the project ID from the URL, fetches the project
 * data from the API, and calls `setActiveProject` to broadcast the selection.
 * Layout components (Header, Sidebar) and page components read from this
 * context to display the current project name, state badge, and to make
 * project-scoped API calls.
 */
import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ActiveProject {
  id: string
  name: string
  state: string
}

export interface ProjectContextValue {
  /** The currently active project, or null if no project is loaded. */
  activeProject: ActiveProject | null
  /** Convenience getter: the active project's ID, or null. */
  projectId: string | null
  setActiveProject: (project: ActiveProject) => void
  clearActiveProject: () => void
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const ProjectContext = createContext<ProjectContextValue | null>(null)

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

interface ProjectProviderProps {
  children: ReactNode
}

export function ProjectProvider({ children }: ProjectProviderProps) {
  const [activeProject, setActiveProjectState] = useState<ActiveProject | null>(null)

  const setActiveProject = useCallback((project: ActiveProject) => {
    setActiveProjectState(project)
  }, [])

  const clearActiveProject = useCallback(() => {
    setActiveProjectState(null)
  }, [])

  const projectId = activeProject?.id ?? null

  return (
    <ProjectContext.Provider
      value={{ activeProject, projectId, setActiveProject, clearActiveProject }}
    >
      {children}
    </ProjectContext.Provider>
  )
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

// eslint-disable-next-line react-refresh/only-export-components
export function useProject(): ProjectContextValue {
  const ctx = useContext(ProjectContext)
  if (!ctx) {
    throw new Error('useProject must be used within a ProjectProvider')
  }
  return ctx
}
