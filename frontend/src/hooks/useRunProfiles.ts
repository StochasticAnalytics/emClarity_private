/**
 * useRunProfiles – server-backed hook for managing run profiles.
 *
 * Reads and writes profile/system-param settings via the project settings API.
 * On first load, performs a one-time migration from localStorage (if the server
 * has no profiles yet and localStorage contains data).
 *
 * Usage:
 *   const { profiles, selectedId, select, create, update, remove,
 *           systemParams, setSystemParams, loading, error } = useRunProfiles(projectId)
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import type { RunProfile, SystemParams } from '@/types/runProfile'
import { DEFAULT_SYSTEM_PARAMS } from '@/types/runProfile'
import { apiClient } from '@/api/client'

// ---------------------------------------------------------------------------
// localStorage keys (used only for one-time migration)
// ---------------------------------------------------------------------------

const PROFILES_KEY = 'emClarity_runProfiles'
const SYSTEM_PARAMS_KEY = 'emClarity_systemParams'
const SELECTED_ID_KEY = 'emClarity_selectedRunProfile'

// ---------------------------------------------------------------------------
// Backend API types
// ---------------------------------------------------------------------------

interface BackendRunProfile {
  name: string
  gpu_count: number
  cpu_cores: number
  scratch_disk: string | null
  command_template: string | null
}

interface BackendSystemParams {
  nGPUs: number
  nCpuCores: number
  fastScratchDisk: string
}

interface ProjectSettings {
  run_profiles: BackendRunProfile[]
  selected_run_profile: string | null
  system_params: BackendSystemParams | null
  viewer_path: string | null
  executable_paths: Record<string, string>
}

// ---------------------------------------------------------------------------
// Conversion helpers
// ---------------------------------------------------------------------------

function backendToFrontend(bp: BackendRunProfile): RunProfile {
  return {
    id: bp.name,
    name: bp.name,
    nGPUs: bp.gpu_count,
    nCpuCores: bp.cpu_cores,
    fastScratchDisk: bp.scratch_disk ?? '/tmp',
    commandTemplate: bp.command_template ?? '$command',
  }
}

function frontendToBackend(fp: RunProfile): BackendRunProfile {
  return {
    name: fp.name,
    gpu_count: fp.nGPUs,
    cpu_cores: fp.nCpuCores,
    scratch_disk: fp.fastScratchDisk || null,
    command_template: fp.commandTemplate || null,
  }
}

function generateId(): string {
  return `profile-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

// ---------------------------------------------------------------------------
// localStorage migration helpers
// ---------------------------------------------------------------------------

function loadLocalStorageProfiles(): RunProfile[] | null {
  try {
    const raw = localStorage.getItem(PROFILES_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as unknown
      if (Array.isArray(parsed) && parsed.length > 0) return parsed as RunProfile[]
    }
  } catch {
    // Corrupted localStorage — ignore
  }
  return null
}

function loadLocalStorageSystemParams(): SystemParams | null {
  try {
    const raw = localStorage.getItem(SYSTEM_PARAMS_KEY)
    if (raw) return { ...DEFAULT_SYSTEM_PARAMS, ...(JSON.parse(raw) as Partial<SystemParams>) }
  } catch {
    // Corrupted localStorage — ignore
  }
  return null
}

function loadLocalStorageSelectedId(): string | null {
  return localStorage.getItem(SELECTED_ID_KEY)
}

function clearLocalStorageKeys(): void {
  localStorage.removeItem(PROFILES_KEY)
  localStorage.removeItem(SYSTEM_PARAMS_KEY)
  localStorage.removeItem(SELECTED_ID_KEY)
}

// ---------------------------------------------------------------------------
// Public interface
// ---------------------------------------------------------------------------

export interface UseRunProfilesResult {
  profiles: RunProfile[]
  selectedId: string
  selectedProfile: RunProfile | null
  select: (id: string) => void
  create: () => RunProfile
  update: (id: string, patch: Partial<Omit<RunProfile, 'id'>>) => void
  remove: (id: string) => void
  systemParams: SystemParams
  setSystemParams: (patch: Partial<SystemParams>) => void
  loading: boolean
  error: string | null
}

// ---------------------------------------------------------------------------
// Hook implementation
// ---------------------------------------------------------------------------

export function useRunProfiles(projectId: string | null = null): UseRunProfilesResult {
  const [profiles, setProfilesState] = useState<RunProfile[]>([])
  const [selectedId, setSelectedIdState] = useState<string>('')
  const [systemParams, setSystemParamsState] = useState<SystemParams>(DEFAULT_SYSTEM_PARAMS)
  const [loading, setLoading] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)

  // Track whether initial fetch + migration has happened for this projectId
  const fetchedProjectRef = useRef<string | null>(null)

  // -----------------------------------------------------------------------
  // Fetch settings from server (with optional migration from localStorage)
  // -----------------------------------------------------------------------

  useEffect(() => {
    if (!projectId) {
      // No project: reset to empty state
      setProfilesState([])
      setSelectedIdState('')
      setSystemParamsState(DEFAULT_SYSTEM_PARAMS)
      setError(null)
      setLoading(false)
      fetchedProjectRef.current = null
      return
    }

    // Avoid re-fetching for the same project
    if (fetchedProjectRef.current === projectId) return

    let cancelled = false
    const controller = new AbortController()

    async function fetchAndMigrate() {
      setLoading(true)
      setError(null)

      try {
        let settings = await apiClient.get<ProjectSettings>(
          `/api/v1/projects/${projectId}/settings`,
          controller.signal,
        )

        if (cancelled) return

        // One-time migration: if server has no profiles but localStorage does
        const localProfiles = loadLocalStorageProfiles()
        if (settings.run_profiles.length === 0 && localProfiles && localProfiles.length > 0) {
          const localSystemParams = loadLocalStorageSystemParams()
          const localSelectedId = loadLocalStorageSelectedId()

          const migrationPayload: Record<string, unknown> = {
            run_profiles: localProfiles.map(frontendToBackend),
          }
          if (localSystemParams) {
            migrationPayload.system_params = localSystemParams
          }
          if (localSelectedId) {
            // The selected_run_profile on the backend is the profile name.
            // In the old frontend, selectedId could be something like 'local-1gpu'.
            // Find the matching profile's name to use as the selection.
            const matchingProfile = localProfiles.find((p) => p.id === localSelectedId)
            if (matchingProfile) {
              migrationPayload.selected_run_profile = matchingProfile.name
            }
          }

          settings = await apiClient.patch<ProjectSettings>(
            `/api/v1/projects/${projectId}/settings`,
            migrationPayload,
          )

          if (cancelled) return

          // Clear localStorage after successful migration
          clearLocalStorageKeys()
        }

        // Apply server state to local React state
        const frontendProfiles = settings.run_profiles.map(backendToFrontend)
        setProfilesState(frontendProfiles)

        // Resolve selected profile
        const serverSelected = settings.selected_run_profile
        if (serverSelected && frontendProfiles.some((p) => p.id === serverSelected)) {
          setSelectedIdState(serverSelected)
        } else {
          setSelectedIdState(frontendProfiles[0]?.id ?? '')
        }

        // System params
        if (settings.system_params) {
          setSystemParamsState(settings.system_params)
        } else {
          setSystemParamsState(DEFAULT_SYSTEM_PARAMS)
        }

        fetchedProjectRef.current = projectId
      } catch (err: unknown) {
        if (cancelled) return
        const message = err instanceof Error ? err.message : 'Failed to load settings'
        setError(message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void fetchAndMigrate()

    return () => {
      cancelled = true
      controller.abort()
    }
  }, [projectId])

  // -----------------------------------------------------------------------
  // Helper to PATCH settings to server
  // -----------------------------------------------------------------------

  const patchSettings = useCallback(
    async (payload: Record<string, unknown>): Promise<ProjectSettings | null> => {
      if (!projectId) return null
      try {
        setError(null)
        return await apiClient.patch<ProjectSettings>(
          `/api/v1/projects/${projectId}/settings`,
          payload,
        )
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to save settings'
        setError(message)
        return null
      }
    },
    [projectId],
  )

  // -----------------------------------------------------------------------
  // Actions
  // -----------------------------------------------------------------------

  const select = useCallback(
    (id: string) => {
      setSelectedIdState(id)
      // Find the profile name corresponding to this id (id === name in server-backed mode)
      void patchSettings({ selected_run_profile: id })
    },
    [patchSettings],
  )

  const create = useCallback((): RunProfile => {
    const newProfile: RunProfile = {
      id: generateId(),
      name: 'New Profile',
      nGPUs: systemParams.nGPUs,
      nCpuCores: systemParams.nCpuCores,
      fastScratchDisk: systemParams.fastScratchDisk,
      commandTemplate: '$command',
    }
    const nextProfiles = [...profiles, newProfile]
    setProfilesState(nextProfiles)
    setSelectedIdState(newProfile.id)

    void patchSettings({
      run_profiles: nextProfiles.map(frontendToBackend),
      selected_run_profile: newProfile.name,
    }).then((settings) => {
      if (settings) {
        // Re-sync: the server may have normalized names
        const synced = settings.run_profiles.map(backendToFrontend)
        setProfilesState(synced)
        // Find the newly created profile by name
        const created = synced.find((p) => p.name === newProfile.name)
        if (created) setSelectedIdState(created.id)
      }
    })

    return newProfile
  }, [profiles, systemParams, patchSettings])

  const update = useCallback(
    (id: string, patch: Partial<Omit<RunProfile, 'id'>>) => {
      const nextProfiles = profiles.map((p) => {
        if (p.id !== id) return p
        const updated = { ...p, ...patch }
        // Keep id in sync with name (id === name for server profiles)
        if (patch.name !== undefined) {
          updated.id = patch.name
        }
        return updated
      })
      setProfilesState(nextProfiles)

      // If the updated profile was selected and its name/id changed, update selectedId
      if (patch.name !== undefined && id === selectedId) {
        setSelectedIdState(patch.name)
      }

      void patchSettings({
        run_profiles: nextProfiles.map(frontendToBackend),
        ...(patch.name !== undefined && id === selectedId
          ? { selected_run_profile: patch.name }
          : {}),
      })
    },
    [profiles, selectedId, patchSettings],
  )

  const remove = useCallback(
    (id: string) => {
      const next = profiles.filter((p) => p.id !== id)
      setProfilesState(next)

      let newSelectedId = selectedId
      if (selectedId === id) {
        newSelectedId = next[0]?.id ?? ''
        setSelectedIdState(newSelectedId)
      }

      void patchSettings({
        run_profiles: next.map(frontendToBackend),
        selected_run_profile: newSelectedId || null,
      })
    },
    [profiles, selectedId, patchSettings],
  )

  const setSystemParams = useCallback(
    (patch: Partial<SystemParams>) => {
      const next = { ...systemParams, ...patch }
      setSystemParamsState(next)
      void patchSettings({ system_params: next })
    },
    [systemParams, patchSettings],
  )

  // -----------------------------------------------------------------------
  // Derived
  // -----------------------------------------------------------------------

  const selectedProfile = profiles.find((p) => p.id === selectedId) ?? null

  return {
    profiles,
    selectedId,
    selectedProfile,
    select,
    create,
    update,
    remove,
    systemParams,
    setSystemParams,
    loading,
    error,
  }
}
