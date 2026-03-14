/**
 * Shared API response types for the emClarity backend.
 */

/** Standard paginated response envelope. */
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

/** Standard API error response body. */
export interface ApiErrorResponse {
  detail: string
  code?: string
}

/** Job status as reported by the backend. */
export type JobStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

/** Summary of a backend processing job. */
export interface JobSummary {
  id: string
  command: string
  status: JobStatus
  created_at: string
  started_at: string | null
  finished_at: string | null
  progress: number
  error_message: string | null
}

/** Health-check response. */
export interface HealthResponse {
  status: 'ok' | 'degraded'
  version: string
}
