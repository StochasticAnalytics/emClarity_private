/**
 * Type definitions for emClarity processing parameters.
 *
 * These mirror the parameter schema from BH_parseParameterFile.m
 * and will be populated as the backend API is developed.
 */

/** A single parameter definition from the schema. */
export interface ParameterDefinition {
  key: string
  label: string
  type: 'number' | 'string' | 'boolean' | 'vector'
  default_value: unknown
  description: string
  units?: string
  min?: number
  max?: number
  group: string
}

/** The full set of runtime parameters for a processing cycle. */
export interface ParameterSet {
  [key: string]: unknown
}

/** Grouped parameters for display in the editor. */
export interface ParameterGroup {
  name: string
  label: string
  parameters: ParameterDefinition[]
}
