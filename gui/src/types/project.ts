/**
 * Type definitions for emClarity project state.
 */

/** Summary of a project on disk. */
export interface ProjectInfo {
  name: string
  path: string
  created_at: string
  modified_at: string
  current_cycle: number
  tilt_series_count: number
  particle_count: number
}

/** Status of project directories. */
export interface ProjectDirectories {
  raw_data: string
  fixed_stacks: string
  ali_stacks: string
  cache: string
  convmap: string
  fsc: string
  log_file: string
}

/** Project creation request. */
export interface CreateProjectRequest {
  name: string
  path: string
  parameter_file?: string
}
