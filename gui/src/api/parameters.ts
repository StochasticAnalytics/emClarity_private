/**
 * API module for parameter schema operations.
 *
 * Provides typed functions and hooks for fetching the parameter schema
 * from the backend. Currently returns a stub response; backend
 * integration will be wired in TASK-002c.
 */

import type {
  ParameterSchemaResponse,
  ParameterValidationResult,
} from '@/types/parameters.ts'

/** API v1 endpoint for the parameter schema. */
export const PARAMETER_SCHEMA_ENDPOINT = '/api/v1/parameters/schema'

/** API v1 endpoint for parameter validation. */
export const PARAMETER_VALIDATE_ENDPOINT = '/api/v1/parameters/validate'

/**
 * Fetch the full parameter schema from the backend.
 *
 * @param signal - Optional AbortSignal for cancellation
 * @returns Promise resolving to the parameter schema response
 *
 * @remarks
 * In TASK-002c this will call the real backend endpoint.
 * For now it returns undefined to indicate no data loaded.
 */
export async function fetchParameterSchema(
  _signal?: AbortSignal,
): Promise<ParameterSchemaResponse | undefined> {
  // TODO(TASK-002c): Replace with actual API call:
  //   return apiClient.get<ParameterSchemaResponse>(PARAMETER_SCHEMA_ENDPOINT, signal)
  return undefined
}

/**
 * Validate parameter values against the schema.
 *
 * @param parameters - Map of parameter names to values
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
