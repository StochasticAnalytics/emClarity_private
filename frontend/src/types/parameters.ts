/**
 * Type definitions for emClarity processing parameters.
 *
 * These mirror the parameter schema served by the backend at
 * GET /api/v1/parameters/schema, which is derived from
 * metaData/BH_parseParameterFile.m.
 */

/** Parameter value types as defined in the golden schema. */
export type ParameterType = 'numeric' | 'numeric_array' | 'string' | 'boolean'

/** Logical category groupings used to organize parameters in the UI. */
export type ParameterCategory =
  | 'alignment'
  | 'classification'
  | 'ctf'
  | 'disk_management'
  | 'dose'
  | 'fsc'
  | 'hardware'
  | 'masking'
  | 'metadata'
  | 'microscope'
  | 'template_matching'
  | 'tomoCPR'

/** A single parameter definition from the schema. */
export interface ParameterDefinition {
  name: string
  type: ParameterType
  required: boolean
  default: unknown
  range: [number, number] | null
  n_elements: number | null
  allowed_values: unknown[] | null
  deprecated_name: string | null
  description: string
  category: ParameterCategory
  units?: string | null
}

/** Response shape from GET /api/v1/parameters/schema. */
export interface ParameterSchemaResponse {
  parameters: ParameterDefinition[]
}

/** Grouped parameters for display in the editor tabs. */
export interface ParameterGroup {
  category: ParameterCategory
  label: string
  parameters: ParameterDefinition[]
}

/** Concrete name-value pair for a parameter. */
export interface ParameterValue {
  name: string
  value: unknown
}

/** Result of validating parameter values against the schema. */
export interface ParameterValidationResult {
  valid: boolean
  errors: string[]
  warnings: string[]
}

/**
 * Human-readable labels for each parameter category.
 * Used in the tabbed UI to display friendly names.
 */
export const CATEGORY_LABELS: Record<ParameterCategory, string> = {
  microscope: 'Microscope',
  hardware: 'Hardware',
  ctf: 'CTF',
  alignment: 'Alignment',
  classification: 'Classification',
  masking: 'Masking',
  metadata: 'Metadata',
  disk_management: 'Disk Management',
  dose: 'Dose',
  fsc: 'FSC',
  template_matching: 'Template Matching',
  tomoCPR: 'TomoCPR',
}

/**
 * Display order for parameter categories in the tabbed UI.
 * Core categories appear first, specialized ones later.
 */
export const CATEGORY_ORDER: ParameterCategory[] = [
  'microscope',
  'hardware',
  'ctf',
  'alignment',
  'classification',
  'masking',
  'metadata',
  'disk_management',
  'dose',
  'fsc',
  'template_matching',
  'tomoCPR',
]
