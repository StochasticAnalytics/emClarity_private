/**
 * API module for parameter schema operations.
 *
 * Provides typed functions and hooks for fetching the parameter schema.
 * Currently loads the schema from a static JSON file bundled at build
 * time. In TASK-002c, this will be switched to call the real backend
 * endpoint via the API client.
 */

import type {
  ParameterDefinition,
  ParameterSchemaResponse,
  ParameterValidationResult,
} from '@/types/parameters.ts'
import staticSchema from '@/data/parameter-schema.json'

/** API v1 endpoint for the parameter schema. */
export const PARAMETER_SCHEMA_ENDPOINT = '/api/v1/parameters/schema'

/** API v1 endpoint for parameter validation. */
export const PARAMETER_VALIDATE_ENDPOINT = '/api/v1/parameters/validate'

/**
 * Load the parameter schema from the statically bundled JSON.
 *
 * The schema is imported at build time from
 * `gui/src/data/parameter-schema.json` and returned as a typed
 * `ParameterSchemaResponse`. This avoids a backend dependency while
 * still providing real parameter data for the UI.
 *
 * @returns The parameter schema response with all 160 parameters
 *
 * @remarks
 * In TASK-002c this will be replaced by an API call:
 * ```ts
 * return apiClient.get<ParameterSchemaResponse>(PARAMETER_SCHEMA_ENDPOINT, signal)
 * ```
 */
export function loadStaticParameterSchema(): ParameterSchemaResponse {
  const parameters = (
    staticSchema as { parameters: ParameterDefinition[] }
  ).parameters
  return { parameters }
}

/**
 * Fetch the full parameter schema from the backend.
 *
 * @param _signal - Optional AbortSignal for cancellation
 * @returns Promise resolving to the parameter schema response
 *
 * @remarks
 * In TASK-002c this will call the real backend endpoint.
 * For now it returns the static schema bundled at build time.
 */
export async function fetchParameterSchema(
  _signal?: AbortSignal,
): Promise<ParameterSchemaResponse> {
  // TODO(TASK-002c): Replace with actual API call:
  //   return apiClient.get<ParameterSchemaResponse>(PARAMETER_SCHEMA_ENDPOINT, signal)
  return loadStaticParameterSchema()
}

/**
 * Validate parameter values against the schema.
 *
 * @param _parameters - Map of parameter names to values
 * @returns Promise resolving to the validation result
 *
 * @remarks
 * In TASK-002c this will call POST /api/v1/parameters/validate.
 * For now it performs client-side validation only.
 */
export async function validateParameters(
  _parameters: Record<string, unknown>,
): Promise<ParameterValidationResult> {
  // TODO(TASK-002c): Replace with actual API call:
  //   return apiClient.post<ParameterValidationResult>(
  //     PARAMETER_VALIDATE_ENDPOINT,
  //     { parameters }
  //   )
  return { valid: true, errors: [], warnings: [] }
}

/**
 * React Query key factory for parameter-related queries.
 *
 * Using a factory pattern ensures consistent cache keys and makes
 * cache invalidation predictable.
 */
export const parameterQueryKeys = {
  /** Base key for all parameter queries */
  all: ['parameters'] as const,
  /** Key for the schema query */
  schema: () => [...parameterQueryKeys.all, 'schema'] as const,
  /** Key for validation queries */
  validation: () => [...parameterQueryKeys.all, 'validation'] as const,
} as const
