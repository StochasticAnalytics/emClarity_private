/**
 * Project manager page (landing page / welcome screen).
 *
 * Provides two workflows:
 *  1. Create New Project – wizard dialog with name, directory, and microscope
 *     parameters; submits to POST /api/v1/projects then navigates to overview.
 *  2. Open Existing Project – enter a directory path and call
 *     POST /api/v1/projects/load to open it.
 *
 * Recent projects are fetched from the server-side registry via
 * useRecentProjects. Stale entries (backend returns 404) are automatically
 * removed.
 */
import { useState, useCallback, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { apiClient, ApiError } from '@/api/client.ts'
import { useRecentProjects } from '@/hooks/useRecentProjects.ts'
import { DirectoryPickerModal } from '@/components/common/DirectoryPickerModal.tsx'

// ---------------------------------------------------------------------------
// Types mirroring the backend response models
// ---------------------------------------------------------------------------

interface ProjectResponse {
  id: string
  name: string
  directory: string
  state: string
}

// ---------------------------------------------------------------------------
// Zod schema for the create-project form
// ---------------------------------------------------------------------------

const createProjectSchema = z.object({
  name: z.string().min(1, 'Project name is required'),
  directory: z.string().min(1, 'Directory path is required'),
  PIXEL_SIZE: z.coerce.number().positive('Must be a positive value'),
  Cs: z.coerce.number().positive('Must be a positive value'),
  VOLTAGE: z.coerce.number().positive('Must be a positive value'),
  AMPCONT: z.coerce.number().min(0, 'Must be ≥ 0').max(1, 'Must be ≤ 1'),
})

type CreateProjectFormValues = z.infer<typeof createProjectSchema>

// ---------------------------------------------------------------------------
// Shared input styling
// ---------------------------------------------------------------------------

const inputClass =
  'mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm ' +
  'focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 ' +
  'dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100'

const labelClass = 'block text-sm font-medium text-gray-700 dark:text-gray-300'

// ---------------------------------------------------------------------------
// NewProjectForm
// ---------------------------------------------------------------------------

interface NewProjectFormProps {
  onCreated: (projectId: string, name: string, directory: string) => void
}

function NewProjectForm({ onCreated }: NewProjectFormProps) {
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isPickerOpen, setIsPickerOpen] = useState(false)

  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors },
  } = useForm<CreateProjectFormValues>({
    resolver: zodResolver(createProjectSchema),
  })

  const onSubmit = useCallback(
    async (data: CreateProjectFormValues) => {
      setSubmitError(null)
      setIsSubmitting(true)
      try {
        const response = await apiClient.post<ProjectResponse>('/api/v1/projects', {
          name: data.name,
          directory: data.directory,
          parameters: {
            PIXEL_SIZE: data.PIXEL_SIZE,
            Cs: data.Cs,
            VOLTAGE: data.VOLTAGE,
            AMPCONT: data.AMPCONT,
          },
        })
        onCreated(response.id, data.name, data.directory)
      } catch (err) {
        if (err instanceof ApiError) {
          const rawBody: unknown = err.body
          const detail =
            rawBody !== null &&
            typeof rawBody === 'object' &&
            'detail' in rawBody &&
            typeof (rawBody as Record<string, unknown>).detail === 'string'
              ? ((rawBody as Record<string, unknown>).detail as string)
              : undefined
          setSubmitError(`Failed to create project: ${detail ?? err.message}`)
        } else {
          setSubmitError('An unexpected error occurred. Is the backend running?')
        }
      } finally {
        setIsSubmitting(false)
      }
    },
    [onCreated],
  )

  return (
    <form
      onSubmit={handleSubmit((data) => {
        void onSubmit(data)
      })}
      className="space-y-6"
    >
      {/* Project details */}
      <section className="space-y-4">
        <h3 className="text-base font-medium text-gray-900 dark:text-gray-100">
          Project Details
        </h3>

        <div>
          <label htmlFor="project-name" className={labelClass}>
            Project Name <span className="text-red-500">*</span>
          </label>
          <input
            id="project-name"
            type="text"
            autoComplete="off"
            placeholder="my_project"
            {...register('name')}
            className={inputClass}
          />
          {errors.name && (
            <p className="mt-1 text-xs text-red-600 dark:text-red-400">{errors.name.message}</p>
          )}
        </div>

        <div>
          <label htmlFor="project-directory" className={labelClass}>
            Directory Path <span className="text-red-500">*</span>
          </label>
          <div className="mt-1 flex gap-2">
            <input
              id="project-directory"
              type="text"
              autoComplete="off"
              placeholder="/path/to/project"
              {...register('directory')}
              className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
            />
            <button
              type="button"
              onClick={() => setIsPickerOpen(true)}
              aria-label="Browse for directory"
              className="shrink-0 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
            >
              Browse…
            </button>
          </div>
          {errors.directory && (
            <p className="mt-1 text-xs text-red-600 dark:text-red-400">
              {errors.directory.message}
            </p>
          )}
        </div>

        <DirectoryPickerModal
          isOpen={isPickerOpen}
          onSelect={(path) => {
            setValue('directory', path, { shouldValidate: true })
            setIsPickerOpen(false)
          }}
          onClose={() => setIsPickerOpen(false)}
        />
      </section>

      {/* Microscope parameters */}
      <section className="space-y-4">
        <h3 className="text-base font-medium text-gray-900 dark:text-gray-100">
          Microscope Parameters
        </h3>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="param-pixel-size" className={labelClass}>
              Pixel Size (Å) <span className="text-red-500">*</span>
            </label>
            <input
              id="param-pixel-size"
              type="number"
              step="any"
              placeholder="1.35"
              {...register('PIXEL_SIZE', { valueAsNumber: true })}
              className={inputClass}
            />
            {errors.PIXEL_SIZE && (
              <p className="mt-1 text-xs text-red-600 dark:text-red-400">
                {errors.PIXEL_SIZE.message}
              </p>
            )}
          </div>

          <div>
            <label htmlFor="param-cs" className={labelClass}>
              Cs (mm) <span className="text-red-500">*</span>
            </label>
            <input
              id="param-cs"
              type="number"
              step="any"
              placeholder="2.7"
              {...register('Cs', { valueAsNumber: true })}
              className={inputClass}
            />
            {errors.Cs && (
              <p className="mt-1 text-xs text-red-600 dark:text-red-400">{errors.Cs.message}</p>
            )}
          </div>

          <div>
            <label htmlFor="param-voltage" className={labelClass}>
              Voltage (V) <span className="text-red-500">*</span>
            </label>
            <input
              id="param-voltage"
              type="number"
              step="any"
              placeholder="300000"
              {...register('VOLTAGE', { valueAsNumber: true })}
              className={inputClass}
            />
            {errors.VOLTAGE && (
              <p className="mt-1 text-xs text-red-600 dark:text-red-400">
                {errors.VOLTAGE.message}
              </p>
            )}
          </div>

          <div>
            <label htmlFor="param-ampcont" className={labelClass}>
              Amplitude Contrast <span className="text-red-500">*</span>
            </label>
            <input
              id="param-ampcont"
              type="number"
              step="any"
              placeholder="0.07"
              {...register('AMPCONT', { valueAsNumber: true })}
              className={inputClass}
            />
            {errors.AMPCONT && (
              <p className="mt-1 text-xs text-red-600 dark:text-red-400">
                {errors.AMPCONT.message}
              </p>
            )}
          </div>
        </div>
      </section>

      {submitError && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-900/20">
          <p className="text-sm text-red-600 dark:text-red-400">{submitError}</p>
        </div>
      )}

      <button
        type="submit"
        disabled={isSubmitting}
        className="w-full rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-blue-500 dark:hover:bg-blue-600"
      >
        {isSubmitting ? 'Creating…' : 'Create Project'}
      </button>
    </form>
  )
}

// ---------------------------------------------------------------------------
// LoadProjectPanel
// ---------------------------------------------------------------------------

interface LoadProjectPanelProps {
  onLoaded: (projectId: string, name: string, directory: string) => void
}

function LoadProjectPanel({ onLoaded }: LoadProjectPanelProps) {
  const [directory, setDirectory] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isPickerOpen, setIsPickerOpen] = useState(false)

  const handleLoad = useCallback(async () => {
    const trimmed = directory.trim()
    if (!trimmed) {
      setError('Directory path is required')
      return
    }
    setError(null)
    setIsLoading(true)
    try {
      const project = await apiClient.post<ProjectResponse>('/api/v1/projects/load', {
        directory: trimmed,
      })
      onLoaded(project.id, project.name, project.directory)
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setError('Directory not found. Check that the path exists and is an emClarity project.')
      } else if (err instanceof ApiError && err.status === 400) {
        const rawBody: unknown = err.body
        const detail =
          rawBody !== null &&
          typeof rawBody === 'object' &&
          'detail' in rawBody &&
          typeof (rawBody as Record<string, unknown>).detail === 'string'
            ? ((rawBody as Record<string, unknown>).detail as string)
            : undefined
        setError(`Invalid path: ${detail ?? err.message}`)
      } else {
        setError('Failed to load project. Check the path and ensure the backend is running.')
      }
    } finally {
      setIsLoading(false)
    }
  }, [directory, onLoaded])

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <input
          type="text"
          value={directory}
          onChange={(e) => {
            setDirectory(e.target.value)
            setError(null)
          }}
          placeholder="/path/to/existing/project"
          aria-label="Project directory path"
          className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              void handleLoad()
            }
          }}
        />
        <button
          type="button"
          onClick={() => setIsPickerOpen(true)}
          aria-label="Browse for project directory"
          className="shrink-0 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
        >
          Browse…
        </button>
        <button
          type="button"
          onClick={() => {
            void handleLoad()
          }}
          disabled={isLoading}
          className="rounded-md bg-gray-700 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-gray-600 dark:hover:bg-gray-500"
        >
          {isLoading ? 'Opening…' : 'Open'}
        </button>
      </div>
      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
      <DirectoryPickerModal
        isOpen={isPickerOpen}
        onSelect={(path) => {
          setDirectory(path)
          setIsPickerOpen(false)
        }}
        onClose={() => setIsPickerOpen(false)}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// RecentProjectsList
// ---------------------------------------------------------------------------

interface RecentProjectsListProps {
  projects: { id: string; name: string; directory: string; lastAccessed: string }[]
  onOpen: (projectId: string, name: string, directory: string) => void
  onRemove: (projectId: string) => void | Promise<void>
}

function RecentProjectsList({ projects, onOpen, onRemove }: RecentProjectsListProps) {
  const [loadingId, setLoadingId] = useState<string | null>(null)
  const [errorId, setErrorId] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const removeTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())

  useEffect(() => {
    const timers = removeTimersRef.current
    return () => {
      timers.forEach((timer) => clearTimeout(timer))
    }
  }, [])

  // Early return must be after all hooks to satisfy the Rules of Hooks.
  if (projects.length === 0) return null

  const handleOpen = async (id: string, name: string, directory: string) => {
    setLoadingId(id)
    setErrorId(null)
    setErrorMessage(null)
    try {
      // Verify project still exists on backend before navigating
      await apiClient.get<ProjectResponse>(`/api/v1/projects/${id}`)
      onOpen(id, name, directory)
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        // Show error on the entry first, then remove it after a brief delay
        // so the user sees the "not found" message before it disappears.
        setErrorId(id)
        const existing = removeTimersRef.current.get(id)
        if (existing !== undefined) clearTimeout(existing)
        const timer = setTimeout(() => {
          removeTimersRef.current.delete(id)
          void onRemove(id)
        }, 2000)
        removeTimersRef.current.set(id, timer)
      } else {
        // For non-404 errors (403, 500, network failures) show a message on the entry
        setErrorId(id)
        const msg =
          err instanceof ApiError
            ? `Could not open project (${err.status} ${err.statusText})`
            : err instanceof Error
              ? `Could not open project: ${err.message}`
              : 'Could not open project — unexpected error'
        setErrorMessage(msg)
      }
    } finally {
      setLoadingId(null)
    }
  }

  function formatDate(iso: string): string {
    try {
      return new Date(iso).toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    } catch {
      return iso
    }
  }

  return (
    <div>
      <h3 className="mb-2 text-sm font-medium text-gray-700 dark:text-gray-300">
        Recent Projects
      </h3>
      {/* Single aria-live region for all row-level errors — avoids N simultaneous
          live regions and uses 'polite' urgency which is appropriate for non-critical errors */}
      <span aria-live="polite" className="sr-only">
        {errorId !== null ? (errorMessage ?? 'Project not found on server — entry removed') : ''}
      </span>
      <ul className="divide-y divide-gray-100 rounded-lg border border-gray-200 bg-white dark:divide-gray-700 dark:border-gray-700 dark:bg-gray-900">
        {projects.map((p) => (
          <li key={p.id} className="flex items-center justify-between gap-3 px-4 py-3">
            <div className="min-w-0 flex-1">
              <button
                type="button"
                onClick={() => {
                  void handleOpen(p.id, p.name, p.directory)
                }}
                disabled={loadingId === p.id}
                className="block truncate text-left text-sm font-medium text-blue-600 hover:underline disabled:opacity-60 dark:text-blue-400"
              >
                {loadingId === p.id ? 'Opening…' : p.name}
              </button>
              <span className="block truncate font-mono text-xs text-gray-400 dark:text-gray-500">
                {p.directory}
              </span>
              <span className="text-xs text-red-500" aria-hidden="true">
                {errorId === p.id
                  ? (errorMessage ?? 'Project not found on server — entry removed')
                  : ''}
              </span>
            </div>
            <div className="shrink-0 text-right">
              <span className="block text-xs text-gray-400 dark:text-gray-500">
                {formatDate(p.lastAccessed)}
              </span>
              <button
                type="button"
                onClick={() => { void onRemove(p.id) }}
                className="mt-0.5 text-xs text-gray-300 hover:text-red-500 dark:text-gray-600 dark:hover:text-red-400"
                aria-label={`Remove ${p.name} from recent projects`}
              >
                remove
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}

// ---------------------------------------------------------------------------
// NewProjectDialog – modal wizard wrapping NewProjectForm
// ---------------------------------------------------------------------------

interface NewProjectDialogProps {
  isOpen: boolean
  onClose: () => void
  onCreated: (projectId: string, name: string, directory: string) => void
}

function NewProjectDialog({ isOpen, onClose, onCreated }: NewProjectDialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const onCloseRef = useRef(onClose)
  useEffect(() => { onCloseRef.current = onClose }, [onClose])

  // Escape key + focus trap
  useEffect(() => {
    if (!isOpen) return

    // Focus the dialog panel when it opens
    if (dialogRef.current) {
      dialogRef.current.focus()
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onCloseRef.current()
        return
      }

      if (e.key !== 'Tab') return

      const el = dialogRef.current
      if (!el) return

      const focusableSelectors =
        'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])'
      const focusableList = Array.from(el.querySelectorAll<HTMLElement>(focusableSelectors))
      if (focusableList.length === 0) return

      const first = focusableList[0]
      const last = focusableList[focusableList.length - 1]
      if (!first || !last) return

      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault()
          last.focus()
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isOpen])

  if (!isOpen) return null

  return (
    /* Backdrop */
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button
        type="button"
        className="absolute inset-0 bg-black/50 cursor-default"
        onClick={onClose}
        aria-label="Close dialog"
        tabIndex={-1}
      />
      {/* Dialog panel */}
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="new-project-dialog-title"
        tabIndex={-1}
        className="relative w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-xl border border-gray-200 bg-white shadow-2xl focus:outline-none dark:border-gray-700 dark:bg-gray-900"
      >
        {/* Dialog header */}
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4 dark:border-gray-700">
          <h2
            id="new-project-dialog-title"
            className="text-lg font-semibold text-gray-900 dark:text-gray-100"
          >
            New Project
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close dialog"
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:hover:bg-gray-800 dark:hover:text-gray-300"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Dialog body */}
        <div className="px-6 py-4">
          <NewProjectForm onCreated={onCreated} />
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// ProjectPage – main exported component
// ---------------------------------------------------------------------------

export function ProjectPage() {
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false)
  const navigate = useNavigate()
  const {
    projects: recentProjects,
    addProject,
    removeProject,
    isLoading: isRecentLoading,
    error: recentError,
  } = useRecentProjects()

  const handleProjectCreated = useCallback(
    (projectId: string, name: string, directory: string) => {
      setIsCreateDialogOpen(false)
      void addProject({ id: projectId, name, directory })
      void navigate(`/project/${projectId}/overview`)
    },
    [navigate, addProject],
  )

  const handleProjectLoaded = useCallback(
    (projectId: string, name: string, directory: string) => {
      void addProject({ id: projectId, name, directory })
      void navigate(`/project/${projectId}/overview`)
    },
    [navigate, addProject],
  )

  return (
    <>
      {/* New project wizard dialog */}
      <NewProjectDialog
        isOpen={isCreateDialogOpen}
        onClose={() => setIsCreateDialogOpen(false)}
        onCreated={handleProjectCreated}
      />

      <div className="space-y-8">
        {/* Branding header */}
        <div className="text-center py-6">
          <h1 className="text-4xl font-bold tracking-tight text-gray-900 dark:text-gray-100">
            emClarity
          </h1>
          <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
            Sub-tomogram averaging for cryo-electron tomography · v1.5.3.10
          </p>
        </div>

        {/* Action cards */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* Create new project card */}
          <div className="rounded-lg border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-900">
            <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">
              Create New Project
            </h3>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              Set up a new emClarity processing directory with initial microscope parameters.
            </p>
            <button
              type="button"
              onClick={() => setIsCreateDialogOpen(true)}
              className="mt-4 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:bg-blue-500 dark:hover:bg-blue-600"
            >
              Create Project
            </button>
          </div>

          {/* Load existing project card */}
          <div className="rounded-lg border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-900">
            <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">
              Open Existing Project
            </h3>
            <p className="mt-1 mb-4 text-sm text-gray-500 dark:text-gray-400">
              Open a previously created project by its directory path.
            </p>
            <LoadProjectPanel onLoaded={handleProjectLoaded} />
          </div>
        </div>

        {/* Recent projects */}
        {/* aria-live region announces loading state changes to assistive technology (WCAG 4.1.3) */}
        <span aria-live="polite" className="sr-only">
          {isRecentLoading ? 'Loading recent projects…' : ''}
        </span>
        {isRecentLoading ? (
          <p aria-hidden="true" className="text-sm text-gray-500 dark:text-gray-400">
            Loading recent projects…
          </p>
        ) : recentError ? (
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-900/20">
            <p className="text-sm text-red-600 dark:text-red-400">{recentError}</p>
          </div>
        ) : recentProjects.length === 0 ? (
          <p className="text-sm text-gray-500 dark:text-gray-400">No recent projects</p>
        ) : (
          <RecentProjectsList
            projects={recentProjects}
            onOpen={handleProjectLoaded}
            onRemove={removeProject}
          />
        )}
      </div>
    </>
  )
}
