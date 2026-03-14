/**
 * ProjectContext – shares the currently active project state across the app.
 *
 * Components inside a /project/:projectId route call `setProjectId` (via
 * ProjectLayout) so that the sidebar and header know which project is active.
 * When a project's data has been fetched, pages call `setActiveProject` to
 * broadcast the name and state badge to the Header.
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
  /** Project ID extracted from the URL (set by ProjectLayout). */
  projectId: string | null
  /** Full project metadata fetched from the API. */
  activeProject: ActiveProject | null
  setProjectId: (id: string | null) => void
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
  const [projectId, setProjectIdState] = useState<string | null>(null)
  const [activeProject, setActiveProjectState] = useState<ActiveProject | null>(null)

  const setProjectId = useCallback((id: string | null) => {
    setProjectIdState(id)
  }, [])

  const setActiveProject = useCallback((project: ActiveProject) => {
    setActiveProjectState(project)
  }, [])

  const clearActiveProject = useCallback(() => {
    setActiveProjectState(null)
    setProjectIdState(null)
  }, [])

  return (
    <ProjectContext.Provider
      value={{ projectId, activeProject, setProjectId, setActiveProject, clearActiveProject }}
    >
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
