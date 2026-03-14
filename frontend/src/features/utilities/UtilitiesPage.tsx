/**
 * Utilities panel page.
 *
 * Provides standalone utility tools:
 *   1. System Check         – Verify emClarity installation via `emClarity check`
 *   2. Mask Creator         – Interface for `emClarity mask` command
 *   3. Volume Rescaler      – Interface for `emClarity rescale` command
 *   4. Geometry Operations  – Interface for `emClarity geometry` operations
 *
 * API calls:
 *   POST /api/v1/utilities/check    – Run emClarity check
 *   POST /api/v1/utilities/mask     – Run emClarity mask
 *   POST /api/v1/utilities/rescale  – Run emClarity rescale
 *   POST /api/v1/utilities/geometry – Run emClarity geometry operations
 */

import { useState } from 'react'
import type { ReactNode, InputHTMLAttributes, SelectHTMLAttributes } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import {
  CheckCircle,
  XCircle,
  Loader2,
  Play,
  Settings,
  Layers,
  Sliders,
  Terminal,
} from 'lucide-react'
import { apiClient, ApiError } from '@/api/client.ts'

// ---------------------------------------------------------------------------
// API Response Types
// ---------------------------------------------------------------------------

interface CheckResult {
  success: boolean
  output: string
  errors: string
}

interface CommandResult {
  success: boolean
  output: string
  command: string
}

interface GeometryResult extends CommandResult {
  operation: string
}

type UtilityResult = CheckResult | CommandResult | GeometryResult

type OperationState<T extends UtilityResult> =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; data: T }
  | { status: 'error'; message: string }

// ---------------------------------------------------------------------------
// Zod validation schemas
// ---------------------------------------------------------------------------

const paramFileField = z
  .string()
  .min(1, 'Parameter file path is required')
  .regex(/\.m$/, 'Must be a .m parameter file')

const maskSchema = z.object({
  param_file: paramFileField,
  tilt_series_name: z.string().min(1, 'Tilt series name is required'),
})

const rescaleSchema = z.object({
  param_file: paramFileField,
  target_pixel_size: z
    .number({ message: 'Must be a positive number' })
    .positive('Must be a positive number'),
})

const geometrySchema = z.object({
  param_file: paramFileField,
  operation: z.string().min(1, 'Please select an operation'),
  cycle: z
    .number({ message: 'Must be a positive integer' })
    .int('Must be an integer')
    .min(1, 'Cycle must be at least 1'),
})

type MaskFormData = z.infer<typeof maskSchema>
type RescaleFormData = z.infer<typeof rescaleSchema>
type GeometryFormData = z.infer<typeof geometrySchema>

// ---------------------------------------------------------------------------
// Geometry operations registry
// ---------------------------------------------------------------------------

const GEOMETRY_OPERATIONS = [
  { value: 'RemoveClasses', label: 'Remove Classes' },
  { value: 'RemoveFraction', label: 'Remove Fraction' },
  { value: 'RemoveLowScoringParticles', label: 'Remove Low-Scoring Particles' },
  { value: 'RestoreParticles', label: 'Restore Particles' },
  { value: 'PrintGeometry', label: 'Print Geometry' },
]

// ---------------------------------------------------------------------------
// Helper: extract human-readable error message
// ---------------------------------------------------------------------------

function extractErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    return `Request failed (${err.status} ${err.statusText})`
  }
  if (err instanceof Error) {
    return err.message
  }
  return 'An unexpected error occurred'
}

// ---------------------------------------------------------------------------
// Shared UI components
// ---------------------------------------------------------------------------

interface SectionCardProps {
  title: string
  icon: ReactNode
  children: ReactNode
}

function SectionCard({ title, icon, children }: SectionCardProps) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <div className="mb-4 flex items-center gap-3">
        <span className="text-blue-600 dark:text-blue-400">{icon}</span>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">{title}</h3>
      </div>
      {children}
    </div>
  )
}

interface FormFieldProps {
  label: string
  children: ReactNode
  error?: string
}

function FormField({ label, children, error }: FormFieldProps) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
        {label}
      </label>
      <div className="mt-1">{children}</div>
      {error != null && error !== '' && (
        <p className="mt-1 text-sm text-red-500">{error}</p>
      )}
    </div>
  )
}

const inputClass =
  'w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 ' +
  'placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 ' +
  'dark:border-gray-600 dark:bg-gray-700 dark:text-white dark:placeholder-gray-500'

const selectClass =
  'w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 ' +
  'focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 ' +
  'dark:border-gray-600 dark:bg-gray-700 dark:text-white'

type StyledInputProps = InputHTMLAttributes<HTMLInputElement>

function StyledInput(props: StyledInputProps) {
  return <input className={inputClass} {...props} />
}

type StyledSelectProps = SelectHTMLAttributes<HTMLSelectElement>

function StyledSelect(props: StyledSelectProps) {
  return <select className={selectClass} {...props} />
}

interface SubmitButtonProps {
  loading: boolean
  label: string
}

function SubmitButton({ loading, label }: SubmitButtonProps) {
  return (
    <button
      type="submit"
      disabled={loading}
      className="flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
    >
      {loading ? (
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
      ) : (
        <Play className="h-4 w-4" aria-hidden="true" />
      )}
      {label}
    </button>
  )
}

interface ResultOutputProps<T extends UtilityResult> {
  state: OperationState<T>
}

function ResultOutput<T extends UtilityResult>({ state }: ResultOutputProps<T>) {
  if (state.status === 'idle') {
    return null
  }

  if (state.status === 'loading') {
    return (
      <div className="mt-4 flex items-center gap-2 text-sm text-gray-500">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        Running command…
      </div>
    )
  }

  if (state.status === 'error') {
    return (
      <div
        role="alert"
        className="mt-4 flex items-start gap-2 rounded-md bg-red-50 p-3 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-400"
      >
        <XCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        {state.message}
      </div>
    )
  }

  const { data } = state
  const isSuccess = data.success
  const output = data.output
  const command = 'command' in data ? data.command : ''
  const errors = 'errors' in data ? (data as CheckResult).errors : ''

  return (
    <div className="mt-4 space-y-2" role="status" aria-live="polite">
      <div
        className={`flex items-center gap-2 text-sm font-medium ${
          isSuccess
            ? 'text-green-600 dark:text-green-400'
            : 'text-red-600 dark:text-red-400'
        }`}
      >
        {isSuccess ? (
          <CheckCircle className="h-4 w-4" aria-hidden="true" />
        ) : (
          <XCircle className="h-4 w-4" aria-hidden="true" />
        )}
        {isSuccess ? 'Command completed successfully' : 'Command failed'}
      </div>

      {command !== '' && (
        <p className="font-mono text-xs text-gray-500 dark:text-gray-400">
          $ {command}
        </p>
      )}

      {output !== '' && (
        <pre className="max-h-48 overflow-auto rounded-md bg-gray-900 p-3 font-mono text-xs text-gray-100 whitespace-pre-wrap">
          {output}
        </pre>
      )}

      {errors !== '' && (
        <pre className="max-h-32 overflow-auto rounded-md bg-red-900 p-3 font-mono text-xs text-red-100 whitespace-pre-wrap">
          {errors}
        </pre>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Section 1: System Check
// ---------------------------------------------------------------------------

function SystemCheckSection() {
  const [state, setState] = useState<OperationState<CheckResult>>({ status: 'idle' })

  function handleCheck() {
    setState({ status: 'loading' })
    apiClient
      .post<CheckResult>('/api/v1/utilities/check')
      .then((result) => {
        setState({ status: 'success', data: result })
      })
      .catch((err: unknown) => {
        setState({ status: 'error', message: extractErrorMessage(err) })
      })
  }

  return (
    <SectionCard title="System Check" icon={<Terminal className="h-5 w-5" />}>
      <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
        Verify that emClarity is correctly installed and all required dependencies are
        available on this system.
      </p>
      <button
        type="button"
        onClick={handleCheck}
        disabled={state.status === 'loading'}
        aria-label="Run emClarity system check"
        className="flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {state.status === 'loading' ? (
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        ) : (
          <Play className="h-4 w-4" aria-hidden="true" />
        )}
        Run Check
      </button>
      <ResultOutput state={state} />
    </SectionCard>
  )
}

// ---------------------------------------------------------------------------
// Section 2: Mask Creator
// ---------------------------------------------------------------------------

function MaskCreatorSection() {
  const [state, setState] = useState<OperationState<CommandResult>>({ status: 'idle' })

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<MaskFormData>({ resolver: zodResolver(maskSchema) })

  function onSubmit(data: MaskFormData) {
    setState({ status: 'loading' })
    apiClient
      .post<CommandResult>('/api/v1/utilities/mask', data)
      .then((result) => {
        setState({ status: 'success', data: result })
      })
      .catch((err: unknown) => {
        setState({ status: 'error', message: extractErrorMessage(err) })
      })
  }

  return (
    <SectionCard title="Mask Creator" icon={<Layers className="h-5 w-5" />}>
      <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
        Create particle masks using the{' '}
        <code className="rounded bg-gray-100 px-1 text-xs dark:bg-gray-700">
          emClarity mask
        </code>{' '}
        command.
      </p>
      <form
        onSubmit={handleSubmit(onSubmit)}
        className="space-y-4"
        noValidate
        aria-label="Mask creator form"
      >
        <FormField label="Parameter File" error={errors.param_file?.message}>
          <StyledInput
            {...register('param_file')}
            placeholder="param.m"
            aria-label="Parameter file path"
          />
        </FormField>

        <FormField label="Tilt Series Name" error={errors.tilt_series_name?.message}>
          <StyledInput
            {...register('tilt_series_name')}
            placeholder="tilt1"
            aria-label="Tilt series name"
          />
        </FormField>

        <SubmitButton loading={state.status === 'loading'} label="Create Mask" />
      </form>
      <ResultOutput state={state} />
    </SectionCard>
  )
}

// ---------------------------------------------------------------------------
// Section 3: Volume Rescaler
// ---------------------------------------------------------------------------

function VolumeRescalerSection() {
  const [state, setState] = useState<OperationState<CommandResult>>({ status: 'idle' })

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<RescaleFormData>({ resolver: zodResolver(rescaleSchema) })

  function onSubmit(data: RescaleFormData) {
    setState({ status: 'loading' })
    apiClient
      .post<CommandResult>('/api/v1/utilities/rescale', data)
      .then((result) => {
        setState({ status: 'success', data: result })
      })
      .catch((err: unknown) => {
        setState({ status: 'error', message: extractErrorMessage(err) })
      })
  }

  return (
    <SectionCard title="Volume Rescaler" icon={<Sliders className="h-5 w-5" />}>
      <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
        Rescale volume files to a new pixel size using the{' '}
        <code className="rounded bg-gray-100 px-1 text-xs dark:bg-gray-700">
          emClarity rescale
        </code>{' '}
        command.
      </p>
      <form
        onSubmit={handleSubmit(onSubmit)}
        className="space-y-4"
        noValidate
        aria-label="Volume rescaler form"
      >
        <FormField label="Parameter File" error={errors.param_file?.message}>
          <StyledInput
            {...register('param_file')}
            placeholder="param.m"
            aria-label="Parameter file path"
          />
        </FormField>

        <FormField label="Target Pixel Size (Å)" error={errors.target_pixel_size?.message}>
          <StyledInput
            {...register('target_pixel_size', { valueAsNumber: true })}
            type="number"
            step="0.01"
            min="0.01"
            placeholder="1.35"
            aria-label="Target pixel size in Angstroms"
          />
        </FormField>

        <SubmitButton loading={state.status === 'loading'} label="Rescale Volume" />
      </form>
      <ResultOutput state={state} />
    </SectionCard>
  )
}

// ---------------------------------------------------------------------------
// Section 4: Geometry Operations
// ---------------------------------------------------------------------------

function GeometryOperationsSection() {
  const [state, setState] = useState<OperationState<GeometryResult>>({ status: 'idle' })

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<GeometryFormData>({
    resolver: zodResolver(geometrySchema),
    defaultValues: { cycle: 1 },
  })

  function onSubmit(data: GeometryFormData) {
    setState({ status: 'loading' })
    apiClient
      .post<GeometryResult>('/api/v1/utilities/geometry', data)
      .then((result) => {
        setState({ status: 'success', data: result })
      })
      .catch((err: unknown) => {
        setState({ status: 'error', message: extractErrorMessage(err) })
      })
  }

  return (
    <SectionCard title="Geometry Operations" icon={<Settings className="h-5 w-5" />}>
      <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
        Perform geometry operations on the particle set using the{' '}
        <code className="rounded bg-gray-100 px-1 text-xs dark:bg-gray-700">
          emClarity geometry
        </code>{' '}
        command.
      </p>
      <form
        onSubmit={handleSubmit(onSubmit)}
        className="space-y-4"
        noValidate
        aria-label="Geometry operations form"
      >
        <FormField label="Operation" error={errors.operation?.message}>
          <StyledSelect {...register('operation')} aria-label="Geometry operation">
            <option value="">Select an operation…</option>
            {GEOMETRY_OPERATIONS.map(({ value, label }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </StyledSelect>
        </FormField>

        <FormField label="Parameter File" error={errors.param_file?.message}>
          <StyledInput
            {...register('param_file')}
            placeholder="param.m"
            aria-label="Parameter file path"
          />
        </FormField>

        <FormField label="Cycle Number" error={errors.cycle?.message}>
          <StyledInput
            {...register('cycle', { valueAsNumber: true })}
            type="number"
            min="1"
            step="1"
            placeholder="1"
            aria-label="Processing cycle number"
          />
        </FormField>

        <SubmitButton loading={state.status === 'loading'} label="Run Operation" />
      </form>
      <ResultOutput state={state} />
    </SectionCard>
  )
}

// ---------------------------------------------------------------------------
// Main page export
// ---------------------------------------------------------------------------

export function UtilitiesPage() {
  return (
    <div>
      <h2 className="text-2xl font-semibold text-gray-900 dark:text-white">Utilities</h2>
      <p className="mt-2 text-gray-500 dark:text-gray-400">
        Access standalone tools and utility functions for emClarity processing.
      </p>
      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <SystemCheckSection />
        <MaskCreatorSection />
        <VolumeRescalerSection />
        <GeometryOperationsSection />
      </div>
    </div>
  )
}
