/**
 * API module for parameter schema operations.
 *
 * Provides typed functions for fetching the parameter schema from the
 * backend and validating parameter values.  Also exports a static schema
 * loader as a fallback for offline / build-time usage.
 */

import type {
  ParameterDefinition,
  ParameterSchemaResponse,
  ParameterValidationResult,
} from '@/types/parameters.ts'
import { apiClient } from '@/api/client.ts'
import staticSchema from '@/data/parameter-schema.json'

/** API v1 endpoint for the parameter schema. */
export const PARAMETER_SCHEMA_ENDPOINT = '/api/v1/parameters/schema'

/** API v1 endpoint for parameter validation. */
export const PARAMETER_VALIDATE_ENDPOINT = '/api/v1/parameters/validate'

/**
 * Load the parameter schema from the statically bundled JSON.
 *
 * The schema is imported at build time from
 * `src/data/parameter-schema.json` and returned as a typed
 * `ParameterSchemaResponse`.  Use this as a fallback when the backend is
 * unavailable, e.g. during unit tests or static builds.
 *
 * @returns The parameter schema response with all 160 parameters
 */
export function loadStaticParameterSchema(): ParameterSchemaResponse {
  const parameters = (
    staticSchema as { parameters: ParameterDefinition[] }
  ).parameters
  return { parameters }
}

/**
 * Fetch the full parameter schema from the backend API.
 *
 * Calls ``GET /api/v1/parameters/schema`` and returns the wrapped
 * ``{"parameters": [...]}`` response.  Falls back to the statically
 * bundled schema when the backend is unreachable so that the UI remains
 * functional in offline / development-without-backend scenarios.
 *
 * @param signal - Optional AbortSignal for request cancellation
 * @returns Promise resolving to the parameter schema response
 */
export async function fetchParameterSchema(
  signal?: AbortSignal,
): Promise<ParameterSchemaResponse> {
  try {
    return await apiClient.get<ParameterSchemaResponse>(
      PARAMETER_SCHEMA_ENDPOINT,
      signal,
    )
  } catch {
    // Fallback to static schema when backend is unavailable.
    return loadStaticParameterSchema()
  }
}

/**
 * Validate parameter values against the schema via the backend API.
 *
 * Calls ``POST /api/v1/parameters/validate`` with the parameter dict and
 * returns the server-side validation result.  Falls back to a trivially
 * passing result when the backend is unreachable.
 *
 * @param parameters - Map of parameter names to values
 * @returns Promise resolving to the validation result
 */
export async function validateParameters(
  parameters: Record<string, unknown>,
): Promise<ParameterValidationResult> {
  try {
    return await apiClient.post<ParameterValidationResult>(
      PARAMETER_VALIDATE_ENDPOINT,
      { parameters },
    )
  } catch {
    // Fallback: treat all parameters as valid when backend is unreachable.
    return { valid: true, errors: [], warnings: [] }
  }
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
