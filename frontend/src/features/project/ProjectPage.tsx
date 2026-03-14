/**
 * Project manager page (landing / welcome mode).
 *
 * Shown at `/` when no project is loaded. Provides:
 *  1. emClarity branding + version
 *  2. Create New Project – form with name, directory, and microscope parameters;
 *     submits to POST /api/v1/projects then navigates to /project/:id/overview.
 *  3. Open Existing Project – directory path input; submits to
 *     POST /api/v1/projects/load then navigates to /project/:id/overview.
 *  4. Recent Projects – up to 5 previously opened projects from localStorage.
 */
import { useState, useCallback } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { apiClient, ApiError } from '@/api/client.ts'
import { useRecentProjects } from '@/hooks/useRecentProjects.ts'

// ---------------------------------------------------------------------------
// Types mirroring the backend response models
// ---------------------------------------------------------------------------

interface ProjectResponse {
  id: string
  name: string
  state: string
  directory: string
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
  onCreated: (project: ProjectResponse) => void
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
        onCreated(response)
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
// OpenProjectPanel – directory path input
// ---------------------------------------------------------------------------

interface OpenProjectPanelProps {
  onLoaded: (project: ProjectResponse) => void
}

function OpenProjectPanel({ onLoaded }: OpenProjectPanelProps) {
  const [directory, setDirectory] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  const handleLoad = useCallback(async () => {
    const trimmed = directory.trim()
    if (!trimmed) {
      setError('Directory path is required')
      return
    }
    setError(null)
    setIsLoading(true)
    try {
      const response = await apiClient.post<ProjectResponse>('/api/v1/projects/load', {
        directory: trimmed,
      })
      onLoaded(response)
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setError('Project directory not found. Check the path and ensure it is a valid emClarity project.')
      } else {
        setError('Failed to open project. Check the path and ensure the backend is running.')
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
    </div>
  )
}

// ---------------------------------------------------------------------------
// ProjectPage – main exported component
// ---------------------------------------------------------------------------

type View = 'home' | 'create'

export function ProjectPage() {
  const [view, setView] = useState<View>('home')
  const navigate = useNavigate()
  const { recentProjects, addRecentProject } = useRecentProjects()

  const handleProjectCreated = useCallback(
    (project: ProjectResponse) => {
      addRecentProject({ id: project.id, name: project.name, directory: project.directory })
      void navigate(`/project/${project.id}/overview`)
    },
    [navigate, addRecentProject],
  )

  const handleProjectOpened = useCallback(
    (project: ProjectResponse) => {
      addRecentProject({ id: project.id, name: project.name, directory: project.directory })
      void navigate(`/project/${project.id}/overview`)
    },
    [navigate, addRecentProject],
  )

  const handleBack = useCallback(() => {
    setView('home')
  }, [])

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

  // Welcome / home view
  return (
    <div className="space-y-8">
      {/* emClarity branding */}
      <div className="text-center pt-4">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-blue-600 dark:bg-blue-500 mb-4 shadow-lg">
          <span className="text-2xl font-bold text-white select-none">eC</span>
        </div>
        <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100 tracking-tight">
          emClarity
        </h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Cryo-ET Sub-tomogram Averaging · v1.5.3
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
            onClick={() => setView('create')}
            className="mt-4 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:bg-blue-500 dark:hover:bg-blue-600"
          >
            Create Project
          </button>
        </div>

        {/* Open existing project card */}
        <div className="rounded-lg border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-900">
          <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">
            Open Existing Project
          </h3>
          <p className="mt-1 mb-4 text-sm text-gray-500 dark:text-gray-400">
            Enter the path to an existing emClarity project directory.
          </p>
          <OpenProjectPanel onLoaded={handleProjectOpened} />
        </div>
      </div>

      {/* Recent projects */}
      {recentProjects.length > 0 && (
        <section aria-labelledby="recent-heading">
          <h3
            id="recent-heading"
            className="mb-3 text-sm font-medium text-gray-700 dark:text-gray-300"
          >
            Recent Projects
          </h3>
          <div className="rounded-lg border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900 divide-y divide-gray-100 dark:divide-gray-800">
            {recentProjects.map((project) => (
              <Link
                key={project.id}
                to={`/project/${project.id}/overview`}
                className="flex items-start justify-between px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors group"
              >
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-gray-900 dark:text-gray-100 group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors truncate">
                    {project.name}
                  </p>
                  <p className="mt-0.5 text-xs font-mono text-gray-400 dark:text-gray-500 truncate">
                    {project.directory}
                  </p>
                </div>
                <span className="ml-3 flex-shrink-0 text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap">
                  {new Date(project.lastOpened).toLocaleDateString()}
                </span>
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
