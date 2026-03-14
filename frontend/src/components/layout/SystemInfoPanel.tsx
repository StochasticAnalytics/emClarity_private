/**
 * SystemInfoPanel – slide-in panel showing hardware capabilities of the host.
 *
 * Opened from the settings gear icon in the Header.  Fetches
 * GET /api/v1/system/info and displays CPU, memory, and GPU details.
 */
import { X, Cpu, MemoryStick, MonitorCheck, Server } from 'lucide-react'
import { useApiQuery } from '@/hooks/useApi.ts'

// ---------------------------------------------------------------------------
// Types (mirroring backend SystemInfo / GpuInfo models)
// ---------------------------------------------------------------------------

interface GpuInfo {
  index: number
  name: string
  memory_total_mb: number
  memory_used_mb: number
  memory_free_mb: number
  driver_version: string
  cuda_version: string
}

interface SystemInfo {
  cpu_count: number
  cpu_count_physical: number
  memory_total_gb: number
  memory_available_gb: number
  hostname: string
  gpus: GpuInfo[]
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatGB(value: number): string {
  return `${value.toFixed(1)} GB`
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface SystemInfoPanelProps {
  onClose: () => void
}

export function SystemInfoPanel({ onClose }: SystemInfoPanelProps) {
  const {
    data,
    isLoading,
    error,
    refetch,
  } = useApiQuery<SystemInfo>(['system-info'], '/api/v1/system/info', {
    staleTime: 30_000,
  })

  return (
    /* Backdrop */
    <div
      className="fixed inset-0 z-50 flex justify-end"
      role="dialog"
      aria-modal="true"
      aria-label="System Information"
    >
      {/* Dimmed overlay */}
      <div
        className="absolute inset-0 bg-black/30"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Panel */}
      <div className="relative z-10 flex h-full w-80 flex-col overflow-y-auto border-l border-gray-200 bg-white shadow-xl dark:border-gray-700 dark:bg-gray-900">
        {/* Panel header */}
        <div className="flex items-center justify-between border-b border-gray-200 px-5 py-4 dark:border-gray-700">
          <div className="flex items-center gap-2">
            <Server className="h-4 w-4 text-gray-500 dark:text-gray-400" />
            <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              System Information
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close system info panel"
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:hover:bg-gray-800 dark:hover:text-gray-300"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Panel body */}
        <div className="flex-1 px-5 py-4">
          {isLoading && (
            <div className="flex items-center gap-3 py-8">
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
              <span className="text-sm text-gray-500 dark:text-gray-400">
                Detecting hardware…
              </span>
            </div>
          )}

          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-900/20">
              <p className="text-sm text-red-600 dark:text-red-400">
                Failed to load system info: {error.message}
              </p>
              <button
                type="button"
                onClick={() => void refetch()}
                className="mt-2 text-xs text-red-600 underline hover:text-red-800 dark:text-red-400"
              >
                Retry
              </button>
            </div>
          )}

          {data && (
            <div className="space-y-5">
              {/* Host */}
              {data.hostname && (
                <section>
                  <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">
                    Host
                  </p>
                  <p className="font-mono text-sm text-gray-900 dark:text-gray-100">
                    {data.hostname}
                  </p>
                </section>
              )}

              {/* CPU */}
              <section>
                <div className="mb-2 flex items-center gap-1.5">
                  <Cpu className="h-3.5 w-3.5 text-gray-400 dark:text-gray-500" />
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">
                    CPU
                  </p>
                </div>
                <dl className="space-y-1 text-sm">
                  <div className="flex justify-between">
                    <dt className="text-gray-500 dark:text-gray-400">Logical cores</dt>
                    <dd className="font-medium text-gray-900 dark:text-gray-100">
                      {data.cpu_count}
                    </dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-gray-500 dark:text-gray-400">Physical cores</dt>
                    <dd className="font-medium text-gray-900 dark:text-gray-100">
                      {data.cpu_count_physical}
                    </dd>
                  </div>
                </dl>
              </section>

              {/* Memory */}
              <section>
                <div className="mb-2 flex items-center gap-1.5">
                  <MemoryStick className="h-3.5 w-3.5 text-gray-400 dark:text-gray-500" />
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">
                    Memory
                  </p>
                </div>
                <dl className="space-y-1 text-sm">
                  <div className="flex justify-between">
                    <dt className="text-gray-500 dark:text-gray-400">Total RAM</dt>
                    <dd className="font-medium text-gray-900 dark:text-gray-100">
                      {formatGB(data.memory_total_gb)}
                    </dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-gray-500 dark:text-gray-400">Available</dt>
                    <dd className="font-medium text-gray-900 dark:text-gray-100">
                      {formatGB(data.memory_available_gb)}
                    </dd>
                  </div>
                </dl>
              </section>

              {/* GPUs */}
              <section>
                <div className="mb-2 flex items-center gap-1.5">
                  <MonitorCheck className="h-3.5 w-3.5 text-gray-400 dark:text-gray-500" />
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">
                    GPUs
                  </p>
                </div>

                {data.gpus.length === 0 ? (
                  <p className="text-sm text-amber-600 dark:text-amber-400">
                    No NVIDIA GPUs detected. emClarity requires a CUDA-capable GPU for
                    processing.
                  </p>
                ) : (
                  <div className="space-y-3">
                    {data.gpus.map((gpu) => (
                      <div
                        key={gpu.index}
                        className="rounded-md border border-gray-200 p-3 text-sm dark:border-gray-700"
                      >
                        <p className="font-medium text-gray-900 dark:text-gray-100">
                          GPU {gpu.index}: {gpu.name}
                        </p>
                        <dl className="mt-1.5 space-y-1">
                          <div className="flex justify-between">
                            <dt className="text-gray-500 dark:text-gray-400">VRAM total</dt>
                            <dd className="text-gray-900 dark:text-gray-100">
                              {(gpu.memory_total_mb / 1024).toFixed(1)} GB
                            </dd>
                          </div>
                          <div className="flex justify-between">
                            <dt className="text-gray-500 dark:text-gray-400">VRAM free</dt>
                            <dd className="text-gray-900 dark:text-gray-100">
                              {(gpu.memory_free_mb / 1024).toFixed(1)} GB
                            </dd>
                          </div>
                          {gpu.driver_version && (
                            <div className="flex justify-between">
                              <dt className="text-gray-500 dark:text-gray-400">Driver</dt>
                              <dd className="text-gray-900 dark:text-gray-100">
                                {gpu.driver_version}
                              </dd>
                            </div>
                          )}
                          {gpu.cuda_version && (
                            <div className="flex justify-between">
                              <dt className="text-gray-500 dark:text-gray-400">CUDA</dt>
                              <dd className="text-gray-900 dark:text-gray-100">
                                {gpu.cuda_version}
                              </dd>
                            </div>
                          )}
                        </dl>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
