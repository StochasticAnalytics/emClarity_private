/**
 * useRecentProjects – fetch recent projects from server API.
 *
 * All project data is server-side; no browser storage is used.
 */
import { useState, useCallback, useEffect } from 'react'
import { apiClient } from '@/api/client.ts'

export interface RecentProject {
  id: string
  name: string
  directory: string
  lastAccessed: string
}

interface ProjectResponse {
  id: string
  name: string
  directory: string
  state: string
  parameters: Record<string, unknown>
  current_cycle: number
  last_accessed: string | null
}

function toRecentProject(p: ProjectResponse): RecentProject | null {
  if (!p.last_accessed) return null
  return {
    id: p.id,
    name: p.name,
    directory: p.directory,
    lastAccessed: p.last_accessed,
  }
}

export function useRecentProjects() {
  const [projects, setProjects] = useState<RecentProject[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchProjects = useCallback(async () => {
    const all = await apiClient.get<ProjectResponse[]>('/api/v1/projects')
    const recent = all
      .map(toRecentProject)
      .filter((p): p is RecentProject => p !== null)
    setProjects(recent)
  }, [])

  useEffect(() => {
    let cancelled = false

    async function load() {
      setIsLoading(true)
      setError(null)
      try {
        await fetchProjects()
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load projects')
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false)
        }
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [fetchProjects])

  const addProject = useCallback(
    async (entry: { id: string; name: string; directory: string }) => {
      try {
        await apiClient.patch<ProjectResponse>(
          `/api/v1/projects/${entry.id}/accessed`,
        )
        await fetchProjects()
      } catch (err) {
        // Server call failed – add optimistic entry but log for debugging
        console.warn('[useRecentProjects] addProject failed, using optimistic entry:', err)
        const now = new Date().toISOString()
        setProjects((prev) => {
          const filtered = prev.filter((p) => p.id !== entry.id)
          return [{ ...entry, lastAccessed: now }, ...filtered]
        })
      }
    },
    [fetchProjects],
  )

  const removeProject = useCallback(
    async (id: string) => {
      // Optimistically remove from local state
      setProjects((prev) => prev.filter((p) => p.id !== id))
      try {
        await apiClient.delete(`/api/v1/projects/${id}`)
      } catch {
        // If the server call fails, re-fetch to restore accurate state
        await fetchProjects()
      }
    },
    [fetchProjects],
  )

  return { projects, addProject, removeProject, isLoading, error }
}
