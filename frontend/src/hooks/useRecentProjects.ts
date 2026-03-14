/**
 * useRecentProjects – manages recently opened projects in localStorage.
 *
 * Stores up to 5 recent projects (id, name, directory, lastOpened).
 * Used by the welcome page to provide quick re-open links.
 */
import { useState, useCallback } from 'react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface RecentProject {
  id: string
  name: string
  directory: string
  lastOpened: string // ISO-8601 timestamp
}

// ---------------------------------------------------------------------------
// Storage helpers
// ---------------------------------------------------------------------------

const STORAGE_KEY = 'emclarity:recent-projects'
const MAX_RECENT = 5

function loadFromStorage(): RecentProject[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    return Array.isArray(parsed) ? (parsed as RecentProject[]) : []
  } catch {
    return []
  }
}

function saveToStorage(projects: RecentProject[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(projects))
  } catch {
    // ignore write errors (e.g. private-browsing quota exceeded)
  }
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useRecentProjects() {
  const [recentProjects, setRecentProjects] = useState<RecentProject[]>(loadFromStorage)

  /** Add or update a project entry, bumping it to the top of the list. */
  const addRecentProject = useCallback(
    (project: Omit<RecentProject, 'lastOpened'>) => {
      setRecentProjects((prev) => {
        const filtered = prev.filter((p) => p.id !== project.id)
        const updated = [
          { ...project, lastOpened: new Date().toISOString() },
          ...filtered,
        ].slice(0, MAX_RECENT)
        saveToStorage(updated)
        return updated
      })
    },
    [],
  )

  /** Remove all recent projects from storage. */
  const clearRecentProjects = useCallback(() => {
    saveToStorage([])
    setRecentProjects([])
  }, [])

  return { recentProjects, addRecentProject, clearRecentProjects }
}
