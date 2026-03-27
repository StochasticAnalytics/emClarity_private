/**
 * SettingsPage – Run profile management panel.
 *
 * Layout (cisTEM Settings_panel.md reference):
 *   Top:    System params banner (nGPUs, nCpuCores, fastScratchDisk) — always visible
 *   Left:   Profile list with Create/Delete buttons
 *   Right:  Profile detail form (name, GPU count, CPU cores, scratch disk, command template)
 *
 * Profiles and system params are persisted server-side via the project
 * settings API, accessed through the useRunProfiles hook.
 *
 * Tutorial reference: Section 1.5, Table 1 (system parameters).
 */

import { useState, useCallback, useId } from 'react'
import { useTabParam } from '@/hooks/useTabParam'
import { Cpu, HardDrive, Plus, Trash2, Server, AlertCircle } from 'lucide-react'
import { useRunProfiles } from '@/hooks/useRunProfiles'
import { useProject } from '@/context/ProjectContext'
import type { RunProfile } from '@/types/runProfile'
import { EnvironmentPanel } from './EnvironmentPanel'

// ---------------------------------------------------------------------------
// System params banner
// ---------------------------------------------------------------------------

interface SystemParamsBannerProps {
  nGPUs: number
  nCpuCores: number
  fastScratchDisk: string
  onChange: (field: 'nGPUs' | 'nCpuCores' | 'fastScratchDisk', value: string) => void
}

function SystemParamsBanner({
  nGPUs,
  nCpuCores,
  fastScratchDisk,
  onChange,
}: SystemParamsBannerProps) {
  const gpuId = useId()
  const cpuId = useId()
  const diskId = useId()

  return (
    <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4 mb-6">
      <div className="flex items-center gap-2 mb-3">
        <Server className="h-4 w-4 text-blue-600 dark:text-blue-400" aria-hidden="true" />
        <h2 className="text-sm font-semibold text-blue-900 dark:text-blue-200">
          System Parameters (Table 1)
        </h2>
        <span className="text-xs text-blue-600 dark:text-blue-400 ml-1">
          — global defaults for new profiles
        </span>
      </div>

      <div className="grid grid-cols-3 gap-4">
        {/* nGPUs */}
        <div>
          <label
            htmlFor={gpuId}
            className="flex items-center gap-1.5 text-xs font-medium text-gray-700 dark:text-gray-300 mb-1"
          >
            <Cpu className="h-3.5 w-3.5 text-blue-500" aria-hidden="true" />
            nGPUs
            <span className="text-red-500" aria-label="required">*</span>
          </label>
          <input
            id={gpuId}
            type="number"
            min={1}
            max={1000}
            value={nGPUs}
            onChange={(e) => onChange('nGPUs', e.target.value)}
            className="w-full rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-1.5 text-sm text-gray-900 dark:text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            aria-describedby={`${gpuId}-desc`}
          />
          <p id={`${gpuId}-desc`} className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
            Number of GPUs to use for processing
          </p>
        </div>

        {/* nCpuCores */}
        <div>
          <label
            htmlFor={cpuId}
            className="flex items-center gap-1.5 text-xs font-medium text-gray-700 dark:text-gray-300 mb-1"
          >
            <Cpu className="h-3.5 w-3.5 text-blue-500" aria-hidden="true" />
            nCpuCores
            <span className="text-red-500" aria-label="required">*</span>
          </label>
          <input
            id={cpuId}
            type="number"
            min={1}
            max={1000}
            value={nCpuCores}
            onChange={(e) => onChange('nCpuCores', e.target.value)}
            className="w-full rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-1.5 text-sm text-gray-900 dark:text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            aria-describedby={`${cpuId}-desc`}
          />
          <p id={`${cpuId}-desc`} className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
            Number of CPU cores to use for processing
          </p>
        </div>

        {/* fastScratchDisk */}
        <div>
          <label
            htmlFor={diskId}
            className="flex items-center gap-1.5 text-xs font-medium text-gray-700 dark:text-gray-300 mb-1"
          >
            <HardDrive className="h-3.5 w-3.5 text-blue-500" aria-hidden="true" />
            fastScratchDisk
          </label>
          <input
            id={diskId}
            type="text"
            value={fastScratchDisk}
            onChange={(e) => onChange('fastScratchDisk', e.target.value)}
            placeholder="/tmp"
            className="w-full rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-1.5 text-sm text-gray-900 dark:text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            aria-describedby={`${diskId}-desc`}
          />
          <p id={`${diskId}-desc`} className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
            Path to fast local storage (or "ram")
          </p>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Profile list (left panel)
// ---------------------------------------------------------------------------

interface ProfileListProps {
  profiles: RunProfile[]
  selectedId: string
  onSelect: (id: string) => void
  onCreate: () => void
  onDelete: (id: string) => void
}

function ProfileList({ profiles, selectedId, onSelect, onCreate, onDelete }: ProfileListProps) {
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null)

  const handleDeleteClick = useCallback(
    (e: React.MouseEvent, id: string) => {
      e.stopPropagation()
      if (deleteConfirmId === id) {
        onDelete(id)
        setDeleteConfirmId(null)
      } else {
        setDeleteConfirmId(id)
      }
    },
    [deleteConfirmId, onDelete],
  )

  return (
    <div className="flex flex-col h-full border-r border-gray-200 dark:border-gray-700">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-200 dark:border-gray-700">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
          Run Profiles
        </h3>
        <button
          type="button"
          onClick={onCreate}
          aria-label="Create new profile"
          title="Create new profile"
          className="flex items-center gap-1 rounded px-2 py-1 text-xs font-medium text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/30 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-colors"
        >
          <Plus className="h-3.5 w-3.5" aria-hidden="true" />
          New
        </button>
      </div>

      {/* Profile list */}
      <ul aria-label="Run profiles" className="flex-1 overflow-y-auto py-1">
        {profiles.map((profile) => {
          const isSelected = profile.id === selectedId
          const isPendingDelete = deleteConfirmId === profile.id
          return (
            <li key={profile.id}>
              <div
                className={[
                  'group flex items-center justify-between px-3 py-2 transition-colors',
                  isSelected
                    ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-900 dark:text-blue-100'
                    : 'hover:bg-gray-50 dark:hover:bg-gray-800/50 text-gray-800 dark:text-gray-200',
                ].join(' ')}
              >
                <button
                  type="button"
                  className="text-sm truncate flex-1 min-w-0 text-left cursor-pointer"
                  aria-pressed={isSelected}
                  onClick={() => {
                    onSelect(profile.id)
                    setDeleteConfirmId(null)
                  }}
                >
                  {profile.name}
                </button>

                <button
                  type="button"
                  onClick={(e) => handleDeleteClick(e, profile.id)}
                  title={isPendingDelete ? 'Click again to confirm delete' : 'Delete profile'}
                  className={[
                    'ml-2 flex-shrink-0 rounded p-0.5 focus:outline-none focus:ring-1 focus:ring-red-400 transition-colors',
                    isPendingDelete
                      ? 'text-red-600 dark:text-red-400'
                      : 'text-gray-400 dark:text-gray-600 opacity-0 group-hover:opacity-100 hover:text-red-500 dark:hover:text-red-400',
                  ].join(' ')}
                  aria-label={
                    isPendingDelete
                      ? `Confirm delete "${profile.name}"`
                      : `Delete profile "${profile.name}"`
                  }
                >
                  {isPendingDelete ? (
                    <AlertCircle className="h-3.5 w-3.5" aria-hidden="true" />
                  ) : (
                    <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                  )}
                </button>
              </div>

              {/* Inline confirmation message */}
              {isPendingDelete && (
                <p
                  role="alert"
                  className="px-3 py-1 text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20"
                >
                  Click trash again to confirm deletion.
                </p>
              )}
            </li>
          )
        })}

        {profiles.length === 0 && (
          <li className="px-3 py-4 text-xs text-gray-400 dark:text-gray-600 text-center">
            No profiles. Click "New" to create one.
          </li>
        )}
      </ul>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Profile detail form (right panel)
// ---------------------------------------------------------------------------

interface ProfileDetailProps {
  profile: RunProfile
  onChange: (patch: Partial<Omit<RunProfile, 'id'>>) => void
}

function ProfileDetail({ profile, onChange }: ProfileDetailProps) {
  const nameId = useId()
  const gpuId = useId()
  const cpuId = useId()
  const diskId = useId()
  const cmdId = useId()

  return (
    <div className="flex-1 overflow-y-auto p-5 space-y-5">
      <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Profile Configuration</h3>

      {/* Profile name */}
      <div>
        <label
          htmlFor={nameId}
          className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1"
        >
          Profile Name
        </label>
        <input
          id={nameId}
          type="text"
          value={profile.name}
          onChange={(e) => onChange({ name: e.target.value })}
          className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-1.5 text-sm text-gray-900 dark:text-gray-100 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          placeholder="e.g. Local 4 GPU"
        />
      </div>

      {/* Hardware settings row */}
      <div className="grid grid-cols-2 gap-4">
        {/* GPU count */}
        <div>
          <label
            htmlFor={gpuId}
            className="flex items-center gap-1.5 text-xs font-medium text-gray-700 dark:text-gray-300 mb-1"
          >
            <Cpu className="h-3.5 w-3.5 text-gray-400" aria-hidden="true" />
            GPU Count (nGPUs)
          </label>
          <input
            id={gpuId}
            type="number"
            min={1}
            max={1000}
            value={profile.nGPUs}
            onChange={(e) => onChange({ nGPUs: Math.max(1, parseInt(e.target.value, 10) || 1) })}
            className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-1.5 text-sm text-gray-900 dark:text-gray-100 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>

        {/* CPU cores */}
        <div>
          <label
            htmlFor={cpuId}
            className="flex items-center gap-1.5 text-xs font-medium text-gray-700 dark:text-gray-300 mb-1"
          >
            <Cpu className="h-3.5 w-3.5 text-gray-400" aria-hidden="true" />
            CPU Cores (nCpuCores)
          </label>
          <input
            id={cpuId}
            type="number"
            min={1}
            max={1000}
            value={profile.nCpuCores}
            onChange={(e) =>
              onChange({ nCpuCores: Math.max(1, parseInt(e.target.value, 10) || 1) })
            }
            className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-1.5 text-sm text-gray-900 dark:text-gray-100 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>
      </div>

      {/* Scratch disk path */}
      <div>
        <label
          htmlFor={diskId}
          className="flex items-center gap-1.5 text-xs font-medium text-gray-700 dark:text-gray-300 mb-1"
        >
          <HardDrive className="h-3.5 w-3.5 text-gray-400" aria-hidden="true" />
          Scratch Disk Path (fastScratchDisk)
        </label>
        <input
          id={diskId}
          type="text"
          value={profile.fastScratchDisk}
          onChange={(e) => onChange({ fastScratchDisk: e.target.value })}
          placeholder="/tmp"
          className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-1.5 text-sm text-gray-900 dark:text-gray-100 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
          Path to fast local storage, or "ram" to use ramdisk.
        </p>
      </div>

      {/* Command template */}
      <div>
        <label
          htmlFor={cmdId}
          className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1"
        >
          Command Template
          <span className="ml-1 font-normal text-gray-400">(advanced)</span>
        </label>
        <textarea
          id={cmdId}
          rows={4}
          value={profile.commandTemplate}
          onChange={(e) => onChange({ commandTemplate: e.target.value })}
          spellCheck={false}
          className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-1.5 text-sm font-mono text-gray-900 dark:text-gray-100 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 resize-y"
          aria-describedby={`${cmdId}-desc`}
        />
        <p id={`${cmdId}-desc`} className="mt-1 text-xs text-gray-500 dark:text-gray-400">
          Use <code className="bg-gray-100 dark:bg-gray-700 px-1 rounded">$command</code> as a
          placeholder for the emClarity command. Example:{' '}
          <code className="bg-gray-100 dark:bg-gray-700 px-1 rounded">
            singularity exec --nv emclarity.sif $command
          </code>
        </p>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Settings tab definitions
// ---------------------------------------------------------------------------

const SETTINGS_TAB_IDS = ['runProfiles', 'environment'] as const

type SettingsTabId = (typeof SETTINGS_TAB_IDS)[number]

interface SettingsTab {
  id: SettingsTabId
  label: string
}

const SETTINGS_TABS: SettingsTab[] = [
  { id: 'runProfiles', label: 'Run Profiles' },
  { id: 'environment', label: 'Environment' },
]

// ---------------------------------------------------------------------------
// Main SettingsPage
// ---------------------------------------------------------------------------

export function SettingsPage() {
  const { projectId } = useProject()
  const { profiles, selectedId, selectedProfile, select, create, update, remove, systemParams, setSystemParams, loading, loadError, saveError } =
    useRunProfiles(projectId)

  // Active settings tab — persisted in URL ?tab= query parameter.
  // Switching tabs must NOT reset profile edit state.
  const [activeTab, setActiveTab] = useTabParam(SETTINGS_TAB_IDS)

  const handleSystemParamChange = useCallback(
    (field: 'nGPUs' | 'nCpuCores' | 'fastScratchDisk', value: string) => {
      if (field === 'fastScratchDisk') {
        setSystemParams({ fastScratchDisk: value })
      } else {
        const num = Math.max(1, parseInt(value, 10) || 1)
        setSystemParams({ [field]: num })
      }
    },
    [setSystemParams],
  )

  const handleProfileChange = useCallback(
    (patch: Partial<Omit<RunProfile, 'id'>>) => {
      if (selectedProfile) update(selectedProfile.id, patch)
    },
    [selectedProfile, update],
  )

  if (!projectId) {
    return (
      <div className="flex flex-col items-center justify-center h-full bg-white dark:bg-gray-900">
        <p className="text-gray-500 dark:text-gray-400 text-sm">
          Open a project first to configure settings.
        </p>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-full bg-white dark:bg-gray-900">
        <p role="status" className="text-gray-500 dark:text-gray-400 text-sm">Loading settings...</p>
      </div>
    )
  }

  if (loadError) {
    return (
      <div className="flex flex-col items-center justify-center h-full bg-white dark:bg-gray-900">
        <div role="alert" className="text-center">
          <p className="text-red-600 dark:text-red-400 text-sm font-medium">Failed to load settings</p>
          <p className="text-gray-500 dark:text-gray-400 text-xs mt-1">{loadError}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full bg-white dark:bg-gray-900 overflow-hidden">
      {/* Page header */}
      <div className="px-6 pt-5 pb-3 border-b border-gray-200 dark:border-gray-700 flex-shrink-0">
        <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Settings</h1>
        <p className="mt-0.5 text-sm text-gray-500 dark:text-gray-400">
          Configure system hardware parameters and manage run profiles.
        </p>
      </div>

      {/* Non-destructive save error banner (defect 1: does NOT replace the page) */}
      {saveError && (
        <div role="alert" className="mx-6 mt-3 rounded-md border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 px-4 py-2 text-sm text-red-700 dark:text-red-300">
          <span className="font-medium">Save failed:</span> {saveError}
        </div>
      )}

      {/* Horizontal tab bar */}
      <div
        className="flex border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shrink-0"
        role="tablist"
        aria-label="Settings sections"
        tabIndex={-1}
        onKeyDown={(e) => {
          const tabEls = Array.from(
            e.currentTarget.querySelectorAll<HTMLElement>('[role="tab"]'),
          )
          const currentIndex = tabEls.findIndex((el) => el === document.activeElement)
          if (currentIndex === -1) return

          let newIndex = currentIndex
          if (e.key === 'ArrowRight') {
            newIndex = (currentIndex + 1) % tabEls.length
          } else if (e.key === 'ArrowLeft') {
            newIndex = (currentIndex - 1 + tabEls.length) % tabEls.length
          } else if (e.key === 'Home') {
            newIndex = 0
          } else if (e.key === 'End') {
            newIndex = tabEls.length - 1
          } else {
            return
          }
          e.preventDefault()
          tabEls[newIndex].focus()
          const nextTab = SETTINGS_TABS[newIndex]
          if (nextTab) setActiveTab(nextTab.id)
        }}
      >
        {SETTINGS_TABS.map((tab) => {
          const isActive = tab.id === activeTab
          return (
            <button
              key={tab.id}
              id={`settings-tab-${tab.id}`}
              role="tab"
              aria-selected={isActive}
              aria-controls={`settings-tabpanel-${tab.id}`}
              tabIndex={isActive ? 0 : -1}
              onClick={() => setActiveTab(tab.id)}
              className={[
                'px-5 py-2.5 text-sm font-medium whitespace-nowrap transition-colors border-b-2',
                isActive
                  ? 'border-blue-600 text-blue-700 dark:border-blue-400 dark:text-blue-300 bg-blue-50 dark:bg-blue-900/20'
                  : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:border-gray-300 dark:hover:border-gray-600',
              ].join(' ')}
            >
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* Tab panels — both kept in DOM so unsaved edits survive tab switches */}

      {/* Run Profiles tab panel */}
      <div
        id="settings-tabpanel-runProfiles"
        role="tabpanel"
        aria-labelledby="settings-tab-runProfiles"
        className={activeTab === 'runProfiles' ? 'flex-1 overflow-y-auto px-6 py-5 flex flex-col min-h-0' : 'hidden'}
      >
        {/* System params banner */}
        <SystemParamsBanner
          nGPUs={systemParams.nGPUs}
          nCpuCores={systemParams.nCpuCores}
          fastScratchDisk={systemParams.fastScratchDisk}
          onChange={handleSystemParamChange}
        />

        {/* Two-panel layout */}
        <div className="flex flex-1 min-h-0 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
          {/* Left: profile list */}
          <div className="w-56 flex-shrink-0">
            <ProfileList
              profiles={profiles}
              selectedId={selectedId}
              onSelect={select}
              onCreate={create}
              onDelete={remove}
            />
          </div>

          {/* Right: profile detail */}
          <div className="flex-1 min-w-0 overflow-hidden">
            {selectedProfile ? (
              <ProfileDetail profile={selectedProfile} onChange={handleProfileChange} />
            ) : (
              <div className="flex items-center justify-center h-full text-sm text-gray-400 dark:text-gray-600">
                Select a profile or create a new one.
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Environment tab panel */}
      <div
        id="settings-tabpanel-environment"
        role="tabpanel"
        aria-labelledby="settings-tab-environment"
        className={activeTab === 'environment' ? 'flex-1 overflow-hidden' : 'hidden'}
      >
        <EnvironmentPanel profiles={profiles} projectId={projectId} />
      </div>
    </div>
  )
}
