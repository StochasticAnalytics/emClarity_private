/**
 * ProjectLayout – nested route wrapper for all project-scoped pages.
 *
 * Reads `:projectId` from the URL via useParams and writes it into
 * ProjectContext so that child pages and the Sidebar can access it without
 * re-reading the URL themselves.
 *
 * Renders an <Outlet /> for the matched child route (overview, assets, …).
 */
import { useEffect } from 'react'
import { Outlet, useParams, Navigate } from 'react-router-dom'
import { useProject } from '@/context/ProjectContext.tsx'

export function ProjectLayout() {
  const { projectId } = useParams<{ projectId: string }>()
  const { setProjectId } = useProject()

  // Sync URL param into shared context so Sidebar / Header can read it.
  useEffect(() => {
    setProjectId(projectId ?? null)
    // Clear on unmount (when navigating away from any project route).
    return () => {
      setProjectId(null)
    }
  }, [projectId, setProjectId])

  if (!projectId) {
    return <Navigate to="/" replace />
  }

  return <Outlet />
}
