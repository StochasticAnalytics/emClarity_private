/**
 * API module for parameter schema operations.
 *
 * Provides typed functions and hooks for fetching the parameter schema
 * from the live backend endpoint GET /api/v1/parameters/schema, with
 * automatic fallback to the statically bundled JSON when the backend
 * is unreachable.
 */

import { apiClient } from '@/api/client.ts'
import type {
  ParameterDefinition,
  ParameterSchemaResponse,
  ParameterValidationResult,
} from '@/types/parameters.ts'
import staticSchemaJson from '@/data/parameter-schema.json'

/** API v1 endpoint for the parameter schema. */
export const PARAMETER_SCHEMA_ENDPOINT = '/api/v1/parameters/schema'

/**
 * API endpoint for parameter validation.
 *
 * Uses the legacy /api/parameters prefix because the validate endpoint
 * is only registered on the base router (not the v1 router).
 */
export const PARAMETER_VALIDATE_ENDPOINT = '/api/parameters/validate'

/**
 * Load the parameter schema from the statically bundled JSON.
 *
 * The schema is imported at build time from
 * `frontend/src/data/parameter-schema.json` and returned as a typed
 * `ParameterSchemaResponse`. Used as a fallback when the backend is
 * unreachable, and as `initialData` for the react-query cache.
 *
 * @returns The parameter schema response with all 160 parameters
 */
export function loadStaticParameterSchema(): ParameterSchemaResponse {
  const parameters = (
    staticSchemaJson as { parameters: ParameterDefinition[] }
  ).parameters
  return { parameters }
}

/**
 * Fetch the full parameter schema from the backend.
 *
 * Calls GET /api/v1/parameters/schema and returns the response as a
 * typed `ParameterSchemaResponse`. Supports request cancellation via
 * an optional AbortSignal.
 *
 * @param signal - Optional AbortSignal for cancellation
 * @returns Promise resolving to the parameter schema response
 */
export async function fetchParameterSchema(
  signal?: AbortSignal,
): Promise<ParameterSchemaResponse> {
  return apiClient.get<ParameterSchemaResponse>(PARAMETER_SCHEMA_ENDPOINT, signal)
}

/**
 * Validate parameter values against the schema.
 *
 * Calls POST /api/parameters/validate. The backend expects a list of
 * `{name, value}` objects, so the input dict is converted to that format.
 *
 * @param parameters - Map of parameter names to values
 * @returns Promise resolving to the validation result
 */
export async function validateParameters(
  parameters: Record<string, unknown>,
): Promise<ParameterValidationResult> {
  // Convert dict to list of {name, value} objects as expected by the backend
  const parameterList = Object.entries(parameters).map(([name, value]) => ({
    name,
    value,
  }))
  return apiClient.post<ParameterValidationResult>(
    PARAMETER_VALIDATE_ENDPOINT,
    parameterList,
  )
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
