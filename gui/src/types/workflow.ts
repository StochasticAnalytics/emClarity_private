/**
 * Type definitions for the emClarity processing pipeline.
 */

/** Processing step identifiers matching emClarity commands. */
export type WorkflowStep =
  | 'autoAlign'
  | 'ctf_estimate'
  | 'templateSearch'
  | 'init'
  | 'ctf_3d'
  | 'avg'
  | 'alignRaw'
  | 'tomoCPR'
  | 'classify'

/** Execution status of a pipeline step. */
export type StepStatus = 'pending' | 'ready' | 'running' | 'completed' | 'failed' | 'skipped'

/** A single step in the processing pipeline. */
export interface PipelineStep {
  id: WorkflowStep
  label: string
  status: StepStatus
  cycle: number
  depends_on: WorkflowStep[]
}

/** Overall pipeline state. */
export interface PipelineState {
  steps: PipelineStep[]
  current_cycle: number
  is_running: boolean
}
