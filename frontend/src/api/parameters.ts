/**
 * API module for parameter schema operations.
 *
 * Provides typed functions for fetching the parameter schema from the
 * backend and validating parameter values.  Also exports a static schema
 * loader as a fallback for offline / build-time usage.
 */

import type {
  ParameterDefinition,
  ParameterFile,
  ParameterSchemaResponse,
  ParameterValidationResult,
} from '@/types/parameters.ts'
import { apiClient } from '@/api/client.ts'
import staticSchema from '@/data/parameter-schema.json'

/** API v1 endpoint for the parameter schema. */
export const PARAMETER_SCHEMA_ENDPOINT = '/api/v1/parameters/schema'

/** API v1 endpoint for parameter validation. */
export const PARAMETER_VALIDATE_ENDPOINT = '/api/v1/parameters/validate'

/** API v1 base endpoint for parameter file I/O. */
export const PARAMETER_FILE_ENDPOINT = '/api/v1/parameters/file'

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
 * Load a parameter file from the server by filesystem path.
 *
 * Calls ``GET /api/v1/parameters/file/{path}`` which parses the MATLAB
 * ``.m`` format and migrates any deprecated parameter names before
 * returning the result.
 *
 * @param path - Absolute or relative server-side path to the ``.m`` file
 * @returns Promise resolving to the parsed parameter file
 */
export async function importParameterFile(path: string): Promise<ParameterFile> {
  return apiClient.get<ParameterFile>(`${PARAMETER_FILE_ENDPOINT}/${path}`)
}

/**
 * Save the current parameter values to a ``.m`` file on the server.
 *
 * Calls ``POST /api/v1/parameters/file`` with the serialized parameters and
 * target path.  Creates parent directories if they do not exist.
 *
 * @param path - Absolute or relative server-side destination path
 * @param values - Map of parameter names to their current values
 * @returns Promise resolving to the saved parameter file
 */
export async function exportParameterFile(
  path: string,
  values: Record<string, unknown>,
): Promise<ParameterFile> {
  const parameters = Object.entries(values).map(([name, value]) => ({ name, value }))
  return apiClient.post<ParameterFile>(PARAMETER_FILE_ENDPOINT, { path, parameters })
}

/**
 * Parse the text content of a MATLAB-style ``.m`` parameter file
 * entirely on the client side (no network call required).
 *
 * Handles the same ``key = value;`` format as the backend parser and
 * transparently migrates deprecated parameter names using the supplied
 * schema (which already carries ``deprecated_name`` fields).
 *
 * @param content  - Raw text content of the ``.m`` file
 * @param schema   - Parameter schema for deprecated-name translation
 * @returns A flat map of canonical parameter names to parsed values
 */
export function parseMatlabContent(
  content: string,
  schema: ParameterDefinition[],
): Record<string, unknown> {
  // Build deprecated-name → canonical-name lookup from the schema.
  const deprecatedLookup = new Map<string, string>()
  for (const param of schema) {
    if (param.deprecated_name) {
      deprecatedLookup.set(param.deprecated_name, param.name)
    }
  }

  const values: Record<string, unknown> = {}

  for (const rawLine of content.split('\n')) {
    const line = rawLine.trim()
    // Skip empty lines and MATLAB comment lines.
    if (!line || line.startsWith('%')) continue

    // Match:  paramName = value  (optional trailing semicolon / comment)
    const match = /^(\w+)\s*=\s*(.+?)(?:;\s*(?:%.*)?)?$/.exec(line)
    if (!match) continue

    const rawName = match[1] ?? ''
    const rawValue = (match[2] ?? '').trim().replace(/;$/, '').trim()
    const parsed = parseMatlabValue(rawValue)

    // Translate deprecated names to canonical form.
    const canonical = deprecatedLookup.get(rawName) ?? rawName
    if (canonical) {
      values[canonical] = parsed
    }
  }

  return values
}

/**
 * Parse a single MATLAB value string into the appropriate JS type.
 *
 * Handles vectors (``[1, 2, 3]``), quoted strings, and numeric scalars.
 */
function parseMatlabValue(raw: string): unknown {
  // Numeric vector: [1, 2, 3] or [1 2 3]
  if (raw.startsWith('[') && raw.endsWith(']')) {
    const inner = raw.slice(1, -1)
    const parts = inner.split(/[,\s]+/).filter((p) => p.length > 0)
    const nums = parts.map(Number)
    if (parts.length > 0 && nums.every((n) => !isNaN(n))) return nums
    return raw
  }

  // Quoted string: 'hello' or "hello"
  const strMatch = /^['"](.*)['"]$/.exec(raw)
  if (strMatch) return strMatch[1]

  // Numeric scalar
  const trimmed = raw.trim()
  if (trimmed !== '') {
    const num = Number(trimmed)
    if (!isNaN(num)) return num
  }

  return trimmed
}

/**
 * Serialise a flat map of parameter values to MATLAB ``.m`` file content.
 *
 * The output is compatible with the emClarity MATLAB parameter file
 * parser (``BH_parseParameterFile.m``).
 *
 * @param values - Map of parameter names to their current values
 * @returns The ``.m`` file content as a string
 */
export function generateMatlabContent(values: Record<string, unknown>): string {
  const lines: string[] = [
    '% emClarity parameter file',
    `% Generated by emClarity frontend on ${new Date().toISOString()}`,
    '',
  ]

  for (const [name, value] of Object.entries(values)) {
    lines.push(`${name} = ${formatMatlabValue(value)};`)
  }

  return lines.join('\n') + '\n'
}

/**
 * Format a single JS value for writing into a MATLAB parameter file.
 */
function formatMatlabValue(value: unknown): string {
  if (typeof value === 'boolean') return value ? '1' : '0'
  if (Array.isArray(value)) return `[${(value as unknown[]).join(', ')}]`
  if (typeof value === 'string') return `'${value}'`
  if (value === null || value === undefined) return "''"
  return String(value)
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
