/**
 * Renders all parameters belonging to a single category.
 *
 * Displays parameters in a responsive grid with two columns on
 * larger screens. Required parameters are listed first.
 */
import { ParameterInput } from './ParameterInput.tsx'
import type { ParameterDefinition, ParameterGroup } from '@/types/parameters.ts'

interface ParameterCategoryTabProps {
  group: ParameterGroup
  values: Record<string, unknown>
  errors: Record<string, string>
  onChange: (name: string, value: unknown) => void
}

export function ParameterCategoryTab({
  group,
  values,
  errors,
  onChange,
}: ParameterCategoryTabProps) {
  // Sort: required parameters first, then alphabetical by name
  const sortedParams = [...group.parameters].sort((a, b) => {
    if (a.required !== b.required) return a.required ? -1 : 1
    return a.name.localeCompare(b.name)
  })

  const requiredParams = sortedParams.filter((p) => p.required)
  const optionalParams = sortedParams.filter((p) => !p.required)

  return (
    <div className="space-y-6">
      {requiredParams.length > 0 && (
        <div>
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
            Required Parameters
          </h3>
          <div className="grid grid-cols-1 gap-x-6 gap-y-2 md:grid-cols-2">
            {requiredParams.map((param: ParameterDefinition) => (
              <ParameterInput
                key={param.name}
                parameter={param}
                value={values[param.name]}
                error={errors[param.name]}
                onChange={onChange}
              />
            ))}
          </div>
        </div>
      )}

      {optionalParams.length > 0 && (
        <div>
          {requiredParams.length > 0 && (
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
              Optional Parameters
            </h3>
          )}
          <div className="grid grid-cols-1 gap-x-6 gap-y-2 md:grid-cols-2">
            {optionalParams.map((param: ParameterDefinition) => (
              <ParameterInput
                key={param.name}
                parameter={param}
                value={values[param.name]}
                error={errors[param.name]}
                onChange={onChange}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
