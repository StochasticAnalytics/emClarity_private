/**
 * ProjectLayout – wrapper for all project-scoped routes.
 *
 * Reads the project ID from the URL, fetches the project data from the API,
 * and broadcasts it to child pages via ProjectContext. Renders <Outlet />
 * once the project is loaded.
 *
 * URL structure: /project/:projectId/<section>
 */
import { useEffect, useState, useCallback } from 'react'
import { Outlet, useParams, Navigate, Link } from 'react-router-dom'
import { apiClient, ApiError } from '@/api/client.ts'
import { useProject } from '@/context/ProjectContext.tsx'
import { DEMO_PROJECT_ID } from '@/constants'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ProjectDetails {
  id: string
  name: string
  state: string
  current_cycle?: number
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ProjectLayout() {
  const { projectId } = useParams<{ projectId: string }>()
  const isDemoMode = projectId === DEMO_PROJECT_ID
  const { setActiveProject, clearActiveProject } = useProject()
  // Start loading only when a real projectId is present (not demo, not missing)
  const [isLoading, setIsLoading] = useState(projectId !== undefined && !isDemoMode)
  const [error, setError] = useState<string | null>(null)

  const loadProject = useCallback(
    async (id: string, signal: AbortSignal) => {
      setIsLoading(true)
      setError(null)
      try {
        const data = await apiClient.get<ProjectDetails>(`/api/v1/projects/${id}`, signal)
        if (!signal.aborted) {
          setActiveProject({ id: data.id, name: data.name, state: data.state, current_cycle: data.current_cycle })
          setIsLoading(false)
        }
      } catch (err: unknown) {
        if (signal.aborted) return
        const message =
          err instanceof ApiError
            ? `Failed to load project (${err.status}): ${err.statusText}`
            : 'Failed to load project.'
        setError(message)
        setIsLoading(false)
      }
    },
    [setActiveProject],
  )

  useEffect(() => {
    if (!projectId || isDemoMode) {
      // No project in URL, or demo sentinel — no fetch needed
      return
    }

    const controller = new AbortController()
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadProject(projectId, controller.signal)

    return () => {
      controller.abort()
      clearActiveProject()
    }
  }, [projectId, isDemoMode, loadProject, clearActiveProject])

  // No projectId in URL – redirect to landing page
  if (!projectId) {
    return <Navigate to="/" replace />
  }

  // Demo mode: render child pages directly with no active project context.
  // Pages will display their own empty/error states via API calls.
  if (isDemoMode) {
    return <Outlet />
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
        <span className="ml-3 text-gray-500 dark:text-gray-400">Loading project…</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-6 dark:border-red-800 dark:bg-red-900/20 space-y-3">
        <h3 className="font-semibold text-red-800 dark:text-red-200">Failed to load project</h3>
        <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
        <Link
          to="/"
          className="inline-block text-sm text-red-600 underline hover:text-red-800 dark:text-red-400"
        >
          ← Back to projects
        </Link>
      </div>
    )
  }

  return <Outlet />
}
