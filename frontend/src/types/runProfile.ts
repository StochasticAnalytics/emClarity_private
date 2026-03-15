/**
 * Run Profile types for TASK-023.
 *
 * A RunProfile stores the hardware configuration and command template
 * used to launch emClarity processing steps. Profiles are stored in
 * browser localStorage and exposed via the useRunProfiles hook.
 */

export interface RunProfile {
  /** Unique identifier (UUID). */
  id: string
  /** Human-readable profile name. */
  name: string
  /** Number of GPUs to use. Maps to emClarity parameter nGPUs. */
  nGPUs: number
  /** Number of CPU cores. Maps to emClarity parameter nCpuCores. */
  nCpuCores: number
  /** Path to fast scratch disk. Maps to emClarity parameter fastScratchDisk. */
  fastScratchDisk: string
  /**
   * Command template for advanced users. Supports $command placeholder which
   * gets replaced with the actual emClarity command at launch time.
   * Example: "singularity exec emclarity.sif $command"
   */
  commandTemplate: string
}

/** System-wide hardware defaults displayed prominently at the top of Settings. */
export interface SystemParams {
  nGPUs: number
  nCpuCores: number
  fastScratchDisk: string
}

export const DEFAULT_SYSTEM_PARAMS: SystemParams = {
  nGPUs: 1,
  nCpuCores: 4,
  fastScratchDisk: '/tmp',
}

export const DEFAULT_RUN_PROFILES: RunProfile[] = [
  {
    id: 'local-1gpu',
    name: 'Local (1 GPU)',
    nGPUs: 1,
    nCpuCores: 4,
    fastScratchDisk: '/tmp',
    commandTemplate: '$command',
  },
  {
    id: 'local-multi',
    name: 'Local (multi-GPU)',
    nGPUs: 4,
    nCpuCores: 16,
    fastScratchDisk: '/tmp',
    commandTemplate: '$command',
  },
  {
    id: 'singularity',
    name: 'Singularity container',
    nGPUs: 1,
    nCpuCores: 4,
    fastScratchDisk: '/tmp',
    commandTemplate: 'singularity exec --nv emclarity.sif $command',
  },
]
