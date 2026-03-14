/**
 * Project manager page.
 * Handles creating, opening, and managing emClarity projects.
 *
 * Provides two primary workflows:
 *  1. Create New Project – form with name, directory, and microscope parameters;
 *     submits to POST /api/v1/projects and navigates to the dashboard.
 *  2. Load Existing Project – enter a project ID to open its dashboard.
 *
 * The project dashboard fetches state and tilt-series data from:
 *  - GET /api/v1/projects/{id}
 *  - GET /api/v1/projects/{id}/tilt-series
 */
import { useState, useCallback } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { apiClient, ApiError } from '@/api/client.ts'
import { useApiQuery } from '@/hooks/useApi.ts'

// ---------------------------------------------------------------------------
// Types mirroring the backend response models
// ---------------------------------------------------------------------------

interface ProjectResponse {
  id: string
  name: string
  directory: string
  state: string
  parameters: Record<string, unknown>
  current_cycle: number
}

interface TiltSeriesItem {
  name: string
  stack_path?: string
  rawtlt_path?: string
  aligned: boolean
  ctf_estimated: boolean
}

interface TiltSeriesListResponse {
  tilt_series: TiltSeriesItem[]
}

// ---------------------------------------------------------------------------
// Zod schema for the create-project form
// ---------------------------------------------------------------------------

const createProjectSchema = z.object({
  name: z.string().min(1, 'Project name is required'),
  directory: z.string().min(1, 'Directory path is required'),
  PIXEL_SIZE: z.number().positive('Must be a positive value'),
  Cs: z.number().positive('Must be a positive value'),
  VOLTAGE: z.number().positive('Must be a positive value'),
  AMPCONT: z.number().min(0, 'Must be ≥ 0').max(1, 'Must be ≤ 1'),
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
  onCreated: (projectId: string) => void
}

function NewProjectForm({ onCreated }: NewProjectFormProps) {
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const {
    register,
    handleSubmit,
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
        onCreated(response.id)
      } catch (err) {
        if (err instanceof ApiError) {
          setSubmitError(`Failed to create project: ${err.message}`)
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
          <input
            id="project-directory"
            type="text"
            autoComplete="off"
            placeholder="/path/to/project"
            {...register('directory')}
            className={inputClass}
          />
          {errors.directory && (
            <p className="mt-1 text-xs text-red-600 dark:text-red-400">
              {errors.directory.message}
            </p>
          )}
        </div>
      </section>

      {/* Microscope parameters */}
      <section className="space-y-4">
        <h3 className="text-base font-medium text-gray-900 dark:text-gray-100">
          Microscope Parameters
        </h3>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {/* PIXEL_SIZE */}
          <div>
            <label htmlFor="param-pixel-size" className={labelClass}>
              Pixel Size (m) <span className="text-red-500">*</span>
            </label>
            <input
              id="param-pixel-size"
              type="number"
              step="any"
              placeholder="1.35e-10"
              {...register('PIXEL_SIZE', { valueAsNumber: true })}
              className={inputClass}
            />
            {errors.PIXEL_SIZE && (
              <p className="mt-1 text-xs text-red-600 dark:text-red-400">
                {errors.PIXEL_SIZE.message}
              </p>
            )}
          </div>

          {/* Cs */}
          <div>
            <label htmlFor="param-cs" className={labelClass}>
              Cs (m) <span className="text-red-500">*</span>
            </label>
            <input
              id="param-cs"
              type="number"
              step="any"
              placeholder="2.7e-3"
              {...register('Cs', { valueAsNumber: true })}
              className={inputClass}
            />
            {errors.Cs && (
              <p className="mt-1 text-xs text-red-600 dark:text-red-400">{errors.Cs.message}</p>
            )}
          </div>

          {/* VOLTAGE */}
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

          {/* AMPCONT */}
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

      {/* Submission error */}
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
// ProjectDashboard
// ---------------------------------------------------------------------------

interface ProjectDashboardProps {
  projectId: string
  onBack: () => void
}

function ProjectDashboard({ projectId, onBack }: ProjectDashboardProps) {
  const {
    data: project,
    isLoading: projectLoading,
    error: projectError,
  } = useApiQuery<ProjectResponse>(['project', projectId], `/api/v1/projects/${projectId}`)

  const {
    data: tiltsData,
    isLoading: tiltsLoading,
    error: tiltsError,
  } = useApiQuery<TiltSeriesListResponse>(
    ['project-tilt-series', projectId],
    `/api/v1/projects/${projectId}/tilt-series`,
  )

  if (projectLoading || tiltsLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
        <span className="ml-3 text-gray-500 dark:text-gray-400">Loading project…</span>
      </div>
    )
  }

  if (projectError) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-6 dark:border-red-800 dark:bg-red-900/20">
        <h3 className="font-semibold text-red-800 dark:text-red-200">Failed to load project</h3>
        <p className="mt-1 text-sm text-red-600 dark:text-red-400">{projectError.message}</p>
        <button
          type="button"
          onClick={onBack}
          className="mt-4 text-sm text-red-600 underline hover:text-red-800 dark:text-red-400"
        >
          ← Back
        </button>
      </div>
    )
  }

  if (!project) return null

  const tiltSeries = tiltsData?.tilt_series ?? []

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-xl font-semibold text-gray-900 dark:text-gray-100">{project.name}</h3>
          <p className="mt-1 break-all font-mono text-xs text-gray-500 dark:text-gray-400">
            {project.directory}
          </p>
        </div>
        <button
          type="button"
          onClick={onBack}
          className="shrink-0 rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
        >
          ← Back
        </button>
      </div>

      {/* Status summary cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900">
          <p className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
            State
          </p>
          <p className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100">
            {project.state}
          </p>
        </div>

        <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900">
          <p className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
            Current Cycle
          </p>
          <p className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100">
            {String(project.current_cycle)}
          </p>
        </div>

        <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900">
          <p className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
            Tilt Series
          </p>
          <p className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100">
            {String(tiltSeries.length)}
          </p>
        </div>
      </div>

      {/* Tilt-series list */}
      <section>
        <h4 className="mb-2 text-sm font-medium text-gray-700 dark:text-gray-300">
          Tilt Series
        </h4>

        {tiltsError ? (
          <p className="text-sm text-red-600 dark:text-red-400">
            Failed to load tilt series: {tiltsError.message}
          </p>
        ) : tiltSeries.length === 0 ? (
          <div className="rounded-lg border border-dashed border-gray-300 p-8 text-center dark:border-gray-600">
            <p className="text-sm text-gray-500 dark:text-gray-400">
              No tilt series found. Add <code className="font-mono">.st</code> files to the{' '}
              <code className="font-mono">rawData/</code> directory.
            </p>
          </div>
        ) : (
          <div className="overflow-hidden rounded-lg border border-gray-200 dark:border-gray-700">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead className="bg-gray-50 dark:bg-gray-800">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                    Name
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                    Aligned
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                    CTF Estimated
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 bg-white dark:divide-gray-700 dark:bg-gray-900">
                {tiltSeries.map((ts) => (
                  <tr key={ts.name}>
                    <td className="px-4 py-3 font-mono text-sm text-gray-900 dark:text-gray-100">
                      {ts.name}
                    </td>
                    <td className="px-4 py-3 text-sm">
                      <span
                        className={
                          ts.aligned
                            ? 'text-green-600 dark:text-green-400'
                            : 'text-gray-400 dark:text-gray-600'
                        }
                      >
                        {ts.aligned ? '✓' : '—'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm">
                      <span
                        className={
                          ts.ctf_estimated
                            ? 'text-green-600 dark:text-green-400'
                            : 'text-gray-400 dark:text-gray-600'
                        }
                      >
                        {ts.ctf_estimated ? '✓' : '—'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}

// ---------------------------------------------------------------------------
// LoadProjectPanel
// ---------------------------------------------------------------------------

interface LoadProjectPanelProps {
  onLoaded: (projectId: string) => void
}

function LoadProjectPanel({ onLoaded }: LoadProjectPanelProps) {
  const [projectId, setProjectId] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  const handleLoad = useCallback(async () => {
    const trimmed = projectId.trim()
    if (!trimmed) {
      setError('Project ID is required')
      return
    }
    setError(null)
    setIsLoading(true)
    try {
      await apiClient.get<ProjectResponse>(`/api/v1/projects/${trimmed}`)
      onLoaded(trimmed)
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setError('Project not found')
      } else {
        setError('Failed to load project. Check the ID and ensure the backend is running.')
      }
    } finally {
      setIsLoading(false)
    }
  }, [projectId, onLoaded])

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <input
          type="text"
          value={projectId}
          onChange={(e) => {
            setProjectId(e.target.value)
            setError(null)
          }}
          placeholder="Enter project ID…"
          aria-label="Project ID"
          className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              void handleLoad()
            }
          }}
        />
        <button
          type="button"
          onClick={() => {
            void handleLoad()
          }}
          disabled={isLoading}
          className="rounded-md bg-gray-700 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-gray-600 dark:hover:bg-gray-500"
        >
          {isLoading ? 'Loading…' : 'Load'}
        </button>
      </div>
      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// ProjectPage – main exported component
// ---------------------------------------------------------------------------

type View = 'home' | 'create' | 'dashboard'

export function ProjectPage() {
  const [view, setView] = useState<View>('home')
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null)

  const handleProjectCreated = useCallback((projectId: string) => {
    setActiveProjectId(projectId)
    setView('dashboard')
  }, [])

  const handleProjectLoaded = useCallback((projectId: string) => {
    setActiveProjectId(projectId)
    setView('dashboard')
  }, [])

  const handleBack = useCallback(() => {
    setView('home')
    setActiveProjectId(null)
  }, [])

  // Dashboard view
  if (view === 'dashboard' && activeProjectId) {
    return (
      <div className="space-y-4">
        <h2 className="text-2xl font-semibold">Project Manager</h2>
        <ProjectDashboard projectId={activeProjectId} onBack={handleBack} />
      </div>
    )
  }

  // Create project view
  if (view === 'create') {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleBack}
            className="text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
          >
            ← Back
          </button>
          <h2 className="text-2xl font-semibold">New Project</h2>
        </div>
        <div className="rounded-lg border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-900">
          <NewProjectForm onCreated={handleProjectCreated} />
        </div>
      </div>
    )
  }

  // Home view
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold">Project Manager</h2>
        <p className="mt-2 text-gray-500 dark:text-gray-400">
          Create or open an emClarity project to get started.
        </p>
      </div>

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
            onClick={() => setView('create')}
            className="mt-4 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:bg-blue-500 dark:hover:bg-blue-600"
          >
            Create Project
          </button>
        </div>

        {/* Load existing project card */}
        <div className="rounded-lg border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-900">
          <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">
            Load Existing Project
          </h3>
          <p className="mt-1 mb-4 text-sm text-gray-500 dark:text-gray-400">
            Open a previously created project by its ID.
          </p>
          <LoadProjectPanel onLoaded={handleProjectLoaded} />
        </div>
      </div>
    </div>
  )
}
