/**
 * ProjectContext – shares the currently active project state across the app.
 *
 * Components that load or create a project call `setActiveProject` to
 * broadcast the selection.  Layout components (Header, Sidebar) read from
 * this context to display the current project name and state badge.
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
  activeProject: ActiveProject | null
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

  return (
    <ProjectContext.Provider value={{ activeProject, setActiveProject, clearActiveProject }}>
      {children}
    </ProjectContext.Provider>
  )
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useProject(): ProjectContextValue {
  const ctx = useContext(ProjectContext)
  if (!ctx) {
    throw new Error('useProject must be used within a ProjectProvider')
  }
  return ctx
}
