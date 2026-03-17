/**
 * useRecentProjects – fetch recent projects from server API.
 *
 * Replaces the old localStorage-based hook. On first load performs
 * a one-time migration from localStorage to server-side timestamps.
 */
import { useState, useCallback, useEffect, useRef } from 'react'
import { apiClient } from '@/api/client.ts'

const STORAGE_KEY = 'emclarity_recent_projects'

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
  const migrationDone = useRef(false)

  const fetchProjects = useCallback(async (): Promise<ProjectResponse[]> => {
    const all = await apiClient.get<ProjectResponse[]>('/api/v1/projects')
    const recent = all
      .map(toRecentProject)
      .filter((p): p is RecentProject => p !== null)
    setProjects(recent)
    return all
  }, [])

  // One-time migration from localStorage
  const migrateFromLocalStorage = useCallback(
    async (serverProjects: ProjectResponse[]) => {
      if (migrationDone.current) return
      migrationDone.current = true

      try {
        const raw = localStorage.getItem(STORAGE_KEY)
        if (!raw) return

        const localEntries: unknown = JSON.parse(raw)
        if (!Array.isArray(localEntries) || localEntries.length === 0) return

        // Only migrate if server projects have no last_accessed timestamps
        const anyServerTimestamp = serverProjects.some((p) => p.last_accessed !== null)
        if (anyServerTimestamp) {
          // Server already has timestamps; just clear localStorage
          localStorage.removeItem(STORAGE_KEY)
          return
        }

        // Build a set of server project IDs for matching
        const serverIds = new Set(serverProjects.map((p) => p.id))

        // Call PATCH for each matching project
        for (const entry of localEntries) {
          if (
            entry !== null &&
            typeof entry === 'object' &&
            'id' in entry &&
            typeof (entry as Record<string, unknown>).id === 'string'
          ) {
            const id = (entry as Record<string, unknown>).id as string
            if (serverIds.has(id)) {
              try {
                await apiClient.patch<ProjectResponse>(
                  `/api/v1/projects/${id}/accessed`,
                )
              } catch {
                // Best effort – continue with remaining entries
              }
            }
          }
        }

        localStorage.removeItem(STORAGE_KEY)

        // Refetch to get updated timestamps
        await fetchProjects()
      } catch {
        // Migration is best-effort; don't break the hook
      }
    },
    [fetchProjects],
  )

  useEffect(() => {
    let cancelled = false

    async function load() {
      setIsLoading(true)
      setError(null)
      try {
        const serverProjects = await fetchProjects()
        if (!cancelled) {
          await migrateFromLocalStorage(serverProjects)
        }
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
  }, [fetchProjects, migrateFromLocalStorage])

  const addProject = useCallback(
    async (entry: { id: string; name: string; directory: string }) => {
      try {
        await apiClient.patch<ProjectResponse>(
          `/api/v1/projects/${entry.id}/accessed`,
        )
        await fetchProjects()
      } catch {
        // Best effort – at least add to local state
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
