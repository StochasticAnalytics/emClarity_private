/**
 * Input widget for a single parameter.
 *
 * Renders the appropriate HTML input element based on the parameter type:
 *   - numeric     -> number input with optional min/max from range
 *   - numeric_array -> comma-separated text input
 *   - string      -> text input
 *   - boolean     -> checkbox
 *
 * Required parameters are marked with a red asterisk.
 * Range constraints are shown as helper text.
 */
import type { ParameterDefinition } from '@/types/parameters.ts'

interface ParameterInputProps {
  parameter: ParameterDefinition
  value: unknown
  onChange: (name: string, value: unknown) => void
  error?: string
}

export function ParameterInput({ parameter, value, onChange, error }: ParameterInputProps) {
  const inputId = `param-${parameter.name}`

  return (
    <div className="mb-4">
      <label
        htmlFor={inputId}
        className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300"
      >
        {parameter.name}
        {parameter.required && (
          <span className="ml-1 text-red-500" title="Required parameter">
            *
          </span>
        )}
      </label>

      {renderInput(parameter, value, onChange, inputId)}

      {parameter.description && (
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
          {parameter.description}
        </p>
      )}

      {parameter.range && (
        <p className="mt-0.5 text-xs text-gray-400 dark:text-gray-500">
          Range: [{parameter.range[0]}, {parameter.range[1]}]
          {parameter.units ? ` (${parameter.units})` : ''}
        </p>
      )}

      {error && (
        <p className="mt-1 text-xs text-red-600 dark:text-red-400">{error}</p>
      )}
    </div>
  )
}

function renderInput(
  parameter: ParameterDefinition,
  value: unknown,
  onChange: (name: string, value: unknown) => void,
  inputId: string,
) {
  const baseInputClasses =
    'block w-full rounded-md border border-gray-300 px-3 py-2 text-sm ' +
    'shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 ' +
    'dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 ' +
    'disabled:cursor-not-allowed disabled:bg-gray-100 dark:disabled:bg-gray-900'

  switch (parameter.type) {
    case 'boolean':
      return (
        <div className="flex items-center gap-2">
          <input
            id={inputId}
            type="checkbox"
            checked={value === true}
            onChange={(e) => onChange(parameter.name, e.target.checked)}
            className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500 dark:border-gray-600"
          />
          <span className="text-sm text-gray-600 dark:text-gray-400">
            {value === true ? 'Enabled' : 'Disabled'}
          </span>
        </div>
      )

    case 'numeric':
      return (
        <input
          id={inputId}
          type="number"
          value={value !== null && value !== undefined ? String(value) : ''}
          onChange={(e) => {
            const rawValue = e.target.value
            if (rawValue === '') {
              onChange(parameter.name, null)
            } else {
              onChange(parameter.name, Number(rawValue))
            }
          }}
          min={parameter.range?.[0]}
          max={parameter.range?.[1]}
          step="any"
          className={baseInputClasses}
          placeholder={
            parameter.default !== null && parameter.default !== undefined
              ? `Default: ${String(parameter.default)}`
              : undefined
          }
        />
      )

    case 'numeric_array':
      return (
        <input
          id={inputId}
          type="text"
          value={Array.isArray(value) ? (value as number[]).join(', ') : ''}
          onChange={(e) => {
            const rawValue = e.target.value
            if (rawValue.trim() === '') {
              onChange(parameter.name, [])
            } else {
              const parts = rawValue.split(',').map((s) => s.trim())
              const numbers = parts
                .filter((s) => s !== '')
                .map(Number)
                .filter((n) => !isNaN(n))
              onChange(parameter.name, numbers)
            }
          }}
          className={baseInputClasses}
          placeholder={
            parameter.default !== null && parameter.default !== undefined
              ? `Default: ${String(parameter.default)}`
              : 'Comma-separated numbers'
          }
        />
      )

    case 'string':
    default:
      return (
        <input
          id={inputId}
          type="text"
          value={typeof value === 'string' ? value : ''}
          onChange={(e) => onChange(parameter.name, e.target.value)}
          className={baseInputClasses}
          placeholder={
            parameter.default !== null &&
            parameter.default !== undefined &&
            typeof parameter.default === 'string'
              ? `Default: ${parameter.default}`
              : undefined
          }
        />
      )
  }
}
