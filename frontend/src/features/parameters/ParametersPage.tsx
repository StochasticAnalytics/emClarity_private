/**
 * Parameter editor page.
 *
 * Provides a tabbed, form-based interface for editing emClarity processing
 * parameters. Parameters are grouped by category (microscope, hardware,
 * ctf, alignment, classification, etc.), each displayed in its own tab.
 *
 * The parameter schema is fetched from GET /api/v1/parameters/schema on
 * mount via react-query. Form submission calls POST /api/v1/parameters/validate
 * to validate parameter values against the backend schema.
 */
import { useState, useMemo, useCallback, useRef, type ChangeEvent } from 'react'
import { useTabParam } from '@/hooks/useTabParam'
import { ParameterCategoryTab } from './ParameterCategoryTab.tsx'
import { useApiQuery } from '@/hooks/useApi.ts'
import {
  PARAMETER_SCHEMA_ENDPOINT,
  parameterQueryKeys,
  validateParameters,
  parseMatlabContent,
  generateMatlabContent,
} from '@/api/parameters.ts'
import type {
  ParameterCategory,
  ParameterDefinition,
  ParameterGroup,
  ParameterSchemaResponse,
} from '@/types/parameters.ts'
import { CATEGORY_LABELS, CATEGORY_ORDER } from '@/types/parameters.ts'

/**
 * Groups a flat list of parameter definitions by category,
 * respecting the defined display order.
 */
function groupByCategory(parameters: ParameterDefinition[]): ParameterGroup[] {
  const grouped = new Map<ParameterCategory, ParameterDefinition[]>()

  for (const param of parameters) {
    const existing = grouped.get(param.category)
    if (existing) {
      existing.push(param)
    } else {
      grouped.set(param.category, [param])
    }
  }

  // Build groups in the standard display order, then append any extras
  const orderedGroups: ParameterGroup[] = []
  const seen = new Set<ParameterCategory>()

  for (const category of CATEGORY_ORDER) {
    const params = grouped.get(category)
    if (params && params.length > 0) {
      orderedGroups.push({
        category,
        label: CATEGORY_LABELS[category] ?? category,
        parameters: params,
      })
      seen.add(category)
    }
  }

  // Include any categories not in the predefined order
  for (const [category, params] of grouped) {
    if (!seen.has(category) && params.length > 0) {
      orderedGroups.push({
        category,
        label: CATEGORY_LABELS[category] ?? category,
        parameters: params,
      })
    }
  }

  return orderedGroups
}

export function ParametersPage() {
  // Fetch parameter schema from the backend API on mount via react-query.
  // Falls back to the static bundled schema when the backend is unreachable
  // (handled inside fetchParameterSchema / the api client).
  const {
    data: schema,
    isLoading,
    error,
  } = useApiQuery<ParameterSchemaResponse>(
    parameterQueryKeys.schema(),
    PARAMETER_SCHEMA_ENDPOINT,
  )

  // Active tab — persisted in URL ?tab= query parameter
  const [activeTab, setActiveTab] = useTabParam(CATEGORY_ORDER)
  const [values, setValues] = useState<Record<string, unknown>>({})
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [isValidating, setIsValidating] = useState(false)

  // ── Import state ───────────────────────────────────────────────────────────
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [importStatus, setImportStatus] = useState<
    'idle' | 'loading' | 'success' | 'error'
  >('idle')
  const [importError, setImportError] = useState<string | null>(null)

  // ── Export state ───────────────────────────────────────────────────────────
  const [exportStatus, setExportStatus] = useState<
    'idle' | 'loading' | 'success' | 'error'
  >('idle')

  const groups = useMemo(() => {
    if (!schema?.parameters) return []
    return groupByCategory(schema.parameters)
  }, [schema])

  const activeGroup = useMemo(
    () => groups.find((g) => g.category === activeTab),
    [groups, activeTab],
  )

  const handleChange = useCallback((name: string, value: unknown) => {
    setValues((prev) => ({ ...prev, [name]: value }))
    // Clear any existing error when user modifies the field
    setErrors((prev) => {
      if (prev[name]) {
        const next = { ...prev }
        delete next[name]
        return next
      }
      return prev
    })
  }, [])

  /**
   * Validate form values by:
   * 1. Running client-side required-field and range checks for instant feedback
   * 2. Calling POST /api/v1/parameters/validate for server-side validation
   *
   * Errors from both passes are merged and displayed inline next to each field.
   */
  const handleValidate = useCallback(async () => {
    if (!schema?.parameters || isValidating) return

    setIsValidating(true)
    const newErrors: Record<string, string> = {}

    // --- Client-side validation pass ---
    for (const param of schema.parameters) {
      const val = values[param.name]

      // Check required fields
      if (param.required && (val === undefined || val === null || val === '')) {
        newErrors[param.name] = `${param.name} is required`
      }

      // Check numeric range
      if (
        param.type === 'numeric' &&
        param.range &&
        typeof val === 'number'
      ) {
        const [min, max] = param.range
        if (val < min || val > max) {
          newErrors[param.name] = `Value must be between ${String(min)} and ${String(max)}`
        }
      }
    }

    // --- Server-side validation via POST /api/v1/parameters/validate ---
    try {
      const result = await validateParameters(values)
      if (!result.valid) {
        for (const errMsg of result.errors) {
          // Extract parameter name from messages like "Parameter 'FOO' ..."
          const match = /Parameter '(\w+)'/.exec(errMsg)
          if (match?.[1]) {
            const paramName = match[1]
            // Prefer the more specific server error message
            newErrors[paramName] = errMsg
          }
        }
      }
    } catch {
      // Backend unreachable – client-side errors are still applied above
    }

    setErrors(newErrors)
    setIsValidating(false)
  }, [schema, values, isValidating])

  /**
   * Trigger the hidden file input to open the browser's file picker.
   */
  const handleImportClick = useCallback(() => {
    setImportStatus('idle')
    setImportError(null)
    fileInputRef.current?.click()
  }, [])

  /**
   * Handle file selection from the browser file picker.
   *
   * Reads the selected ``.m`` file as text, parses key-value pairs
   * (including deprecated-name migration using the loaded schema),
   * and merges the result into the current form values.
   */
  const handleFileChange = useCallback(
    (event: ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0]
      if (!file) return

      setImportStatus('loading')
      setImportError(null)

      const reader = new FileReader()
      reader.onload = (e) => {
        const content = e.target?.result
        if (typeof content !== 'string') {
          setImportStatus('error')
          setImportError('Failed to read file content.')
          return
        }
        try {
          const parsed = parseMatlabContent(content, schema?.parameters ?? [])
          setValues((prev) => ({ ...prev, ...parsed }))
          setImportStatus('success')
          // Clear field-level errors for freshly imported parameters.
          setErrors((prev) => {
            const next = { ...prev }
            for (const name of Object.keys(parsed)) {
              delete next[name]
            }
            return next
          })
        } catch (err) {
          setImportStatus('error')
          setImportError(
            err instanceof Error ? err.message : 'Failed to parse parameter file.',
          )
        }
      }
      reader.onerror = () => {
        setImportStatus('error')
        setImportError('Failed to read the selected file.')
      }
      reader.readAsText(file)

      // Reset the input so the same file can be re-imported if needed.
      event.target.value = ''
    },
    [schema],
  )

  /**
   * Serialise the current form values to MATLAB ``.m`` format and
   * trigger a browser download so the user can save the file locally.
   */
  const handleExport = useCallback(() => {
    if (Object.keys(values).length === 0) return

    setExportStatus('loading')
    try {
      const content = generateMatlabContent(values)
      const blob = new Blob([content], { type: 'text/plain' })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = 'param.m'
      anchor.click()
      URL.revokeObjectURL(url)
      setExportStatus('success')
    } catch {
      setExportStatus('error')
    }
  }, [values])

  // Loading state
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
        <span className="ml-3 text-gray-500">Loading parameter schema...</span>
      </div>
    )
  }

  // Error state
  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-6 dark:border-red-800 dark:bg-red-900/20">
        <h2 className="text-lg font-semibold text-red-800 dark:text-red-200">
          Failed to load parameter schema
        </h2>
        <p className="mt-2 text-sm text-red-600 dark:text-red-400">
          {error.message}
        </p>
      </div>
    )
  }

  // Empty state — schema not yet available
  if (!schema?.parameters || groups.length === 0) {
    return (
      <div className="space-y-4">
        <div>
          <h2 className="text-2xl font-semibold">Parameters</h2>
          <p className="mt-1 text-gray-500 dark:text-gray-400">
            Configure processing parameters for the current project.
          </p>
        </div>

        <div className="rounded-lg border border-gray-200 bg-white p-8 text-center dark:border-gray-700 dark:bg-gray-900">
          <svg
            className="mx-auto h-12 w-12 text-gray-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M10.5 6h9.75M10.5 6a1.5 1.5 0 11-3 0m3 0a1.5 1.5 0 10-3 0M3.75 6H7.5m3 12h9.75m-9.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-3.75 0H7.5m9-6h3.75m-3.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-9.75 0h9.75"
            />
          </svg>
          <h3 className="mt-4 text-lg font-medium text-gray-900 dark:text-gray-100">
            No parameter schema loaded
          </h3>
          <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
            Connect to the backend API to load the parameter schema and
            configure processing parameters.
          </p>
        </div>
      </div>
    )
  }

  // Full parameter editor
  return (
    <div className="space-y-4">
      {/* Hidden file input for Import */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".m"
        className="hidden"
        aria-hidden="true"
        onChange={handleFileChange}
      />

      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold">Parameters</h2>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            {schema.parameters.length} parameters across {String(groups.length)} categories.
            Required fields are marked with{' '}
            <span className="text-red-500">*</span>
          </p>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-2">
          {/* Import status feedback */}
          {importStatus === 'success' && (
            <span className="text-xs text-green-600 dark:text-green-400">
              Imported ✓
            </span>
          )}
          {importStatus === 'error' && importError && (
            <span className="max-w-xs truncate text-xs text-red-600 dark:text-red-400" title={importError}>
              {importError}
            </span>
          )}

          {/* Export status feedback */}
          {exportStatus === 'success' && (
            <span className="text-xs text-green-600 dark:text-green-400">
              Exported ✓
            </span>
          )}

          {/* Import button – opens browser file picker */}
          <button
            type="button"
            onClick={handleImportClick}
            disabled={importStatus === 'loading'}
            className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
          >
            {importStatus === 'loading' ? 'Importing…' : 'Import'}
          </button>

          {/* Export button – generates and downloads param.m */}
          <button
            type="button"
            onClick={handleExport}
            disabled={exportStatus === 'loading' || Object.keys(values).length === 0}
            className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
          >
            {exportStatus === 'loading' ? 'Exporting…' : 'Export'}
          </button>

          <button
            type="button"
            onClick={() => { void handleValidate() }}
            disabled={isValidating}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-blue-500 dark:hover:bg-blue-600"
          >
            {isValidating ? 'Validating…' : 'Validate'}
          </button>
        </div>
      </div>

      {/* Category tabs */}
      <div className="border-b border-gray-200 dark:border-gray-700">
        <nav className="-mb-px flex space-x-1 overflow-x-auto" aria-label="Parameter categories">
          {groups.map((group) => {
            const isActive = group.category === activeTab
            const groupErrors = group.parameters.filter(
              (p) => errors[p.name],
            ).length
            return (
              <button
                key={group.category}
                type="button"
                onClick={() => setActiveTab(group.category)}
                className={`
                  whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition-colors
                  ${
                    isActive
                      ? 'border-blue-500 text-blue-600 dark:border-blue-400 dark:text-blue-400'
                      : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
                  }
                `}
                aria-current={isActive ? 'page' : undefined}
              >
                {group.label}
                <span className="ml-1.5 text-xs text-gray-400 dark:text-gray-500">
                  ({String(group.parameters.length)})
                </span>
                {groupErrors > 0 && (
                  <span className="ml-1 inline-flex h-4 w-4 items-center justify-center rounded-full bg-red-100 text-xs text-red-600 dark:bg-red-900 dark:text-red-300">
                    {String(groupErrors)}
                  </span>
                )}
              </button>
            )
          })}
        </nav>
      </div>

      {/* Active tab content */}
      <div className="rounded-lg border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-900">
        {activeGroup ? (
          <ParameterCategoryTab
            group={activeGroup}
            values={values}
            errors={errors}
            onChange={handleChange}
          />
        ) : (
          <p className="text-sm text-gray-500">
            Select a category tab above to view parameters.
          </p>
        )}
      </div>

      {/* Validation error summary */}
      {Object.keys(errors).length > 0 && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-900/20">
          <h3 className="text-sm font-medium text-red-800 dark:text-red-200">
            Validation errors ({String(Object.keys(errors).length)})
          </h3>
          <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-red-700 dark:text-red-300">
            {Object.entries(errors).map(([name, msg]) => (
              <li key={name}>
                <span className="font-mono text-xs">{name}</span>: {msg}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
