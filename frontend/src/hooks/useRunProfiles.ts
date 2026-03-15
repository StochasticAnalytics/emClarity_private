/**
 * useRunProfiles – localStorage-backed hook for managing run profiles.
 *
 * Profiles are persisted under `emClarity_runProfiles` in localStorage.
 * System params are persisted under `emClarity_systemParams`.
 *
 * Usage:
 *   const { profiles, selectedId, select, create, update, remove,
 *           systemParams, setSystemParams } = useRunProfiles()
 */

import { useState, useCallback, useEffect } from 'react'
import type { RunProfile, SystemParams } from '@/types/runProfile'
import { DEFAULT_RUN_PROFILES, DEFAULT_SYSTEM_PARAMS } from '@/types/runProfile'

const PROFILES_KEY = 'emClarity_runProfiles'
const SYSTEM_PARAMS_KEY = 'emClarity_systemParams'
const SELECTED_ID_KEY = 'emClarity_selectedRunProfile'

function generateId(): string {
  return `profile-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

function loadProfiles(): RunProfile[] {
  try {
    const raw = localStorage.getItem(PROFILES_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as unknown
      if (Array.isArray(parsed) && parsed.length > 0) return parsed as RunProfile[]
    }
  } catch {
    // Corrupted localStorage — fall back to defaults
  }
  return DEFAULT_RUN_PROFILES
}

function saveProfiles(profiles: RunProfile[]): void {
  localStorage.setItem(PROFILES_KEY, JSON.stringify(profiles))
}

function loadSystemParams(): SystemParams {
  try {
    const raw = localStorage.getItem(SYSTEM_PARAMS_KEY)
    if (raw) return { ...DEFAULT_SYSTEM_PARAMS, ...(JSON.parse(raw) as Partial<SystemParams>) }
  } catch {
    // Corrupted localStorage — fall back to defaults
  }
  return DEFAULT_SYSTEM_PARAMS
}

function saveSystemParams(params: SystemParams): void {
  localStorage.setItem(SYSTEM_PARAMS_KEY, JSON.stringify(params))
}

function loadSelectedId(profiles: RunProfile[]): string {
  const stored = localStorage.getItem(SELECTED_ID_KEY)
  if (stored && profiles.some((p) => p.id === stored)) return stored
  return profiles[0]?.id ?? ''
}

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
}

export function useRunProfiles(): UseRunProfilesResult {
  const [profiles, setProfilesState] = useState<RunProfile[]>(loadProfiles)
  const [selectedId, setSelectedIdState] = useState<string>(() =>
    loadSelectedId(loadProfiles()),
  )
  const [systemParams, setSystemParamsState] = useState<SystemParams>(loadSystemParams)

  // Keep selectedId valid when profiles change
  useEffect(() => {
    if (profiles.length > 0 && !profiles.some((p) => p.id === selectedId)) {
      const newId = profiles[0].id
      setSelectedIdState(newId)
      localStorage.setItem(SELECTED_ID_KEY, newId)
    }
  }, [profiles, selectedId])

  const setProfiles = useCallback((next: RunProfile[]) => {
    setProfilesState(next)
    saveProfiles(next)
  }, [])

  const select = useCallback((id: string) => {
    setSelectedIdState(id)
    localStorage.setItem(SELECTED_ID_KEY, id)
  }, [])

  const create = useCallback((): RunProfile => {
    const newProfile: RunProfile = {
      id: generateId(),
      name: 'New Profile',
      nGPUs: systemParams.nGPUs,
      nCpuCores: systemParams.nCpuCores,
      fastScratchDisk: systemParams.fastScratchDisk,
      commandTemplate: '$command',
    }
    setProfiles([...profiles, newProfile])
    select(newProfile.id)
    return newProfile
  }, [profiles, setProfiles, select, systemParams])

  const update = useCallback(
    (id: string, patch: Partial<Omit<RunProfile, 'id'>>) => {
      setProfiles(profiles.map((p) => (p.id === id ? { ...p, ...patch } : p)))
    },
    [profiles, setProfiles],
  )

  const remove = useCallback(
    (id: string) => {
      const next = profiles.filter((p) => p.id !== id)
      setProfiles(next)
      // If the removed profile was selected, select the first remaining one
      if (selectedId === id) {
        const newId = next[0]?.id ?? ''
        setSelectedIdState(newId)
        localStorage.setItem(SELECTED_ID_KEY, newId)
      }
    },
    [profiles, setProfiles, selectedId],
  )

  const setSystemParams = useCallback(
    (patch: Partial<SystemParams>) => {
      const next = { ...systemParams, ...patch }
      setSystemParamsState(next)
      saveSystemParams(next)
    },
    [systemParams],
  )

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
  }
}
