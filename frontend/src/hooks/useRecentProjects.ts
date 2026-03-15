/**
 * useRecentProjects – manage a persisted list of recently accessed projects.
 *
 * Reads from and writes to localStorage with full per-entry Zod validation
 * so corrupt or stale storage data never crashes the UI.
 */
import { useState, useCallback } from 'react'
import { z } from 'zod'

// ---------------------------------------------------------------------------
// Schema
// ---------------------------------------------------------------------------

const STORAGE_KEY = 'emclarity_recent_projects'
const MAX_RECENT = 10

/** Each stored entry must have these fields. */
const RecentProjectEntrySchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  directory: z.string().min(1),
  lastAccessed: z.string().min(1),
})

const RecentProjectsSchema = z.array(RecentProjectEntrySchema)

export type RecentProject = z.infer<typeof RecentProjectEntrySchema>

// ---------------------------------------------------------------------------
// Storage helpers
// ---------------------------------------------------------------------------

function readFromStorage(): RecentProject[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []

    const parsed: unknown = JSON.parse(raw)

    // Validate the entire array, then validate each entry individually.
    // Per-entry validation means one corrupt entry doesn't discard the rest.
    if (!Array.isArray(parsed)) return []

    const valid: RecentProject[] = []
    for (const item of parsed) {
      const result = RecentProjectEntrySchema.safeParse(item)
      if (result.success) {
        valid.push(result.data)
      }
      // Silently drop invalid entries
    }

    // Sort newest-first by lastAccessed
    return valid.sort(
      (a, b) => new Date(b.lastAccessed).getTime() - new Date(a.lastAccessed).getTime(),
    )
  } catch {
    // JSON parse error or other failure – start fresh
    return []
  }
}

function writeToStorage(projects: RecentProject[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(projects))
  } catch {
    // Ignore – private browsing or storage full
  }
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useRecentProjects() {
  const [projects, setProjects] = useState<RecentProject[]>(readFromStorage)

  /**
   * Add or update a project entry (by ID) and persist.
   * If a project with the same ID already exists, it is moved to the top.
   */
  const addProject = useCallback(
    (entry: Omit<RecentProject, 'lastAccessed'>) => {
      const now = new Date().toISOString()
      const newEntry: RecentProject = { ...entry, lastAccessed: now }

      setProjects((prev) => {
        const updated = [newEntry, ...prev.filter((p) => p.id !== entry.id)].slice(0, MAX_RECENT)
        writeToStorage(updated)
        return updated
      })
    },
    [],
  )

  /**
   * Remove a project entry by ID and persist.
   * Use this when a 404 confirms the project no longer exists on the backend.
   */
  const removeProject = useCallback((id: string) => {
    setProjects((prev) => {
      const updated = prev.filter((p) => p.id !== id)
      writeToStorage(updated)
      return updated
    })
  }, [])

  return { projects, addProject, removeProject }
}
