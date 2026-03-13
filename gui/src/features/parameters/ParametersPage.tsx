/**
 * Parameter editor page.
 *
 * Provides a tabbed, form-based interface for editing emClarity processing
 * parameters. Parameters are grouped by category (microscope, hardware,
 * ctf, alignment, classification, etc.), each displayed in its own tab.
 *
 * This component currently uses a static parameter schema loaded from the
 * golden schema JSON. Backend API integration will be added in TASK-002c.
 */
import { useState, useMemo, useCallback } from 'react'
import { ParameterCategoryTab } from './ParameterCategoryTab.tsx'
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

/** Static schema data — will be replaced with API fetch in TASK-002c */
function useParameterSchema(): {
  data: ParameterSchemaResponse | undefined
  isLoading: boolean
  error: Error | null
} {
  // For now, return undefined (no data loaded yet).
  // The component handles the empty state gracefully.
  // In TASK-002c, this will be replaced with:
  //   useApiQuery<ParameterSchemaResponse>(['parameters', 'schema'], '/api/v1/parameters/schema')
  return {
    data: undefined,
    isLoading: false,
    error: null,
  }
}

export function ParametersPage() {
  const { data: schema, isLoading, error } = useParameterSchema()
  const [activeTab, setActiveTab] = useState<ParameterCategory>('microscope')
  const [values, setValues] = useState<Record<string, unknown>>({})
  const [errors, setErrors] = useState<Record<string, string>>({})

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

  const handleValidate = useCallback(() => {
    if (!schema?.parameters) return

    const newErrors: Record<string, string> = {}

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

    setErrors(newErrors)
  }, [schema, values])

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

  // Empty state — no schema loaded yet (pre-integration)
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
        <button
          type="button"
          onClick={handleValidate}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:bg-blue-500 dark:hover:bg-blue-600"
        >
          Validate
        </button>
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
